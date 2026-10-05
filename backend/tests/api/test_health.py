"""Contrato do `/health` (`context/01` §7, `context/02` §7)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.configuracao import Configuracao
from app.main import criar_app

CAMPOS_OBRIGATORIOS = {
    "estado",
    "versao",
    "perfil_parametros",
    "banco",
    "ponte",
    "uno_respondendo",
    "simulacao_ao_vivo",
    "clientes_websocket",
}


def test_sem_banco_o_health_e_honesto() -> None:
    """Sem DATABASE_URL: degradado e 503, não um verde falso."""
    with TestClient(criar_app(Configuracao())) as cliente:
        resposta = cliente.get("/api/v1/health")

    corpo = resposta.json()
    assert set(corpo) >= CAMPOS_OBRIGATORIOS
    assert resposta.status_code == 503
    assert (corpo["estado"], corpo["banco"]) == ("degradado", "nao_configurado")
    assert (corpo["ponte"], corpo["uno_respondendo"]) == ("nao_configurado", None)
    assert corpo["simulacao_ao_vivo"] is False


def test_ponte_fora_do_ar_nao_derruba_o_backend() -> None:
    """A bancada pode não estar na mesa: o backend sobe e mostra `ponte: falha`."""
    config = Configuracao(url_ponte="http://127.0.0.1:9", intervalo_leitura_ponte_s=0.01)
    with TestClient(criar_app(config)) as cliente:
        corpo = cliente.get("/api/v1/health").json()

    assert corpo["ponte"] == "falha"
    assert corpo["uno_respondendo"] is False


@pytest.mark.banco
def test_com_banco_o_health_e_ok(cliente: TestClient) -> None:
    resposta = cliente.get("/api/v1/health")

    assert resposta.status_code == 200
    assert resposta.json()["banco"] == "ok"


def test_health_vive_sob_o_prefixo_da_api() -> None:
    """A base é /api/v1 — não há rota solta na raiz."""
    with TestClient(criar_app(Configuracao())) as cliente:
        assert cliente.get("/health").status_code == 404
