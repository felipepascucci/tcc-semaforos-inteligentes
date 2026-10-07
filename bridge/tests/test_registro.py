"""Registro da telemetria do UNO — `bridge/registro.py`, o dado do checklist."""

from __future__ import annotations

import asyncio
import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path

from bridge.ponte import Ponte
from bridge.protocolo import Autorizacao
from bridge.registro import COLUNAS_TELEMETRIA, Direcao, GravadorTelemetria, texto_da_linha
from bridge.tests.conftest import PortaRoteirizada, ate
from bridge.transporte import LinhaRecebida
from core.modelos import TipoVeiculo

T0 = datetime(2026, 10, 7, 18, 0, tzinfo=UTC)


def _linhas(caminho: Path) -> list[dict[str, str]]:
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


def test_texto_da_linha_tira_o_terminador_e_escreve_o_lixo() -> None:
    assert texto_da_linha(b"ST,100,GGRR,C,0,0,000\r\n") == "ST,100,GGRR,C,0,0,000"
    assert texto_da_linha(b"\xff\x00x\n") == "\\xff\\x00x"


def test_gravador_acumula_sessoes_com_um_cabecalho(tmp_path: Path) -> None:
    caminho = tmp_path / "telemetria.csv"
    GravadorTelemetria(caminho, sessao=T0, versao_codigo="abc1234").gravar(
        T0, Direcao.UNO, b"EV,0,BOOT\r\n", bytes_em_espera=3
    )
    outra = T0 + timedelta(minutes=40)
    GravadorTelemetria(caminho, sessao=outra, versao_codigo="abc1234").gravar(
        outra, Direcao.PONTE, b"AUT,AMBULANCIA,1\n"
    )

    assert caminho.read_text(encoding="utf-8").splitlines()[0] == ",".join(COLUNAS_TELEMETRIA)
    linhas = _linhas(caminho)
    assert [(r["sessao"], r["direcao"], r["linha"], r["bytes_em_espera"]) for r in linhas] == [
        (T0.isoformat(), "UNO", "EV,0,BOOT", "3"),
        (outra.isoformat(), "PONTE", "AUT,AMBULANCIA,1", "0"),
    ]


async def test_a_ponte_registra_o_que_le_e_o_que_escreve(tmp_path: Path) -> None:
    caminho = tmp_path / "telemetria.csv"
    t_primeiro_byte = 1000.0
    porta = PortaRoteirizada(
        [
            b"\xff\x00lixo de boot\n",
            LinhaRecebida(b"ST,100,GGRR,C,0,0,000\r\n", t_primeiro_byte, bytes_em_espera=2),
        ]
    )
    ponte = Ponte(porta, registro=GravadorTelemetria(caminho, sessao=T0, versao_codigo="teste"))
    tarefa = asyncio.create_task(ponte.rodar())
    try:
        await ate(lambda: ponte.ultima_telemetria is not None)
        await ponte.autorizar([Autorizacao(TipoVeiculo.AMBULANCIA, 1)])
    finally:
        ponte.parar()
        await asyncio.wait_for(tarefa, 5.0)

    linhas = _linhas(caminho)
    assert [(r["direcao"], r["linha"]) for r in linhas] == [
        ("UNO", "\\xff\\x00lixo de boot"),
        ("UNO", "ST,100,GGRR,C,0,0,000"),
        ("PONTE", "AUT,AMBULANCIA,1"),
    ]
    # O carimbo é o mesmo que a ponte dá à telemetria, e que o backend grava.
    assert linhas[1]["t"] == ponte.relogio.em(t_primeiro_byte).isoformat()
    assert linhas[1]["bytes_em_espera"] == "2"


async def test_arquivo_inacessivel_nao_derruba_a_escuta(tmp_path: Path) -> None:
    # Um diretório no lugar do arquivo: abrir para acrescentar falha.
    caminho = tmp_path / "telemetria.csv"
    caminho.mkdir()
    porta = PortaRoteirizada([b"ST,100,GGRR,C,0,0,000\n", b"ST,600,YYRR,C,0,0,000\n"])
    ponte = Ponte(porta, registro=GravadorTelemetria(caminho, sessao=T0, versao_codigo="teste"))
    tarefa = asyncio.create_task(ponte.rodar())
    await ate(lambda: len(ponte.telemetrias) == 2)
    ponte.parar()
    await asyncio.wait_for(tarefa, 5.0)
