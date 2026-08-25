"""Veículo de emergência e suas tags RFID — `context/03` §3.1 e §3.2.

`veiculo_emergencia` é uma das quatro tabelas do texto original: campos
preservados exatamente (`context/03` §1).
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CriadoEmMixin
from app.models.enums import STATUS_OPERACAO, TIPO_VEICULO, StatusOperacao, TipoVeiculo


class VeiculoEmergencia(CriadoEmMixin, Base):
    """Ambulância, viatura de bombeiros ou viatura policial cadastrada."""

    __tablename__ = "veiculo_emergencia"

    id_veiculo: Mapped[int] = mapped_column(Integer, primary_key=True)
    placa: Mapped[str] = mapped_column(String(7), nullable=False, unique=True)  # padrão Mercosul
    tipo: Mapped[TipoVeiculo] = mapped_column(TIPO_VEICULO, nullable=False)
    identificacao: Mapped[str | None] = mapped_column(String(60))  # "SAMU 192 - Unidade 07"
    status_operacional: Mapped[StatusOperacao] = mapped_column(
        STATUS_OPERACAO, nullable=False, server_default=StatusOperacao.ATIVO.value
    )

    tags: Mapped[list[TagRfid]] = relationship(
        back_populates="veiculo", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<VeiculoEmergencia {self.placa} {self.tipo}>"


class TagRfid(CriadoEmMixin, Base):
    """Tag Mifare S50 que identifica o veículo no protótipo físico.

    No protótipo o RC522 **emula** o conjunto radar + V2I (decisão P7): a
    validação da fusão de sensores acontece só em simulação.

    `ativo` é uma trava de autorização, não um campo de conveniência: UID ausente
    da tabela ou com `ativo = false` resulta em HTTP 403 e registro da tentativa
    em `deteccao` (`context/02` §6).
    """

    __tablename__ = "tag_rfid"

    id_tag: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Normalizado: maiúsculas, sem espaços. "A3 4F 21 9C" é gravado "A34F219C".
    uid: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    fk_veiculo: Mapped[int] = mapped_column(
        ForeignKey("veiculo_emergencia.id_veiculo", ondelete="CASCADE"), nullable=False
    )
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    veiculo: Mapped[VeiculoEmergencia] = relationship(back_populates="tags")

    def __repr__(self) -> str:
        return f"<TagRfid {self.uid} ativo={self.ativo}>"
