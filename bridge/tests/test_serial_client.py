"""Cliente pyserial, testado contra a porta de loopback `loop://` — sem Arduino."""

from __future__ import annotations

import asyncio

import pytest

from bridge.serial_client import TransporteSerial
from bridge.transporte import ConexaoPerdidaError


@pytest.fixture
async def loopback() -> TransporteSerial:
    porta = TransporteSerial("loop://")
    await porta.abrir()
    yield porta  # type: ignore[misc]
    await porta.fechar()


async def test_le_o_que_foi_escrito(loopback: TransporteSerial) -> None:
    await loopback.escrever(b"EV,0,BOOT\n")
    assert await asyncio.wait_for(loopback.ler_linha(), 2.0) == b"EV,0,BOOT\n"


async def test_junta_linha_que_chega_em_pedacos(loopback: TransporteSerial) -> None:
    await loopback.escrever(b"ST,1000,")
    leitura = asyncio.create_task(loopback.ler_linha())
    await asyncio.sleep(0.25)  # mais de um timeout de leitura com a linha pela metade
    assert not leitura.done()

    await loopback.escrever(b"GGRR,C,0,0\n")
    assert await asyncio.wait_for(leitura, 2.0) == b"ST,1000,GGRR,C,0,0\n"


async def test_separa_duas_linhas_de_uma_escrita(loopback: TransporteSerial) -> None:
    await loopback.escrever(b"EV,10,PREEMP_INI,3,AMBULANCIA\nST,10,GGRR,E,3,0\n")
    assert await asyncio.wait_for(loopback.ler_linha(), 2.0) == b"EV,10,PREEMP_INI,3,AMBULANCIA\n"
    assert await asyncio.wait_for(loopback.ler_linha(), 2.0) == b"ST,10,GGRR,E,3,0\n"


async def test_porta_inexistente_vira_conexao_perdida() -> None:
    with pytest.raises(ConexaoPerdidaError):
        await TransporteSerial("COM_QUE_NAO_EXISTE").abrir()


async def test_escrever_e_ler_com_a_porta_fechada_vira_conexao_perdida() -> None:
    porta = TransporteSerial("loop://")
    with pytest.raises(ConexaoPerdidaError):
        await porta.escrever(b"RUA3,AMBULANCIA\n")
    with pytest.raises(ConexaoPerdidaError):
        await porta.ler_linha()


async def test_fechar_no_meio_da_leitura_vira_conexao_perdida() -> None:
    """É o que acontece quando o cabo é puxado com a ponte esperando linha."""
    porta = TransporteSerial("loop://")
    await porta.abrir()
    leitura = asyncio.create_task(porta.ler_linha())
    await asyncio.sleep(0.05)
    await porta.fechar()

    with pytest.raises(ConexaoPerdidaError):
        await asyncio.wait_for(leitura, 2.0)
