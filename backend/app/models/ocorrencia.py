"""Ocorrência atendida por um VE — `context/03` §3.2, decisão P20.

**Emergência é estado declarado, não propriedade do veículo.** A tag prova quem
é o veículo; a ocorrência aberta pela central de despacho prova que ele está em
serviço. Sem ocorrência aberta, a tag é reconhecida e não preempta — a regra
vive em `core/autorizacao.py`, e esta tabela é o dado que ela consulta.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, SmallInteger, String, func, text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.veiculo import VeiculoEmergencia


class Ocorrencia(Base):
    """Um atendimento em curso ou encerrado.

    `criticidade` é ordinal, 1 = mais crítico (`core.modelos.Criticidade`), e é o
    primeiro critério de E8. Fica como `SMALLINT` com `CHECK`, e não como ENUM
    nativo, porque a escala é numérica por natureza — a ordem é o dado.
    """

    __tablename__ = "ocorrencia"
    __table_args__ = (
        CheckConstraint("criticidade BETWEEN 1 AND 3", name="criticidade_na_escala"),
        CheckConstraint(
            "encerrada_em IS NULL OR encerrada_em >= aberta_em", name="encerra_depois_de_abrir"
        ),
        # No máximo UMA ocorrência aberta por veículo: é o banco, e não o código,
        # que impede duas criticidades concorrentes para o mesmo VE.
        Index(
            "uq_ocorrencia_aberta_por_veiculo",
            "fk_veiculo",
            unique=True,
            postgresql_where=text("encerrada_em IS NULL"),
        ),
    )

    id_ocorrencia: Mapped[int] = mapped_column(Integer, primary_key=True)
    fk_veiculo: Mapped[int] = mapped_column(
        ForeignKey("veiculo_emergencia.id_veiculo"), nullable=False
    )
    criticidade: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    descricao: Mapped[str | None] = mapped_column(String(200))
    # CENTRAL | OPERADOR — a central de despacho é simulada (context/00 §8).
    origem: Mapped[str] = mapped_column(String(20), nullable=False, server_default="CENTRAL")
    aberta_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    encerrada_em: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    veiculo: Mapped[VeiculoEmergencia] = relationship()

    @property
    def aberta(self) -> bool:
        """Se o VE ainda está em serviço por esta ocorrência."""
        return self.encerrada_em is None

    def __repr__(self) -> str:
        estado = "aberta" if self.aberta else "encerrada"
        return f"<Ocorrencia {self.id_ocorrencia} veiculo={self.fk_veiculo} {estado}>"
