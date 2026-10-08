"""Estatística do capítulo 5 (`analysis/estatistica.py`), com valores conhecidos."""

from __future__ import annotations

import math

import numpy as np
import pytest

from analysis.estatistica import (
    cliff_delta,
    comparar_pareado,
    holm,
    ic_bootstrap,
    magnitude_cliff,
    mediana_iqr,
    t_pareado,
    wilcoxon_pareado,
)


def test_cliff_delta_dominancia_total_e_menos_um_quando_o_alvo_e_sempre_menor() -> None:
    assert cliff_delta([1.0, 2.0], [10.0, 20.0]) == -1.0
    assert cliff_delta([10.0, 20.0], [1.0, 2.0]) == 1.0


def test_cliff_delta_conta_empates_como_zero() -> None:
    # Pares: (1,1)=0, (1,2)=-1, (2,1)=+1, (2,2)=0 -> média 0.
    assert cliff_delta([1.0, 2.0], [1.0, 2.0]) == 0.0
    # Pares: (2,1)=+1, (2,3)=-1, (2,2)=0 -> 0; com (4,·): +1, +1, +1 -> 3/6.
    assert cliff_delta([2.0, 4.0], [1.0, 2.0, 3.0]) == pytest.approx(3 / 6)


def test_cliff_delta_vazio_e_nan() -> None:
    assert math.isnan(cliff_delta([], [1.0]))


@pytest.mark.parametrize(
    ("delta", "rotulo"),
    [(0.1, "desprezível"), (-0.2, "pequeno"), (0.4, "médio"), (-0.9, "grande")],
)
def test_magnitude_pelos_cortes_de_romano(delta: float, rotulo: str) -> None:
    assert magnitude_cliff(delta) == rotulo


def test_holm_no_exemplo_classico() -> None:
    # Em ordem: 0,01*3 = 0,03; 0,03*2 = 0,06; 0,04*1 = 0,04 -> monotonia força 0,06.
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])


def test_holm_limita_em_um_e_ignora_nan() -> None:
    ajustados = holm([0.5, math.nan, 0.6])
    assert ajustados[0] == pytest.approx(1.0)
    assert math.isnan(ajustados[1])
    assert ajustados[2] == pytest.approx(1.0)


def test_wilcoxon_sem_diferenca_nenhuma_devolve_p_um() -> None:
    x = np.array([5.0, 6.0, 7.0])
    assert wilcoxon_pareado(x, x.copy()) == (0.0, 1.0)
    assert t_pareado(x, x.copy()) == (0.0, 1.0)


def test_t_pareado_com_diferenca_constante_nao_nula_e_infinito() -> None:
    base = np.array([10.0, 20.0, 30.0])
    t, p = t_pareado(base - 5.0, base)
    assert t == -math.inf
    assert p == 0.0


def test_wilcoxon_detecta_reducao_consistente() -> None:
    base = np.arange(100.0, 112.0)
    alvo = base - np.arange(10.0, 22.0)
    _, p = wilcoxon_pareado(alvo, base)
    assert p < 0.01


def test_ic_bootstrap_e_reprodutivel_e_contem_a_media() -> None:
    valores = np.arange(1.0, 21.0)

    def media(indices: np.ndarray) -> float:
        return float(valores[indices].mean())

    primeiro = ic_bootstrap(valores.size, media, reamostragens=500)
    segundo = ic_bootstrap(valores.size, media, reamostragens=500)
    assert primeiro == segundo
    assert primeiro[0] < valores.mean() < primeiro[1]


def test_ic_bootstrap_com_uma_seed_nao_existe() -> None:
    assert all(math.isnan(v) for v in ic_bootstrap(1, lambda i: 0.0))


def test_mediana_iqr() -> None:
    assert mediana_iqr([1.0, 2.0, 3.0, 4.0, 5.0]) == (3.0, 2.0)


def test_comparar_pareado_monta_os_quatro_itens() -> None:
    base = np.arange(200.0, 212.0)
    alvo = base - 50.0 - np.arange(12.0) * 0.5
    resultado = comparar_pareado(alvo, base, reamostragens=300)

    assert resultado.n == 12
    assert resultado.mediana_diferenca < 0
    assert resultado.ic_mediana_diferenca[1] < 0
    assert resultado.p_wilcoxon < 0.01
    assert resultado.delta < 0
    assert resultado.p_shapiro is not None


def test_comparar_pareado_recusa_vetores_desiguais_ou_vazios() -> None:
    with pytest.raises(ValueError, match="tamanhos diferentes"):
        comparar_pareado([1.0, 2.0], [1.0])
    with pytest.raises(ValueError, match="nenhuma seed"):
        comparar_pareado([], [])
