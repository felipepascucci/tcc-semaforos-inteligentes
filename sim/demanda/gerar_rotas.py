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

from sim.calibracao import cenarios as calibracao
from sim.demanda.fluxos import rotas_de_emergencia

RAIZ = Path(__file__).resolve().parents[2]
DIRETORIO_DEMANDA = RAIZ / "sim" / "demanda"
EMERGENCIAS = DIRETORIO_DEMANDA / "emergencias.rou.xml"
SAIDA = RAIZ / "sim" / "saida" / "rotas"

#: Cenário -> arquivo de fluxo. `multiplas_emergencias` compartilha a demanda de
#: fundo de `moderado` (context/04 §5): o que muda é a emergência, não o tráfego.
ARQUIVO_DE_FLUXO = {
    "leve": "fluxo_leve.rou.xml",
    "moderado": "fluxo_moderado.rou.xml",
    "intenso": "fluxo_intenso.rou.xml",
    "multiplas_emergencias": "fluxo_moderado.rou.xml",
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
    """

    id_veiculo: str
    tipo: str
    rota: str
    instante_s: float
    emergencia: bool = False


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


def partidas_de_emergencia(configuracao: Mapping[str, Any], nome_cenario: str) -> Iterator[Partida]:
    """Gera as partidas dos VEs — determinísticas, sem sorteio.

    Os instantes **não** dependem da seed, e isso é deliberado: o VE é o objeto
    de medida do experimento, e variar sua partida junto com o tráfego
    misturaria duas fontes de variação. A seed varia o tráfego de fundo; o VE
    entra sempre nos mesmos instantes, encontrando um trânsito diferente a cada
    seed. O tipo também é fixo por rodízio, porque o tipo define a prioridade em
    E8 e precisa ser o mesmo nos três braços.
    """
    emergencias = configuracao["emergencias"]
    execucao = configuracao["execucao"]
    intervalo = float(emergencias["intervalo_s"])
    tipos = [str(tipo).lower() for tipo in emergencias["tipos"]]
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
    if nome_cenario not in ARQUIVO_DE_FLUXO:
        raise KeyError(f"cenário desconhecido: {nome_cenario!r}")

    configuracao = calibracao.carregar_configuracao()
    rotas, fluxos = _rotas_e_fluxos(DIRETORIO_DEMANDA / ARQUIVO_DE_FLUXO[nome_cenario])
    rotas_ve = _rotas_de_emergencia_declaradas()

    gerador = random.Random(seed)
    fundo = list(partidas_de_fundo(fluxos, gerador))
    emergencia = list(partidas_de_emergencia(configuracao, nome_cenario))

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
    linhas += [
        f'    <vehicle id="{partida.id_veiculo}" type="{partida.tipo}" '
        f'route="{partida.rota}" depart="{partida.instante_s:.2f}" '
        f'departLane="free" departSpeed="max"/>'
        for partida in partidas
    ]
    linhas += ["", "</routes>"]

    destino = destino or SAIDA / f"{nome_cenario}_{seed}.rou.xml"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return destino


def caminho_das_rotas(nome_cenario: str, seed: int) -> Path:
    """Onde fica o arquivo de rotas de um ponto experimental."""
    return SAIDA / f"{nome_cenario}_{seed}.rou.xml"


def garantir(nome_cenario: str, seed: int) -> Path:
    """Devolve o arquivo de rotas, gerando-o se ainda não existir.

    Reaproveitar o arquivo existente **é** o pareamento: os três modos chamam
    isto e recebem o mesmo caminho.
    """
    caminho = caminho_das_rotas(nome_cenario, seed)
    return caminho if caminho.is_file() else gerar(nome_cenario, seed)


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
