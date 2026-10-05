"""Laço da ponte contra o dublê do UNO — entrega 5.7, refeita: a ponte só escuta."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from adapters.hardware.simulado import TransporteSimulado
from bridge.ponte import Ponte
from bridge.protocolo import Deteccao, Regime, TipoEvento
from bridge.tests.conftest import (
    PortaAusente,
    PortaRoteirizada,
    ate,
    fabrica_de_uno,
    transporte_rapido,
)
from bridge.transporte import ConexaoPerdidaError
from core.modelos import TipoVeiculo

AMB_RUA_3 = Deteccao(3, TipoVeiculo.AMBULANCIA)


@asynccontextmanager
async def _rodando(ponte: Ponte) -> AsyncIterator[Ponte]:
    tarefa = asyncio.create_task(ponte.rodar())
    try:
        await ate(ponte.uno_respondendo)
        yield ponte
    finally:
        ponte.parar()
        await asyncio.wait_for(tarefa, 5.0)


@pytest.fixture
async def ponte() -> AsyncIterator[Ponte]:
    async with _rodando(Ponte(transporte_rapido())) as rodando:
        yield rodando


def _eventos(ponte: Ponte, tipo: TipoEvento) -> int:
    return sum(1 for _, ev in ponte.eventos if ev.tipo is tipo)


# ---------------------------------------------------------------------------
# Escuta
# ---------------------------------------------------------------------------


async def test_escuta_o_boot_e_a_telemetria(ponte: Ponte) -> None:
    assert _eventos(ponte, TipoEvento.BOOT) == 1
    assert ponte.ultima_telemetria is not None
    assert ponte.ultima_telemetria.regime is Regime.CICLO
    assert ponte.t_ultima_telemetria is not None


async def test_decisao_vinda_do_receptor_tambem_e_ouvida() -> None:
    """Na operação quem escreve no RX é o NodeMCU, e a ponte só ouve."""
    transporte = transporte_rapido(fio_do_nodemcu_no_rx=True)
    async with _rodando(Ponte(transporte)) as ponte:
        transporte.simular_receptor(AMB_RUA_3)
        await ate(lambda: _eventos(ponte, TipoEvento.PREEMP_INI) == 1)
        _, evento = ponte.eventos[-1]
        assert (evento.rua, evento.veiculo) == (3, TipoVeiculo.AMBULANCIA)


async def test_ruido_e_contado_e_verde_nos_dois_eixos_e_denunciado() -> None:
    porta = PortaRoteirizada(
        [b"\xff\x00lixo de boot\n", b"ST,100,GGRR,C,0,0\n", b"ST,600,GRGR,C,0,0\n"]
    )
    ponte = Ponte(porta)
    tarefa = asyncio.create_task(ponte.rodar())
    await ate(lambda: ponte.telemetrias_violando_i1 == 1)

    assert ponte.linhas_invalidas == 1
    assert ponte.ultima_telemetria is not None
    assert ponte.ultima_telemetria.t_dispositivo_ms == 600
    assert len(ponte.telemetrias) == 2
    ponte.parar()
    await asyncio.wait_for(tarefa, 5.0)


# ---------------------------------------------------------------------------
# Injeção de teste
# ---------------------------------------------------------------------------


async def test_injecao_devolve_a_decisao_do_uno() -> None:
    latencia_s = 0.05
    async with _rodando(Ponte(transporte_rapido(latencia_s=latencia_s))) as ponte:
        resultado = await ponte.injetar(AMB_RUA_3)

        assert resultado.linha == "RUA3,AMBULANCIA"
        assert resultado.decisao is not None
        assert resultado.decisao.tipo is TipoEvento.PREEMP_INI
        assert resultado.t_decisao is not None
        assert resultado.t_decisao > resultado.t_envio
        # Folga da resolução de timers do Windows (~15,6 ms).
        assert resultado.latencia_ms is not None
        assert resultado.latencia_ms >= latencia_s * 1000 - 20


async def test_injecoes_seguidas_casam_cada_uma_com_a_sua_decisao(ponte: Ponte) -> None:
    primeira = await ponte.injetar(Deteccao(1, TipoVeiculo.POLICIA))
    segunda = await ponte.injetar(Deteccao(2, TipoVeiculo.POLICIA))
    terceira = await ponte.injetar(Deteccao(2, TipoVeiculo.POLICIA))

    assert [r.decisao.tipo if r.decisao else None for r in (primeira, segunda, terceira)] == [
        TipoEvento.PREEMP_INI,
        TipoEvento.FILA,
        TipoEvento.DESCARTADO,
    ]


async def test_com_o_fio_do_nodemcu_no_rx_a_injecao_volta_sem_decisao() -> None:
    transporte = transporte_rapido(fio_do_nodemcu_no_rx=True)
    async with _rodando(Ponte(transporte, timeout_decisao_s=0.2)) as ponte:
        resultado = await ponte.injetar(AMB_RUA_3)

        assert resultado.decisao is None
        assert resultado.latencia_ms is None


async def test_injecao_bruta_recebe_recusa(ponte: Ponte) -> None:
    await ponte.injetar_bruta("RUA3,HELICOPTERO")
    await ate(lambda: _eventos(ponte, TipoEvento.RECUSADO) == 1)


async def test_injetar_com_a_porta_fechada_e_recusado() -> None:
    ponte = Ponte(PortaAusente(), espera_reconexao_s=0.01)
    tarefa = asyncio.create_task(ponte.rodar())
    await asyncio.sleep(0.05)

    with pytest.raises(ConexaoPerdidaError):
        await ponte.injetar(AMB_RUA_3)
    with pytest.raises(ConexaoPerdidaError):
        await ponte.injetar_bruta("RUA3,AMBULANCIA")
    assert not ponte.uno_respondendo()
    ponte.parar()
    await asyncio.wait_for(tarefa, 5.0)


# ---------------------------------------------------------------------------
# Reconexão
# ---------------------------------------------------------------------------


async def test_porta_perdida_reconecta_sozinha_e_a_placa_reinicia() -> None:
    transporte = TransporteSimulado(fabrica_de_uno(), passo_s=0.01)
    ponte = Ponte(transporte, espera_reconexao_s=0.05)
    async with _rodando(ponte):
        primeiro_uno = transporte.uno
        transporte.puxar_cabo()

        await ate(lambda: ponte.reconexoes == 1 and ponte.uno_respondendo())
        assert transporte.uno is not primeiro_uno  # abrir de novo reinicia a placa
        assert _eventos(ponte, TipoEvento.BOOT) == 2
        assert (await ponte.injetar(AMB_RUA_3)).decisao is not None


async def test_injecao_pendente_falha_quando_a_porta_cai() -> None:
    transporte = TransporteSimulado(fabrica_de_uno(), passo_s=0.01, latencia_s=0.5)
    ponte = Ponte(transporte, espera_reconexao_s=5.0)
    async with _rodando(ponte):
        envio = asyncio.create_task(ponte.injetar(AMB_RUA_3))
        await asyncio.sleep(0.1)
        transporte.puxar_cabo()

        with pytest.raises(ConexaoPerdidaError):
            await asyncio.wait_for(envio, 2.0)


async def test_porta_ausente_continua_tentando() -> None:
    porta = PortaAusente()
    ponte = Ponte(porta, espera_reconexao_s=0.01)
    tarefa = asyncio.create_task(ponte.rodar())
    await ate(lambda: porta.tentativas >= 3)
    ponte.parar()
    await asyncio.wait_for(tarefa, 5.0)
