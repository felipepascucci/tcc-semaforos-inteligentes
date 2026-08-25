"""Semáforo e suas fases — `context/03` §3.1 e §3.2.

`semaforo` é uma das quatro tabelas que já constam do texto do TCC: nomes e
campos são preservados exatamente (`context/03` §1).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CriadoEmMixin
from app.models.enums import ESTADO_SINAL, STATUS_OPERACAO, EstadoSinal, StatusOperacao

if TYPE_CHECKING:
    from app.models.dispositivo import DispositivoIot


class Semaforo(CriadoEmMixin, Base):
    """Um cruzamento semaforizado — um TLS do SUMO ou o cruzamento do protótipo."""

    __tablename__ = "semaforo"

    id_semaforo: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Id do TLS no SUMO (ex.: "CRUZ_01") ou do controlador físico ("PROTO_CRUZ_01").
    # É a chave de junção entre o mundo simulado e o banco.
    codigo_externo: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    descricao: Mapped[str | None] = mapped_column(String(120))

    # longitude é DECIMAL(11,8), não (10,8): -46,63 (São Paulo) precisa de três
    # dígitos inteiros e não cabe em (10,8). Correção obrigatória de P4.
    latitude: Mapped[Decimal] = mapped_column(Numeric(10, 8), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(11, 8), nullable=False)

    estado_atual: Mapped[EstadoSinal] = mapped_column(
        ESTADO_SINAL, nullable=False, server_default=EstadoSinal.VERMELHO.value
    )
    tempo_ciclo: Mapped[int] = mapped_column(Integer, nullable=False)
    status_operacao: Mapped[StatusOperacao] = mapped_column(
        STATUS_OPERACAO, nullable=False, server_default=StatusOperacao.ATIVO.value
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    fases: Mapped[list[FaseSemaforo]] = relationship(
        back_populates="semaforo", cascade="all, delete-orphan", order_by="FaseSemaforo.indice_fase"
    )
    dispositivos: Mapped[list[DispositivoIot]] = relationship(back_populates="semaforo")

    def __repr__(self) -> str:
        return f"<Semaforo {self.codigo_externo}>"


class FaseSemaforo(Base):
    """Uma fase do cruzamento: o conjunto de movimentos que recebem verde juntos.

    É a tabela consultada por E4 (`context/01` §5.2) para traduzir o movimento do
    VE — via de entrada → via de saída — na fase que o serve. O espelho em
    arquivo é `sim/config/mapa_fases.yaml`.
    """

    __tablename__ = "fase_semaforo"
    __table_args__ = (UniqueConstraint("fk_semaforo", "indice_fase"),)

    id_fase: Mapped[int] = mapped_column(Integer, primary_key=True)
    fk_semaforo: Mapped[int] = mapped_column(
        ForeignKey("semaforo.id_semaforo", ondelete="CASCADE"), nullable=False
    )
    indice_fase: Mapped[int] = mapped_column(Integer, nullable=False)
    descricao: Mapped[str] = mapped_column(String(80), nullable=False)
    movimentos: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    duracao_base: Mapped[int] = mapped_column(Integer, nullable=False)

    # Pisos e tetos de I4: nenhum verde é truncado antes de verde_min.
    verde_min: Mapped[int] = mapped_column(Integer, nullable=False, server_default="7")
    verde_max: Mapped[int] = mapped_column(Integer, nullable=False, server_default="60")

    semaforo: Mapped[Semaforo] = relationship(back_populates="fases")

    def __repr__(self) -> str:
        return f"<FaseSemaforo {self.fk_semaforo}#{self.indice_fase} {self.descricao!r}>"
