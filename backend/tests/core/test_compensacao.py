"""E7 — compensação de ciclo pós-evento, a evidência de H2."""

from __future__ import annotations

import pytest

from core.malha import Cruzamento
from core.modelos import EstadoSemaforo
from core.parametros import Parametros
from core.priorizacao.compensacao import calcular_deficit_s, compensar, filas_por_fase
from tests.core.conftest import FASE_ARTERIAL, FASE_TRANSVERSAL, construir_parametros


def _estado_com_filas(arterial: int, transversal: int) -> EstadoSemaforo:
    return EstadoSemaforo(
        id="CRUZ_TESTE_1",
        fase_atual=FASE_ARTERIAL,
        tempo_na_fase=0.0,
        fila_por_acesso={"E0": arterial, "T1_IN": transversal},
    )


def test_filas_sao_agregadas_na_fase_que_serve_o_acesso(cruzamento: Cruzamento) -> None:
    filas = filas_por_fase(_estado_com_filas(arterial=3, transversal=12), cruzamento)
    assert filas == {FASE_ARTERIAL: 3, FASE_TRANSVERSAL: 12}


# ---------------------------------------------------------------------------
# Déficit
# ---------------------------------------------------------------------------


def test_deficit_e_proporcional_a_duracao_da_preempcao(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    """`(D / C) * base_das_outras` — ver a derivação em `compensacao.py`."""
    # Ciclo: 2 fases x (30 + 3 + 2) = 70 s. Base das outras = 30 s.
    ciclo = cruzamento.duracao_do_ciclo_s(parametros.amarelo_s, parametros.all_red_s)
    assert ciclo == pytest.approx(70.0)

    deficit = calcular_deficit_s(35.0, FASE_ARTERIAL, cruzamento, parametros)
    assert deficit == pytest.approx(0.5 * 30.0)


def test_preempcao_de_duracao_zero_nao_gera_deficit(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    assert calcular_deficit_s(0.0, FASE_ARTERIAL, cruzamento, parametros) == 0.0


def test_deficit_dobra_quando_a_preempcao_dobra(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    curto = calcular_deficit_s(20.0, FASE_ARTERIAL, cruzamento, parametros)
    longo = calcular_deficit_s(40.0, FASE_ARTERIAL, cruzamento, parametros)
    assert longo == pytest.approx(2 * curto)


# ---------------------------------------------------------------------------
# Redistribuição
# ---------------------------------------------------------------------------


def test_verde_extra_vai_para_quem_tem_mais_fila(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    """O ponto de E7: quem esperou durante a preempção recebe de volta."""
    filas = {FASE_ARTERIAL: 2, FASE_TRANSVERSAL: 18}
    plano = compensar(cruzamento, filas, deficit_total_s=20.0, parametros=parametros)

    base = cruzamento.fase(FASE_ARTERIAL).duracao_base_s
    # K * (18/20) * 20 = 0,7 * 0,9 * 20 = 12,6 s para a transversal
    assert plano.duracao_por_fase_s[FASE_TRANSVERSAL] == pytest.approx(base + 12.6)
    # K * (2/20) * 20 = 1,4 s para a arterial
    assert plano.duracao_por_fase_s[FASE_ARTERIAL] == pytest.approx(base + 1.4)


def test_ganho_k_escala_a_compensacao(cruzamento: Cruzamento) -> None:
    """`K` é parâmetro do experimento — não pode estar embutido no código."""
    filas = {FASE_ARTERIAL: 0, FASE_TRANSVERSAL: 10}
    base = cruzamento.fase(FASE_TRANSVERSAL).duracao_base_s

    sem_ganho = compensar(cruzamento, filas, 20.0, construir_parametros(ganho_compensacao_k=0.0))
    com_ganho = compensar(cruzamento, filas, 20.0, construir_parametros(ganho_compensacao_k=1.0))

    assert sem_ganho.duracao_por_fase_s[FASE_TRANSVERSAL] == pytest.approx(base)
    assert com_ganho.duracao_por_fase_s[FASE_TRANSVERSAL] == pytest.approx(base + 20.0)


def test_compensacao_respeita_verde_min_e_verde_max(cruzamento: Cruzamento) -> None:
    """O `clamp` da fórmula não é decoração: sem ele E7 violaria I4 e I5."""
    parametros = construir_parametros(ganho_compensacao_k=10.0)
    filas = {FASE_ARTERIAL: 0, FASE_TRANSVERSAL: 100}

    plano = compensar(cruzamento, filas, deficit_total_s=500.0, parametros=parametros)

    for indice, duracao in plano.duracao_por_fase_s.items():
        fase = cruzamento.fase(indice)
        assert fase.verde_min_s <= duracao <= fase.verde_max_s


def test_cruzamento_vazio_nao_e_compensado(cruzamento: Cruzamento, parametros: Parametros) -> None:
    """Compensar um cruzamento sem fila só atrasaria a volta ao regime normal."""
    plano = compensar(cruzamento, {FASE_ARTERIAL: 0, FASE_TRANSVERSAL: 0}, 30.0, parametros)

    for indice, duracao in plano.duracao_por_fase_s.items():
        assert duracao == pytest.approx(cruzamento.fase(indice).duracao_base_s)


def test_sem_deficit_nao_ha_compensacao(cruzamento: Cruzamento, parametros: Parametros) -> None:
    plano = compensar(cruzamento, {FASE_ARTERIAL: 5, FASE_TRANSVERSAL: 5}, 0.0, parametros)

    for indice, duracao in plano.duracao_por_fase_s.items():
        assert duracao == pytest.approx(cruzamento.fase(indice).duracao_base_s)


def test_plano_carrega_o_numero_de_ciclos_dos_parametros(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    plano = compensar(cruzamento, {FASE_TRANSVERSAL: 10}, 20.0, parametros)
    assert plano.n_ciclos == parametros.n_ciclos_compensacao == 2
