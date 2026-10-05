"""`ws://host/api/v1/stream` — o servidor empurra, com throttle de 5 Hz (`context/01` §7).

Mensagens `{"tipo": ..., "dados": {...}}`: `estado_semaforo`, `posicao_ve`,
`evento` e `metrica`. Quem conecta recebe primeiro o último estado conhecido de
cada semáforo e VE. O que o cliente manda é ignorado; a leitura só serve para
perceber que ele desconectou.
"""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.dependencias import Recursos

router = APIRouter(tags=["websocket"])


async def _enviar(websocket: WebSocket, fila: asyncio.Queue[str | None]) -> None:
    while (texto := await fila.get()) is not None:
        await websocket.send_text(texto)
    await websocket.close(code=1013)  # cliente lento demais: tente de novo


@router.websocket("/stream")
async def stream(websocket: WebSocket) -> None:
    recursos: Recursos = websocket.app.state.recursos
    await websocket.accept()
    async with recursos.difusor.assinar() as fila:
        envio = asyncio.create_task(_enviar(websocket, fila))
        try:
            while not envio.done():
                recebido = asyncio.create_task(websocket.receive_text())
                await asyncio.wait({recebido, envio}, return_when=asyncio.FIRST_COMPLETED)
                if not recebido.done():
                    recebido.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await recebido
                elif recebido.exception() is not None:
                    break
        except WebSocketDisconnect:
            pass
        finally:
            envio.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await envio
