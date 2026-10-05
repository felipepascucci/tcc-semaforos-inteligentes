"""`/veiculos` — cadastro de VEs e tags (`context/01` §7)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.dependencias import SessaoDep
from app.models import Ocorrencia, TagRfid, VeiculoEmergencia
from app.schemas.cadastro import PedidoVeiculo, VeiculoSchema

router = APIRouter(tags=["veiculos"])


def _schema(veiculo: VeiculoEmergencia, em_servico: set[int]) -> VeiculoSchema:
    esquema = VeiculoSchema.model_validate(veiculo)
    return esquema.model_copy(update={"em_servico": veiculo.id_veiculo in em_servico})


def _em_servico(sessao: SessaoDep) -> set[int]:
    return set(
        sessao.scalars(select(Ocorrencia.fk_veiculo).where(Ocorrencia.encerrada_em.is_(None)))
    )


@router.get("/veiculos", response_model=list[VeiculoSchema], summary="Cadastro de VEs")
def listar(sessao: SessaoDep) -> list[VeiculoSchema]:
    """Os VEs com as tags e se estão em serviço (ocorrência aberta, P20)."""
    veiculos = sessao.scalars(
        select(VeiculoEmergencia)
        .options(selectinload(VeiculoEmergencia.tags))
        .order_by(VeiculoEmergencia.id_veiculo)
    )
    em_servico = _em_servico(sessao)
    return [_schema(veiculo, em_servico) for veiculo in veiculos]


@router.post(
    "/veiculos",
    response_model=VeiculoSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra VE e tag",
    responses={409: {"description": "Placa ou UID já cadastrados"}},
)
def cadastrar(pedido: PedidoVeiculo, sessao: SessaoDep) -> VeiculoSchema:
    """Cadastra o VE e, se vier `uid_tag`, a tag dele, ativa e normalizada."""
    veiculo = VeiculoEmergencia(
        placa=pedido.placa, tipo=pedido.tipo, identificacao=pedido.identificacao
    )
    if pedido.uid_tag is not None:
        veiculo.tags.append(TagRfid(uid=pedido.uid_tag, ativo=True))
    sessao.add(veiculo)
    try:
        sessao.commit()
    except IntegrityError as erro:
        sessao.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "placa ou UID já cadastrados") from erro
    sessao.refresh(veiculo, ["tags", "status_operacional"])
    return _schema(veiculo, set())
