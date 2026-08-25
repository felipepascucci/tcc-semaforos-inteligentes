"""Liveness/readiness — context/01 §7 e context/02 §7.

O `/health` deve reportar o estado do banco, dos adaptadores e do watchdog
serial. No Bloco 0 só o banco existe; os demais são declarados como
`nao_configurado` — que é a verdade, e não um verde falso.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter(tags=["infraestrutura"])

EstadoComponente = Literal["ok", "falha", "nao_configurado"]


class RespostaHealth(BaseModel):
    """Estado agregado do processo backend."""

    estado: Literal["ok", "degradado"]
    versao: str
    perfil_parametros: str
    banco: EstadoComponente
    adaptador_sumo: EstadoComponente
    adaptador_hardware: EstadoComponente
    watchdog_serial: EstadoComponente
    detalhe: str | None = None


@lru_cache(maxsize=1)
def _motor(url: str) -> Engine:
    """Devolve um Engine único por URL — criar um por requisição vaza conexões."""
    return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 3})


def _verificar_banco() -> tuple[EstadoComponente, str | None]:
    url = os.getenv("DATABASE_URL")
    if not url:
        return "nao_configurado", "DATABASE_URL ausente"
    try:
        with _motor(url).connect() as conexao:
            conexao.execute(text("SELECT 1"))
    except SQLAlchemyError as erro:
        return "falha", type(erro).__name__
    return "ok", None


@router.get("/health", response_model=RespostaHealth, summary="Liveness/readiness")
def health(resposta: Response) -> RespostaHealth:
    """Reporta o estado do backend e de suas dependências."""
    banco, detalhe = _verificar_banco()

    corpo = RespostaHealth(
        estado="ok" if banco == "ok" else "degradado",
        versao="0.1.0",
        perfil_parametros=os.getenv("PERFIL_PARAMETROS", "simulacao"),
        banco=banco,
        # Bloco 3 e Bloco 5, respectivamente.
        adaptador_sumo="nao_configurado",
        adaptador_hardware="nao_configurado",
        watchdog_serial="nao_configurado",
        detalhe=detalhe,
    )
    if corpo.estado != "ok":
        resposta.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return corpo
