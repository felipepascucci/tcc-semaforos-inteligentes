"""Base declarativa e convenções compartilhadas dos models.

A convenção de nomes existe para que o Alembic gere migrations estáveis: sem
ela, constraints anônimas ganham nomes atribuídos pelo Postgres, que variam entre
ambientes e produzem diffs espúrios no autogenerate.

Os índices nomeados em `context/03` §3.3 são declarados explicitamente nos
models e mantêm o nome do documento — a convenção só age sobre o que não tem
nome próprio.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import MetaData, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

#: `column_0_N_name` lista **todas** as colunas da constraint, não só a primeira.
#: Num anexo acadêmico isso importa: `uq_fase_semaforo_fk_semaforo` sobre
#: `(fk_semaforo, indice_fase)` faz o leitor concluir que a unicidade é só do
#: semáforo — o oposto do que a constraint faz.
CONVENCAO_NOMES = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base declarativa de todos os models do projeto."""

    metadata = MetaData(naming_convention=CONVENCAO_NOMES)


class CriadoEmMixin:
    """Carimbo de criação, presente na maioria das tabelas de cadastro."""

    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
