"""Execuções de simulação e transições de fase — `context/03` §3.2.

A forma de `estado_semaforo_amostra` é consequência direta da **decisão P5**:
o banco recebe apenas **transições** de fase, e apenas de execuções marcadas como
**exemplares**. Amostrar a 10 Hz daria ~173 milhões de linhas.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import ESTADO_SINAL, MODO_CONTROLE, EstadoSinal, ModoControle

if TYPE_CHECKING:
    from app.models.semaforo import Semaforo


class ExecucaoSimulacao(Base):
    """Uma execução de cenário — a unidade de reprodutibilidade do experimento.

    `versao_codigo` e `parametros` não são metadados decorativos: sem eles a
    execução não é reproduzível e o resultado não é defensável na banca
    (`context/03` §4.3). A restrição única em (cenário, modo, seed) é o que
    garante o **pareamento por seed** entre os três braços.
    """

    __tablename__ = "execucao_simulacao"
    __table_args__ = (UniqueConstraint("nome_cenario", "modo", "seed"),)

    id_execucao: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome_cenario: Mapped[str] = mapped_column(String(50), nullable=False)
    modo: Mapped[ModoControle] = mapped_column(MODO_CONTROLE, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    duracao_s: Mapped[int] = mapped_column(Integer, nullable=False)
    arquivo_rede: Mapped[str] = mapped_column(String(120), nullable=False)
    # `git rev-parse --short HEAD`, com `-suja` se há código fora do commit.
    versao_codigo: Mapped[str | None] = mapped_column(String(40))
    parametros: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # P5: só execuções exemplares gravam transições no banco. Uma por par
    # (cenário x modo) — as que geram as figuras. As demais das 600 ficam em CSV.
    exemplar: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    iniciada_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    finalizada_em: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    transicoes: Mapped[list[EstadoSemaforoAmostra]] = relationship(
        back_populates="execucao", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ExecucaoSimulacao {self.nome_cenario}/{self.modo}/seed={self.seed}>"


class EstadoSemaforoAmostra(Base):
    """Uma **transição** de fase, não uma amostra periódica (decisão P5).

    O nome da tabela vem do texto original e foi preservado; a semântica mudou e
    está registrada em `context/03` §3.2. `t_simulacao` marca o instante da
    virada.

    `fase_anterior` e `duracao_fase_anterior_s` são o que torna a verificação dos
    invariantes uma consulta SQL em vez de uma série temporal densa:
    I2/I3 pela sequência de transições, I4 comparando
    `duracao_fase_anterior_s` com `verde_min` (`context/06` §3).
    """

    __tablename__ = "estado_semaforo_amostra"
    __table_args__ = (Index("idx_amostra_exec_t", "fk_execucao", "t_simulacao"),)

    id_amostra: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    fk_execucao: Mapped[int] = mapped_column(
        ForeignKey("execucao_simulacao.id_execucao", ondelete="CASCADE"), nullable=False
    )
    fk_semaforo: Mapped[int] = mapped_column(ForeignKey("semaforo.id_semaforo"), nullable=False)
    t_simulacao: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    fase_anterior: Mapped[int | None] = mapped_column(Integer)  # NULL na primeira transição
    fase: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[EstadoSinal] = mapped_column(ESTADO_SINAL, nullable=False)
    em_preempcao: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    fila_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    duracao_fase_anterior_s: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))

    execucao: Mapped[ExecucaoSimulacao] = relationship(back_populates="transicoes")
    semaforo: Mapped[Semaforo] = relationship()

    def __repr__(self) -> str:
        return f"<Transicao exec={self.fk_execucao} t={self.t_simulacao} fase={self.fase}>"


#: Os estados de um pedido, na ordem em que ele passa por eles.
STATUS_PEDIDO = ("PENDENTE", "RODANDO", "CONCLUIDA", "FALHA")


class PedidoSimulacao(Base):
    """Uma execução pedida pela API, à espera do atendente do host (Bloco 6).

    O backend roda no contêiner e o SUMO fica no host (`context/02` §3), então
    `POST /simulacoes` não roda nada: grava o pedido, e
    `python -m sim.controlador.atendente` o pega, roda o executor e grava o
    desfecho aqui. É demonstração, não experimento: a API recusa as seeds
    reservadas ao Bloco 8 e à calibração, e o atendente nunca escreve em
    `analysis/data/` (decisão de 2026-10-05).

    `resumo` guarda o que o executor mediu nessa execução, para
    `GET /simulacoes/{id}`. Não é fonte de número do capítulo 5.
    """

    __tablename__ = "pedido_simulacao"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDENTE', 'RODANDO', 'CONCLUIDA', 'FALHA')", name="status_conhecido"
        ),
        CheckConstraint("duracao_s IS NULL OR duracao_s > 0", name="duracao_positiva"),
        CheckConstraint(
            "velocidade IS NULL OR velocidade IN (1, 2, 5, 10)", name="velocidade_conhecida"
        ),
        # O atendente procura sempre "o pendente mais antigo".
        Index("idx_pedido_status_criado", "status", "criado_em"),
    )

    id_pedido: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome_cenario: Mapped[str] = mapped_column(String(50), nullable=False)
    modo: Mapped[ModoControle] = mapped_column(MODO_CONTROLE, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    # Nulo usa a duração de cenarios.yaml.
    duracao_s: Mapped[int | None] = mapped_column(Integer)
    # Múltiplo do tempo real em que o atendente roda (Bloco 7). Nulo é o máximo
    # que a máquina permite. Não muda o resultado: o ritmo fica fora do SUMO.
    velocidade: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default="PENDENTE")
    fk_execucao: Mapped[int | None] = mapped_column(
        ForeignKey("execucao_simulacao.id_execucao", ondelete="SET NULL")
    )
    mensagem: Mapped[str | None] = mapped_column(String(200))
    resumo: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    iniciado_em: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    finalizado_em: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    execucao: Mapped[ExecucaoSimulacao | None] = relationship()

    def __repr__(self) -> str:
        return f"<PedidoSimulacao {self.id_pedido} {self.nome_cenario}/{self.modo} {self.status}>"
