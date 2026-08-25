# Backend FastAPI — context/02 §3.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Camada de dependências separada do código, para aproveitar o cache do Docker.
COPY pyproject.toml README.md ./
COPY backend/ ./backend/

# Modo editável: package-dir aponta para /app/backend, o mesmo caminho montado
# como volume no compose. Assim `--reload` enxerga as alterações do host.
RUN pip install -e .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
