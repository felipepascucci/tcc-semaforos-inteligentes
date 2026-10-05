"""Laço da ponte contra o dublê do UNO — entrega 5.7, refeita: a ponte só escuta."""

from __future__ import annotations

import asyncio
import csv
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest

from adapters.hardware.simulado import TransporteSimulado
from bridge.latencia import JANELA_S, GravadorCsv
from bridge.ponte import Ponte
from bridge.protocolo import Deteccao, Regime, TipoEvento
from bridge.tests.conftest import (
    PortaAusente,
    PortaRoteirizada,
    ate,
    fabrica_de_uno,
    transporte_rapido,
)
from bridge.transporte import ConexaoPerdidaError, LinhaRecebida
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


# ---------------------------------------------------------------------------
# Carimbo e medição de H3 (context/05 §4.3)
# ---------------------------------------------------------------------------


async def test_carimbo_e_o_do_transporte_e_nao_o_da_leitura() -> None:
    """O instante vem do primeiro byte; a ponte só o converte para o relógio de parede."""
    t_primeiro_byte = time.perf_counter() - 0.5  # chegou meio segundo antes de ser lido
    porta = PortaRoteirizada([LinhaRecebida(b"ST,100,GGRR,C,0,0\r\n", t_primeiro_byte)])
    ponte = Ponte(porta)
    tarefa = asyncio.create_task(ponte.rodar())
    await ate(lambda: ponte.ultima_telemetria is not None)

    assert ponte.t_ultima_telemetria == ponte.relogio.em(t_primeiro_byte)
    ponte.parar()
    await asyncio.wait_for(tarefa, 5.0)


def _tag(rua: int, t: float) -> LinhaRecebida:
    uid = {1: "F39BD606", 2: "1BD2308E", 3: "B7EF8FA0", 4: "97ABAFA0"}[rua]
    return LinhaRecebida(f"Tag {uid} lida -> Enviando RUA{rua}\r\n".encode(), t)


def _ev(texto: str, t: float, em_espera: int = 0) -> LinhaRecebida:
    return LinhaRecebida(f"{texto}\r\n".encode(), t, em_espera)


@asynccontextmanager
async def _medindo(csv: Path) -> AsyncIterator[tuple[Ponte, PortaRoteirizada, PortaRoteirizada]]:
    uno, emissor = PortaRoteirizada(), PortaRoteirizada()
    gravador = GravadorCsv(csv, sessao=datetime.now(UTC), versao_codigo="teste")
    ponte = Ponte(uno, transporte_veiculo=emissor, gravador=gravador)
    tarefa = asyncio.create_task(ponte.rodar())
    try:
        await ate(lambda: ponte.emissor_conectado)
        yield ponte, uno, emissor
    finally:
        ponte.parar()
        await asyncio.wait_for(tarefa, 5.0)


async def test_tag_lida_e_preemp_ini_viram_uma_linha_do_csv(tmp_path: Path) -> None:
    csv_h3 = tmp_path / "latencia_bancada.csv"
    t = time.perf_counter()
    async with _medindo(csv_h3) as (ponte, uno, emissor):
        emissor.entregar(b"\xff\x00lixo de boot a 74880\r\n")
        emissor.entregar(_tag(3, t))
        uno.entregar(_ev("EV,142350,PREEMP_INI,3,AMBULANCIA", t + 0.045, em_espera=1))
        await ate(lambda: len(ponte.amostras_h3) == 1)

    amostra = ponte.amostras_h3[0]
    # O `datetime` guarda microssegundos: cada carimbo arredonda até 0,5 µs, e a
    # diferença pode sair 1 µs fora. Irrelevante para H3, que se mede em ms.
    assert amostra.latencia_total_ms == pytest.approx(45.0, abs=0.002)
    with csv_h3.open(encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    assert len(linhas) == 1
    assert float(linhas[0]["latencia_total_ms"]) == pytest.approx(45.0, abs=0.002)
    assert (linhas[0]["rua"], linhas[0]["uid"], linhas[0]["uno_ms"]) == ("3", "B7EF8FA0", "142350")
    assert linhas[0]["bytes_em_espera_atuacao"] == "1"


async def test_decisao_que_chega_antes_da_linha_do_emissor_tambem_casa(tmp_path: Path) -> None:
    t = time.perf_counter()
    async with _medindo(tmp_path / "h3.csv") as (ponte, uno, emissor):
        uno.entregar(_ev("EV,1,PREEMP_INI,2,AMBULANCIA", t + 0.020))
        await asyncio.sleep(0.05)
        emissor.entregar(_tag(2, t))
        await ate(lambda: len(ponte.amostras_h3) == 1)
    assert ponte.amostras_h3[0].latencia_total_ms == pytest.approx(20.0, abs=0.002)


async def test_deteccao_que_vira_fila_ou_renovado_nao_vai_para_o_csv(tmp_path: Path) -> None:
    csv_h3 = tmp_path / "h3.csv"
    t = time.perf_counter()
    async with _medindo(csv_h3) as (ponte, uno, emissor):
        emissor.entregar(_tag(1, t))
        uno.entregar(_ev("EV,10,FILA,1,AMBULANCIA", t + 0.030))
        emissor.entregar(_tag(4, t + 1.0))
        uno.entregar(_ev("EV,1010,RENOVADO,4,AMBULANCIA", t + 1.030))
        # A saída da fila, depois, não é decisão de detecção nenhuma.
        uno.entregar(_ev("EV,9000,PREEMP_INI,1,AMBULANCIA", t + 9.0))
        await ate(lambda: sum(ponte.deteccoes_sem_amostra.values()) == 2)
        await asyncio.sleep(0.05)

    assert ponte.deteccoes_sem_amostra == {"FILA": 1, "RENOVADO": 1}
    assert ponte.amostras_h3 == []
    assert not csv_h3.exists()


async def test_deteccao_que_nao_chega_ao_uno_expira_sem_amostra(tmp_path: Path) -> None:
    t = time.perf_counter()
    async with _medindo(tmp_path / "h3.csv") as (ponte, uno, emissor):
        emissor.entregar(_tag(3, t))
        await asyncio.sleep(0.05)
        # A telemetria segue chegando; passada a janela, a detecção é encerrada.
        uno.entregar(_ev("ST,4000,GGRR,C,0,0", t + JANELA_S + 0.5))
        await ate(lambda: ponte.deteccoes_sem_amostra == {"SEM_DECISAO": 1})
    assert ponte.amostras_h3 == []


async def test_porta_do_emissor_ausente_nao_atrapalha_a_escuta_do_uno() -> None:
    emissor = PortaAusente()
    ponte = Ponte(transporte_rapido(), transporte_veiculo=emissor, espera_reconexao_s=0.01)
    async with _rodando(ponte):
        await ate(lambda: emissor.tentativas >= 3)
        assert ponte.emissor_conectado is False
        assert (await ponte.injetar(AMB_RUA_3)).decisao is not None


async def test_sem_medicao_nao_ha_casador_nem_gravador(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="emissor"):
        Ponte(PortaRoteirizada(), gravador=GravadorCsv(tmp_path / "x.csv", datetime.now(UTC)))


async def test_fim_a_fim_contra_o_duble_com_o_receptor_no_rx(tmp_path: Path) -> None:
    """O caminho inteiro da operação: emissor imprime, receptor entrega, UNO decide.

    A latência aqui é a constante do dublê, **não dado experimental**; o CSV vai
    para `tmp_path`.
    """
    transporte = transporte_rapido(latencia_s=0.03, fio_do_nodemcu_no_rx=True)
    emissor = PortaRoteirizada()
    csv_h3 = tmp_path / "h3.csv"
    gravador = GravadorCsv(csv_h3, sessao=datetime.now(UTC), versao_codigo="teste")
    ponte = Ponte(transporte, transporte_veiculo=emissor, gravador=gravador)
    async with _rodando(ponte):
        emissor.entregar(_tag(3, time.perf_counter()))
        transporte.simular_receptor(AMB_RUA_3)
        await ate(lambda: len(ponte.amostras_h3) == 1)

    # Folga da resolução de timers do Windows (~15,6 ms).
    assert ponte.amostras_h3[0].latencia_total_ms >= 30 - 20
    assert csv_h3.read_text(encoding="utf-8").count("\n") == 2  # cabeçalho + 1
