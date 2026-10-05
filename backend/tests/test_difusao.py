"""Throttle de 5 Hz do WebSocket (`context/01` §7) — `app/services/difusao.py`."""

from __future__ import annotations

import asyncio
import json

import pytest

from app.services import difusao
from app.services.difusao import Difusor


def _drenar(fila: asyncio.Queue[str | None]) -> list[dict[str, object]]:
    mensagens = []
    while not fila.empty():
        texto = fila.get_nowait()
        assert texto is not None
        mensagens.append(json.loads(texto))
    return mensagens


async def test_primeira_mensagem_sai_na_hora() -> None:
    """Borda de subida: sem descarga recente, ninguém espera o intervalo."""
    difusor = Difusor(intervalo_s=10.0)
    async with difusor.assinar() as fila:
        difusor.publicar_estado("estado_semaforo", "CRUZ_01", {"fase": 1})
        await asyncio.sleep(0)
        assert _drenar(fila) == [{"tipo": "estado_semaforo", "dados": {"fase": 1}}]


async def test_rajada_vira_um_estado_por_chave_e_nenhum_evento_se_perde() -> None:
    difusor = Difusor(intervalo_s=0.1)
    async with difusor.assinar() as fila:
        difusor.publicar_estado("estado_semaforo", "CRUZ_01", {"fase": 0})
        await asyncio.sleep(0)
        _drenar(fila)

        for fase in range(1, 51):  # uma simulação a 10 passos/s, cinco segundos
            difusor.publicar_estado("estado_semaforo", "CRUZ_01", {"fase": fase})
            difusor.publicar_estado("estado_semaforo", "CRUZ_02", {"fase": -fase})
        difusor.publicar_evento({"texto": "A"})
        difusor.publicar_evento({"texto": "B"})
        await asyncio.sleep(0.02)
        assert fila.empty(), "dentro do intervalo nada sai"

        await asyncio.sleep(0.15)
        mensagens = _drenar(fila)

    assert mensagens == [
        {"tipo": "estado_semaforo", "dados": {"fase": 50}},
        {"tipo": "estado_semaforo", "dados": {"fase": -50}},
        {"tipo": "evento", "dados": {"texto": "A"}},
        {"tipo": "evento", "dados": {"texto": "B"}},
    ]
    assert difusor.descargas == 2


async def test_quem_conecta_depois_recebe_o_ultimo_estado() -> None:
    difusor = Difusor(intervalo_s=0.01)
    async with difusor.assinar():
        difusor.publicar_estado("posicao_ve", "ve_amb_0", {"lat": -23.5})
        difusor.publicar_evento({"texto": "evento antigo não é estado"})
        await asyncio.sleep(0.05)

    async with difusor.assinar() as nova:
        assert _drenar(nova) == [{"tipo": "posicao_ve", "dados": {"lat": -23.5}}]


async def test_cliente_travado_e_desligado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Segurar a fila de quem não lê seria vazar memória (RNF02)."""
    monkeypatch.setattr(difusao, "LIMITE_FILA_CLIENTE", 3)
    difusor = Difusor(intervalo_s=0.0)
    async with difusor.assinar() as fila:
        for i in range(5):
            difusor.publicar_evento({"i": i})
            await asyncio.sleep(0)
        assert difusor.clientes == 0
        textos = [fila.get_nowait() for _ in range(fila.qsize())]
    assert textos[-1] is None
