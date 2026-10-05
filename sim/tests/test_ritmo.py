"""Ritmo da simulação ao vivo (`sim/controlador/ritmo.py`, Bloco 7). Relógio falso."""

from __future__ import annotations

import pytest

from sim.controlador.ritmo import Ritmo


class Relogio:
    def __init__(self) -> None:
        self.agora = 1000.0
        self.dormido: list[float] = []

    def __call__(self) -> float:
        return self.agora

    def dormir(self, segundos: float) -> None:
        self.dormido.append(segundos)
        self.agora += segundos


def _ritmo(velocidade: float, relogio: Relogio) -> Ritmo:
    return Ritmo(velocidade, relogio=relogio, dormir=relogio.dormir)


def test_o_primeiro_passo_marca_a_origem_e_nao_dorme() -> None:
    relogio = Relogio()
    assert _ritmo(1, relogio).esperar(0.1) == 0.0
    assert relogio.dormido == []


@pytest.mark.parametrize("velocidade", [1, 2, 5, 10])
def test_cada_segundo_simulado_leva_um_segundo_dividido_pela_velocidade(velocidade: int) -> None:
    relogio = Relogio()
    ritmo = _ritmo(velocidade, relogio)
    ritmo.esperar(0.0)

    for passo in range(1, 101):  # 10 s simulados, laço instantâneo
        ritmo.esperar(passo * 0.1)

    assert relogio.agora - 1000.0 == pytest.approx(10.0 / velocidade)


def test_laco_mais_lento_que_a_velocidade_nao_dorme_nem_acumula_divida() -> None:
    """Se a máquina não acompanha, a simulação só anda o mais rápido que conseguir."""
    relogio = Relogio()
    ritmo = _ritmo(10, relogio)
    ritmo.esperar(0.0)

    relogio.agora += 1.0  # 1 s de relógio para 0,1 s simulado: atrasado
    assert ritmo.esperar(0.1) == 0.0
    assert relogio.dormido == []


def test_tempo_do_laco_e_descontado_da_espera() -> None:
    relogio = Relogio()
    ritmo = _ritmo(1, relogio)
    ritmo.esperar(0.0)

    relogio.agora += 0.03  # o passo levou 30 ms
    assert ritmo.esperar(0.1) == pytest.approx(0.07)


@pytest.mark.parametrize("velocidade", [0, -1])
def test_velocidade_nao_positiva_e_erro(velocidade: float) -> None:
    with pytest.raises(ValueError, match="positiva"):
        Ritmo(velocidade)
