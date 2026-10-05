"""Bloco 6: latência da bancada sem `t_decisao` e pedidos de simulação pela API

Duas decisões da equipe de 2026-10-05 (`context/09`):

- **`metrica_latencia.t_decisao` passa a aceitar nulo.** Na bancada o UNO decide
  sozinho, e o instante da decisão não é observável à parte (`context/05` §4.3).
  As amostras de H3 vão para a tabela com `ambiente = 'HARDWARE'` e
  `t_decisao` nulo, em vez de um carimbo inventado. `latencia_decisao_ms` é
  gerada a partir de `t_decisao` e perde o `NOT NULL` junto: sem isso o Postgres
  recusaria a linha, porque a expressão gerada dá nulo. Na simulação nada muda,
  os dois carimbos continuam presentes.
- **Tabela `pedido_simulacao`.** `POST /simulacoes` não roda o SUMO: o backend
  está no contêiner, e o SUMO fica no host (`context/02` §3). A API grava o
  pedido, e o atendente do host (`python -m sim.controlador.atendente`) o pega,
  roda o executor e grava o desfecho. O `status` é texto com `CHECK`, e não ENUM
  nativo, porque é estado de fila, não domínio do experimento.

Revision ID: c4d81f2b9a60
Revises: 7b2e4d9a1c35
Create Date: 2026-10-05 18:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4d81f2b9a60"
down_revision: str | None = "7b2e4d9a1c35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("metrica_latencia", "t_decisao", nullable=True)
    op.alter_column("metrica_latencia", "latencia_decisao_ms", nullable=True)

    op.create_table(
        "pedido_simulacao",
        sa.Column("id_pedido", sa.Integer(), nullable=False),
        sa.Column("nome_cenario", sa.String(length=50), nullable=False),
        sa.Column(
            "modo",
            postgresql.ENUM(name="modo_controle", create_type=False),
            nullable=False,
        ),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("duracao_s", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=12), server_default="PENDENTE", nullable=False),
        sa.Column("fk_execucao", sa.Integer(), nullable=True),
        sa.Column("mensagem", sa.String(length=200), nullable=True),
        sa.Column("resumo", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "criado_em",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("iniciado_em", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finalizado_em", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDENTE', 'RODANDO', 'CONCLUIDA', 'FALHA')",
            name=op.f("ck_pedido_simulacao_status_conhecido"),
        ),
        sa.CheckConstraint(
            "duracao_s IS NULL OR duracao_s > 0",
            name=op.f("ck_pedido_simulacao_duracao_positiva"),
        ),
        sa.ForeignKeyConstraint(
            ["fk_execucao"],
            ["execucao_simulacao.id_execucao"],
            name=op.f("fk_pedido_simulacao_fk_execucao"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id_pedido", name=op.f("pk_pedido_simulacao")),
    )
    op.create_index(
        "idx_pedido_status_criado", "pedido_simulacao", ["status", "criado_em"], unique=False
    )


def downgrade() -> None:
    op.drop_index("idx_pedido_status_criado", table_name="pedido_simulacao")
    op.drop_table("pedido_simulacao")
    # Linhas da bancada não têm `t_decisao`; voltar ao NOT NULL exige tirá-las.
    op.execute(sa.text("DELETE FROM metrica_latencia WHERE t_decisao IS NULL"))
    op.alter_column("metrica_latencia", "latencia_decisao_ms", nullable=False)
    op.alter_column("metrica_latencia", "t_decisao", nullable=False)
