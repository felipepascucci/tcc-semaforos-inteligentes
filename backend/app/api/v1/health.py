"""Liveness/readiness — `context/01` §7 e `context/02` §7.

Reporta o banco, a ponte da bancada e a transmissão da simulação. **Só o banco
decide o `estado`**: a ponte e a simulação são opcionais (a bancada pode não
estar na mesa, e nenhuma simulação precisa estar rodando), e dizer "degradado"
por isso faria o `/health` ficar vermelho no uso normal.

O `watchdog_serial` do Bloco 0 saiu: I6 foi redefinida em 2026-10-05, e o UNO
não depende mais de comunicação (`context/01` §6).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Final, Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencias import RecursosDep

router = APIRouter(tags=["infraestrutura"])

VERSAO = "0.2.0"

#: O UNO manda `ST` a 2 Hz; o mesmo limite da ponte (`bridge.ponte.SILENCIO_MAXIMO_S`).
SILENCIO_DO_UNO: Final = timedelta(seconds=2)

EstadoComponente = Literal["ok", "falha", "nao_configurado"]


class RespostaHealth(BaseModel):
    """Estado agregado do processo backend."""

    estado: Literal["ok", "degradado"]
    versao: str
    perfil_parametros: str
    banco: EstadoComponente
    ponte: EstadoComponente = Field(description="GET /estado da ponte respondendo")
    uno_respondendo: bool | None = Field(
        description="Telemetria recente do UNO pela ponte; nulo sem ponte"
    )
    simulacao_ao_vivo: bool = Field(description="Transmissão do executor nos últimos 5 s")
    clientes_websocket: int
    detalhe: str | None = None


def _telemetria_recente(estado: dict[str, Any] | None) -> bool:
    """A ponte guarda a última `ST` mesmo com o UNO calado; vale a idade dela."""
    telemetria = (estado or {}).get("telemetria")
    if telemetria is None:
        return False
    recebida = datetime.fromisoformat(telemetria["recebida_em"])
    return datetime.now(UTC) - recebida < SILENCIO_DO_UNO


def _banco(recursos: RecursosDep) -> tuple[EstadoComponente, str | None]:
    if recursos.engine is None:
        return "nao_configurado", "DATABASE_URL ausente"
    try:
        with recursos.engine.connect() as conexao:
            conexao.execute(text("SELECT 1"))
    except SQLAlchemyError as erro:
        return "falha", type(erro).__name__
    return "ok", None


@router.get("/health", response_model=RespostaHealth, summary="Liveness/readiness")
def health(recursos: RecursosDep, resposta: Response) -> RespostaHealth:
    """Reporta o estado do backend e de suas dependências."""
    banco, detalhe = _banco(recursos)
    leitor = recursos.leitor
    ponte: EstadoComponente = "nao_configurado"
    uno: bool | None = None
    if leitor is not None:
        ponte = "ok" if leitor.disponivel else "falha"
        uno = leitor.disponivel and _telemetria_recente(leitor.ultimo_estado)

    corpo = RespostaHealth(
        estado="ok" if banco == "ok" else "degradado",
        versao=VERSAO,
        perfil_parametros=recursos.configuracao.perfil_parametros,
        banco=banco,
        ponte=ponte,
        uno_respondendo=uno,
        simulacao_ao_vivo=recursos.ao_vivo.ativa(),
        clientes_websocket=recursos.difusor.clientes,
        detalhe=detalhe,
    )
    if corpo.estado != "ok":
        resposta.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return corpo
