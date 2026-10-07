"""Validação da malha antes de experimentar — entrega 3.4 (`context/04` §12).

    python -m sim.validacao.malha                    # cenário leve, 900 s
    python -m sim.validacao.malha --cenario intenso
    python -m sim.validacao.malha --todos

Os quatro itens de `context/04` §12, e o que cada um pega:

1. **`netconvert` sem avisos.** Conexão inválida vira movimento que não existe;
   o veículo some da rota e o fluxo medido não bate com o declarado.
2. **Zero colisões.** O pré-projeto afirma zero. Afirmação precisa de medição.
3. **Zero teleportes.** Com `time-to-teleport = -1` o SUMO não dissolve gridlock
   em silêncio: se um veículo travou, ele fica travado e o teleporte não
   acontece. Contar teleportes é, portanto, contar gridlock.
4. **v/c medido batendo com o v/c derivado.** É o fecho da cadeia de P11: o
   fluxo de saturação foi medido, a capacidade derivada dele, o v/c calculado —
   e agora a malha completa é interrogada para ver se ela de fato opera no
   regime que a conta previu.

> "Um gridlock não detectado invalida silenciosamente todo o experimento. Este
> passo não é opcional." (`context/04` §12)

SOBRE O ITEM 4, E O QUE ELE PROVA. O fluxo medido vem dos laços de indução E1,
que contam veículos por faixa depois de cada cruzamento. Como o tráfego de fundo
é passante (sem conversões), o que passa pelo E1 a jusante de uma aproximação é o
que aquela aproximação escoou. Em regime não saturado, escoamento é demanda —
então o confronto responde à pergunta certa: *a demanda que a malha realmente
recebeu é a que o cenário declara?* Divergência aponta para veículo que não
conseguiu entrar, fila que não dissipou ou rota mal montada.

O aquecimento é descartado: a malha começa vazia, e medir os primeiros minutos
misturaria o transiente de enchimento com o regime que se quer caracterizar.
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from adapters.terminal import saida_utf8
from sim.calibracao import cenarios as calibracao
from sim.calibracao.fluxo_saturacao import APROXIMACOES
from sim.controlador import executor
from sim.controlador.coletor import ResultadoExecucao
from sim.rede import construir as construtor

RAIZ = Path(__file__).resolve().parents[2]

#: Tolerância relativa entre o v/c medido e o derivado.
#:
#: Os 10% cobrem o que separa legitimamente os dois números: a execução é finita
#: (uma hora não é o infinito), as chegadas são um processo de Poisson com
#: variância própria, e o descarte do aquecimento nunca cai exatamente na virada
#: do regime. Divergência maior que isso não é ruído — é a malha operando em
#: regime diferente do que a calibração previu, e aí há o que corrigir.
TOLERANCIA_VC = 0.10


@dataclass(frozen=True)
class ResultadoValidacao:
    """O veredito sobre uma malha e um cenário.

    Attributes:
        cenario: Cenário validado.
        problemas: Lista de problemas. Vazia significa malha aprovada.
        vc_medido: v/c medido por aproximação.
        vc_derivado: v/c derivado da calibração.
        execucao: A execução usada na validação.
    """

    cenario: str
    problemas: tuple[str, ...]
    vc_medido: Mapping[str, float]
    vc_derivado: float
    execucao: ResultadoExecucao | None = None

    @property
    def aprovada(self) -> bool:
        """Se a malha pode ser usada para experimentar."""
        return not self.problemas


def fluxo_medido_veic_h(
    saida_e1: Path, faixas: Sequence[str], inicio_s: float, fim_s: float
) -> float:
    """Fluxo que passou pelos laços E1 de uma via, em veículos por hora.

    Args:
        saida_e1: `detectores_e1.xml` produzido pela execução.
        faixas: Ids das faixas cujos laços somar.
        inicio_s: Início da janela de medição (descarta o aquecimento).
        fim_s: Fim da janela.

    Returns:
        Fluxo em veíc./h, ou 0.0 se não houver intervalo na janela.
    """
    if not saida_e1.is_file():
        return 0.0

    alvos = {f"E1_{faixa}" for faixa in faixas}
    veiculos = 0.0
    coberto_s = 0.0
    por_intervalo: dict[tuple[float, float], float] = {}

    for elemento in ET.parse(saida_e1).getroot().iter("interval"):
        if str(elemento.get("id")) not in alvos:
            continue
        comeco, fim = float(elemento.get("begin", 0.0)), float(elemento.get("end", 0.0))
        if comeco < inicio_s or fim > fim_s:
            continue
        veiculos += float(elemento.get("nVehContrib", 0.0))
        por_intervalo[(comeco, fim)] = fim - comeco

    coberto_s = sum(por_intervalo.values())
    return veiculos * 3600.0 / coberto_s if coberto_s > 0 else 0.0


def capacidades_veic_h() -> dict[str, float]:
    """Capacidade de cada aproximação, derivada do fluxo de saturação medido."""
    configuracao = calibracao.carregar_configuracao()
    medicao = calibracao.carregar_medicao()
    arterial, transversal = calibracao.aproximacoes_medidas(configuracao, medicao)
    programa = calibracao.programa_de(configuracao)
    return {
        "arterial": calibracao.capacidade_veic_h(arterial, programa),
        "transversal": calibracao.capacidade_veic_h(transversal, programa),
    }


def validar(
    nome_cenario: str = "leve",
    *,
    duracao_s: float = 900.0,
    seed: int = 1,
    reconstruir: bool = True,
) -> ResultadoValidacao:
    """Roda a validação completa da malha para um cenário.

    Args:
        nome_cenario: Cenário a validar.
        duracao_s: Duração da execução de validação, em segundos.
        seed: Seed da execução.
        reconstruir: Se reconstrói a rede antes (item 1 da checagem).

    Returns:
        O veredito, com a lista de problemas encontrados.
    """
    problemas: list[str] = []

    # 1 — netconvert sem avisos (o modo estrito transforma aviso em erro).
    if reconstruir:
        try:
            construtor.construir(estrito=True)
        except construtor.ConstrucaoDeRedeError as erro:
            problemas.append(str(erro))

    # 2 e 3 — a execução propriamente dita, no baseline.
    execucao = executor.executar(
        executor.Opcoes(
            cenario=nome_cenario,
            modo="FIXO",
            seed=seed,
            duracao_s=duracao_s,
            persistir=False,
        )
    )
    if execucao.colisoes:
        problemas.append(f"{execucao.colisoes} colisão(ões) — o esperado é zero (context/04 §12)")
    if execucao.teleportes:
        problemas.append(
            f"{execucao.teleportes} teleporte(s) — com time-to-teleport desligado isso "
            "significa gridlock, e gridlock invalida o experimento"
        )
    if execucao.violacoes:
        problemas.append(
            f"{len(execucao.violacoes)} violação(ões) de invariante no BASELINE — "
            "o programa fixo do .tll.xml está inseguro"
        )

    # 4 — v/c medido contra v/c derivado.
    configuracao = calibracao.carregar_configuracao()
    linhas, _ = calibracao.calibrar()
    linha = next(linha for linha in linhas if linha.cenario == nome_cenario)
    capacidades = capacidades_veic_h()

    saida = executor.SAIDA / f"{nome_cenario}_FIXO_{seed}" / "detectores_e1.xml"
    aquecimento = float(configuracao["execucao"]["aquecimento_s"])
    faixas = calibracao_de_faixas()

    medidos: dict[str, float] = {}
    for aproximacao, ids_de_faixa in faixas.items():
        fluxo = fluxo_medido_veic_h(saida, ids_de_faixa, aquecimento, duracao_s)
        medidos[aproximacao] = fluxo / capacidades[aproximacao]

    for aproximacao, vc_medido in medidos.items():
        desvio = abs(vc_medido - linha.grau_saturacao)
        if desvio > TOLERANCIA_VC * max(linha.grau_saturacao, 1e-9):
            problemas.append(
                f"{aproximacao}: v/c medido {vc_medido:.3f} contra derivado "
                f"{linha.grau_saturacao:.3f} — desvio de "
                f"{desvio / linha.grau_saturacao * 100:.1f}%, acima da tolerância de "
                f"{TOLERANCIA_VC * 100:.0f}%"
            )

    return ResultadoValidacao(
        cenario=nome_cenario,
        problemas=tuple(problemas),
        vc_medido=medidos,
        vc_derivado=linha.grau_saturacao,
        execucao=execucao,
    )


def calibracao_de_faixas() -> dict[str, tuple[str, ...]]:
    """Faixas de saída onde o fluxo de cada aproximação é medido.

    Reaproveita o mapa de `fluxo_saturacao.APROXIMACOES`: a mesma aproximação que
    teve seu fluxo de saturação medido é a que tem seu fluxo real conferido aqui.
    Medir a capacidade num lugar e a demanda em outro compararia coisas
    diferentes.
    """
    from adapters.sumo import topologia as topologia_sumo  # import local: evita ciclo

    malha = topologia_sumo.carregar()
    return {
        nome: malha.faixas_do_acesso.get(saida, ())
        or tuple(f"{saida}_{indice}" for indice in range(2))
        for nome, (_, _, saida) in APROXIMACOES.items()
    }


def main(argumentos: list[str] | None = None) -> int:
    saida_utf8()
    analisador = argparse.ArgumentParser(description="Valida a malha (entrega 3.4).")
    analisador.add_argument("--cenario", default="leve")
    analisador.add_argument("--todos", action="store_true", help="valida os quatro cenários")
    analisador.add_argument("--duracao", type=float, default=900.0)
    analisador.add_argument("--seed", type=int, default=1)
    opcoes = analisador.parse_args(argumentos)

    configuracao = calibracao.carregar_configuracao()
    alvos = list(configuracao["cenarios"]) if opcoes.todos else [opcoes.cenario]

    falhou = False
    for nome in alvos:
        print(f"\n=== validando cenário {nome} ({opcoes.duracao:.0f} s, modo FIXO) ===")
        resultado = validar(nome, duracao_s=opcoes.duracao, seed=opcoes.seed)
        print(f"  v/c derivado   {resultado.vc_derivado:.3f}")
        for aproximacao, valor in sorted(resultado.vc_medido.items()):
            print(f"  v/c medido     {aproximacao:<12} {valor:.3f}")
        if resultado.aprovada:
            print("  APROVADA")
        else:
            falhou = True
            print("  REPROVADA")
            for problema in resultado.problemas:
                print(f"  ! {problema}")

    return 1 if falhou else 0


if __name__ == "__main__":
    raise SystemExit(main())
