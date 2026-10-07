"""HTTP da ponte — `/health`, `/estado`, `/autorizacoes` e `/injecao` (`context/05` §6).

A ponte é um processo separado do backend (`context/02` §3: precisa da porta
USB, e o backend roda no compose). Ela **não sabe que o backend existe**: é o
backend que lê `GET /estado` a 5 Hz (decisão de 2026-10-05, Bloco 6). O
histórico de telemetrias, eventos e amostras de H3 existe para isso: quem lê
entre duas consultas não perde nada.

Duas escritas no UNO, pelo USB (decisão de 2026-10-06):

* `PUT /autorizacoes` — a lista da Central, a criticidade da ocorrência ativa de
  cada tipo. O backend a chama quando a lista que a `ST` traz difere da dele;
  na bancada sem backend, o roteiro de aceitação a chama direto.
* `POST /injecao` — de teste: faz o papel do receptor. É o que o roteiro de
  aceitação (`bridge/verificar.py`) e o passo 5 da demonstração (`bridge/demo.py`)
  usam.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal

from fastapi import FastAPI, HTTPException, Response, status
from pydantic import BaseModel, Field

from bridge.latencia import AmostraH3
from bridge.ponte import Ponte
from bridge.protocolo import (
    CRITICIDADE_MAXIMA,
    N_SEMAFOROS,
    SEM_OCORRENCIA,
    TIPOS_DA_BANCADA,
    Autorizacao,
    Deteccao,
    Regime,
    Telemetria,
    TipoEvento,
)
from bridge.transporte import ConexaoPerdidaError
from core.modelos import TipoVeiculo

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TelemetriaSchema(BaseModel):
    recebida_em: datetime
    t_dispositivo_ms: int
    cores: str = Field(description="S1 S2 S3 S4, como na linha ST")
    regime: Regime
    rua_ativa: int | None
    rua_fila: int | None
    autorizacoes: dict[TipoVeiculo, int] = Field(
        description="A criticidade que o UNO tem para cada tipo; 0 é sem ocorrência"
    )


class EventoSchema(BaseModel):
    recebido_em: datetime
    t_dispositivo_ms: int
    tipo: TipoEvento
    rua: int | None
    veiculo: TipoVeiculo | None


class AmostraH3Schema(BaseModel):
    """Uma amostra de H3, a mesma linha que vai para o `latencia_bancada.csv`."""

    t_deteccao: datetime = Field(description="Primeiro byte de `Tag … lida`, no emissor")
    t_atuacao: datetime = Field(description="Primeiro byte do `EV,…,PREEMP_INI` do UNO")
    latencia_total_ms: float
    rua: int
    uid: str
    veiculo: TipoVeiculo
    uno_ms: int = Field(description="millis() do UNO no PREEMP_INI")


class RespostaEstado(BaseModel):
    telemetria: TelemetriaSchema | None = Field(description="A mais recente")
    telemetrias: list[TelemetriaSchema] = Field(
        description="As mais recentes, em ordem; a ST sai a cada mudança de estado"
    )
    eventos: list[EventoSchema]
    amostras_h3: list[AmostraH3Schema] = Field(
        description="As desta sessão da ponte; vazia fora da medição de H3"
    )


class RespostaHealth(BaseModel):
    estado: Literal["ok", "degradado"]
    porta: str
    conectada: bool
    uno_respondendo: bool
    ultima_telemetria_ha_s: float | None
    reconexoes: int
    linhas_invalidas: int
    telemetrias_violando_i1: int
    emissor_conectado: bool | None = Field(
        description="Porta do NodeMCU emissor; null fora da medição de H3"
    )
    amostras_h3: int | None = Field(
        description="Amostras de H3 desta sessão; null fora da medição de H3"
    )
    deteccoes_sem_amostra: dict[str, int] = Field(
        description="Detecções que viraram FILA, RENOVADO, DESCARTADO ou SEM_DECISAO"
    )


class PedidoAutorizacoes(BaseModel):
    """A lista da Central: a criticidade da ocorrência ativa de cada tipo.

    Os tipos ausentes não são tocados. 0 é sem ocorrência (o VE não preempta);
    de 1 a 3, a criticidade (1 a mais crítica).
    """

    autorizacoes: dict[TipoVeiculo, int] = Field(min_length=1)

    def linhas(self) -> list[Autorizacao]:
        return [Autorizacao(tipo, c) for tipo, c in self.autorizacoes.items()]


class RespostaAutorizacoes(BaseModel):
    linhas: list[str]
    t_envio: datetime


class PedidoInjecao(BaseModel):
    """Um VE chegando pela rua — a linha que o NodeMCU receptor escreveria."""

    rua: int = Field(ge=1, le=N_SEMAFOROS)
    veiculo: TipoVeiculo


class RespostaInjecao(BaseModel):
    linha: str
    t_envio: datetime
    decisao: TipoEvento | None = Field(
        description="PREEMP_INI, RENOVADO, FILA, DESCARTADO ou SEM_OCORRENCIA"
    )
    decisao_t_dispositivo_ms: int | None = Field(description="millis() do UNO na decisão")
    t_decisao: datetime | None
    latencia_ms: float | None = Field(description="Envio -> decisão; conferência, não H3")


class PedidoInjecaoBruta(BaseModel):
    """Uma linha qualquer, para conferir que o UNO recusa o que não entende."""

    linha: str = Field(min_length=1, max_length=64, pattern=r"^[\x20-\x7e]+$")


class RespostaInjecaoBruta(BaseModel):
    linha: str
    t_envio: datetime


def _amostra(amostra: AmostraH3) -> AmostraH3Schema:
    evento = amostra.decisao.evento
    assert evento.veiculo is not None  # PREEMP_INI sempre traz o VE
    return AmostraH3Schema(
        t_deteccao=amostra.deteccao.t,
        t_atuacao=amostra.decisao.t,
        latencia_total_ms=amostra.latencia_total_ms,
        rua=amostra.deteccao.rua,
        uid=amostra.deteccao.leitura.uid,
        veiculo=evento.veiculo,
        uno_ms=evento.t_dispositivo_ms,
    )


def _telemetria(recebida_em: datetime, telemetria: Telemetria) -> TelemetriaSchema:
    return TelemetriaSchema(
        recebida_em=recebida_em,
        t_dispositivo_ms=telemetria.t_dispositivo_ms,
        cores=telemetria.estado,
        regime=telemetria.regime,
        rua_ativa=telemetria.rua_ativa,
        rua_fila=telemetria.rua_fila,
        autorizacoes=dict(zip(TIPOS_DA_BANCADA, telemetria.autorizacoes, strict=True)),
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

    app = FastAPI(title="Ponte serial", version="0.2.0", lifespan=ciclo_de_vida)

    @app.get("/health", response_model=RespostaHealth)
    def health(resposta: Response) -> RespostaHealth:
        """Estado da porta serial e do UNO do outro lado."""
        ultima = ponte.t_ultima_telemetria
        medindo = ponte.transporte_veiculo is not None
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
            telemetrias_violando_i1=ponte.telemetrias_violando_i1,
            emissor_conectado=ponte.emissor_conectado if medindo else None,
            amostras_h3=len(ponte.amostras_h3) if medindo else None,
            deteccoes_sem_amostra=dict(ponte.deteccoes_sem_amostra),
        )
        if corpo.estado != "ok":
            resposta.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return corpo

    @app.get("/estado", response_model=RespostaEstado)
    def estado() -> RespostaEstado:
        """Telemetrias, eventos e amostras de H3 mais recentes do UNO."""
        telemetrias = [_telemetria(quando, st) for quando, st in ponte.telemetrias]
        return RespostaEstado(
            telemetria=telemetrias[-1] if telemetrias else None,
            telemetrias=telemetrias,
            eventos=[
                EventoSchema(
                    recebido_em=quando,
                    t_dispositivo_ms=ev.t_dispositivo_ms,
                    tipo=ev.tipo,
                    rua=ev.rua,
                    veiculo=ev.veiculo,
                )
                for quando, ev in ponte.eventos
            ],
            amostras_h3=[_amostra(amostra) for amostra in ponte.amostras_h3],
        )

    @app.put(
        "/autorizacoes",
        response_model=RespostaAutorizacoes,
        status_code=status.HTTP_202_ACCEPTED,
        responses={
            422: {"description": f"Criticidade fora de {SEM_OCORRENCIA}..{CRITICIDADE_MAXIMA}"},
            503: {"description": "Porta serial fechada"},
        },
    )
    async def autorizacoes(pedido: PedidoAutorizacoes) -> RespostaAutorizacoes:
        """Manda ao UNO a lista da Central. A confirmação vem na `ST` seguinte."""
        for criticidade in pedido.autorizacoes.values():
            if not SEM_OCORRENCIA <= criticidade <= CRITICIDADE_MAXIMA:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    f"criticidade fora de {SEM_OCORRENCIA}..{CRITICIDADE_MAXIMA}: {criticidade}",
                )
        linhas = pedido.linhas()
        try:
            t_envio = await ponte.autorizar(linhas)
        except ConexaoPerdidaError as erro:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(erro)) from erro
        return RespostaAutorizacoes(
            linhas=[a.codificar().decode("ascii").rstrip("\n") for a in linhas], t_envio=t_envio
        )

    @app.post(
        "/injecao",
        response_model=RespostaInjecao,
        responses={
            503: {"description": "Porta serial fechada"},
            504: {"description": "O UNO não decidiu no prazo"},
        },
    )
    async def injecao(pedido: PedidoInjecao, resposta: Response) -> RespostaInjecao:
        """Escreve a detecção no RX do UNO e devolve a decisão dele."""
        try:
            resultado = await ponte.injetar(Deteccao(pedido.rua, pedido.veiculo))
        except ConexaoPerdidaError as erro:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(erro)) from erro
        decisao = resultado.decisao
        if decisao is None:
            resposta.status_code = status.HTTP_504_GATEWAY_TIMEOUT
        return RespostaInjecao(
            linha=resultado.linha,
            t_envio=resultado.t_envio,
            decisao=None if decisao is None else decisao.tipo,
            decisao_t_dispositivo_ms=None if decisao is None else decisao.t_dispositivo_ms,
            t_decisao=resultado.t_decisao,
            latencia_ms=resultado.latencia_ms,
        )

    @app.post(
        "/injecao/bruta",
        response_model=RespostaInjecaoBruta,
        status_code=status.HTTP_202_ACCEPTED,
        responses={503: {"description": "Porta serial fechada"}},
    )
    async def injecao_bruta(pedido: PedidoInjecaoBruta) -> RespostaInjecaoBruta:
        """Escreve uma linha qualquer; a reação do UNO aparece em `/estado`."""
        try:
            t_envio = await ponte.injetar_bruta(pedido.linha)
        except ConexaoPerdidaError as erro:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(erro)) from erro
        return RespostaInjecaoBruta(linha=pedido.linha, t_envio=t_envio)

    return app
