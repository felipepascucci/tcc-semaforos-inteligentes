"""Logs estruturados — os seis campos obrigatórios de `context/02` §7."""

from __future__ import annotations

import json
from typing import Any

import structlog

from app.logs import PROCESSADORES

OBRIGATORIOS = {"timestamp", "nivel", "evento", "id_correlacao", "id_semaforo", "id_veiculo"}


def _linha(metodo: str, **campos: Any) -> dict[str, Any]:
    evento: Any = dict(campos)
    for processador in PROCESSADORES:
        evento = processador(None, metodo, evento)
    return json.loads(evento)  # type: ignore[no-any-return]


def test_toda_linha_tem_os_seis_campos_mesmo_nulos() -> None:
    linha = _linha("info", event="backend_no_ar")

    assert set(linha) >= OBRIGATORIOS
    assert (linha["evento"], linha["nivel"]) == ("backend_no_ar", "INFO")
    assert linha["id_correlacao"] is None and linha["id_veiculo"] is None


def test_id_de_correlacao_vem_do_contexto_do_fluxo() -> None:
    structlog.contextvars.bind_contextvars(id_correlacao="0f3c-teste")
    try:
        linha = _linha("warning", event="deteccao_negada", id_veiculo=3)
    finally:
        structlog.contextvars.clear_contextvars()

    assert (linha["id_correlacao"], linha["id_veiculo"], linha["nivel"]) == (
        "0f3c-teste",
        "3",
        "WARNING",
    )
