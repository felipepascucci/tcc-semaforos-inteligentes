"""`/api/v1/stream` — RF04 e RF06 pelo caminho da simulação (`context/06` §2).

A simulação transmite (`POST /simulacoes/transmissao`, o que o executor faz com
`--transmitir`) e o cliente do WebSocket recebe. Sem banco: a transmissão não
grava nada. O RF04 da bancada está em `test_bancada_integrada.py`.
"""

from __future__ import annotations

import itertools
import time
from typing import Any

from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from app.configuracao import Configuracao
from app.main import criar_app


def _transmissao(t: float, lat: float = -23.55) -> dict[str, Any]:
    return {
        "cenario": "moderado",
        "modo": "PREEMPCAO",
        "seed": 1001,
        "t": t,
        "semaforos": [{"id": "CRUZ_03", "fase": 2, "sinal": "AMARELO", "em_preempcao": True}],
        "veiculos": [
            {
                "id": "ve_amb_0",
                "tipo": "AMBULANCIA",
                "criticidade": 1,
                "lat": lat,
                "lon": -46.62,
                "velocidade": 11.2,
            }
        ],
        "eventos": [{"nivel": "INFO", "texto": "Preempção iniciada em CRUZ_03 (t=10.0 s)"}],
        "latencia_ms": 0.12,
    }


def _ate_o_tipo(ws: WebSocketTestSession, tipo: str) -> dict[str, Any]:
    while True:
        mensagem: dict[str, Any] = ws.receive_json()
        if mensagem["tipo"] == tipo:
            return mensagem


def test_rf04_mudanca_de_estado_chega_ao_cliente_em_menos_de_500_ms() -> None:
    with (
        TestClient(criar_app(Configuracao())) as cliente,
        cliente.websocket_connect("/api/v1/stream") as ws,
    ):
        inicio = time.perf_counter()
        cliente.post("/api/v1/simulacoes/transmissao", json=_transmissao(10.0))
        mensagem = _ate_o_tipo(ws, "estado_semaforo")
        decorrido = time.perf_counter() - inicio

    assert decorrido < 0.5
    assert mensagem["dados"]["id"] == "CRUZ_03"
    assert (mensagem["dados"]["estado"], mensagem["dados"]["em_preempcao"]) == ("AMARELO", True)


def test_mensagens_seguem_o_contrato_de_context_01() -> None:
    with (
        TestClient(criar_app(Configuracao())) as cliente,
        cliente.websocket_connect("/api/v1/stream") as ws,
    ):
        cliente.post("/api/v1/simulacoes/transmissao", json=_transmissao(10.0))
        tipos = {}
        while len(tipos) < 4:
            mensagem = ws.receive_json()
            tipos[mensagem["tipo"]] = mensagem["dados"]

    assert set(tipos) == {"estado_semaforo", "posicao_ve", "evento", "metrica"}
    posicao = tipos["posicao_ve"]
    assert (posicao["id_veiculo"], posicao["lat"], posicao["velocidade"]) == (
        "ve_amb_0",
        -23.55,
        11.2,
    )
    assert tipos["evento"]["texto"].startswith("Preempção iniciada")
    assert tipos["metrica"]["priorizacoes_ativas"] == 1


def test_rf06_posicao_do_ve_e_publicada_a_pelo_menos_1_hz() -> None:
    """O executor transmite a 5 Hz; o cliente precisa ver a posição a cada ≤ 1 s."""
    instantes = []
    with (
        TestClient(criar_app(Configuracao())) as cliente,
        cliente.websocket_connect("/api/v1/stream") as ws,
    ):
        for passo in range(10):  # 2 s de simulação transmitida a 5 Hz
            cliente.post(
                "/api/v1/simulacoes/transmissao",
                json=_transmissao(10.0 + passo * 0.2, lat=-23.55 + passo * 1e-5),
            )
            _ate_o_tipo(ws, "posicao_ve")
            instantes.append(time.perf_counter())
            time.sleep(0.2)

    intervalos = [b - a for a, b in itertools.pairwise(instantes)]
    assert len(intervalos) == 9
    assert max(intervalos) <= 1.0
