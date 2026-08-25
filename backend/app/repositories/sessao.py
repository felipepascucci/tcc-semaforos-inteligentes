"""Engine e sessões do SQLAlchemy.

`DATABASE_URL` é a única variável de conexão (context/02 §4), e ela significa
coisas diferentes conforme onde o processo roda — o que se resolve sozinho pela
precedência do ambiente:

* **No contêiner**, o `docker-compose.yml` a define no `environment:` do serviço,
  apontando para o host `db` da rede do Docker.
* **No host** — `alembic`, `db/seeds`, `sim/`, `bridge/` — ela vem do `.env`,
  apontando para `localhost`.

`load_dotenv(override=False)` é o que faz isso funcionar: o ambiente real do
processo sempre vence o `.env`, então o valor do compose nunca é sobrescrito
dentro do contêiner.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

RAIZ = Path(__file__).resolve().parents[3]

VARIAVEIS_URL = ("DATABASE_URL",)


def url_do_banco() -> str:
    """Resolve a URL de conexão a partir do ambiente.

    Returns:
        URL no formato SQLAlchemy, ex.: ``postgresql+psycopg://tcc:...@db:5432/semaforo``.

    Raises:
        RuntimeError: se nenhuma das variáveis esperadas estiver definida.
    """
    load_dotenv(RAIZ / ".env", override=False)
    for variavel in VARIAVEIS_URL:
        if url := os.getenv(variavel):
            return url
    mensagem = (
        f"Nenhuma URL de banco no ambiente (tentei: {', '.join(VARIAVEIS_URL)}). "
        "Copie .env.example para .env."
    )
    raise RuntimeError(mensagem)


def criar_engine(url: str | None = None, *, echo: bool = False) -> Engine:
    """Cria o Engine.

    `pool_pre_ping` evita a classe de falha mais comum em execução longa: a
    conexão que o pool guardou foi fechada pelo servidor e só se descobre no meio
    de um flush, já com o lote montado.
    """
    return create_engine(url or url_do_banco(), echo=echo, pool_pre_ping=True, future=True)


def criar_fabrica_sessao(engine: Engine) -> sessionmaker[Session]:
    """Cria a fábrica de sessões.

    `expire_on_commit=False` porque o loop de simulação lê atributos de objetos
    já commitados; com o padrão, cada leitura dispararia um SELECT novo — I/O
    dentro do loop, exatamente o que `context/03` §4.1 proíbe.
    """
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def sessao_de(fabrica: sessionmaker[Session]) -> Iterator[Session]:
    """Abre uma sessão, com commit no sucesso e rollback na exceção."""
    with fabrica() as sessao:
        try:
            yield sessao
            sessao.commit()
        except Exception:
            sessao.rollback()
            raise
