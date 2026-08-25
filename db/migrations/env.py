"""Ambiente de execução das migrations Alembic.

A URL do banco vem do ambiente, nunca do `alembic.ini` — credencial em arquivo
versionado é exatamente o que `context/02` §6 manda evitar.

1. ``ALEMBIC_DATABASE_URL`` — escape explícito, usado pelo banco efêmero dos
   testes de integração para nunca migrar o banco de desenvolvimento por engano.
2. ``DATABASE_URL``         — o normal (context/02 §4).
"""

from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

from app.models import Base

RAIZ = Path(__file__).resolve().parents[2]
load_dotenv(RAIZ / ".env")

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url_do_banco() -> str:
    for variavel in ("ALEMBIC_DATABASE_URL", "DATABASE_URL"):
        if url := os.getenv(variavel):
            return url
    mensagem = (
        "Nenhuma URL de banco no ambiente. Copie .env.example para .env "
        "(ou defina ALEMBIC_DATABASE_URL) antes de rodar as migrations."
    )
    raise RuntimeError(mensagem)


def _incluir_objeto(objeto: object, nome: str | None, tipo: str, *_: object) -> bool:
    """Mantém fora do autogenerate o que não pertence ao schema da aplicação."""
    return not (tipo == "table" and nome == "alembic_version")


def executar_offline() -> None:
    """Gera o SQL sem conectar — útil para revisar o DDL antes de aplicar."""
    context.configure(
        url=_url_do_banco(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=_incluir_objeto,
    )
    with context.begin_transaction():
        context.run_migrations()


def executar_online() -> None:
    """Aplica as migrations contra o banco configurado."""
    secao = config.get_section(config.config_ini_section, {})
    secao["sqlalchemy.url"] = _url_do_banco()

    conectavel = engine_from_config(secao, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with conectavel.connect() as conexao:
        context.configure(
            connection=conexao,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=_incluir_objeto,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    executar_offline()
else:
    executar_online()
