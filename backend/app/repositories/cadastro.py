"""Leitura dos cadastros: semáforos, fases, veículos, tags e dispositivos.

São consultas de baixo volume e alta frequência de leitura — o oposto do perfil
de `fila_lote.py`. Quem chama no caminho quente (resolução de UID a cada
detecção) deve manter o resultado em memória; estas funções não têm cache
próprio de propósito, para não esconder invalidação de cadastro alterado.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import DispositivoIot, FaseSemaforo, Semaforo, TagRfid, VeiculoEmergencia


def normalizar_uid(uid_bruto: str) -> str:
    """Normaliza o UID de uma tag: maiúsculas, sem espaços nem separadores.

    O RC522 entrega ``"A3 4F 21 9C"``; o banco guarda ``"A34F219C"``
    (`context/03` §3.2). Sem normalizar numa fronteira única, a mesma tag vira
    dois cadastros diferentes e a preempção falha por "UID desconhecido" com o
    cartão certo na mão.

    Args:
        uid_bruto: UID como veio do leitor.

    Returns:
        UID normalizado, pronto para comparação com `tag_rfid.uid`.
    """
    return "".join(uid_bruto.split()).replace(":", "").replace("-", "").upper()


def listar_semaforos(sessao: Session) -> list[Semaforo]:
    """Todos os semáforos cadastrados, com as fases já carregadas."""
    consulta = select(Semaforo).options(selectinload(Semaforo.fases)).order_by(Semaforo.id_semaforo)
    return list(sessao.scalars(consulta))


def buscar_semaforo_por_codigo(sessao: Session, codigo_externo: str) -> Semaforo | None:
    """Localiza um semáforo pelo id do TLS no SUMO ou do controlador físico."""
    consulta = select(Semaforo).where(Semaforo.codigo_externo == codigo_externo)
    return sessao.scalars(consulta).one_or_none()


def mapa_codigo_para_id(sessao: Session) -> dict[str, int]:
    """Devolve ``{codigo_externo: id_semaforo}``.

    O adaptador do SUMO trabalha com o código do TLS e a gravação precisa da
    chave numérica. Carregar o mapa uma vez, antes do loop, evita um SELECT por
    transição — a mesma preocupação da regra de `context/03` §4.1.
    """
    consulta = select(Semaforo.codigo_externo, Semaforo.id_semaforo)
    return dict(sessao.execute(consulta).all())


def fases_de(sessao: Session, id_semaforo: int) -> list[FaseSemaforo]:
    """Fases de um cruzamento, em ordem de índice."""
    consulta = (
        select(FaseSemaforo)
        .where(FaseSemaforo.fk_semaforo == id_semaforo)
        .order_by(FaseSemaforo.indice_fase)
    )
    return list(sessao.scalars(consulta))


def buscar_veiculo_por_uid(sessao: Session, uid_bruto: str) -> VeiculoEmergencia | None:
    """Resolve o UID de uma tag no veículo correspondente.

    Só tags **ativas** resolvem. Tag inativa é tratada como desconhecida, e é
    isso que permite revogar um cartão perdido sem apagar o histórico que já
    aponta para ele (`context/02` §6).

    Args:
        sessao: Sessão aberta do SQLAlchemy.
        uid_bruto: UID como veio do leitor; a normalização acontece aqui.

    Returns:
        O veículo, ou `None` se o UID não estiver cadastrado ou a tag estiver
        inativa.
    """
    consulta = (
        select(VeiculoEmergencia)
        .join(TagRfid, TagRfid.fk_veiculo == VeiculoEmergencia.id_veiculo)
        .where(TagRfid.uid == normalizar_uid(uid_bruto), TagRfid.ativo.is_(True))
    )
    return sessao.scalars(consulta).one_or_none()


def buscar_dispositivo_por_codigo(sessao: Session, codigo: str) -> DispositivoIot | None:
    """Localiza um dispositivo de borda pelo código (ex.: ``LEITOR_CRUZ_01``)."""
    consulta = select(DispositivoIot).where(DispositivoIot.codigo == codigo)
    return sessao.scalars(consulta).one_or_none()
