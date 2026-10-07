"""Ocorrências abertas e encerradas pela central de despacho — decisão P20.

É o dado que `core.autorizacao.autorizar()` consulta: sem ocorrência aberta, a
tag é reconhecida e não preempta. A central é simulada (painel "Central" do
dashboard ou `POST /ocorrencias`, Bloco 6); a integração real com SAMU, Corpo de
Bombeiros ou PM está fora de escopo (`context/00` §8).

A regra "no máximo uma ocorrência aberta por veículo" é do banco — índice único
parcial `uq_ocorrencia_aberta_por_veiculo` —, e não deste módulo. Abrir uma
segunda falha com `IntegrityError`, que o serviço traduz em resposta HTTP.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Ocorrencia, StatusOperacao, VeiculoEmergencia
from core.autorizacao import OcorrenciaAtiva
from core.modelos import Criticidade, TipoVeiculo

#: "Sem ocorrência ativa" na lista da bancada: o VE do tipo não preempta.
SEM_OCORRENCIA = 0


class OcorrenciaJaEncerradaError(ValueError):
    """Tentativa de encerrar uma ocorrência que já foi encerrada."""


def abrir_ocorrencia(
    sessao: Session,
    *,
    fk_veiculo: int,
    criticidade: Criticidade,
    descricao: str | None = None,
    origem: str = "CENTRAL",
) -> Ocorrencia:
    """Põe o veículo em serviço, com a criticidade atribuída pela central.

    Raises:
        sqlalchemy.exc.IntegrityError: se o veículo já tem ocorrência aberta.
    """
    ocorrencia = Ocorrencia(
        fk_veiculo=fk_veiculo,
        criticidade=int(criticidade),
        descricao=descricao,
        origem=origem,
    )
    sessao.add(ocorrencia)
    sessao.flush()
    return ocorrencia


def encerrar_ocorrencia(
    sessao: Session, id_ocorrencia: int, *, quando: datetime | None = None
) -> Ocorrencia:
    """Encerra o atendimento: o veículo deixa de ter prioridade.

    Se houver preempção em curso para ele, o motor a libera pelo caminho normal
    de E6 no passo seguinte, porque o VE deixa de ser entregue no `EstadoMalha`.

    **O instante padrão vem do relógio do banco**, o mesmo que carimba
    `aberta_em` (`DEFAULT now()`). Carimbar com o relógio da aplicação misturaria
    dois relógios: com o do banco poucos milissegundos adiantado — o caso comum
    de Postgres em contêiner —, um encerramento logo após a abertura caía *antes*
    dela e era recusado pelo `CHECK ck_ocorrencia_encerra_depois_de_abrir`.

    Raises:
        LookupError: se a ocorrência não existe.
        OcorrenciaJaEncerradaError: se ela já estava encerrada — reencerrar
            apagaria o instante verdadeiro do fim do atendimento.
    """
    ocorrencia = sessao.get(Ocorrencia, id_ocorrencia)
    if ocorrencia is None:
        raise LookupError(f"ocorrência {id_ocorrencia} não existe")
    if not ocorrencia.aberta:
        raise OcorrenciaJaEncerradaError(f"ocorrência {id_ocorrencia} já foi encerrada")
    ocorrencia.encerrada_em = quando if quando is not None else func.now()  # type: ignore[assignment]
    sessao.flush()
    sessao.refresh(ocorrencia, ["encerrada_em"])
    return ocorrencia


def ocorrencia_ativa_do_veiculo(sessao: Session, fk_veiculo: int) -> OcorrenciaAtiva | None:
    """A ocorrência aberta do veículo, no formato que `autorizar()` recebe.

    Devolve o tipo do núcleo, e não o model, para que a regra de `core/` não
    dependa do ORM (`context/01` §1).
    """
    consulta = select(Ocorrencia).where(
        Ocorrencia.fk_veiculo == fk_veiculo, Ocorrencia.encerrada_em.is_(None)
    )
    ocorrencia = sessao.scalars(consulta).one_or_none()
    if ocorrencia is None:
        return None
    return OcorrenciaAtiva(
        id_ocorrencia=ocorrencia.id_ocorrencia,
        criticidade=Criticidade(ocorrencia.criticidade),
    )


def criticidade_por_tipo(sessao: Session) -> dict[TipoVeiculo, int]:
    """A lista da Central para a bancada (decisão de 2026-10-06).

    Na bancada a identidade do VE é só o tipo (`context/05` §3.3), então a
    lista é por tipo: a criticidade **mais alta** (o menor número) entre as
    ocorrências abertas de veículos ativos daquele tipo, e `SEM_OCORRENCIA`
    quando não há nenhuma. Veículo inativo não conta, como em
    `core.autorizacao.autorizar()`.
    """
    consulta = (
        select(VeiculoEmergencia.tipo, func.min(Ocorrencia.criticidade))
        .join(VeiculoEmergencia, VeiculoEmergencia.id_veiculo == Ocorrencia.fk_veiculo)
        .where(
            Ocorrencia.encerrada_em.is_(None),
            VeiculoEmergencia.status_operacional == StatusOperacao.ATIVO,
        )
        .group_by(VeiculoEmergencia.tipo)
    )
    ativas = {tipo: int(criticidade) for tipo, criticidade in sessao.execute(consulta).tuples()}
    return {tipo: ativas.get(tipo, SEM_OCORRENCIA) for tipo in TipoVeiculo}


def listar_ocorrencias_ativas(sessao: Session) -> list[Ocorrencia]:
    """Quem está em serviço agora — o que o painel "Central" mostra."""
    consulta = (
        select(Ocorrencia)
        .where(Ocorrencia.encerrada_em.is_(None))
        .order_by(Ocorrencia.criticidade, Ocorrencia.aberta_em)
    )
    return list(sessao.scalars(consulta))
