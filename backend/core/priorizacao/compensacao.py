"""Etapa E7 — compensação de ciclo pós-evento (`context/01` §5.2).

É a etapa que sustenta **H2**: mitigar em **no mínimo 15%** o impacto negativo nas
vias transversais (enunciado corrigido em 2026-08-31 — "em até 15%" era um teto,
não uma meta, e a mitigação medida no piloto o cumpriria). Sem ela o trabalho
ainda mede H1, mas H2 fica sem evidência — e o `context/08` §2 é explícito: cortar
E7 obriga a tirar H2 do trabalho, não a deixá-la sem sustentação.

`K` e `n_ciclos_compensacao` continuam nos valores de partida de `context/01` §5.3
e **nunca foram calibrados contra dado real** (pendência P17). O piloto do Bloco 4
mede mitigação entre -1,0% e +0,6%.

A fórmula é a de `context/01` §5.2::

    verde_i = clamp(VERDE_BASE_i + K * (fila_i / soma_filas) * DEFICIT_TOTAL,
                    VERDE_MIN, VERDE_MAX)
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from core.malha import Cruzamento
from core.modelos import EstadoSemaforo
from core.parametros import Parametros


@dataclass(frozen=True)
class PlanoCompensacao:
    """Durações de verde a aplicar nos próximos ciclos.

    Attributes:
        id_semaforo: Cruzamento compensado.
        duracao_por_fase_s: Nova duração de verde de cada fase.
        n_ciclos: Por quantos ciclos o plano vale.
        deficit_total_s: Verde que as fases deixaram de receber na preempção.
    """

    id_semaforo: str
    duracao_por_fase_s: Mapping[int, float]
    n_ciclos: int
    deficit_total_s: float

    @property
    def acrescimo_total_s(self) -> float:
        """Quanto de verde o plano acrescenta em relação ao déficit."""
        return sum(self.duracao_por_fase_s.values())


def filas_por_fase(estado: EstadoSemaforo, cruzamento: Cruzamento) -> dict[int, int]:
    """Agrega a fila de cada acesso na fase que o serve.

    Args:
        estado: Estado observado do cruzamento, com fila por acesso.
        cruzamento: Topologia, que diz qual fase serve qual acesso.

    Returns:
        Fila acumulada por índice de fase.
    """
    return {
        fase.indice: sum(estado.fila_por_acesso.get(acesso, 0) for acesso in fase.acessos)
        for fase in cruzamento.fases
    }


def calcular_deficit_s(
    duracao_preempcao_s: float,
    fase_preemptada: int,
    cruzamento: Cruzamento,
    parametros: Parametros,
) -> float:
    """Verde que as demais fases deixaram de receber durante a preempção.

    Derivação: no ciclo fixo de duração `C`, a fase `i` recebe `base_i` de verde
    por ciclo. Durante `D` segundos de preempção teriam ocorrido `D / C` ciclos,
    logo a fase `i` perdeu `(D / C) * base_i`. O déficit total é a soma sobre as
    fases que **não** foram servidas pela preempção.

    Args:
        duracao_preempcao_s: Quanto durou a preempção, em segundos.
        fase_preemptada: Fase que recebeu o verde da preempção.
        cruzamento: Cruzamento em questão.
        parametros: Parâmetros do algoritmo.

    Returns:
        Déficit total, em segundos. Zero quando a preempção não durou nada.
    """
    if duracao_preempcao_s <= 0:
        return 0.0
    ciclo_s = cruzamento.duracao_do_ciclo_s(parametros.amarelo_s, parametros.all_red_s)
    if ciclo_s <= 0:
        return 0.0
    ciclos_perdidos = duracao_preempcao_s / ciclo_s
    base_das_outras = sum(
        fase.duracao_base_s for fase in cruzamento.fases if fase.indice != fase_preemptada
    )
    return ciclos_perdidos * base_das_outras


def compensar(
    cruzamento: Cruzamento,
    filas: Mapping[int, int],
    deficit_total_s: float,
    parametros: Parametros,
) -> PlanoCompensacao:
    """Etapa **E7** — redistribui verde proporcionalmente à fila acumulada.

    Args:
        cruzamento: Cruzamento a compensar.
        filas: Fila acumulada por fase (ver `filas_por_fase`).
        deficit_total_s: Verde perdido durante a preempção, em segundos.
        parametros: Parâmetros do algoritmo, incluindo o ganho `K`.

    Returns:
        O plano de compensação. Quando não há fila em lugar nenhum, o plano
        devolve as durações base — compensar um cruzamento vazio só atrasaria o
        retorno ao regime normal.
    """
    soma_filas = sum(max(fila, 0) for fila in filas.values())

    duracoes: dict[int, float] = {}
    for fase in cruzamento.fases:
        base = fase.duracao_base_s
        if soma_filas > 0 and deficit_total_s > 0:
            proporcao = max(filas.get(fase.indice, 0), 0) / soma_filas
            acrescimo = parametros.ganho_compensacao_k * proporcao * deficit_total_s
        else:
            acrescimo = 0.0
        piso = max(parametros.verde_min_s, fase.verde_min_s)
        teto = min(parametros.verde_max_s, fase.verde_max_s)
        duracoes[fase.indice] = min(max(base + acrescimo, piso), teto)

    return PlanoCompensacao(
        id_semaforo=cruzamento.id,
        duracao_por_fase_s=duracoes,
        n_ciclos=parametros.n_ciclos_compensacao,
        deficit_total_s=deficit_total_s,
    )
