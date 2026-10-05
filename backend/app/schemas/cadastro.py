"""Schemas de `/semaforos`, `/veiculos`, `/ocorrencias` e `/logs/prioridade`."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import StatusExecucao, StatusOperacao, TipoVeiculo
from app.repositories.cadastro import normalizar_uid

#: Placa Mercosul, ABC1D23 (`context/03` §3.1).
PADRAO_PLACA = r"^[A-Z]{3}[0-9][A-Z][0-9]{2}$"

# ---------------------------------------------------------------------------
# Semáforos
# ---------------------------------------------------------------------------


class FaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    indice_fase: int
    descricao: str
    movimentos: list[str]
    duracao_base: int
    verde_min: int
    verde_max: int


class SemaforoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_semaforo: int
    codigo_externo: str
    descricao: str | None
    latitude: Decimal
    longitude: Decimal
    tempo_ciclo: int
    status_operacao: StatusOperacao
    estado_atual: str = Field(description="O do cadastro; o vivo está em `ao_vivo`")
    ao_vivo: dict[str, Any] | None = Field(
        default=None,
        description="Último estado da bancada ou da simulação transmitida; nulo se não há",
    )


class LogSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_log: int
    id_correlacao: uuid.UUID
    codigo_semaforo: str
    fk_veiculo: int | None
    fk_execucao: int | None
    timestamp_inicio: datetime
    timestamp_fim: datetime | None
    status_execucao: StatusExecucao
    motivo: str | None
    fase_anterior: int | None
    fase_aplicada: int | None


class SemaforoDetalhe(SemaforoSchema):
    fases: list[FaseSchema]
    logs_recentes: list[LogSchema]
    telemetrias_recentes: list[dict[str, Any]] = Field(
        default=[], description="Só na bancada: as últimas linhas ST lidas da ponte"
    )


class PedidoPreempcao(BaseModel):
    """Preempção manual. Só a bancada tem atuador ligado ao backend, pela injeção da ponte."""

    rua: int = Field(ge=1, le=4, description="Aproximação S1..S4")
    veiculo: TipoVeiculo = TipoVeiculo.AMBULANCIA


class RespostaPreempcao(BaseModel):
    linha: str
    decisao: str | None = Field(description="PREEMP_INI, RENOVADO, FILA ou DESCARTADO")
    t_decisao: datetime | None


# ---------------------------------------------------------------------------
# Veículos
# ---------------------------------------------------------------------------


class TagSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str
    ativo: bool


class VeiculoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_veiculo: int
    placa: str
    tipo: TipoVeiculo
    identificacao: str | None
    status_operacional: StatusOperacao
    tags: list[TagSchema]
    em_servico: bool = Field(default=False, description="Tem ocorrência aberta (P20)")


class PedidoVeiculo(BaseModel):
    placa: str = Field(pattern=PADRAO_PLACA, examples=["TST1A23"])
    tipo: TipoVeiculo
    identificacao: str | None = Field(default=None, max_length=60)
    uid_tag: str | None = Field(default=None, max_length=32, examples=["A3 4F 21 9C"])

    @field_validator("placa", mode="before")
    @classmethod
    def _maiusculas(cls, valor: Any) -> Any:
        return valor.strip().upper() if isinstance(valor, str) else valor

    @field_validator("uid_tag")
    @classmethod
    def _uid(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        normalizado = normalizar_uid(valor)
        if not normalizado or any(c not in "0123456789ABCDEF" for c in normalizado):
            raise ValueError("UID precisa ser hexadecimal")
        return normalizado


# ---------------------------------------------------------------------------
# Ocorrências (P20)
# ---------------------------------------------------------------------------


class PedidoOcorrencia(BaseModel):
    id_veiculo: int
    criticidade: int = Field(ge=1, le=3, description="1 RISCO_VIDA, 2 RISCO_COLETIVO, 3 URGENCIA")
    descricao: str | None = Field(default=None, max_length=200)
    origem: Literal["CENTRAL", "OPERADOR"] = "CENTRAL"


class OcorrenciaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_ocorrencia: int
    id_veiculo: int = Field(validation_alias="fk_veiculo")
    criticidade: int
    descricao: str | None
    origem: str
    aberta_em: datetime
    encerrada_em: datetime | None
    aberta: bool


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


class PaginaLogs(BaseModel):
    total: int
    limite: int
    deslocamento: int
    itens: list[LogSchema]
