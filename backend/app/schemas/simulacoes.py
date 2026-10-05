"""Schemas de `/simulacoes` — pedidos ao atendente do host e transmissão ao vivo."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import ModoControle


class PedidoSimulacaoEntrada(BaseModel):
    """`POST /simulacoes`: um ponto (cenário, modo, seed) para o atendente rodar."""

    cenario: str = Field(min_length=1, max_length=50, examples=["moderado"])
    modo: ModoControle
    seed: int = Field(ge=0, description="Não pode ser seed reservada ao experimento")
    duracao_s: int | None = Field(
        default=None, gt=0, le=3600, description="Nula usa a de cenarios.yaml"
    )


class ExecucaoResumo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_execucao: int
    nome_cenario: str
    modo: ModoControle
    seed: int
    duracao_s: int
    versao_codigo: str | None
    exemplar: bool
    iniciada_em: datetime
    finalizada_em: datetime | None


class PedidoSimulacaoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_pedido: int
    nome_cenario: str
    modo: ModoControle
    seed: int
    duracao_s: int | None
    status: Literal["PENDENTE", "RODANDO", "CONCLUIDA", "FALHA"]
    mensagem: str | None
    resumo: dict[str, Any] | None = Field(
        description="O que o executor mediu nesta execução. Demonstração, não capítulo 5"
    )
    criado_em: datetime
    iniciado_em: datetime | None
    finalizado_em: datetime | None
    execucao: ExecucaoResumo | None


# ---------------------------------------------------------------------------
# Transmissão ao vivo (executor --transmitir → backend → WebSocket)
# ---------------------------------------------------------------------------


class SemaforoTransmitido(BaseModel):
    id: str = Field(examples=["CRUZ_03"])
    fase: int
    sinal: Literal["VERDE", "AMARELO", "VERMELHO"]
    em_preempcao: bool


class VeTransmitido(BaseModel):
    id: str = Field(description="Id do VE no SUMO", examples=["ve_amb_0"])
    tipo: str
    criticidade: int = Field(ge=1, le=3)
    lat: float
    lon: float
    velocidade: float = Field(description="m/s")


class EventoTransmitido(BaseModel):
    nivel: Literal["INFO", "WARNING", "ERROR"] = "INFO"
    texto: str = Field(max_length=200)


class TransmissaoSimulacao(BaseModel):
    """`POST /simulacoes/transmissao`: uma fotografia da simulação em curso."""

    cenario: str
    modo: ModoControle
    seed: int
    id_pedido: int | None = None
    t: float = Field(description="Segundos simulados")
    semaforos: list[SemaforoTransmitido]
    veiculos: list[VeTransmitido] = []
    eventos: list[EventoTransmitido] = []
    latencia_ms: float | None = Field(
        default=None, description="Última latência de decisão do motor; nula no FIXO"
    )
