"""Desenho da malha para o dashboard (`sim/rede/exportar_mapa.py`, Bloco 7). Sem SUMO."""

from __future__ import annotations

import math

import pytest

from db.seeds.carregar import METROS_POR_GRAU_LAT, metros_por_grau_lon
from sim.rede import exportar_mapa

CRUZAMENTOS = [f"CRUZ_0{i}" for i in range(1, 9)]


@pytest.fixture(scope="module")
def desenho() -> dict:
    return exportar_mapa.exportar()


def _metros(a: list[float], b: list[float]) -> float:
    dy = (a[0] - b[0]) * METROS_POR_GRAU_LAT
    dx = (a[1] - b[1]) * metros_por_grau_lon(a[0])
    return math.hypot(dx, dy)


def test_o_arquivo_versionado_esta_em_dia_com_a_rede(desenho: dict) -> None:
    """Mudou a rede ou o mapa de fases: `python -m sim.rede.exportar_mapa`."""
    gravado = exportar_mapa.DESTINO.read_text(encoding="utf-8")
    assert gravado == exportar_mapa.serializar(desenho)


def test_os_oito_cruzamentos_estao_la_e_o_prototipo_nao(desenho: dict) -> None:
    assert [c["id"] for c in desenho["cruzamentos"]] == CRUZAMENTOS


def test_cada_cruzamento_tem_quatro_aproximacoes_duas_por_fase(desenho: dict) -> None:
    for cruzamento in desenho["cruzamentos"]:
        fases = sorted(a["fase"] for a in cruzamento["aproximacoes"])
        assert fases == [1, 1, 2, 2], cruzamento["id"]


def test_aproximacao_arterial_e_fase_1_e_transversal_fase_2(desenho: dict) -> None:
    for cruzamento in desenho["cruzamentos"]:
        for aproximacao in cruzamento["aproximacoes"]:
            esperada = 1 if aproximacao["via"].startswith("A") else 2
            assert aproximacao["fase"] == esperada, aproximacao["via"]


def test_uma_linha_de_retencao_por_faixa_com_a_largura_da_faixa(desenho: dict) -> None:
    vias = {via["id"]: via for via in desenho["vias"]}
    for cruzamento in desenho["cruzamentos"]:
        for aproximacao in cruzamento["aproximacoes"]:
            faixas = vias[aproximacao["via"]]["faixas"]
            assert len(aproximacao["linhas"]) == len(faixas)
            for linha in aproximacao["linhas"]:
                assert _metros(*linha) == pytest.approx(2 * exportar_mapa.MEIA_LINHA_M, abs=0.05)


def test_a_linha_de_retencao_fica_perto_do_centro_do_cruzamento(desenho: dict) -> None:
    for cruzamento in desenho["cruzamentos"]:
        for aproximacao in cruzamento["aproximacoes"]:
            for linha in aproximacao["linhas"]:
                assert _metros(linha[0], cruzamento["centro"]) < 20, aproximacao["via"]


def test_o_ponto_de_sinal_fica_antes_da_linha_de_retencao(desenho: dict) -> None:
    """30 m atrás, na própria aproximação: longe o bastante para não cobrir o cruzamento."""
    for cruzamento in desenho["cruzamentos"]:
        for aproximacao in cruzamento["aproximacoes"]:
            pontas = [p for linha in aproximacao["linhas"] for p in linha]
            meio = [
                sum(p[0] for p in pontas) / len(pontas),
                sum(p[1] for p in pontas) / len(pontas),
            ]
            assert _metros(aproximacao["sinal"], meio) == pytest.approx(
                exportar_mapa.RECUO_SINAL_M, abs=0.5
            ), aproximacao["via"]
            assert _metros(aproximacao["sinal"], cruzamento["centro"]) > _metros(
                meio, cruzamento["centro"]
            )


def test_recuar_anda_pela_polilinha() -> None:
    faixa = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
    assert exportar_mapa._recuar(faixa, 5.0) == (10.0, 5.0)
    assert exportar_mapa._recuar(faixa, 15.0) == (5.0, 0.0)
    assert exportar_mapa._recuar(faixa, 100.0) == (0.0, 0.0)


def test_os_limites_contem_todas_as_vias(desenho: dict) -> None:
    (lat_min, lon_min), (lat_max, lon_max) = desenho["limites"]
    for via in desenho["vias"]:
        for faixa in via["faixas"]:
            for lat, lon in faixa:
                assert lat_min <= lat <= lat_max
                assert lon_min <= lon <= lon_max


def test_via_sem_fase_no_mapa_e_erro(tmp_path, desenho: dict) -> None:
    """Uma aproximação que nenhuma fase serve não pode virar linha sem cor."""
    original = exportar_mapa.MAPA_FASES.read_text(encoding="utf-8")
    quebrado = tmp_path / "mapa_fases.yaml"
    quebrado.write_text(original.replace("[A1_L0, A1_O1]", "[A1_O1]"), encoding="utf-8")

    with pytest.raises(ValueError, match="A1_L0 chega a CRUZ_01 sem fase"):
        exportar_mapa.exportar(mapa_fases=quebrado)
