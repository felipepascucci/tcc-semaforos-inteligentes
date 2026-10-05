"""HTTP da ponte — `/health`, `/estado`, `/injecao`."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from bridge.api import criar_app
from bridge.ponte import Ponte
from bridge.tests.conftest import PortaAusente, PortaRoteirizada, ate, transporte_rapido
from bridge.transporte import Transporte


@asynccontextmanager
async def _cliente(
    transporte: Transporte, **opcoes: Any
) -> AsyncIterator[tuple[httpx.AsyncClient, Ponte]]:
    ponte = Ponte(transporte, **opcoes)
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


async def test_health_com_o_uno_respondendo(cliente: httpx.AsyncClient) -> None:
    resposta = await cliente.get("/health")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["estado"] == "ok"
    assert corpo["porta"] == "simulada"
    assert corpo["conectada"] is True
    assert corpo["telemetrias_violando_i1"] == 0
    # Fora da medição de H3, os campos dela vêm nulos — não zero.
    assert corpo["emissor_conectado"] is None
    assert corpo["amostras_h3"] is None


async def test_health_na_medicao_de_h3_mostra_o_emissor() -> None:
    emissor = PortaRoteirizada()
    async with _cliente(transporte_rapido(), transporte_veiculo=emissor) as (cliente, ponte):
        await ate(lambda: ponte.uno_respondendo() and ponte.emissor_conectado)
        corpo = (await cliente.get("/health")).json()

    assert corpo["emissor_conectado"] is True
    assert corpo["amostras_h3"] == 0
    assert corpo["deteccoes_sem_amostra"] == {}


async def test_injecao_devolve_a_decisao(cliente: httpx.AsyncClient) -> None:
    resposta = await cliente.post("/injecao", json={"rua": 3, "veiculo": "AMBULANCIA"})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["linha"] == "RUA3,AMBULANCIA"
    assert corpo["decisao"] == "PREEMP_INI"
    assert isinstance(corpo["decisao_t_dispositivo_ms"], int)
    assert corpo["t_decisao"] is not None
    assert corpo["latencia_ms"] > 0


async def test_estado_mostra_telemetrias_e_eventos(cliente: httpx.AsyncClient) -> None:
    await cliente.post("/injecao", json={"rua": 3, "veiculo": "AMBULANCIA"})
    corpo = (await cliente.get("/estado")).json()

    assert corpo["telemetria"] == corpo["telemetrias"][-1]
    assert len(corpo["telemetria"]["cores"]) == 4
    eventos = [(ev["tipo"], ev["rua"], ev["veiculo"]) for ev in corpo["eventos"]]
    assert ("BOOT", None, None) in eventos
    assert ("PREEMP_INI", 3, "AMBULANCIA") in eventos


@pytest.mark.parametrize(
    "pedido",
    [{"rua": 0, "veiculo": "AMBULANCIA"}, {"rua": 3, "veiculo": "HELICOPTERO"}, {"rua": 3}],
    ids=["rua_zero", "tipo_desconhecido", "sem_veiculo"],
)
async def test_pedido_invalido_e_422(cliente: httpx.AsyncClient, pedido: dict[str, object]) -> None:
    assert (await cliente.post("/injecao", json=pedido)).status_code == 422


async def test_injecao_bruta_aparece_como_recusa_no_estado(cliente: httpx.AsyncClient) -> None:
    resposta = await cliente.post("/injecao/bruta", json={"linha": "RUA3,HELICOPTERO"})
    assert resposta.status_code == 202

    async def recusado() -> bool:
        corpo = (await cliente.get("/estado")).json()
        return "RECUSADO" in [ev["tipo"] for ev in corpo["eventos"]]

    for _ in range(100):
        if await recusado():
            break
        await asyncio.sleep(0.01)
    assert await recusado()


async def test_injecao_bruta_so_aceita_ascii_imprimivel(cliente: httpx.AsyncClient) -> None:
    resposta = await cliente.post("/injecao/bruta", json={"linha": "RUA3\nAMBULANCIA"})
    assert resposta.status_code == 422


async def test_sem_porta_health_e_injecao_dao_503() -> None:
    async with _cliente(PortaAusente(), espera_reconexao_s=0.01) as (cliente, _):
        health = await cliente.get("/health")
        assert health.status_code == 503
        assert health.json()["conectada"] is False

        pedido = {"rua": 3, "veiculo": "AMBULANCIA"}
        assert (await cliente.post("/injecao", json=pedido)).status_code == 503


async def test_fio_do_nodemcu_no_rx_da_504() -> None:
    transporte = transporte_rapido(fio_do_nodemcu_no_rx=True)
    async with _cliente(transporte, timeout_decisao_s=0.2) as (cliente, ponte):
        await ate(ponte.uno_respondendo)
        resposta = await cliente.post("/injecao", json={"rua": 3, "veiculo": "AMBULANCIA"})

        assert resposta.status_code == 504
        assert resposta.json()["decisao"] is None
