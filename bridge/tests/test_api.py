"""HTTP da ponte — `/health`, `/estado`, `/comandos`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from bridge.api import criar_app
from bridge.ponte import Ponte
from bridge.tests.conftest import PortaAusente, PortaRoteirizada, ate, transporte_rapido
from bridge.transporte import Transporte


@asynccontextmanager
async def _cliente(
    transporte: Transporte, **opcoes: float
) -> AsyncIterator[tuple[httpx.AsyncClient, Ponte]]:
    ponte = Ponte(transporte, periodo_ping_s=0.1, **opcoes)
    app: FastAPI = criar_app(ponte, "simulada")
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://ponte"
        ) as cliente,
    ):
        yield cliente, ponte


@pytest.fixture
async def cliente() -> AsyncIterator[httpx.AsyncClient]:
    async with _cliente(transporte_rapido()) as (http, ponte):
        await ate(ponte.uno_respondendo)
        yield http


def _pre(**extra: object) -> dict[str, object]:
    return {
        "tipo": "IR_PARA_FASE",
        "id_semaforo": "PROTO_CRUZ_01",
        "fase_alvo": 3,
        "duracao_s": 20.0,
        "id_veiculo": "VE_1",
        "motivo": "teste",
        **extra,
    }


async def test_health_com_o_uno_respondendo(cliente: httpx.AsyncClient) -> None:
    resposta = await cliente.get("/health")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["estado"] == "ok"
    assert corpo["porta"] == "simulada"
    assert corpo["conectada"] is True
    assert corpo["telemetrias_com_dois_verdes"] == 0


async def test_preempcao_devolve_t_atuacao_e_correlacao(cliente: httpx.AsyncClient) -> None:
    correlacao = str(uuid4())
    resposta = await cliente.post("/comandos", json=_pre(id_correlacao=correlacao))

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["linha"] == "PRE,3,20"
    assert corpo["aceito"] is True
    assert corpo["resposta"] == "ACK,PRE"
    assert corpo["t_atuacao"] is not None
    assert corpo["latencia_serial_ms"] > 0
    assert corpo["id_correlacao"] == correlacao


async def test_estado_mostra_telemetria_e_eventos(cliente: httpx.AsyncClient) -> None:
    await cliente.post("/comandos", json=_pre())
    corpo = (await cliente.get("/estado")).json()

    assert len(corpo["telemetria"]["cores"]) == 4
    assert "PREEMP_INI" in [ev["tipo"] for ev in corpo["eventos"]]


async def test_recusa_do_uno_vem_com_o_motivo(cliente: httpx.AsyncClient) -> None:
    pedido = {"tipo": "LIBERAR", "id_semaforo": "PROTO_CRUZ_01", "motivo": "teste"}
    corpo = (await cliente.post("/comandos", json=pedido)).json()

    assert corpo["aceito"] is False
    assert corpo["motivo_recusa"] == "MODO"
    assert corpo["t_atuacao"] is None


async def test_compensacao_nao_e_enviada(cliente: httpx.AsyncClient) -> None:
    pedido = _pre(tipo="ESTENDER_VERDE", fase_alvo=2, duracao_s=2.0, id_veiculo=None)
    resposta = await cliente.post("/comandos", json=pedido)

    assert resposta.status_code == 200
    assert resposta.json()["linha"] is None


@pytest.mark.parametrize(
    "pedido",
    [_pre(fase_alvo=None), _pre(motivo=""), _pre(tipo="DECOLAR")],
    ids=["sem_fase", "sem_motivo", "tipo_desconhecido"],
)
async def test_pedido_invalido_e_422(cliente: httpx.AsyncClient, pedido: dict[str, object]) -> None:
    assert (await cliente.post("/comandos", json=pedido)).status_code == 422


async def test_sem_porta_health_e_comandos_dao_503() -> None:
    async with _cliente(PortaAusente(), espera_reconexao_s=0.01) as (cliente, _):
        health = await cliente.get("/health")
        assert health.status_code == 503
        assert health.json()["conectada"] is False

        assert (await cliente.post("/comandos", json=_pre())).status_code == 503


async def test_uno_mudo_da_504() -> None:
    async with _cliente(PortaRoteirizada(), timeout_resposta_s=0.1) as (cliente, ponte):
        await ate(lambda: ponte.conectada)
        resposta = await cliente.post("/comandos", json=_pre())

        assert resposta.status_code == 504
        assert resposta.json()["resposta"] is None
