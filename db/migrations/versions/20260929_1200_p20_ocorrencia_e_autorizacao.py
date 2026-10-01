"""P20: ocorrência ativa e autorização da detecção

Emergência passa a ser **estado declarado**: a preempção exige tag reconhecida e
ocorrência aberta pela central de despacho (`context/09` P20). Esta migration cria
a tabela `ocorrencia` e acrescenta a `deteccao` o resultado da confirmação.

- `ocorrencia.criticidade` é ordinal, 1 = mais crítico, e decide E8 antes do
  tipo. `SMALLINT` com `CHECK`, não ENUM: a escala é numérica por natureza.
- O índice único parcial garante **no máximo uma ocorrência aberta por veículo**
  no próprio banco — duas criticidades concorrentes para o mesmo VE seriam
  ambíguas para o motor.
- `deteccao.autorizado` nasce `false` nas linhas existentes: nenhuma detecção
  anterior foi confirmada por ocorrência, porque a regra não existia.

Revision ID: 3f9c2a71d5e8
Revises: eb4834072797
Create Date: 2026-09-29 12:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "3f9c2a71d5e8"
down_revision: str | None = "eb4834072797"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ocorrencia",
        sa.Column("id_ocorrencia", sa.Integer(), nullable=False),
        sa.Column("fk_veiculo", sa.Integer(), nullable=False),
        sa.Column("criticidade", sa.SmallInteger(), nullable=False),
        sa.Column("descricao", sa.String(length=200), nullable=True),
        sa.Column("origem", sa.String(length=20), server_default="CENTRAL", nullable=False),
        sa.Column(
            "aberta_em",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("encerrada_em", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "criticidade BETWEEN 1 AND 3", name=op.f("ck_ocorrencia_criticidade_na_escala")
        ),
        sa.CheckConstraint(
            "encerrada_em IS NULL OR encerrada_em >= aberta_em",
            name=op.f("ck_ocorrencia_encerra_depois_de_abrir"),
        ),
        sa.ForeignKeyConstraint(
            ["fk_veiculo"], ["veiculo_emergencia.id_veiculo"], name=op.f("fk_ocorrencia_fk_veiculo")
        ),
        sa.PrimaryKeyConstraint("id_ocorrencia", name=op.f("pk_ocorrencia")),
    )
    op.create_index(
        "uq_ocorrencia_aberta_por_veiculo",
        "ocorrencia",
        ["fk_veiculo"],
        unique=True,
        postgresql_where=sa.text("encerrada_em IS NULL"),
    )

    op.add_column(
        "deteccao",
        sa.Column("autorizado", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("deteccao", sa.Column("fk_ocorrencia", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_deteccao_fk_ocorrencia"),
        "deteccao",
        "ocorrencia",
        ["fk_ocorrencia"],
        ["id_ocorrencia"],
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_deteccao_fk_ocorrencia"), "deteccao", type_="foreignkey")
    op.drop_column("deteccao", "fk_ocorrencia")
    op.drop_column("deteccao", "autorizado")
    op.drop_index("uq_ocorrencia_aberta_por_veiculo", table_name="ocorrencia")
    op.drop_table("ocorrencia")
