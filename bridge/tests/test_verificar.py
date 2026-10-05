"""O conferidor de invariantes do `verificar.py` precisa acusar o que diz acusar."""

from __future__ import annotations

from bridge.verificar import violacoes

CICLO = ["RRRR", "GRRR", "GRRR", "YRRR", "YRRR", "RRRR", "RRRR", "RGRR", "RYRR"]


def test_ciclo_correto_nao_tem_violacao() -> None:
    assert violacoes(CICLO) == []


def test_dois_verdes_violam_i1() -> None:
    assert any(v.startswith("I1") for v in violacoes(["RRRR", "GRGR"]))


def test_verde_direto_para_vermelho_viola_i2() -> None:
    assert any(v.startswith("I2") for v in violacoes(["GRRR", "RRRR"]))


def test_verde_sem_all_red_antes_viola_i3() -> None:
    assert any(v.startswith("I3") for v in violacoes(["YRRR", "RGRR"]))
