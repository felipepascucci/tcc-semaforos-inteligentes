"""Aplicação FastAPI do backend.

Bloco 0 entrega apenas o esqueleto e o `/health`. As rotas de domínio
(`/deteccoes`, `/semaforos`, `/veiculos`, `/simulacoes`, `/metricas`, `/stream`)
chegam no Bloco 6, conforme os contratos de context/01 §7.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.health import router as router_health

PREFIXO_API = "/api/v1"


def _origens_cors() -> list[str]:
    bruto = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    return [origem.strip() for origem in bruto.split(",") if origem.strip()]


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    """Abre e fecha os recursos de processo (banco, adaptadores, bridge)."""
    # Bloco 1 abre o pool do SQLAlchemy aqui; Bloco 5, o adaptador de hardware.
    yield


app = FastAPI(
    title="TCC — Controle Dinâmico de Semáforos",
    description=(
        "Priorização de veículos de emergência em ambientes urbanos. "
        "UNIP, Ciência da Computação, 2026."
    ),
    version="0.1.0",
    lifespan=ciclo_de_vida,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origens_cors(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router_health, prefix=PREFIXO_API)
