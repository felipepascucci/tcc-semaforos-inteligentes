"""O conferidor de invariantes do `verificar.py` precisa acusar o que diz acusar.

Ele roda sobre a sequência de `(ms, S1S2S3S4)` das linhas `ST`, que trazem toda
mudança de estado com o `millis()` do UNO (`context/05` §4.2).
"""

from __future__ import annotations

from bridge.verificar import transicoes, violacoes

CICLO = [
    (0, "RRRR"),
    (500, "RRRR"),
    (1000, "GGRR"),
    (4000, "YYRR"),
    (6000, "RRRR"),
    (7000, "RRGG"),
    (10_000, "RRYY"),
    (12_000, "RRRR"),
    (13_000, "GGRR"),
]

EMERGENCIA_NO_EIXO_VERDE = [(13_000, "GGRR"), (16_000, "GYRR"), (18_000, "GRRR")]


def _tipos(achados: list[str]) -> set[str]:
    return {a.split(":")[0] for a in achados}


def test_ciclo_correto_nao_tem_violacao() -> None:
    assert violacoes(CICLO) == []


def test_ve_no_eixo_verde_mantem_o_verde_sem_violacao() -> None:
    assert violacoes(EMERGENCIA_NO_EIXO_VERDE) == []


def test_transicoes_descartam_repeticoes() -> None:
    assert transicoes([(0, "RRRR"), (500, "RRRR"), (1000, "GGRR")]) == [
        (0, "RRRR"),
        (1000, "GGRR"),
    ]


def test_verde_nos_dois_eixos_viola_i1() -> None:
    assert "I1" in _tipos(violacoes([(0, "RRRR"), (1000, "GRGR")]))


def test_dois_verdes_no_mesmo_eixo_nao_viola_i1() -> None:
    assert "I1" not in _tipos(violacoes([(0, "RRRR"), (1000, "GGRR")]))


def test_verde_direto_para_vermelho_viola_i2() -> None:
    assert "I2" in _tipos(violacoes([(0, "GRRR"), (1000, "RRRR")]))


def test_amarelo_curto_viola_i2() -> None:
    achados = violacoes([(0, "GRRR"), (3000, "YRRR"), (4000, "RRRR")])
    assert any("amarelo de S1 durou 1000 ms" in a for a in achados)


def test_verde_sem_all_red_antes_viola_i3() -> None:
    assert "I3" in _tipos(violacoes([(0, "YRRR"), (2000, "RGRR")]))


def test_all_red_curto_viola_i3() -> None:
    assert "I3" in _tipos(violacoes([(0, "YRRR"), (2000, "RRRR"), (2500, "RRGR")]))


def test_verde_curto_viola_i4() -> None:
    achados = violacoes([(0, "RRRR"), (1000, "GRRR"), (2000, "YRRR")])
    assert any(a.startswith("I4") for a in achados)


def test_amarelo_para_verde_e_acusado() -> None:
    assert "amarelo -> verde" in _tipos(violacoes([(0, "GRRR"), (3000, "YRRR"), (4000, "GRRR")]))


def test_folga_absorve_uma_volta_do_loop() -> None:
    """Na placa, uma transição pode sair alguns ms antes da conta redonda."""
    ciclo_apertado = [(0, "RRRR"), (990, "GGRR"), (3985, "YYRR"), (5980, "RRRR"), (6975, "RRGG")]
    assert violacoes(ciclo_apertado, folga_ms=60) == []
    assert violacoes(ciclo_apertado) != []
