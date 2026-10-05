"""Schemas de `/auth` — o login do operador do dashboard (Bloco 7)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PedidoLogin(BaseModel):
    usuario: str = Field(min_length=1, max_length=60)
    senha: str = Field(min_length=1, max_length=200)


class SessaoSchema(BaseModel):
    usuario: str
    perfil: str
    expira_em: datetime


class RespostaLogin(SessaoSchema):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
