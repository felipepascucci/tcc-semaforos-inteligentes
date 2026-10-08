"""`/simulacoes` — pedidos ao atendente do host e transmissão ao vivo (Bloco 6).

O backend não roda o SUMO (`context/02` §3): `POST /simulacoes` grava o pedido, e
`python -m sim.controlador.atendente`, no host, o executa. O executor, com
`--transmitir`, empurra o estado a 5 Hz para `POST /simulacoes/transmissao`, que
o repassa ao WebSocket.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.dependencias import EXIGE_OPERADOR, RecursosDep, SessaoDep
from app.schemas.simulacoes import (
    FaixaSeedReservada,
    PedidoSimulacaoEntrada,
    PedidoSimulacaoSchema,
    TransmissaoSimulacao,
)
from app.services import simulacoes

router = APIRouter(tags=["simulacoes"])


@router.post(
    "/simulacoes",
    response_model=PedidoSimulacaoSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Pede uma execução de cenário ao atendente do host",
    dependencies=[EXIGE_OPERADOR],
    responses={
        401: {"description": "Login necessário"},
        422: {"description": "Cenário desconhecido ou seed reservada ao experimento"},
    },
)
def pedir(
    entrada: PedidoSimulacaoEntrada, sessao: SessaoDep, recursos: RecursosDep
) -> PedidoSimulacaoSchema:
    """Grava o pedido como `PENDENTE`.

    As seeds de `GET /simulacoes/seeds-reservadas` são recusadas: são do
    experimento, e uma demonstração não pode ocupar o ponto do lote.
    """
    try:
        pedido = simulacoes.criar_pedido(sessao, entrada, recursos.regras_simulacao)
    except (simulacoes.CenarioDesconhecidoError, simulacoes.SeedReservadaError) as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)) from erro
    sessao.commit()
    return PedidoSimulacaoSchema.model_validate(pedido)


@router.get(
    "/simulacoes", response_model=list[PedidoSimulacaoSchema], summary="Pedidos mais recentes"
)
def listar(sessao: SessaoDep) -> list[PedidoSimulacaoSchema]:
    return [PedidoSimulacaoSchema.model_validate(p) for p in simulacoes.listar_pedidos(sessao)]


@router.get(
    "/simulacoes/seeds-reservadas",
    response_model=list[FaixaSeedReservada],
    summary="Faixas de seed do experimento, que um pedido não pode usar",
)
def seeds_reservadas(recursos: RecursosDep) -> list[FaixaSeedReservada]:
    """As faixas e o uso de cada uma, de `sim/config/cenarios.yaml`.

    Declarada antes de `/simulacoes/{id_pedido}`, senão o caminho cairia lá e
    seria recusado por não ser um número.
    """
    return [
        FaixaSeedReservada(inicio=inicio, fim=fim, uso=uso)
        for inicio, fim, uso in recursos.regras_simulacao.faixas()
    ]


@router.get(
    "/simulacoes/{id_pedido}",
    response_model=PedidoSimulacaoSchema,
    summary="Status e métricas da execução",
)
def detalhar(id_pedido: int, sessao: SessaoDep) -> PedidoSimulacaoSchema:
    pedido = simulacoes.buscar_pedido(sessao, id_pedido)
    if pedido is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"pedido {id_pedido} não existe")
    return PedidoSimulacaoSchema.model_validate(pedido)


@router.post(
    "/simulacoes/transmissao",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Estado ao vivo de uma simulação (executor --transmitir)",
)
async def transmitir(transmissao: TransmissaoSimulacao, recursos: RecursosDep) -> dict[str, int]:
    """Repassa ao WebSocket: semáforos, posição dos VEs, eventos e latência."""
    recursos.ao_vivo.receber(transmissao)
    return {"clientes_websocket": recursos.difusor.clientes}
