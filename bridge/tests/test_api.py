"""HTTP da ponte — `/health`, `/estado`, `/autorizacoes`, `/injecao`."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from bridge.api import criar_app
from bridge.ponte import Ponte
from bridge.protocolo import NENHUMA_AUTORIZACAO
from bridge.tests.conftest import PortaAusente, PortaRoteirizada, ate, transporte_rapido
from bridge.transporte import LinhaRecebida, Transporte


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


async def test_estado_traz_as_amostras_de_h3_com_o_carimbo_do_evento() -> None:
    """O backend liga a amostra ao `PREEMP_INI` pelo carimbo: os dois precisam ser iguais."""
    uno, emissor = PortaRoteirizada(), PortaRoteirizada()
    t = time.perf_counter()
    async with _cliente(uno, transporte_veiculo=emissor) as (cliente, ponte):
        await ate(lambda: ponte.emissor_conectado)
        emissor.entregar(LinhaRecebida(b"Tag B7EF8FA0 lida -> Enviando RUA3\r\n", t))
        uno.entregar(LinhaRecebida(b"EV,142350,PREEMP_INI,3,AMBULANCIA\r\n", t + 0.045))
        await ate(lambda: len(ponte.amostras_h3) == 1)
        corpo = (await cliente.get("/estado")).json()

    (amostra,) = corpo["amostras_h3"]
    assert (amostra["rua"], amostra["uid"], amostra["veiculo"]) == (3, "B7EF8FA0", "AMBULANCIA")
    assert amostra["uno_ms"] == 142350
    assert amostra["latencia_total_ms"] == pytest.approx(45.0, abs=0.002)
    (evento,) = [ev for ev in corpo["eventos"] if ev["tipo"] == "PREEMP_INI"]
    assert amostra["t_atuacao"] == evento["recebido_em"]


async def test_estado_sem_medicao_nao_tem_amostras(cliente: httpx.AsyncClient) -> None:
    assert (await cliente.get("/estado")).json()["amostras_h3"] == []


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


async def test_uno_calado_da_504() -> None:
    """Porta aberta e nenhuma decisão no prazo: o UNO não respondeu à linha."""
    async with _cliente(PortaRoteirizada(), timeout_decisao_s=0.2) as (cliente, ponte):
        await ate(lambda: ponte.conectada)
        resposta = await cliente.post("/injecao", json={"rua": 3, "veiculo": "AMBULANCIA"})

        assert resposta.status_code == 504
        assert resposta.json()["decisao"] is None


async def test_put_autorizacoes_chega_ao_uno_e_aparece_no_estado() -> None:
    transporte = transporte_rapido(autorizacoes=NENHUMA_AUTORIZACAO)
    async with _cliente(transporte) as (cliente, ponte):
        await ate(ponte.uno_respondendo)
        assert (await cliente.get("/estado")).json()["telemetria"]["autorizacoes"] == {
            "AMBULANCIA": 0,
            "BOMBEIRO": 0,
            "POLICIA": 0,
        }
        resposta = await cliente.put(
            "/autorizacoes", json={"autorizacoes": {"AMBULANCIA": 1, "BOMBEIRO": 0}}
        )
        assert resposta.status_code == 202
        assert resposta.json()["linhas"] == ["AUT,AMBULANCIA,1", "AUT,BOMBEIRO,0"]
        await ate(
            lambda: (
                ponte.ultima_telemetria is not None
                and ponte.ultima_telemetria.autorizacoes == (1, 0, 0)
            )
        )
        injecao = await cliente.post("/injecao", json={"rua": 3, "veiculo": "AMBULANCIA"})
        assert injecao.json()["decisao"] == "PREEMP_INI"
        negada = await cliente.post("/injecao", json={"rua": 1, "veiculo": "BOMBEIRO"})
        assert negada.json()["decisao"] == "SEM_OCORRENCIA"


@pytest.mark.parametrize(
    "corpo",
    [
        {"autorizacoes": {"AMBULANCIA": 4}},
        {"autorizacoes": {"AMBULANCIA": -1}},
        {"autorizacoes": {"HELICOPTERO": 1}},
        {"autorizacoes": {}},
    ],
)
async def test_put_autorizacoes_invalido_da_422(cliente: httpx.AsyncClient, corpo: Any) -> None:
    assert (await cliente.put("/autorizacoes", json=corpo)).status_code == 422


async def test_sem_porta_autorizacoes_da_503() -> None:
    porta = PortaAusente()
    async with _cliente(porta, espera_reconexao_s=0.01) as (cliente, _):
        # A ponte precisa ter começado a rodar: `rodar()` limpa o pedido de parada.
        await ate(lambda: porta.tentativas > 0)
        corpo = {"autorizacoes": {"AMBULANCIA": 1}}
        assert (await cliente.put("/autorizacoes", json=corpo)).status_code == 503
