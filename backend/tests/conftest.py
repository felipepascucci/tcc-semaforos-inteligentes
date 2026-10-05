"""Banco efêmero para os testes de integração (`db/` e `api/`).

`context/06` §7 é explícito: banco de teste efêmero, **nunca** o de
desenvolvimento. Um teste que trunca tabelas no banco errado custa uma tarde de
reseed no meio da semana de entrega.

O contêiner sobe uma vez por sessão de teste (é o passo caro, ~5 s) e cada teste
recebe o schema recém-migrado. As fixtures só sobem o contêiner quando um teste
as pede, então a suíte sem `-m banco` não precisa de Docker.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.repositories.sessao import criar_engine, criar_fabrica_sessao

RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def url_banco_efemero() -> Iterator[str]:
    """Sobe um Postgres 16 descartável e devolve a URL de conexão."""
    testcontainers = pytest.importorskip(
        "testcontainers.postgres", reason="testcontainers não instalado"
    )
    with testcontainers.PostgresContainer("postgres:16-alpine", driver="psycopg") as contêiner:
        yield contêiner.get_connection_url()


@pytest.fixture(scope="session")
def _schema_migrado(url_banco_efemero: str) -> str:
    """Aplica `alembic upgrade head` no banco efêmero."""
    configuracao = Config(str(RAIZ / "alembic.ini"))
    configuracao.set_main_option("script_location", str(RAIZ / "db" / "migrations"))
    os.environ["ALEMBIC_DATABASE_URL"] = url_banco_efemero
    command.upgrade(configuracao, "head")
    return url_banco_efemero


@pytest.fixture(scope="session")
def engine(_schema_migrado: str) -> Iterator[Engine]:
    motor = criar_engine(_schema_migrado)
    yield motor
    motor.dispose()


@pytest.fixture(scope="session")
def fabrica_sessao(engine: Engine) -> sessionmaker[Session]:
    return criar_fabrica_sessao(engine)


@pytest.fixture
def sessao(fabrica_sessao: sessionmaker[Session], engine: Engine) -> Iterator[Session]:
    """Uma sessão por teste, sobre um banco limpo.

    O TRUNCATE ... CASCADE roda **antes** de cada teste em vez de depois: se um
    teste falhar no meio, o banco fica com os dados do erro disponíveis para
    inspeção, e o teste seguinte ainda parte de um estado limpo.
    """
    tabelas = (
        "metrica_latencia, log_prioridade, metrica_simulacao, metrica_via_transversal, "
        "estado_semaforo_amostra, deteccao, ocorrencia, pedido_simulacao, execucao_simulacao, "
        "dispositivo_iot, tag_rfid, fase_semaforo, veiculo_emergencia, semaforo"
    )
    with engine.begin() as conexao:
        conexao.execute(text(f"TRUNCATE {tabelas} RESTART IDENTITY CASCADE"))

    with fabrica_sessao() as sessao_teste:
        yield sessao_teste
