"""Bloco 10: braço PREEMPCAO_ML no enum modo_controle

Entrega 10.7 (`context/09` P19). O braço da política aprendida passa a ser um
modo do experimento como os outros três: o lote o grava em
`execucao_simulacao` e o dashboard pode pedi-lo em `pedido_simulacao`.

O `upgrade` só acrescenta o valor ao ENUM nativo. O Postgres não remove valor de
ENUM, então o `downgrade` recria o tipo com os três valores antigos e converte
as duas colunas que o usam. Ele **recusa** rodar se houver linha com
`PREEMPCAO_ML`: apagar execução ou pedido para conseguir voltar o schema seria
perder evidência em silêncio.

Revision ID: 9d3e6b1f4a27
Revises: e5a17c3d8b42
Create Date: 2026-10-07 21:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9d3e6b1f4a27"
down_revision: str | None = "e5a17c3d8b42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: As tabelas com coluna `modo modo_controle`.
_TABELAS = ("execucao_simulacao", "pedido_simulacao")


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE modo_controle ADD VALUE IF NOT EXISTS 'PREEMPCAO_ML'"))


def downgrade() -> None:
    conexao = op.get_bind()
    for tabela in _TABELAS:
        quantas = conexao.execute(
            sa.text(f"SELECT count(*) FROM {tabela} WHERE modo = 'PREEMPCAO_ML'")
        ).scalar_one()
        if quantas:
            raise RuntimeError(
                f"{tabela} tem {quantas} linha(s) com modo PREEMPCAO_ML; "
                "apague-as de propósito antes de voltar o schema"
            )
    op.execute(sa.text("ALTER TYPE modo_controle RENAME TO modo_controle_antigo"))
    op.execute(
        sa.text("CREATE TYPE modo_controle AS ENUM ('FIXO', 'PREEMPCAO', 'PREEMPCAO_COMPENSADA')")
    )
    for tabela in _TABELAS:
        op.execute(
            sa.text(
                f"ALTER TABLE {tabela} ALTER COLUMN modo TYPE modo_controle "
                "USING modo::text::modo_controle"
            )
        )
    op.execute(sa.text("DROP TYPE modo_controle_antigo"))
