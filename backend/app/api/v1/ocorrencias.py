"""`/ocorrencias` — a central de despacho simulada (P20, `context/01` §7).

Abrir uma ocorrência põe o VE em serviço com a criticidade dada; encerrá-la tira a
prioridade. É o dado que `core.autorizacao.autorizar()` consulta em
`POST /deteccoes`. Na bancada não tem efeito: o UNO decide sem consultar
ocorrência (decisão de 2026-10-05).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.dependencias import RecursosDep, SessaoDep
from app.models import Ocorrencia, StatusOperacao, VeiculoEmergencia
from app.repositories.ocorrencia import (
    OcorrenciaJaEncerradaError,
    abrir_ocorrencia,
    encerrar_ocorrencia,
    listar_ocorrencias_ativas,
)
from app.schemas.cadastro import OcorrenciaSchema, PedidoOcorrencia
from core.modelos import Criticidade

router = APIRouter(tags=["ocorrencias"])

#: Quantas ocorrências `GET /ocorrencias` sem filtro devolve, das mais novas.
LIMITE_HISTORICO = 100


@router.post(
    "/ocorrencias",
    response_model=OcorrenciaSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Central abre ocorrência",
    responses={
        404: {"description": "Veículo não existe"},
        409: {"description": "Veículo inativo ou já em serviço"},
    },
)
def abrir(pedido: PedidoOcorrencia, sessao: SessaoDep, recursos: RecursosDep) -> OcorrenciaSchema:
    """Põe o VE em serviço. No máximo uma ocorrência aberta por VE, garantida pelo banco."""
    veiculo = sessao.get(VeiculoEmergencia, pedido.id_veiculo)
    if veiculo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"veículo {pedido.id_veiculo} não existe")
    if veiculo.status_operacional is not StatusOperacao.ATIVO:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"veículo {pedido.id_veiculo} está {veiculo.status_operacional.value}, não despacha",
        )
    try:
        ocorrencia = abrir_ocorrencia(
            sessao,
            fk_veiculo=pedido.id_veiculo,
            criticidade=Criticidade(pedido.criticidade),
            descricao=pedido.descricao,
            origem=pedido.origem,
        )
        sessao.commit()
    except IntegrityError as erro:
        sessao.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"veículo {pedido.id_veiculo} já tem ocorrência aberta"
        ) from erro
    sessao.refresh(ocorrencia)
    recursos.publicar_evento(
        {
            "nivel": "INFO",
            "texto": f"Ocorrência {ocorrencia.id_ocorrencia} aberta: {veiculo.tipo.value} "
            f"{veiculo.placa}, criticidade {ocorrencia.criticidade}",
            "origem": "CENTRAL",
            "id_veiculo": veiculo.id_veiculo,
        }
    )
    return OcorrenciaSchema.model_validate(ocorrencia)


@router.post(
    "/ocorrencias/{id_ocorrencia}/encerramento",
    response_model=OcorrenciaSchema,
    summary="Central encerra a ocorrência",
    responses={
        404: {"description": "Ocorrência não existe"},
        409: {"description": "Ocorrência já encerrada"},
    },
)
def encerrar(id_ocorrencia: int, sessao: SessaoDep, recursos: RecursosDep) -> OcorrenciaSchema:
    """O VE deixa de ter prioridade. Reencerrar é recusado: apagaria o instante verdadeiro."""
    try:
        ocorrencia = encerrar_ocorrencia(sessao, id_ocorrencia)
    except LookupError as erro:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(erro)) from erro
    except OcorrenciaJaEncerradaError as erro:
        raise HTTPException(status.HTTP_409_CONFLICT, str(erro)) from erro
    sessao.commit()
    recursos.publicar_evento(
        {
            "nivel": "INFO",
            "texto": f"Ocorrência {id_ocorrencia} encerrada",
            "origem": "CENTRAL",
            "id_veiculo": ocorrencia.fk_veiculo,
        }
    )
    return OcorrenciaSchema.model_validate(ocorrencia)


@router.get("/ocorrencias", response_model=list[OcorrenciaSchema], summary="Ocorrências")
def listar(
    sessao: SessaoDep,
    ativas: bool = Query(default=False, description="Só as abertas: o painel Central"),
) -> list[OcorrenciaSchema]:
    """Com `ativas=true`, quem está em serviço, da mais crítica para a menos crítica."""
    if ativas:
        ocorrencias = listar_ocorrencias_ativas(sessao)
    else:
        ocorrencias = list(
            sessao.scalars(
                select(Ocorrencia)
                .order_by(Ocorrencia.aberta_em.desc(), Ocorrencia.id_ocorrencia.desc())
                .limit(LIMITE_HISTORICO)
            )
        )
    return [OcorrenciaSchema.model_validate(ocorrencia) for ocorrencia in ocorrencias]
