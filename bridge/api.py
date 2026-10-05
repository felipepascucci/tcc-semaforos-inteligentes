"""HTTP da ponte — `/health`, `/estado` e `/comandos` (`context/05` §6).

A ponte é um processo separado do backend (`context/02` §3: precisa da porta
USB, e o backend roda no compose). É por aqui que o backend lhe entrega o que o
motor decidiu e recebe de volta o `t_atuacao`.

O sentido é **backend → ponte**: o backend chama `POST /comandos` e lê a
telemetria em `GET /estado`. A alternativa, a ponte empurrar telemetria para o
backend, fica para o Bloco 6, que é quando o backend passa a ter onde recebê-la.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException, Response, status
from pydantic import BaseModel, Field

from bridge.ponte import Ponte, ResultadoEnvio
from bridge.protocolo import (
    ComandoInvalidoError,
    MotivoNak,
    Nak,
    Telemetria,
    TipoEvento,
)
from bridge.transporte import ConexaoPerdidaError
from core.comandos import Comando, TipoComando

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PedidoComando(BaseModel):
    """Um `Comando` do motor (`context/01` §9), mais a correlação da detecção."""

    tipo: TipoComando
    id_semaforo: str
    fase_alvo: int | None = None
    duracao_s: float | None = None
    id_veiculo: str | None = None
    # Obrigatório na prática (core/comandos.py): é o que justifica a decisão.
    motivo: str = Field(min_length=1)
    id_correlacao: UUID | None = None


class RespostaComando(BaseModel):
    """O que o UNO fez com o comando, e quando."""

    linha: str | None = Field(description="Linha enviada; nula se o comando não tem tradução")
    aceito: bool
    resposta: str | None = Field(description="Resposta do UNO, como chegou")
    motivo_recusa: MotivoNak | None
    t_envio: datetime | None
    t_atuacao: datetime | None = Field(description="Chegada do ACK (P14)")
    latencia_serial_ms: float | None
    id_correlacao: UUID | None


class TelemetriaSchema(BaseModel):
    t_dispositivo_ms: int
    fase: int
    cores: str = Field(description="S1 S2 S3 S4, como na linha ST")
    em_preempcao: bool
    em_teste: bool


class EventoSchema(BaseModel):
    recebido_em: datetime
    t_dispositivo_ms: int
    tipo: TipoEvento


class RespostaEstado(BaseModel):
    telemetria: TelemetriaSchema | None
    recebida_em: datetime | None
    eventos: list[EventoSchema]


class RespostaHealth(BaseModel):
    estado: Literal["ok", "degradado"]
    porta: str
    conectada: bool
    uno_respondendo: bool
    ultima_telemetria_ha_s: float | None
    reconexoes: int
    linhas_invalidas: int
    telemetrias_com_dois_verdes: int


def _telemetria(telemetria: Telemetria) -> TelemetriaSchema:
    return TelemetriaSchema(
        t_dispositivo_ms=telemetria.t_dispositivo_ms,
        fase=telemetria.fase,
        cores="".join(cor.value for cor in telemetria.cores),
        em_preempcao=telemetria.em_preempcao,
        em_teste=telemetria.em_teste,
    )


def _resposta_comando(resultado: ResultadoEnvio) -> RespostaComando:
    resposta = resultado.resposta
    return RespostaComando(
        linha=resultado.linha,
        aceito=resultado.aceito,
        resposta=None if resposta is None else resposta.codificar().decode("ascii").strip(),
        motivo_recusa=resposta.motivo if isinstance(resposta, Nak) else None,
        t_envio=resultado.t_envio,
        t_atuacao=resultado.t_atuacao,
        latencia_serial_ms=resultado.latencia_serial_ms,
        id_correlacao=UUID(resultado.id_correlacao) if resultado.id_correlacao else None,
    )


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


def criar_app(ponte: Ponte, porta: str) -> FastAPI:
    """A aplicação HTTP da ponte; o ciclo de vida dela liga e desliga a porta.

    Args:
        ponte: A ponte a expor.
        porta: Nome da porta, só para o `/health` (`COM3`, `simulada`).
    """

    @asynccontextmanager
    async def ciclo_de_vida(_: FastAPI) -> AsyncIterator[None]:
        tarefa = asyncio.create_task(ponte.rodar(), name="ponte")
        try:
            yield
        finally:
            ponte.parar()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.wait_for(tarefa, 5.0)

    app = FastAPI(title="Ponte serial", version="0.1.0", lifespan=ciclo_de_vida)

    @app.get("/health", response_model=RespostaHealth)
    def health(resposta: Response) -> RespostaHealth:
        """Estado da porta serial e do UNO do outro lado."""
        ultima = ponte.t_ultima_telemetria
        corpo = RespostaHealth(
            estado="ok" if ponte.uno_respondendo() else "degradado",
            porta=porta,
            conectada=ponte.conectada,
            uno_respondendo=ponte.uno_respondendo(),
            ultima_telemetria_ha_s=(
                None if ultima is None else (ponte.relogio.agora() - ultima).total_seconds()
            ),
            reconexoes=ponte.reconexoes,
            linhas_invalidas=ponte.linhas_invalidas,
            telemetrias_com_dois_verdes=ponte.telemetrias_com_dois_verdes,
        )
        if corpo.estado != "ok":
            resposta.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return corpo

    @app.get("/estado", response_model=RespostaEstado)
    def estado() -> RespostaEstado:
        """Última telemetria do UNO e os eventos mais recentes."""
        telemetria = ponte.ultima_telemetria
        return RespostaEstado(
            telemetria=None if telemetria is None else _telemetria(telemetria),
            recebida_em=ponte.t_ultima_telemetria,
            eventos=[
                EventoSchema(recebido_em=quando, t_dispositivo_ms=ev.t_dispositivo_ms, tipo=ev.tipo)
                for quando, ev in ponte.eventos
            ],
        )

    @app.post(
        "/comandos",
        response_model=RespostaComando,
        responses={
            422: {"description": "Comando sem fase ou duração válida"},
            503: {"description": "Porta serial fechada"},
            504: {"description": "O UNO não respondeu no prazo"},
        },
    )
    async def comandos(pedido: PedidoComando, resposta: Response) -> RespostaComando:
        """Envia ao UNO o que o motor decidiu e devolve o `t_atuacao`."""
        comando = Comando(
            tipo=pedido.tipo,
            id_semaforo=pedido.id_semaforo,
            fase_alvo=pedido.fase_alvo,
            duracao_s=pedido.duracao_s,
            id_veiculo=pedido.id_veiculo,
            motivo=pedido.motivo,
        )
        correlacao = str(pedido.id_correlacao) if pedido.id_correlacao else None
        try:
            resultado = await ponte.enviar(comando, correlacao)
        except ComandoInvalidoError as erro:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)) from erro
        except ConexaoPerdidaError as erro:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(erro)) from erro
        if resultado.linha is not None and resultado.resposta is None:
            resposta.status_code = status.HTTP_504_GATEWAY_TIMEOUT
        return _resposta_comando(resultado)

    return app
