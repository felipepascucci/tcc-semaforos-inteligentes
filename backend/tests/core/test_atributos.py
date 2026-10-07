"""Atributos de um VE numa disputa — a entrada do modelo de P19."""

from __future__ import annotations

import pytest

from core.modelos import TipoVeiculo
from core.priorizacao.atributos import atributos_do_ve, cruzamentos_restantes
from core.priorizacao.deteccao import detectar
from tests.core.conftest import (
    construir_estado,
    construir_parametros,
    construir_topologia,
    construir_ve,
)


@pytest.mark.parametrize(("indice", "esperado"), [(0, 3), (1, 2), (2, 1), (3, 0)])
def test_cruzamentos_restantes_contam_o_atual_e_nao_o_fim_da_rota(
    indice: int, esperado: int
) -> None:
    """Rota E0..E3 por três cruzamentos: cada via, menos a última, desemboca num."""
    topologia = construir_topologia(n_cruzamentos=3)
    veiculo = construir_ve(n_vias=4, indice_via_atual=indice)

    assert cruzamentos_restantes(topologia, veiculo) == esperado


def test_atributos_saem_do_que_o_motor_ja_tem() -> None:
    """ETA da detecção, velocidade do VE e a fila do acesso, somada e por faixa."""
    topologia = construir_topologia(faixas=2)
    parametros = construir_parametros()
    veiculo = construir_ve(
        "AMB", TipoVeiculo.AMBULANCIA, n_vias=4, posicao_na_via_m=400.0, velocidade=12.5
    )
    estado = construir_estado(topologia, veiculos=(veiculo,), fila=6)
    deteccao = detectar(topologia, veiculo, parametros)[0]

    from core.priorizacao.conflito import Disputa

    atributos = atributos_do_ve(Disputa(deteccao, fase_desejada=1), estado, topologia)

    assert atributos.eta_s == deteccao.eta_s
    assert atributos.velocidade_ms == 12.5
    assert atributos.fila_no_acesso == 6
    assert atributos.fila_por_faixa == 3.0
    assert atributos.cruzamentos_restantes == 3


def test_ve_fora_do_estado_falha_alto() -> None:
    """A disputa precisa ter vindo do estado dado; senão o atributo seria de outro instante."""
    topologia = construir_topologia()
    veiculo = construir_ve(posicao_na_via_m=400.0)
    deteccao = detectar(topologia, veiculo, construir_parametros())[0]

    from core.priorizacao.conflito import Disputa

    with pytest.raises(KeyError):
        atributos_do_ve(Disputa(deteccao, fase_desejada=1), construir_estado(topologia), topologia)
