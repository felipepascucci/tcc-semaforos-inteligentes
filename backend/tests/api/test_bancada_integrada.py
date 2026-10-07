"""Bancada → backend de ponta a ponta, com o dublê do UNO no lugar da placa.

A ponte de verdade (`bridge/`) roda sobre `TransporteSimulado`, e o backend a lê
como leria na bancada: `GET /estado`, pelo mesmo leitor do `lifespan`. O que se
prova:

* **RF05** — toda decisão do UNO vira linha em `log_prioridade` (uma por evento
  de decisão), no `PROTO_CRUZ_01`, com a aproximação no `motivo`;
* um backend que reinicia não regrava o histórico da ponte;
* **RF04 na bancada** — da chegada da `ST` à ponte até o WebSocket, menos de
  500 ms, no ritmo real de leitura (5 Hz) e de difusão (5 Hz).

Nenhum número daqui é dado experimental: é o dublê (`context/05` §8).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import LogPrioridade, Semaforo, StatusExecucao, TipoVeiculo, VeiculoEmergencia
from app.repositories.ocorrencia import abrir_ocorrencia, encerrar_ocorrencia
from app.services.bancada import CentralBancada, GravadorBancada, LeitorPonte
from app.services.difusao import Difusor
from bridge.api import criar_app as criar_app_da_ponte
from bridge.ponte import Ponte
from bridge.protocolo import EVENTOS_DE_DECISAO, NENHUMA_AUTORIZACAO, Autorizacoes
from bridge.tests.conftest import TODOS, ate, transporte_rapido
from core.modelos import Criticidade

pytestmark = pytest.mark.banco


@asynccontextmanager
async def _ponte(
    autorizacoes: Autorizacoes = TODOS,
) -> AsyncIterator[tuple[Ponte, httpx.AsyncClient]]:
    """A ponte com o dublê, servida em memória (sem porta TCP)."""
    ponte = Ponte(transporte_rapido(autorizacoes=autorizacoes))
    app = criar_app_da_ponte(ponte, "simulada")
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://ponte") as http,
    ):
        await ate(ponte.uno_respondendo)
        yield ponte, http


def _logs(sessao: Session) -> list[LogPrioridade]:
    sessao.rollback()
    return list(sessao.scalars(select(LogPrioridade).order_by(LogPrioridade.id_log)))


async def test_cada_decisao_do_uno_vira_uma_linha_de_log(
    semeado: Session, fabrica_sessao: sessionmaker[Session]
) -> None:
    """RF05: ambulância atendida, bombeiro na fila, polícia descartada — três linhas."""
    async with _ponte() as (ponte, http):
        leitor = LeitorPonte(http, Difusor(), GravadorBancada(fabrica_sessao), intervalo_s=0.05)
        tarefa = asyncio.create_task(leitor.rodar())
        try:
            for rua, veiculo in ((3, "AMBULANCIA"), (1, "BOMBEIRO"), (2, "POLICIA")):
                resposta = await http.post("/injecao", json={"rua": rua, "veiculo": veiculo})
                assert resposta.status_code == 200
            await ate(lambda: len(_logs(semeado)) == 3, limite_s=5.0)
            decisoes = [ev for _, ev in ponte.eventos if ev.tipo in EVENTOS_DE_DECISAO]
        finally:
            leitor.parar()
            await tarefa

    logs = _logs(semeado)
    assert len(logs) == len(decisoes)
    proto = semeado.scalars(select(Semaforo).filter_by(codigo_externo="PROTO_CRUZ_01")).one()
    assert {log.fk_semaforo for log in logs} == {proto.id_semaforo}
    assert [log.status_execucao for log in logs] == [
        StatusExecucao.SUCESSO,
        StatusExecucao.CONFLITO_ADIADO,
        StatusExecucao.FALHA,
    ]
    assert "S3 (RUA3)" in (logs[0].motivo or "")
    assert all(log.fase_aplicada is None and log.fk_execucao is None for log in logs)
    assert len({log.id_correlacao for log in logs}) == 3


async def test_a_central_decide_quem_preempta_na_bancada(
    semeado: Session, fabrica_sessao: sessionmaker[Session]
) -> None:
    """Abrir a ocorrência libera a ambulância no UNO; encerrar volta a negar.

    Decisão de 2026-10-06: o UNO liga negando todos, e o backend manda a lista.
    """
    ambulancia = semeado.scalars(
        select(VeiculoEmergencia).filter_by(tipo=TipoVeiculo.AMBULANCIA)
    ).first()
    assert ambulancia is not None

    def autorizacoes(ponte: Ponte) -> tuple[int, int, int] | None:
        st = ponte.ultima_telemetria
        return None if st is None else st.autorizacoes

    async with _ponte(NENHUMA_AUTORIZACAO) as (ponte, http):
        leitor = LeitorPonte(
            http, Difusor(), intervalo_s=0.05, central=CentralBancada(fabrica_sessao)
        )
        tarefa = asyncio.create_task(leitor.rodar())
        try:
            negada = await http.post("/injecao", json={"rua": 3, "veiculo": "AMBULANCIA"})
            assert negada.json()["decisao"] == "SEM_OCORRENCIA"

            with fabrica_sessao() as sessao, sessao.begin():
                ocorrencia = abrir_ocorrencia(
                    sessao, fk_veiculo=ambulancia.id_veiculo, criticidade=Criticidade.RISCO_COLETIVO
                )
                id_ocorrencia = ocorrencia.id_ocorrencia
            await ate(lambda: autorizacoes(ponte) == (2, 0, 0), limite_s=5.0)
            aceita = await http.post("/injecao", json={"rua": 3, "veiculo": "AMBULANCIA"})
            assert aceita.json()["decisao"] == "PREEMP_INI"

            with fabrica_sessao() as sessao, sessao.begin():
                encerrar_ocorrencia(sessao, id_ocorrencia)
            await ate(lambda: autorizacoes(ponte) == (0, 0, 0), limite_s=5.0)
        finally:
            leitor.parar()
            await tarefa


async def test_backend_que_reinicia_nao_regrava_o_historico(
    semeado: Session, fabrica_sessao: sessionmaker[Session]
) -> None:
    async with _ponte() as (_, http):
        await http.post("/injecao", json={"rua": 3, "veiculo": "AMBULANCIA"})
        primeiro = LeitorPonte(http, Difusor(), GravadorBancada(fabrica_sessao))
        await primeiro.ler_uma_vez()
        assert len(_logs(semeado)) == 1

        # Um backend novo: tradutor e gravador zerados, a ponte com o mesmo histórico.
        segundo = LeitorPonte(http, Difusor(), GravadorBancada(fabrica_sessao))
        await segundo.ler_uma_vez()
        await http.post("/injecao", json={"rua": 1, "veiculo": "BOMBEIRO"})
        await segundo.ler_uma_vez()

    logs = _logs(semeado)
    assert [log.status_execucao for log in logs] == [
        StatusExecucao.SUCESSO,
        StatusExecucao.CONFLITO_ADIADO,
    ]


async def test_rf04_mudanca_de_estado_chega_ao_websocket_em_menos_de_500_ms(
    semeado: Session, fabrica_sessao: sessionmaker[Session]
) -> None:
    """Da `ST` na ponte ao cliente, a cada mudança de luz, no ritmo de produção.

    Leitura a 5 Hz e difusão a 5 Hz, os valores de `Configuracao`. A ambulância
    na Rua 3 leva o cruzamento por amarelo, all-red e verde exclusivo: pelo
    menos três mudanças em ~6 s.
    """
    difusor = Difusor(intervalo_s=0.2)
    async with _ponte() as (_, http), difusor.assinar() as fila:
        leitor = LeitorPonte(http, difusor, GravadorBancada(fabrica_sessao), intervalo_s=0.2)
        tarefa = asyncio.create_task(leitor.rodar())
        try:
            await http.post("/injecao", json={"rua": 3, "veiculo": "AMBULANCIA"})
            atrasos: list[float] = []
            anterior = None
            while len(atrasos) < 3:
                texto = await asyncio.wait_for(fila.get(), 10.0)
                assert texto is not None
                mensagem = json.loads(texto)
                if mensagem["tipo"] != "estado_semaforo":
                    continue
                chegada = datetime.now(UTC)
                dados = mensagem["dados"]
                if anterior is not None and dados["aproximacoes"] != anterior:
                    recebida = datetime.fromisoformat(dados["recebido_em"])
                    atrasos.append((chegada - recebida).total_seconds())
                anterior = dados["aproximacoes"]
        finally:
            leitor.parar()
            await tarefa

    assert max(atrasos) < 0.5, atrasos
