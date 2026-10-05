"""Laço da ponte contra o dublê do UNO — entrega 5.7."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from adapters.hardware.simulado import TransporteSimulado
from bridge.ponte import Ponte
from bridge.protocolo import Ack, MotivoNak, Nak, NomeComando, TipoEvento, preempcao
from bridge.tests.conftest import (
    PortaAusente,
    PortaRoteirizada,
    ate,
    fabrica_de_uno,
    transporte_rapido,
)
from bridge.transporte import ConexaoPerdidaError
from core.comandos import Comando, TipoComando

CRUZ = "PROTO_CRUZ_01"
PRE_3 = Comando(
    TipoComando.IR_PARA_FASE, CRUZ, fase_alvo=3, duracao_s=20.0, id_veiculo="VE_1", motivo="t"
)


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
    async with _rodando(Ponte(transporte_rapido(), periodo_ping_s=0.1)) as rodando:
        yield rodando


def _eventos(ponte: Ponte, tipo: TipoEvento) -> int:
    return sum(1 for _, ev in ponte.eventos if ev.tipo is tipo)


# ---------------------------------------------------------------------------
# Envio e t_atuacao
# ---------------------------------------------------------------------------


async def test_preempcao_aceita_traz_t_atuacao_na_chegada_do_ack() -> None:
    latencia_s = 0.05
    ponte = Ponte(transporte_rapido(latencia_s=latencia_s), periodo_ping_s=0.1)
    async with _rodando(ponte):
        resultado = await ponte.enviar(PRE_3, id_correlacao="c0ffee")

        assert resultado.linha == "PRE,3,20"
        assert resultado.resposta == Ack(NomeComando.PRE)
        assert resultado.t_atuacao == resultado.t_resposta
        assert resultado.t_envio is not None
        assert resultado.t_atuacao is not None
        assert resultado.t_atuacao > resultado.t_envio
        # Folga da resolução de timers do Windows (~15,6 ms).
        assert resultado.latencia_serial_ms is not None
        assert resultado.latencia_serial_ms >= latencia_s * 1000 - 20
        assert resultado.id_correlacao == "c0ffee"
        await ate(lambda: _eventos(ponte, TipoEvento.PREEMP_INI) == 1)


async def test_nak_nao_tem_t_atuacao(ponte: Ponte) -> None:
    liberar = Comando(TipoComando.LIBERAR, CRUZ, motivo="t")
    resultado = await ponte.enviar(liberar)

    assert resultado.resposta == Nak(NomeComando.CLR, MotivoNak.MODO)
    assert not resultado.aceito
    assert resultado.t_atuacao is None


async def test_compensacao_sem_ve_nao_sai_pela_serial(ponte: Ponte) -> None:
    compensa = Comando(TipoComando.ESTENDER_VERDE, CRUZ, fase_alvo=2, duracao_s=2.0, motivo="E7")
    resultado = await ponte.enviar(compensa)

    assert resultado.linha is None
    assert resultado.t_envio is None


async def test_consulta_e_respondida_pela_telemetria(ponte: Ponte) -> None:
    from bridge.protocolo import Telemetria, consultar

    resultado = await ponte.enviar_serial(consultar())
    assert isinstance(resultado.resposta, Telemetria)


async def test_sem_resposta_no_prazo() -> None:
    porta = PortaRoteirizada()
    ponte = Ponte(porta, timeout_resposta_s=0.1)
    tarefa = asyncio.create_task(ponte.rodar())
    await ate(lambda: ponte.conectada)

    resultado = await ponte.enviar_serial(preempcao(3, 20))

    assert resultado.resposta is None
    assert resultado.t_envio is not None
    assert b"PRE,3,20\n" in porta.escritas
    ponte.parar()
    await asyncio.wait_for(tarefa, 5.0)


# ---------------------------------------------------------------------------
# PING e watchdog
# ---------------------------------------------------------------------------


async def test_ping_periodico_segura_o_watchdog_do_uno(ponte: Ponte) -> None:
    await ponte.enviar(PRE_3)
    await asyncio.sleep(1.0)  # > 3 watchdogs de 0,3 s
    assert _eventos(ponte, TipoEvento.WATCHDOG) == 0


async def test_sem_ping_o_watchdog_do_uno_dispara() -> None:
    """Contraprova: o teste acima só vale se, sem PING, o watchdog dispara."""
    ponte = Ponte(transporte_rapido(), periodo_ping_s=60.0)
    async with _rodando(ponte):
        await ponte.enviar(PRE_3)
        await ate(lambda: _eventos(ponte, TipoEvento.WATCHDOG) == 1, limite_s=1.0)


# ---------------------------------------------------------------------------
# Reconexão
# ---------------------------------------------------------------------------


async def test_cabo_puxado_reconecta_sozinha() -> None:
    transporte = TransporteSimulado(fabrica_de_uno(), passo_s=0.01)
    ponte = Ponte(transporte, periodo_ping_s=0.1, espera_reconexao_s=0.05)
    async with _rodando(ponte):
        primeiro_uno = transporte.uno
        transporte.puxar_cabo()

        await ate(lambda: ponte.reconexoes == 1 and ponte.uno_respondendo())
        assert transporte.uno is not primeiro_uno  # abrir de novo reinicia a placa
        assert (await ponte.enviar(PRE_3)).aceito


async def test_comando_pendente_falha_quando_o_cabo_cai() -> None:
    transporte = TransporteSimulado(fabrica_de_uno(), passo_s=0.01, latencia_s=0.5)
    ponte = Ponte(transporte, periodo_ping_s=0.1, espera_reconexao_s=5.0)
    async with _rodando(ponte):
        envio = asyncio.create_task(ponte.enviar(PRE_3))
        await asyncio.sleep(0.1)
        transporte.puxar_cabo()

        with pytest.raises(ConexaoPerdidaError):
            await asyncio.wait_for(envio, 2.0)


async def test_enviar_com_a_porta_fechada_e_recusado() -> None:
    ponte = Ponte(PortaAusente(), espera_reconexao_s=0.01)
    tarefa = asyncio.create_task(ponte.rodar())
    await asyncio.sleep(0.05)

    with pytest.raises(ConexaoPerdidaError):
        await ponte.enviar(PRE_3)
    assert not ponte.uno_respondendo()
    ponte.parar()
    await asyncio.wait_for(tarefa, 5.0)


async def test_porta_ausente_continua_tentando() -> None:
    porta = PortaAusente()
    ponte = Ponte(porta, espera_reconexao_s=0.01)
    tarefa = asyncio.create_task(ponte.rodar())
    await ate(lambda: porta.tentativas >= 3)
    ponte.parar()
    await asyncio.wait_for(tarefa, 5.0)


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------


async def test_ruido_e_contado_e_dois_verdes_sao_denunciados() -> None:
    porta = PortaRoteirizada(
        [b"\xff\x00lixo de boot\n", b"ST,100,1,GRRR,0,0\n", b"ST,600,1,GRGR,0,0\n"]
    )
    ponte = Ponte(porta)
    tarefa = asyncio.create_task(ponte.rodar())
    await ate(lambda: ponte.telemetrias_com_dois_verdes == 1)

    assert ponte.linhas_invalidas == 1
    assert ponte.ultima_telemetria is not None
    assert ponte.ultima_telemetria.t_dispositivo_ms == 600
    ponte.parar()
    await asyncio.wait_for(tarefa, 5.0)
