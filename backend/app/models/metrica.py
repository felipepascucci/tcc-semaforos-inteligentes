"""Métricas agregadas e de latência — `context/03` §3.1 e §3.2.

`metrica_simulacao` é uma das quatro tabelas do texto original. O único ajuste é
o de P4: `tempo_medio_resposta` passa de `DECIMAL(5,2)` para `DECIMAL(8,2)`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Computed,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.semaforo import Semaforo
    from app.models.simulacao import ExecucaoSimulacao


class MetricaSimulacao(Base):
    """Agregados de uma execução, na forma já publicada no capítulo 4 do TCC."""

    __tablename__ = "metrica_simulacao"
    __table_args__ = (Index("idx_metrica_exec", "id_execucao"),)

    id_metrica: Mapped[int] = mapped_column(Integer, primary_key=True)
    # A coluna chama-se `id_execucao`, não `fk_execucao`: nome do texto original,
    # preservado conforme context/03 §1.
    id_execucao: Mapped[int | None] = mapped_column(
        ForeignKey("execucao_simulacao.id_execucao", ondelete="CASCADE")
    )

    # DECIMAL(8,2) e não (5,2): o limite de 999,99 do texto é apertado demais
    # para tempos de deslocamento em cenário intenso. Correção de P4.
    tempo_medio_resposta: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)  # s
    tempo_espera: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)  # s
    percentual_reducao: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    latencia_ia: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)  # ms
    cenario_simulado: Mapped[str] = mapped_column(String(50), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    execucao: Mapped[ExecucaoSimulacao | None] = relationship()

    def __repr__(self) -> str:
        return f"<MetricaSimulacao exec={self.id_execucao} cenario={self.cenario_simulado!r}>"


class MetricaLatencia(Base):
    """Os três carimbos de tempo de uma priorização (decisão P2).

    São **duas** métricas distintas, e o conflito aparente entre RNF01 e H3 se
    dissolve ao separá-las:

    * `latencia_decisao_ms` (RNF01, < 100 ms p95) — `t_deteccao` → `t_decisao`,
      só `motor.avaliar()`, sem rede e sem I/O. Coluna **gerada** pelo Postgres,
      para que não exista a possibilidade de o cálculo divergir da fonte.
    * `latencia_total_ms` (H3, < 200 ms) — `t_deteccao` → `t_atuacao`. Gravada
      pela aplicação porque `t_atuacao` pode não existir.

    **Na bancada `t_decisao` é nulo** (decisão de 2026-10-05). O UNO decide
    sozinho, e o instante da decisão não é observável à parte (`context/05`
    §4.3): as linhas com `ambiente = 'HARDWARE'` trazem a leitura da tag e o
    `PREEMP_INI`, e `latencia_decisao_ms` sai nula sozinha. Um carimbo inventado
    faria a latência fim-a-fim passar por latência de decisão (RNF01).
    """

    __tablename__ = "metrica_latencia"

    id_latencia: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    id_correlacao: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fk_log: Mapped[int | None] = mapped_column(ForeignKey("log_prioridade.id_log"))
    t_deteccao: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    # Nulo na bancada: o UNO decide sem expor o instante (context/05 §4.3).
    t_decisao: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    t_atuacao: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    latencia_decisao_ms: Mapped[int | None] = mapped_column(
        Integer,
        Computed("(EXTRACT(EPOCH FROM (t_decisao - t_deteccao)) * 1000)::INT", persisted=True),
    )
    latencia_total_ms: Mapped[int | None] = mapped_column(Integer)
    ambiente: Mapped[str] = mapped_column(String(20), nullable=False)  # SIMULACAO | HARDWARE

    def __repr__(self) -> str:
        return f"<MetricaLatencia {self.id_correlacao} {self.ambiente}>"


class MetricaViaTransversal(Base):
    """O custo da preempção nas vias transversais — a evidência de H2.

    A janela (`PRE_EVENTO` / `DURANTE` / `POS_EVENTO`) é o que permite mostrar
    que a compensação de ciclo mitiga o impacto, em vez de apenas afirmá-lo.
    """

    __tablename__ = "metrica_via_transversal"

    id_metrica_tv: Mapped[int] = mapped_column(Integer, primary_key=True)
    fk_execucao: Mapped[int] = mapped_column(
        ForeignKey("execucao_simulacao.id_execucao", ondelete="CASCADE"), nullable=False
    )
    fk_semaforo: Mapped[int] = mapped_column(ForeignKey("semaforo.id_semaforo"), nullable=False)
    tempo_espera_medio: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    fila_maxima: Mapped[int] = mapped_column(Integer, nullable=False)
    veiculos_processados: Mapped[int] = mapped_column(Integer, nullable=False)
    janela: Mapped[str] = mapped_column(String(20), nullable=False)

    execucao: Mapped[ExecucaoSimulacao] = relationship()
    semaforo: Mapped[Semaforo] = relationship()

    def __repr__(self) -> str:
        return f"<MetricaViaTransversal exec={self.fk_execucao} janela={self.janela}>"
