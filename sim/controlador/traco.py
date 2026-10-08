r"""Traço passo a passo de uma execução — insumo das figuras F3, F4 e F6.

    python -m sim.controlador.traco --cenario intenso --seed 1 \
        --saida analysis/data/bloco8_traco

As figuras F3 (perfil espaço-temporal do VE), F4 (fila na transversal ao longo
do tempo) e F6 (diagrama de fases de um cruzamento durante a preempção) de
`context/07` §5 precisam de **séries no tempo**, e o lote não as grava: ele
guarda agregados por execução, que é o que sustenta as hipóteses (`context/04`
§10). Este módulo roda **uma** (cenário, seed) nos três braços de H1 e H2 e
grava, a cada segundo de simulação, a posição de cada VE ao longo da rota e a
fila de cada acesso transversal, além de toda transição de sinal.

O TRAÇO É A MESMA EXECUÇÃO DO LOTE, E PROVA ISSO

O laço é o do executor: `executor.decidir_e_aplicar`, com o motor, o
verificador e o coletor montados do mesmo jeito (`montar_motor`,
`parametros_do_modo`), e as rotas da mesma seed (`gerar_rotas.garantir`). As
leituras extras — `getDistance`, `getSpeed` e `getRoadID` do VE — são consultas,
e não mudam a simulação. Para que isso não fique na palavra, o traço grava
também `traco_viagens.csv`, com o tempo de cada VE tirado do `tripinfo` desta
execução; o pipeline do capítulo 5 compara com o `ve_por_execucao.csv` do lote
para a mesma (cenário, modo, seed) e declara se conferem.

Não grava em `execucao_simulacao`: a figura é ilustração de um ponto que o lote
já registrou, e uma segunda linha do mesmo ponto seria recusada pela restrição
única — com razão.
"""

from __future__ import annotations

import argparse
import csv
import gzip
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from adapters.configuracao import carregar as carregar_parametros
from adapters.sumo import topologia as topologia_sumo
from adapters.sumo.adaptador import AdaptadorSumo
from adapters.sumo.cliente import abrir_cliente
from adapters.terminal import saida_utf8
from core.modelos import EstadoMalha, Transicao
from core.priorizacao.conflito import EventoConflito
from core.priorizacao.politica import ConsultaModelo
from core.seguranca import VerificadorSeguranca
from sim.controlador import executor
from sim.controlador.coletor import ColetorMetricas
from sim.demanda import gerar_rotas

#: Os braços de F3, F4 e F6: os de H1 e H2. O `PREEMPCAO_ML` só existe no
#: cenário de múltiplos VEs, e nenhuma das três figuras é sobre ele.
MODOS_TRACO = ("FIXO", "PREEMPCAO", "PREEMPCAO_COMPENSADA")

#: Uma amostra por segundo de simulação. A F3 e a F4 são lidas em escala de
#: dezenas de segundos; mais fino só aumentaria o arquivo.
INTERVALO_AMOSTRA_S = 1.0

#: Os acessos transversais começam por `T` (`context/04` §3).
PREFIXO_TRANSVERSAL = "T"

ARQUIVO_VE = "traco_ve.csv"
ARQUIVO_FILA = "traco_fila.csv.gz"
ARQUIVO_SINAL = "traco_sinal.csv"
ARQUIVO_VIAGENS = "traco_viagens.csv"

SAIDA_BRUTA = executor.SAIDA / "traco"


@dataclass
class Traco:
    """O que uma execução deixa para as figuras, acumulado em memória.

    Attributes:
        modo: Braço.
        ve: `(t_s, id_veiculo, distancia_m, velocidade_ms, via)` por amostra.
        fila: `(t_s, id_semaforo, acesso, fila)` por amostra, só transversais.
        sinal: Toda transição de sinal da execução.
        viagens: `(id_veiculo, tempo_viagem_s)` do `tripinfo`.
    """

    modo: str
    ve: list[tuple[float, str, float, float, str]] = field(default_factory=list)
    fila: list[tuple[float, str, str, int]] = field(default_factory=list)
    sinal: list[Transicao] = field(default_factory=list)
    viagens: list[tuple[str, float]] = field(default_factory=list)


def deve_amostrar(t: float, passo_s: float, intervalo_s: float = INTERVALO_AMOSTRA_S) -> bool:
    """Se o instante `t` é um múltiplo do intervalo, dentro de meio passo."""
    resto = t % intervalo_s
    return min(resto, intervalo_s - resto) < passo_s / 2


def filas_transversais(estado: EstadoMalha) -> list[tuple[str, str, int]]:
    """`(id_semaforo, acesso, fila)` de todo acesso transversal do estado."""
    return [
        (id_semaforo, acesso, int(fila))
        for id_semaforo, semaforo in sorted(estado.semaforos.items())
        for acesso, fila in sorted(semaforo.fila_por_acesso.items())
        if acesso.startswith(PREFIXO_TRANSVERSAL)
    ]


def rodar_modo(cenario: str, modo: str, seed: int, duracao_s: float | None = None) -> Traco:
    """Roda um braço com o laço do executor e devolve o traço.

    Args:
        cenario: Cenário de `cenarios.yaml`.
        modo: Braço.
        seed: Seed.
        duracao_s: Duração simulada; `None` usa a de `cenarios.yaml`.
    """
    configuracao = executor._configuracao()
    duracao = duracao_s or float(configuracao["execucao"]["duracao_s"])
    passo_s = float(configuracao["execucao"]["passo_s"])

    malha = topologia_sumo.carregar()
    parametros = executor.parametros_do_modo(modo, carregar_parametros("simulacao"))
    rotas = gerar_rotas.garantir(cenario, seed)
    saida = SAIDA_BRUTA / f"{cenario}_{modo}_{seed}"
    saida.mkdir(parents=True, exist_ok=True)

    controlar = modo != "FIXO"
    adaptador = AdaptadorSumo(
        cliente=abrir_cliente(), malha=malha, parametros=parametros, controlar=controlar
    )
    conflitos: list[EventoConflito] = []
    consultas: list[ConsultaModelo] = []
    motor = executor.montar_motor(modo, parametros, malha.topologia, conflitos, consultas)
    verificador = VerificadorSeguranca(parametros=parametros)
    coletor = ColetorMetricas(cenario=cenario, modo=modo, seed=seed, passo_s=passo_s)
    traco = Traco(modo=modo)

    opcoes = executor.Opcoes(cenario=cenario, modo=modo, seed=seed, persistir=False)
    adaptador.iniciar(executor.comando_sumo(opcoes, rotas, saida, duracao))
    veiculo = adaptador.cliente.veiculo
    try:
        while adaptador.cliente.tempo() < duracao:
            t = adaptador.passo()
            estado = adaptador.ler_estado(t)
            executor.decidir_e_aplicar(
                adaptador,
                motor,
                verificador,
                coletor,
                estado,
                controlar,
                conflitos,
                None,
                consultas,
            )
            if deve_amostrar(t, passo_s):
                for ve in estado.veiculos_emergencia:
                    traco.ve.append(
                        (
                            t,
                            ve.id,
                            float(veiculo.getDistance(ve.id)),
                            float(veiculo.getSpeed(ve.id)),
                            str(veiculo.getRoadID(ve.id)),
                        )
                    )
                traco.fila.extend((t, *linha) for linha in filas_transversais(estado))
            if adaptador.cliente.veiculos_restantes() == 0:
                break
    finally:
        adaptador.fechar()

    resultado = coletor.consolidar(
        tripinfo=saida / "tripinfo.xml",
        duracao_s=duracao,
        veiculos_planejados=0,
        aquecimento_s=float(configuracao["execucao"]["aquecimento_s"]),
    )
    traco.sinal = list(resultado.transicoes)
    traco.viagens = [(v.id_veiculo, v.tempo_viagem_s) for v in resultado.viagens_ve]
    return traco


def gravar(tracos: Sequence[Traco], cenario: str, seed: int, pasta: Path) -> None:
    """Escreve os quatro CSV do traço. Sobrescreve: o traço é de um ponto só."""
    pasta.mkdir(parents=True, exist_ok=True)
    ponto = (cenario, seed)

    with (pasta / ARQUIVO_VE).open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(
            ("cenario", "seed", "modo", "t_s", "id_veiculo", "distancia_m", "velocidade_ms", "via")
        )
        for traco in tracos:
            for t, id_ve, distancia, velocidade, via in traco.ve:
                escritor.writerow(
                    (
                        *ponto,
                        traco.modo,
                        f"{t:.1f}",
                        id_ve,
                        f"{distancia:.2f}",
                        f"{velocidade:.2f}",
                        via,
                    )
                )

    # A fila tem uma linha por acesso transversal por segundo, nos três braços:
    # ~170 mil linhas. Comprimido, o arquivo cabe no repositório.
    with gzip.open(pasta / ARQUIVO_FILA, "wt", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(("cenario", "seed", "modo", "t_s", "id_semaforo", "acesso", "fila"))
        for traco in tracos:
            for t, id_semaforo, acesso, fila in traco.fila:
                escritor.writerow((*ponto, traco.modo, f"{t:.1f}", id_semaforo, acesso, fila))

    with (pasta / ARQUIVO_SINAL).open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(
            ("cenario", "seed", "modo", "t_s", "id_semaforo", "fase", "sinal", "em_preempcao")
        )
        for traco in tracos:
            for transicao in traco.sinal:
                escritor.writerow(
                    (
                        *ponto,
                        traco.modo,
                        f"{transicao.t:.1f}",
                        transicao.id_semaforo,
                        transicao.fase,
                        transicao.sinal.value,
                        int(transicao.em_preempcao),
                    )
                )

    with (pasta / ARQUIVO_VIAGENS).open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(("cenario", "seed", "modo", "id_veiculo", "tempo_viagem_s"))
        for traco in tracos:
            for id_ve, tempo in traco.viagens:
                escritor.writerow((*ponto, traco.modo, id_ve, f"{tempo:.2f}"))


def main(argumentos: Sequence[str] | None = None) -> int:
    saida_utf8()
    analisador = argparse.ArgumentParser(description="Traço de uma execução (F3, F4, F6).")
    analisador.add_argument("--cenario", default="intenso")
    analisador.add_argument("--seed", type=int, default=1)
    analisador.add_argument("--modos", default=",".join(MODOS_TRACO))
    analisador.add_argument("--duracao", type=float, default=None, help="segundos simulados")
    analisador.add_argument("--saida", type=Path, required=True, help="pasta dos CSV")
    opcoes = analisador.parse_args(argumentos)

    tracos = []
    for modo in opcoes.modos.split(","):
        print(f"traço {opcoes.cenario}/{modo}/seed={opcoes.seed} ...", flush=True)
        tracos.append(rodar_modo(opcoes.cenario, modo, opcoes.seed, opcoes.duracao))
    gravar(tracos, opcoes.cenario, opcoes.seed, opcoes.saida)
    print(f"traço gravado em {opcoes.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
