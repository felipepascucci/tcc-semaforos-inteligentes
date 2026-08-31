"""Fixtures do núcleo — determinísticas, artificiais e sem SUMO.

`context/06` §7 pede fixtures **obviamente artificiais**: valores redondos e
nomes como `SEMAFORO_TESTE`, para que ninguém confunda dado de teste com
resultado experimental (`context/08` §4.2).

A malha de teste é um corredor linear, que é a forma mínima capaz de exercitar o
"corredor verde": vias `E0..En` em sequência, com um cruzamento ao fim de cada
uma. Cada cruzamento tem duas fases — arterial (a que o VE usa) e transversal.
"""

from __future__ import annotations

import pytest

from core.malha import Cruzamento, Fase, TopologiaMalha
from core.modelos import EstadoMalha, EstadoSemaforo, Sinal, TipoVeiculo, VeiculoEmergencia
from core.parametros import Parametros

COMPRIMENTO_VIA_M = 500.0

FASE_ARTERIAL = 1
FASE_TRANSVERSAL = 2


def construir_topologia(
    n_cruzamentos: int = 3,
    comprimento_via_m: float = COMPRIMENTO_VIA_M,
    verde_min_s: float = 7.0,
    verde_max_s: float = 60.0,
    duracao_base_s: float = 30.0,
    faixas: int = 1,
) -> TopologiaMalha:
    """Corredor linear com `n` cruzamentos.

    Vias `E0..En`; a via `E{i}` desemboca no cruzamento `CRUZ_TESTE_{i+1}`.
    A rota arterial completa é `("E0", "E1", ..., "En")`.

    `faixas` vale para todas as vias e existe para exercitar E3: a fila que os
    detectores E2 entregam é somada sobre as faixas, e o que atrasa o VE é a
    fila da faixa dele.
    """
    cruzamentos: dict[str, Cruzamento] = {}
    comprimentos: dict[str, float] = {}
    apos_via: dict[str, str] = {}

    for indice in range(n_cruzamentos + 1):
        comprimentos[f"E{indice}"] = comprimento_via_m

    for numero in range(1, n_cruzamentos + 1):
        entrada, saida = f"E{numero - 1}", f"E{numero}"
        transversal_entrada = f"T{numero}_IN"
        transversal_saida = f"T{numero}_OUT"
        comprimentos[transversal_entrada] = comprimento_via_m
        comprimentos[transversal_saida] = comprimento_via_m

        id_cruzamento = f"CRUZ_TESTE_{numero}"
        apos_via[entrada] = id_cruzamento
        apos_via[transversal_entrada] = id_cruzamento

        cruzamentos[id_cruzamento] = Cruzamento(
            id=id_cruzamento,
            fases=(
                Fase(
                    indice=FASE_ARTERIAL,
                    descricao="Arterial",
                    movimentos=frozenset({(entrada, saida)}),
                    duracao_base_s=duracao_base_s,
                    verde_min_s=verde_min_s,
                    verde_max_s=verde_max_s,
                ),
                Fase(
                    indice=FASE_TRANSVERSAL,
                    descricao="Transversal",
                    movimentos=frozenset({(transversal_entrada, transversal_saida)}),
                    duracao_base_s=duracao_base_s,
                    verde_min_s=verde_min_s,
                    verde_max_s=verde_max_s,
                ),
            ),
        )

    return TopologiaMalha(
        cruzamentos=cruzamentos,
        comprimento_via_m=comprimentos,
        cruzamento_apos_via=apos_via,
        faixas_por_via=dict.fromkeys(comprimentos, faixas),
    )


def construir_parametros(**sobrescritas: object) -> Parametros:
    """Parâmetros do perfil de simulação, com sobrescrita pontual.

    Os valores são exatamente os de `context/01` §5.3 — testar contra outros
    tornaria o teste um espelho de si mesmo.
    """
    base: dict[str, object] = {
        "raio_deteccao_m": 500,
        "tempo_antecipacao_margem_s": 5.0,
        "headway_saturacao_s": 2.13,
        "velocidade_min_estimativa_ms": 4.0,
        "verde_min_s": 7.0,
        "verde_max_s": 60.0,
        "amarelo_s": 3.0,
        "all_red_s": 2.0,
        "preempcao_timeout_s": 45.0,
        "n_ciclos_compensacao": 2,
        "ganho_compensacao_k": 0.7,
        "prioridade_tipo": ["AMBULANCIA", "BOMBEIRO", "POLICIA"],
        "vermelho_max_s": 120.0,
        "watchdog_s": 3.0,
    }
    base.update(sobrescritas)
    return Parametros.de_dicionario(base)


def construir_ve(
    id_veiculo: str = "VE_TESTE",
    tipo: TipoVeiculo = TipoVeiculo.AMBULANCIA,
    n_vias: int = 4,
    indice_via_atual: int = 0,
    posicao_na_via_m: float = 0.0,
    velocidade: float = 10.0,
) -> VeiculoEmergencia:
    """Um VE percorrendo o corredor arterial de ponta a ponta."""
    return VeiculoEmergencia(
        id=id_veiculo,
        tipo=tipo,
        posicao=(0.0, 0.0),
        velocidade=velocidade,
        rota=tuple(f"E{i}" for i in range(n_vias)),
        indice_via_atual=indice_via_atual,
        posicao_na_via_m=posicao_na_via_m,
    )


def construir_estado(
    topologia: TopologiaMalha,
    t: float = 0.0,
    veiculos: tuple[VeiculoEmergencia, ...] = (),
    fase_atual: int = FASE_TRANSVERSAL,
    tempo_na_fase: float = 20.0,
    sinal: Sinal = Sinal.VERDE,
    fila: int = 0,
) -> EstadoMalha:
    """Estado da malha com todos os cruzamentos na mesma situação."""
    semaforos = {
        id_cruzamento: EstadoSemaforo(
            id=id_cruzamento,
            fase_atual=fase_atual,
            tempo_na_fase=tempo_na_fase,
            fila_por_acesso={acesso: fila for acesso in cruzamento.acessos()},
            sinal=sinal,
        )
        for id_cruzamento, cruzamento in topologia.cruzamentos.items()
    }
    return EstadoMalha(t=t, semaforos=semaforos, veiculos_emergencia=veiculos)


@pytest.fixture
def topologia() -> TopologiaMalha:
    return construir_topologia()


@pytest.fixture
def parametros() -> Parametros:
    return construir_parametros()


@pytest.fixture
def cruzamento(topologia: TopologiaMalha) -> Cruzamento:
    return topologia.cruzamento("CRUZ_TESTE_1")
