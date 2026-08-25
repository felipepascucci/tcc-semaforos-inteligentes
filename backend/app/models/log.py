"""Log de priorização — `context/03` §3.1.

Quarta das tabelas do texto original. `fk_metrica` aparecia no §4.2 do
pré-projeto mas não no §4.1; P4 unificou incluindo a coluna, e o DDL de
`context/03` §3.1 é a referência.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import STATUS_EXECUCAO, StatusExecucao

if TYPE_CHECKING:
    from app.models.metrica import MetricaSimulacao
    from app.models.semaforo import Semaforo
    from app.models.simulacao import ExecucaoSimulacao
    from app.models.veiculo import VeiculoEmergencia


class LogPrioridade(Base):
    """Uma tentativa de priorização, bem ou malsucedida.

    Gravar as malsucedidas é o que dá sentido ao `status_execucao`:
    `CONFLITO_ADIADO` (E8 mandou um VE esperar) e `ABORTADO_SEGURANCA` (fail-safe
    por invariante violado) são resultados legítimos do sistema, não erros a
    esconder — e são exatamente o que o relatório de validação precisa mostrar.

    `motivo` é obrigatório na prática: é o que explica na banca *por que* o
    sistema tomou cada decisão (`context/01` §9).
    """

    __tablename__ = "log_prioridade"
    __table_args__ = (
        # Reconstrói uma priorização inteira, da detecção à métrica.
        Index("idx_log_correlacao", "id_correlacao"),
        Index("idx_log_execucao_semaforo", "fk_execucao", "fk_semaforo"),
        Index("idx_log_inicio", text("timestamp_inicio DESC")),
    )

    id_log: Mapped[int] = mapped_column(Integer, primary_key=True)
    fk_veiculo: Mapped[int | None] = mapped_column(ForeignKey("veiculo_emergencia.id_veiculo"))
    fk_semaforo: Mapped[int] = mapped_column(ForeignKey("semaforo.id_semaforo"), nullable=False)
    fk_metrica: Mapped[int | None] = mapped_column(ForeignKey("metrica_simulacao.id_metrica"))
    fk_execucao: Mapped[int | None] = mapped_column(ForeignKey("execucao_simulacao.id_execucao"))

    # Gerado na detecção e propagado até a atuação (context/02 §7).
    id_correlacao: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    timestamp_inicio: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    timestamp_fim: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    ganho_tempo_segundos: Mapped[int | None] = mapped_column(Integer)
    status_execucao: Mapped[StatusExecucao] = mapped_column(STATUS_EXECUCAO, nullable=False)
    motivo: Mapped[str | None] = mapped_column(String(200))
    fase_anterior: Mapped[int | None] = mapped_column(Integer)
    fase_aplicada: Mapped[int | None] = mapped_column(Integer)

    veiculo: Mapped[VeiculoEmergencia | None] = relationship()
    semaforo: Mapped[Semaforo] = relationship()
    metrica: Mapped[MetricaSimulacao | None] = relationship()
    execucao: Mapped[ExecucaoSimulacao | None] = relationship()

    def __repr__(self) -> str:
        return f"<LogPrioridade {self.id_correlacao} {self.status_execucao}>"
