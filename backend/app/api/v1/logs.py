"""`GET /logs/prioridade` — o log de priorização paginado, com filtros (`context/01` §7)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.dependencias import SessaoDep
from app.models import LogPrioridade, Semaforo, StatusExecucao
from app.schemas.cadastro import LogSchema, PaginaLogs

router = APIRouter(tags=["logs"])


@router.get("/logs/prioridade", response_model=PaginaLogs, summary="Logs de priorização")
def listar(
    sessao: SessaoDep,
    semaforo: str | None = Query(default=None, description="codigo_externo, ex.: PROTO_CRUZ_01"),
    veiculo: int | None = Query(default=None, description="id_veiculo"),
    status_execucao: StatusExecucao | None = None,
    execucao: int | None = Query(default=None, description="id_execucao da simulação"),
    id_correlacao: uuid.UUID | None = None,
    desde: datetime | None = None,
    ate: datetime | None = None,
    limite: int = Query(default=50, ge=1, le=500),
    deslocamento: int = Query(default=0, ge=0),
) -> PaginaLogs:
    """Do mais novo para o mais antigo. `id_correlacao` reconstrói uma priorização inteira."""
    filtros = []
    if semaforo is not None:
        filtros.append(Semaforo.codigo_externo == semaforo)
    if veiculo is not None:
        filtros.append(LogPrioridade.fk_veiculo == veiculo)
    if status_execucao is not None:
        filtros.append(LogPrioridade.status_execucao == status_execucao)
    if execucao is not None:
        filtros.append(LogPrioridade.fk_execucao == execucao)
    if id_correlacao is not None:
        filtros.append(LogPrioridade.id_correlacao == id_correlacao)
    if desde is not None:
        filtros.append(LogPrioridade.timestamp_inicio >= desde)
    if ate is not None:
        filtros.append(LogPrioridade.timestamp_inicio <= ate)

    base = select(LogPrioridade, Semaforo.codigo_externo).join(
        Semaforo, Semaforo.id_semaforo == LogPrioridade.fk_semaforo
    )
    total = sessao.scalar(select(func.count()).select_from(base.where(*filtros).subquery()))
    linhas = sessao.execute(
        base.where(*filtros)
        .order_by(LogPrioridade.timestamp_inicio.desc(), LogPrioridade.id_log.desc())
        .limit(limite)
        .offset(deslocamento)
    ).all()
    return PaginaLogs(
        total=total or 0,
        limite=limite,
        deslocamento=deslocamento,
        itens=[
            LogSchema.model_validate(
                {
                    **{
                        c: getattr(log, c) for c in LogSchema.model_fields if c != "codigo_semaforo"
                    },
                    "codigo_semaforo": codigo,
                }
            )
            for log, codigo in linhas
        ],
    )
