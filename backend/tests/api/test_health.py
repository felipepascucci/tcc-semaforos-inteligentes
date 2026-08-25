"""Contrato mínimo do `/health` (context/01 §7, context/02 §7)."""

import pytest
from app.main import app
from fastapi.testclient import TestClient

CAMPOS_OBRIGATORIOS = {
    "estado",
    "versao",
    "perfil_parametros",
    "banco",
    "adaptador_sumo",
    "adaptador_hardware",
    "watchdog_serial",
}


@pytest.fixture
def cliente() -> TestClient:
    return TestClient(app)


def test_health_reporta_todos_os_componentes(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    resposta = cliente.get("/api/v1/health")
    corpo = resposta.json()

    assert set(corpo) >= CAMPOS_OBRIGATORIOS
    # Sem DATABASE_URL o backend é honesto: degradado, não "ok".
    assert corpo["banco"] == "nao_configurado"
    assert corpo["estado"] == "degradado"
    assert resposta.status_code == 503


def test_health_vive_sob_o_prefixo_da_api(cliente: TestClient) -> None:
    """A base é /api/v1 — não há rota solta na raiz."""
    assert cliente.get("/health").status_code == 404
