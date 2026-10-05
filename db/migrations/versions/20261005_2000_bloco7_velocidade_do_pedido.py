"""Bloco 7: velocidade da simulação pedida pelo dashboard

Decisão da equipe de 2026-10-05 (`context/09`). Sem ritmo, o atendente roda a
simulação o mais rápido que a máquina permite, ~50x o tempo real, e o VE cruza
o mapa do dashboard em segundos. O pedido passa a dizer a que velocidade rodar:
1x, 2x, 5x ou 10x o tempo real. Nulo é a velocidade máxima, que é como os
pedidos anteriores rodaram.

O ritmo é imposto fora do trecho cronometrado do laço, e o SUMO não sabe dele: a
mesma seed dá o mesmo resultado em qualquer velocidade, e a latência de decisão
(RNF01) não muda.

Revision ID: e5a17c3d8b42
Revises: c4d81f2b9a60
Create Date: 2026-10-05 20:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5a17c3d8b42"
down_revision: str | None = "c4d81f2b9a60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("pedido_simulacao", sa.Column("velocidade", sa.SmallInteger(), nullable=True))
    op.create_check_constraint(
        op.f("ck_pedido_simulacao_velocidade_conhecida"),
        "pedido_simulacao",
        "velocidade IS NULL OR velocidade IN (1, 2, 5, 10)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_pedido_simulacao_velocidade_conhecida"), "pedido_simulacao", type_="check"
    )
    op.drop_column("pedido_simulacao", "velocidade")
