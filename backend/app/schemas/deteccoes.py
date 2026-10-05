"""Schemas de `POST /deteccoes` — `context/01` §7."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models import TipoVeiculo


class PedidoDeteccao(BaseModel):
    """O que um leitor V2I com rede envia. Na bancada nenhum dispositivo chama a API."""

    origem: Literal["V2I_RFID", "RADAR_SIM", "MANUAL"] = "V2I_RFID"
    uid_tag: str = Field(min_length=1, max_length=32, examples=["A3 4F 21 9C"])
    id_leitor: str = Field(min_length=1, max_length=50, examples=["LEITOR_CRUZ_01"])
    rssi: int | None = Field(default=None, ge=-128, le=127)
    timestamp_dispositivo: int | None = Field(
        default=None, ge=0, description="millis() do dispositivo; só ordena, não é relógio"
    )
    sequencia: int | None = Field(
        default=None, ge=0, description="Contador monotônico, para descartar repetição"
    )


AcaoDeteccao = Literal["PREEMPCAO_SOLICITADA", "SEM_OCORRENCIA", "VEICULO_INATIVO", "ACESSO_NEGADO"]


class RespostaDeteccao(BaseModel):
    reconhecido: bool
    autorizado: bool
    id_veiculo: int | None
    tipo: TipoVeiculo | None
    criticidade: int | None
    acao: AcaoDeteccao
    id_log: int | None
    mensagem_lcd: str
    duplicada: bool = Field(
        default=False,
        description="Repetição na janela de 2 s: a resposta é a da primeira, e nada é gravado",
    )
