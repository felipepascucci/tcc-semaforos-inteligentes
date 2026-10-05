"""Logs estruturados em JSON — `context/02` §7.

Toda linha sai com os seis campos obrigatórios: `timestamp`, `nivel`, `evento`,
`id_correlacao`, `id_semaforo` e `id_veiculo`. Os três últimos saem `null`
quando não se aplicam, em vez de sumir: um relatório que filtra por
`id_correlacao` não pode depender de o campo existir em cada linha.

`id_correlacao` costuma vir do contexto (`structlog.contextvars`), amarrado por
quem trata a detecção ou o evento da bancada. Assim ele chega a cada linha de
log daquele fluxo sem ser passado de função em função.
"""

from __future__ import annotations

import logging
from collections.abc import MutableMapping
from typing import Any, Final

import structlog

#: Campos que toda linha carrega, presentes mesmo quando nulos.
CAMPOS_OBRIGATORIOS: Final = ("id_correlacao", "id_semaforo", "id_veiculo")


def _nivel(_: Any, metodo: str, evento: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    evento["nivel"] = "WARNING" if metodo == "warn" else metodo.upper()
    return evento


def _obrigatorios(_: Any, __: str, evento: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    for campo in CAMPOS_OBRIGATORIOS:
        valor = evento.get(campo)
        evento[campo] = None if valor is None else str(valor)
    return evento


#: A cadeia de processadores, exposta para os testes conferirem o formato.
PROCESSADORES: Final[list[Any]] = [
    structlog.contextvars.merge_contextvars,
    _nivel,
    structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
    _obrigatorios,
    structlog.processors.format_exc_info,
    structlog.processors.EventRenamer("evento"),
    structlog.processors.JSONRenderer(ensure_ascii=False),
]


def configurar_logs(nivel: str = "INFO") -> None:
    """Configura o structlog do processo: JSON numa linha, a partir de `nivel`."""
    structlog.configure(
        processors=PROCESSADORES,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(nivel.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=False,
    )
