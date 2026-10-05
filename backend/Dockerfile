# Backend FastAPI — context/02 §3.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Camada de dependências separada do código, para aproveitar o cache do Docker.
COPY pyproject.toml README.md alembic.ini ./
COPY backend/ ./backend/
# `db/` entra na imagem porque o serviço `migracoes` do compose roda a partir
# dela: `alembic upgrade head` precisa de db/migrations/, e os seeds de db/seeds/.
COPY db/ ./db/
# `sim/config/cenarios.yaml` valida POST /simulacoes (cenários e seeds reservadas).
# O resto de `sim/` roda no host, onde está o SUMO (context/02 §3).
COPY sim/config/ ./sim/config/

# Modo editável: package-dir aponta para /app/backend, o mesmo caminho montado
# como volume no compose. Assim `--reload` enxerga as alterações do host.
RUN pip install -e .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
