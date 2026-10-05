"""Dispositivos de borda e detecções recebidas — `context/03` §3.2."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import STATUS_OPERACAO, StatusOperacao

if TYPE_CHECKING:
    from app.models.ocorrencia import Ocorrencia
    from app.models.semaforo import Semaforo
    from app.models.veiculo import VeiculoEmergencia


class DispositivoIot(Base):
    """Uma placa da bancada: NodeMCU emissor ou receptor, ou o UNO controlador.

    `token_hash` guarda o *hash* do token pré-compartilhado, nunca o token. É o
    que o header `X-Device-Token` valida (`context/02` §6).
    """

    __tablename__ = "dispositivo_iot"

    id_dispositivo: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    # EMISSOR_V2I | RECEPTOR_V2I | CONTROLADOR_SEMAFORO (bancada de 2026-10-05)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    fk_semaforo: Mapped[int | None] = mapped_column(ForeignKey("semaforo.id_semaforo"))
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    ultimo_contato: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    firmware_versao: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[StatusOperacao] = mapped_column(
        STATUS_OPERACAO, nullable=False, server_default=StatusOperacao.ATIVO.value
    )

    semaforo: Mapped[Semaforo | None] = relationship(back_populates="dispositivos")

    def __repr__(self) -> str:
        return f"<DispositivoIot {self.codigo} ({self.tipo})>"


class Deteccao(Base):
    """Toda leitura recebida, reconhecida ou não.

    Detecções **não reconhecidas** também são gravadas (`reconhecido = false`):
    é o registro da tentativa de acesso com UID desconhecido exigido por
    `context/02` §6, e é o que permite calcular a taxa de reconhecimento do
    RNF05 a partir de dado real em vez de contagem manual.
    """

    __tablename__ = "deteccao"
    __table_args__ = (
        # Sustenta a janela anti-replay de 2 s por UID (context/02 §6): a consulta
        # é sempre "últimas leituras deste UID", e o índice já entrega ordenado.
        Index("idx_deteccao_uid_tempo", "uid_bruto", text("recebido_em DESC")),
    )

    id_deteccao: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    id_correlacao: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    origem: Mapped[str] = mapped_column(String(20), nullable=False)  # V2I_RFID | RADAR_SIM | MANUAL
    fk_dispositivo: Mapped[int | None] = mapped_column(ForeignKey("dispositivo_iot.id_dispositivo"))
    fk_veiculo: Mapped[int | None] = mapped_column(ForeignKey("veiculo_emergencia.id_veiculo"))
    uid_bruto: Mapped[str | None] = mapped_column(String(32))
    reconhecido: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # P20: reconhecido E com ocorrência ativa. Uma tag reconhecida sem ocorrência
    # é gravada com `autorizado = false` — é o registro da ambulância que tentou
    # abrir o corredor sem estar em serviço.
    autorizado: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    fk_ocorrencia: Mapped[int | None] = mapped_column(ForeignKey("ocorrencia.id_ocorrencia"))
    rssi: Mapped[int | None] = mapped_column(SmallInteger)
    # Contador monotônico do ESP8266, reiniciado no boot. Serve para descartar
    # duplicatas e detectar reordenação — não é relógio (context/01 §7).
    sequencia: Mapped[int | None] = mapped_column(Integer)
    recebido_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    dispositivo: Mapped[DispositivoIot | None] = relationship()
    veiculo: Mapped[VeiculoEmergencia | None] = relationship()
    ocorrencia: Mapped[Ocorrencia | None] = relationship()

    def __repr__(self) -> str:
        return (
            f"<Deteccao {self.uid_bruto} reconhecido={self.reconhecido} "
            f"autorizado={self.autorizado}>"
        )
