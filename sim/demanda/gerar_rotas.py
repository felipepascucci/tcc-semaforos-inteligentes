"""Materialização das rotas por (cenário, seed) — entrega 3.3.

    python -m sim.demanda.gerar_rotas --cenario intenso --seed 7

**Este módulo existe por causa de uma regra do protocolo experimental, não por
conveniência.** O `context/04` §7 chama o pareamento por seed de "regra crítica":
a execução com `seed=17` no modo `FIXO` e no modo `PREEMPCAO` precisa ter
*exatamente* o mesmo tráfego de fundo, senão a comparação deixa de ser pareada e
perde o poder estatístico que justifica 50 seeds em vez de 500.

Poderíamos ter deixado o SUMO sortear os instantes de partida a partir do
`--seed`. Não deixamos: isso amarraria a garantia mais importante do experimento
a um detalhe interno do simulador (qual gerador alimenta qual sorteio, e se a
ordem de consumo muda quando o TraCI intervém). Aqui os instantes saem de um
`random.Random(seed)` nosso, o arquivo é escrito uma vez e os três modos leem o
mesmo arquivo. A garantia passa a ser verificável com `diff` — e há teste
conferindo que a mesma seed produz o mesmo arquivo, byte a byte.

As chegadas seguem processo de Poisson (intervalos exponenciais), que é o modelo
usual de chegada de veículos em via urbana sem coordenação a montante. A
alternativa — intervalos constantes — produziria um tráfego artificialmente
regular, que forma menos fila do que o real para o mesmo fluxo médio, e portanto
subestimaria o efeito que o trabalho quer medir.
"""

from __future__ import annotations

import argparse
import random
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adapters.sumo.adaptador import PARAMETRO_CRITICIDADE
from core.modelos import Criticidade
from sim.calibracao import cenarios as calibracao
from sim.demanda.fluxos import rotas_de_emergencia

RAIZ = Path(__file__).resolve().parents[2]
DIRETORIO_DEMANDA = RAIZ / "sim" / "demanda"
EMERGENCIAS = DIRETORIO_DEMANDA / "emergencias.rou.xml"
SAIDA = RAIZ / "sim" / "saida" / "rotas"

#: Cenário -> arquivo de fluxo. `multiplas_emergencias` compartilha a demanda de
#: fundo de `moderado` (context/04 §5): o que muda é a emergência, não o tráfego.
#: O cenário de treino da 10.2 também, pela mesma razão.
ARQUIVO_DE_FLUXO = {
    "leve": "fluxo_leve.rou.xml",
    "moderado": "fluxo_moderado.rou.xml",
    "intenso": "fluxo_intenso.rou.xml",
    "multiplas_emergencias": "fluxo_moderado.rou.xml",
    "treino_multiplas": "fluxo_moderado.rou.xml",
}


@dataclass(frozen=True)
class Partida:
    """Um veículo concreto, com instante de partida definido.

    Attributes:
        id_veiculo: Id no SUMO.
        tipo: `vType` — `carro`, `onibus`, `ambulancia`...
        rota: Id da rota.
        instante_s: Instante de partida, em segundos.
        emergencia: Se é veículo de emergência.
        criticidade: Criticidade da ocorrência que o VE atende (P20). Vai para o
            arquivo como `<param key="criticidade">`, que é o que o adaptador lê
            para saber que o VE está em serviço. `None` no tráfego de fundo.
    """

    id_veiculo: str
    tipo: str
    rota: str
    instante_s: float
    emergencia: bool = False
    criticidade: Criticidade | None = None


def _rotas_e_fluxos(arquivo: Path) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Lê rotas e fluxos de um `fluxo_*.rou.xml`."""
    raiz = ET.parse(arquivo).getroot()
    rotas = {
        str(elemento.get("id")): str(elemento.get("edges")) for elemento in raiz.findall("route")
    }
    fluxos = [
        {chave: str(valor) for chave, valor in elemento.attrib.items()}
        for elemento in raiz.findall("flow")
    ]
    return rotas, fluxos


def _rotas_de_emergencia_declaradas() -> dict[str, str]:
    raiz = ET.parse(EMERGENCIAS).getroot()
    return {
        str(elemento.get("id")): str(elemento.get("edges")) for elemento in raiz.findall("route")
    }


def partidas_de_fundo(
    fluxos: Sequence[Mapping[str, str]], gerador: random.Random
) -> Iterator[Partida]:
    """Gera as partidas do tráfego de fundo, corrente por corrente.

    Args:
        fluxos: Elementos `<flow>` lidos do arquivo de fluxo.
        gerador: Fonte de aleatoriedade, já semeada.

    Yields:
        Uma `Partida` por veículo.
    """
    for fluxo in fluxos:
        veic_h = float(fluxo["vehsPerHour"])
        if veic_h <= 0:
            continue
        taxa = veic_h / 3600.0
        inicio, fim = float(fluxo["begin"]), float(fluxo["end"])

        instante = inicio + gerador.expovariate(taxa)
        indice = 0
        while instante < fim:
            yield Partida(
                id_veiculo=f"{fluxo['id']}_{indice:04d}",
                tipo=fluxo["type"],
                rota=fluxo["route"],
                instante_s=instante,
            )
            indice += 1
            instante += gerador.expovariate(taxa)


def partidas_de_emergencia(
    configuracao: Mapping[str, Any], nome_cenario: str, seed: int | None = None
) -> Iterator[Partida]:
    """Gera as partidas dos VEs — determinísticas, sem sorteio.

    Os instantes **não** dependem da seed, e isso é deliberado: o VE é o objeto
    de medida do experimento, e variar sua partida junto com o tráfego
    misturaria duas fontes de variação. A seed varia o tráfego de fundo; o VE
    entra sempre nos mesmos instantes, encontrando um trânsito diferente a cada
    seed. O tipo também é fixo por rodízio, porque o tipo define a prioridade em
    E8 e precisa ser o mesmo nos três braços.

    A **criticidade** da ocorrência roda em passo com o tipo (P20): a i-ésima
    entrada de `criticidades` acompanha a i-ésima de `tipos`. Nos cenários do
    experimento isso atribui a cada VE a ocorrência típica do seu tipo.

    Os cenários de `cenarios_treino` seguem outra regra, a de
    `partidas_de_treino`, e só eles usam a seed.

    Raises:
        ValueError: se `criticidades` e `tipos` tiverem tamanhos diferentes — o
            rodízio sairia de fase em silêncio —, se houver nível fora da escala,
            ou se um cenário de treino vier sem seed.
    """
    treino = configuracao.get("cenarios_treino", {})
    if nome_cenario in treino:
        if seed is None:
            raise ValueError(f"o cenário de treino {nome_cenario!r} sorteia o atraso: exige seed")
        yield from partidas_de_treino(configuracao, treino[nome_cenario], seed)
        return

    emergencias = configuracao["emergencias"]
    execucao = configuracao["execucao"]
    intervalo = float(emergencias["intervalo_s"])
    tipos = [str(tipo).lower() for tipo in emergencias["tipos"]]
    criticidades = [Criticidade(int(nivel)) for nivel in emergencias["criticidades"]]
    if len(criticidades) != len(tipos):
        raise ValueError(
            f"emergencias.criticidades tem {len(criticidades)} entradas e "
            f"emergencias.tipos tem {len(tipos)}: o rodízio é em passo, e precisa "
            "de uma criticidade por tipo (P20)"
        )
    aquecimento = float(execucao["aquecimento_s"])
    duracao = float(execucao["duracao_s"])

    for rota, atraso in rotas_de_emergencia(configuracao, nome_cenario):
        instante = aquecimento + atraso
        indice = 0
        while instante < duracao:
            tipo = tipos[indice % len(tipos)]
            yield Partida(
                id_veiculo=f"VE_{rota}_{indice:02d}",
                tipo=tipo,
                rota=rota,
                instante_s=instante,
                emergencia=True,
                criticidade=criticidades[indice % len(criticidades)],
            )
            indice += 1
            instante += intervalo


def partidas_de_treino(
    configuracao: Mapping[str, Any], definicao: Mapping[str, Any], seed: int
) -> Iterator[Partida]:
    """Partidas dos VEs de um cenário de treino da entrega 10.2 (P19).

    Um par a cada `intervalo_s`: o VE do corredor parte no início do intervalo, e
    o da rota secundária, depois de um atraso sorteado em
    `atraso_secundario_faixa_s`. O sorteio usa um gerador próprio, derivado da
    seed, e não toca o do tráfego de fundo: a mesma seed dá o mesmo fundo em
    qualquer cenário que o compartilhe.

    **Exceção declarada à regra de `partidas_de_emergencia`.** Aqui a partida do
    VE depende da seed, porque o modelo precisa ver diferenças de ETA variadas, e
    um atraso fixo as deixaria quase constantes. Não há comparação entre braços a
    parear entre seeds; os braços de uma mesma seed continuam lendo o mesmo
    arquivo.

    Tipo e criticidade giram em rodízios separados. O tipo do VE do par `i` é
    `tipos[i]` no corredor e `tipos[i + defasagem_tipo_secundaria]` na rota
    secundária; a criticidade é `criticidades[i]` nos dois, exceto quando
    `(i + 1)` é múltiplo de `par_misto_a_cada`, em que o segundo VE vai para o
    nível seguinte (1→2, 2→3, 3→1).

    Raises:
        ValueError: faixa de atraso negativa ou invertida, intervalo ou
            `par_misto_a_cada` não positivos, ou nível fora da escala.
    """
    emergencias = configuracao["emergencias"]
    execucao = configuracao["execucao"]
    tipos = [str(tipo).lower() for tipo in emergencias["tipos"]]
    criticidades = [Criticidade(int(nivel)) for nivel in definicao["criticidades"]]
    intervalo = float(definicao["intervalo_s"])
    atraso_min, atraso_max = (float(valor) for valor in definicao["atraso_secundario_faixa_s"])
    misto_a_cada = int(definicao["par_misto_a_cada"])
    defasagem = int(definicao["defasagem_tipo_secundaria"])
    if not 0.0 <= atraso_min <= atraso_max:
        raise ValueError(f"faixa de atraso inválida: [{atraso_min}, {atraso_max}]")
    if intervalo <= 0 or misto_a_cada <= 0:
        raise ValueError("intervalo_s e par_misto_a_cada precisam ser positivos")

    rota_corredor = str(emergencias["rota"])
    rota_secundaria = str(definicao["rota_secundaria"])
    aquecimento = float(execucao["aquecimento_s"])
    duracao = float(execucao["duracao_s"])
    # Semente em texto: o `random` a converte por SHA-512, então o resultado não
    # depende de PYTHONHASHSEED nem colide com o gerador do fundo, `Random(seed)`.
    gerador = random.Random(f"emergencias:{seed}")

    indice = 0
    instante = aquecimento
    while instante < duracao:
        nivel = criticidades[indice % len(criticidades)]
        nivel_secundario = (
            Criticidade(int(nivel) % len(Criticidade) + 1)
            if (indice + 1) % misto_a_cada == 0
            else nivel
        )
        # Sorteado sempre, mesmo se o VE cair depois do fim: assim o atraso do
        # par i não depende da duração da execução.
        atraso = gerador.uniform(atraso_min, atraso_max)
        yield Partida(
            id_veiculo=f"VE_{rota_corredor}_{indice:02d}",
            tipo=tipos[indice % len(tipos)],
            rota=rota_corredor,
            instante_s=instante,
            emergencia=True,
            criticidade=nivel,
        )
        if instante + atraso < duracao:
            yield Partida(
                id_veiculo=f"VE_{rota_secundaria}_{indice:02d}",
                tipo=tipos[(indice + defasagem) % len(tipos)],
                rota=rota_secundaria,
                instante_s=instante + atraso,
                emergencia=True,
                criticidade=nivel_secundario,
            )
        indice += 1
        instante += intervalo


def _cabecalho(nome_cenario: str, seed: int, quantos: int, quantos_ves: int) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!--
  ARQUIVO GERADO por `python -m sim.demanda.gerar_rotas`. Não versionado.

  cenário  {nome_cenario}
  seed     {seed}
  veículos {quantos} de fundo + {quantos_ves} de emergência

  Este arquivo é o que garante o PAREAMENTO POR SEED (context/04 §7): os três
  modos de controle leem exatamente este tráfego. Regenerá-lo com a mesma seed
  produz um arquivo idêntico byte a byte.
-->
<routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/routes_file.xsd">
"""


def _elemento_vehicle(partida: Partida) -> str:
    """O `<vehicle>` de uma partida.

    O VE ganha o `<param>` de criticidade (P20) como elemento filho. O parâmetro
    não altera a dinâmica do SUMO; só diz ao adaptador que o VE está em serviço.
    """
    abertura = (
        f'    <vehicle id="{partida.id_veiculo}" type="{partida.tipo}" '
        f'route="{partida.rota}" depart="{partida.instante_s:.2f}" '
        f'departLane="free" departSpeed="max"'
    )
    if partida.criticidade is None:
        return abertura + "/>"
    return (
        f"{abertura}>\n"
        f'        <param key="{PARAMETRO_CRITICIDADE}" value="{int(partida.criticidade)}"/>\n'
        "    </vehicle>"
    )


def conteudo(nome_cenario: str, seed: int) -> str:
    """O texto do arquivo de rotas de um ponto experimental, sem escrever nada.

    Determinístico: mesma seed, mesmo cenário e mesmo código produzem o mesmo
    texto, byte a byte. É o que permite a `garantir()` saber se um arquivo em
    cache ainda é o que o código atual geraria.

    Raises:
        KeyError: se o cenário não tiver arquivo de fluxo mapeado.
    """
    if nome_cenario not in ARQUIVO_DE_FLUXO:
        raise KeyError(f"cenário desconhecido: {nome_cenario!r}")

    configuracao = calibracao.carregar_configuracao()
    rotas, fluxos = _rotas_e_fluxos(DIRETORIO_DEMANDA / ARQUIVO_DE_FLUXO[nome_cenario])
    rotas_ve = _rotas_de_emergencia_declaradas()

    gerador = random.Random(seed)
    fundo = list(partidas_de_fundo(fluxos, gerador))
    emergencia = list(partidas_de_emergencia(configuracao, nome_cenario, seed))

    # O SUMO exige o arquivo ordenado por instante de partida.
    partidas = sorted([*fundo, *emergencia], key=lambda p: (p.instante_s, p.id_veiculo))

    usadas = {partida.rota for partida in partidas}
    linhas = [_cabecalho(nome_cenario, seed, len(fundo), len(emergencia))]
    linhas += [
        f'    <route id="{identificador}" edges="{vias}"/>'
        for identificador, vias in {**rotas, **rotas_ve}.items()
        if identificador in usadas
    ]
    linhas.append("")
    linhas += [_elemento_vehicle(partida) for partida in partidas]
    linhas += ["", "</routes>"]
    return "\n".join(linhas) + "\n"


def gerar(nome_cenario: str, seed: int, destino: Path | None = None) -> Path:
    """Materializa o arquivo de rotas de um ponto experimental.

    Args:
        nome_cenario: Cenário de `cenarios.yaml`.
        seed: Seed do experimento. Mesma seed, mesmo arquivo.
        destino: Caminho de saída. Padrão:
            `sim/saida/rotas/<cenario>_<seed>.rou.xml`.

    Returns:
        O caminho escrito.

    Raises:
        KeyError: se o cenário não tiver arquivo de fluxo mapeado.
    """
    texto = conteudo(nome_cenario, seed)
    destino = destino or caminho_das_rotas(nome_cenario, seed)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    return destino


def caminho_das_rotas(nome_cenario: str, seed: int) -> Path:
    """Onde fica o arquivo de rotas de um ponto experimental."""
    return SAIDA / f"{nome_cenario}_{seed}.rou.xml"


def garantir(nome_cenario: str, seed: int) -> Path:
    """Devolve o arquivo de rotas, (re)gerando-o se não for o que o código atual geraria.

    Os três modos chamam isto e recebem o mesmo caminho com o mesmo conteúdo —
    é o pareamento. Como a geração é determinística, **regenerar não quebra o
    pareamento**: produz os mesmos bytes.

    **Por que não basta o arquivo existir (P20).** O cache em `sim/saida/rotas/`
    sobrevive a mudanças no gerador. Com a P20, arquivos antigos ficaram sem o
    parâmetro `criticidade` — e o adaptador trata VE sem ele como fora de
    serviço. Reaproveitá-los rodaria o lote inteiro **sem preempção nenhuma**, sem
    erro. Comparar com o conteúdo esperado fecha essa classe de falha para
    qualquer mudança futura no gerador, não só esta.
    """
    caminho = caminho_das_rotas(nome_cenario, seed)
    esperado = conteudo(nome_cenario, seed)
    if caminho.is_file() and caminho.read_text(encoding="utf-8") == esperado:
        return caminho
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(esperado, encoding="utf-8")
    return caminho


def main(argumentos: list[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(
        description="Materializa as rotas de um ponto experimental (entrega 3.3)."
    )
    analisador.add_argument("--cenario", required=True, choices=sorted(ARQUIVO_DE_FLUXO))
    analisador.add_argument("--seed", type=int, required=True)
    analisador.add_argument(
        "--forcar", action="store_true", help="regenera mesmo se o arquivo já existir"
    )
    opcoes = analisador.parse_args(argumentos)

    caminho = (
        gerar(opcoes.cenario, opcoes.seed)
        if opcoes.forcar
        else garantir(opcoes.cenario, opcoes.seed)
    )
    print(f"rotas: {caminho}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
