"""Figuras do capítulo 5 (`analysis/figuras.py`), com traço sintético."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from analysis.figuras import (
    f3_espaco_tempo,
    f4_fila_transversal,
    f6_fases,
    intervalos_de_preempcao,
    posicoes_dos_cruzamentos,
)


def _sinal() -> pd.DataFrame:
    """Um ciclo com preempção de 30 a 70 s: verde, amarelo, all-red, verde."""
    linhas = [
        (0.0, 1, "VERDE", 0),
        (30.0, 1, "AMARELO", 1),
        (33.0, 1, "VERMELHO", 1),
        (35.0, 2, "VERDE", 1),
        (70.0, 2, "AMARELO", 0),
        (73.0, 2, "VERMELHO", 0),
        (75.0, 1, "VERDE", 0),
    ]
    return pd.DataFrame(
        [("PREEMPCAO", "SEMAFORO_TESTE", t, f, s, p) for t, f, s, p in linhas],
        columns=["modo", "id_semaforo", "t_s", "fase", "sinal", "em_preempcao"],
    )


def test_intervalos_de_preempcao() -> None:
    assert intervalos_de_preempcao(_sinal(), "PREEMPCAO", "SEMAFORO_TESTE") == [(30.0, 70.0)]
    assert intervalos_de_preempcao(_sinal(), "FIXO", "SEMAFORO_TESTE") == []


def test_cruzamentos_saem_das_faixas_internas() -> None:
    traco = pd.DataFrame(
        {
            "distancia_m": [0.0, 490.0, 500.0, 520.0, 990.0, 1000.0],
            "via": [
                "A1_L0",
                ":CRUZ_TESTE_1_0",
                ":CRUZ_TESTE_1_0",
                "A1_L1",
                ":CRUZ_TESTE_2_3",
                "A1_L2",
            ],
        }
    )
    assert posicoes_dos_cruzamentos(traco) == [490.0, 990.0]


def test_virgula_decimal_nao_apaga_rotulos_postos_a_mao() -> None:
    """Regressão: a F6 saía com 0, 1, 2 no lugar de "Fase 1", "Fase 2", "All-red"."""
    import matplotlib.pyplot as plt

    from analysis.figuras import _virgula_decimal

    figura, eixo = plt.subplots()
    eixo.plot([0.5, 1.5], [0.0, 2.0])
    eixo.set_yticks([0, 1, 2])
    eixo.set_yticklabels(["Fase 1", "Fase 2", "All-red"])
    _virgula_decimal(figura)
    figura.canvas.draw()

    assert [r.get_text() for r in eixo.get_yticklabels()] == ["Fase 1", "Fase 2", "All-red"]
    assert "," in "".join(r.get_text() for r in eixo.get_xticklabels())
    plt.close(figura)


def test_f3_f4_f6_geram_pdf(tmp_path: Path) -> None:
    tempos = [float(t) for t in range(0, 100)]
    ve = pd.DataFrame(
        [
            (modo, t, "VE_TESTE_00", t * velocidade, 10.0, "A1_L0")
            for modo, velocidade in (("FIXO", 5.0), ("PREEMPCAO", 10.0))
            for t in tempos
        ],
        columns=["modo", "t_s", "id_veiculo", "distancia_m", "velocidade_ms", "via"],
    )
    fila = pd.DataFrame(
        [(modo, t, "SEMAFORO_TESTE", "T1_S0", int(t) % 7) for modo in ("FIXO", "PREEMPCAO")
         for t in tempos],
        columns=["modo", "t_s", "id_semaforo", "acesso", "fila"],
    )  # fmt: skip

    destinos = [
        f3_espaco_tempo(ve, "VE_TESTE_00", tmp_path / "F3.pdf"),
        f4_fila_transversal(fila, _sinal(), "SEMAFORO_TESTE", (0.0, 99.0), tmp_path / "F4.pdf"),
        f6_fases(_sinal(), "PREEMPCAO", "SEMAFORO_TESTE", (0.0, 90.0), tmp_path / "F6.pdf"),
    ]

    for destino in destinos:
        assert destino.read_bytes().startswith(b"%PDF")
