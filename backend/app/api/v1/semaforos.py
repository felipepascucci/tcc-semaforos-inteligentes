"""`/semaforos` — cadastro, estado ao vivo e preempção manual (`context/01` §7).

**Só a bancada tem atuador ligado ao backend**, e só pela injeção da ponte
(`POST /injecao`), que exige o fio do NodeMCU solto do RX (`context/05` §6). Por
isso:

* `POST /semaforos/PROTO_CRUZ_01/preempcao` escreve no RX do UNO a mesma linha
  que o receptor escreveria, e devolve a decisão do UNO;
* nos cruzamentos da simulação, o motor roda no processo do executor, e a API
  não tem como comandá-lo: 409;
* `DELETE .../preempcao` é sempre 409. O UNO não aceita cancelamento: a
  emergência termina sozinha, pela duração do tipo ou pelo teto de 30 s (I6,
  `context/01` §6). Na simulação, pelo mesmo motivo do POST.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.dependencias import Recursos, RecursosDep, SessaoDep
from app.configuracao import CODIGO_BANCADA
from app.models import LogPrioridade, Semaforo
from app.repositories.cadastro import listar_semaforos
from app.schemas.cadastro import (
    FaseSchema,
    LogSchema,
    PedidoPreempcao,
    RespostaPreempcao,
    SemaforoDetalhe,
    SemaforoSchema,
)
from app.services.bancada import estado_do_semaforo

router = APIRouter(tags=["semaforos"])

LOGS_NO_DETALHE = 20


def _ao_vivo(recursos: Recursos, codigo: str) -> dict[str, Any] | None:
    if codigo == CODIGO_BANCADA:
        leitor = recursos.leitor
        telemetria = None
        if leitor is not None and leitor.disponivel and leitor.ultimo_estado:
            telemetria = leitor.ultimo_estado.get("telemetria")
        return (
            None if telemetria is None else {"fonte": "BANCADA", **estado_do_semaforo(telemetria)}
        )
    ao_vivo = recursos.ao_vivo
    if not ao_vivo.ativa() or ao_vivo.ultima is None:
        return None
    for semaforo in ao_vivo.ultima.semaforos:
        if semaforo.id == codigo:
            return {
                "fonte": "SIMULACAO",
                **semaforo.model_dump(),
                "t_simulacao": ao_vivo.ultima.t,
                "recebido_em": ao_vivo.recebida_em,
            }
    return None


def _semaforo(recursos: Recursos, semaforo: Semaforo) -> SemaforoSchema:
    return SemaforoSchema.model_validate(
        {
            **{c: getattr(semaforo, c) for c in SemaforoSchema.model_fields if c != "ao_vivo"},
            "ao_vivo": _ao_vivo(recursos, semaforo.codigo_externo),
        }
    )


def _log(linha: LogPrioridade, codigo: str) -> LogSchema:
    return LogSchema.model_validate(
        {
            **{c: getattr(linha, c) for c in LogSchema.model_fields if c != "codigo_semaforo"},
            "codigo_semaforo": codigo,
        }
    )


def _buscar(sessao: SessaoDep, codigo: str) -> Semaforo:
    semaforo = sessao.scalars(
        select(Semaforo)
        .options(selectinload(Semaforo.fases))
        .where(Semaforo.codigo_externo == codigo)
    ).one_or_none()
    if semaforo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"semáforo {codigo} não existe")
    return semaforo


@router.get("/semaforos", response_model=list[SemaforoSchema], summary="Semáforos e estado atual")
def listar(sessao: SessaoDep, recursos: RecursosDep) -> list[SemaforoSchema]:
    """Todos os cruzamentos; `ao_vivo` traz o estado da bancada ou da simulação transmitida."""
    return [_semaforo(recursos, semaforo) for semaforo in listar_semaforos(sessao)]


@router.get("/semaforos/{codigo}", response_model=SemaforoDetalhe, summary="Detalhe e histórico")
def detalhar(codigo: str, sessao: SessaoDep, recursos: RecursosDep) -> SemaforoDetalhe:
    """Fases, últimas priorizações e, na bancada, as últimas telemetrias do UNO."""
    semaforo = _buscar(sessao, codigo)
    logs = sessao.scalars(
        select(LogPrioridade)
        .where(LogPrioridade.fk_semaforo == semaforo.id_semaforo)
        .order_by(LogPrioridade.timestamp_inicio.desc(), LogPrioridade.id_log.desc())
        .limit(LOGS_NO_DETALHE)
    )
    telemetrias: list[dict[str, Any]] = []
    if codigo == CODIGO_BANCADA and recursos.leitor is not None and recursos.leitor.ultimo_estado:
        telemetrias = recursos.leitor.ultimo_estado.get("telemetrias", [])
    return SemaforoDetalhe(
        **_semaforo(recursos, semaforo).model_dump(),
        fases=[FaseSchema.model_validate(fase) for fase in semaforo.fases],
        logs_recentes=[_log(linha, codigo) for linha in logs],
        telemetrias_recentes=telemetrias,
    )


_SEM_ATUADOR = (
    "a API não comanda os cruzamentos da simulação: o motor roda no processo do executor "
    "(context/01 §7)"
)


@router.post(
    "/semaforos/{codigo}/preempcao",
    response_model=RespostaPreempcao,
    summary="Preempção manual (bancada, pela injeção da ponte)",
    responses={
        409: {"description": "Cruzamento sem atuador ligado ao backend"},
        503: {"description": "Ponte não configurada ou fora do ar"},
        504: {"description": "O UNO não decidiu: o fio do NodeMCU está no RX?"},
    },
)
async def preemptar(
    codigo: str, pedido: PedidoPreempcao, recursos: RecursosDep, resposta: Response
) -> RespostaPreempcao:
    """Na bancada, o VE "chega" pela rua pedida, como se o receptor o tivesse repassado.

    A decisão é do UNO; os eventos dela entram no log pela leitura da ponte,
    como os de um VE de verdade.
    """
    if codigo != CODIGO_BANCADA:
        raise HTTPException(status.HTTP_409_CONFLICT, _SEM_ATUADOR)
    leitor = recursos.leitor
    if leitor is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "ponte não configurada (PONTE_URL)"
        )
    try:
        injecao = await leitor.injetar(pedido.rua, pedido.veiculo.value)
    except httpx.HTTPError as erro:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "ponte fora do ar") from erro
    if injecao.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "porta serial da ponte fechada")
    corpo = injecao.json()
    resposta.status_code = injecao.status_code
    return RespostaPreempcao(
        linha=corpo["linha"], decisao=corpo["decisao"], t_decisao=corpo["t_decisao"]
    )


@router.delete(
    "/semaforos/{codigo}/preempcao",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
    summary="Cancela preempção ativa — não suportado pelos atuadores",
    responses={409: {"description": "Nenhum atuador aceita cancelamento"}},
)
def cancelar(codigo: str) -> None:
    """Sempre 409, com o motivo: nenhum atuador ligado ao backend aceita cancelar."""
    if codigo == CODIGO_BANCADA:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "o UNO não aceita cancelamento: a emergência termina sozinha, pela duração do "
            "tipo do VE ou pelo teto de 30 s (I6, context/01 §6)",
        )
    raise HTTPException(status.HTTP_409_CONFLICT, _SEM_ATUADOR)
