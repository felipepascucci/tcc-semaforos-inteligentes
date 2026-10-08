"""O diagrama de infraestrutura acompanha o compose (`context/02` §3 e §8)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
DIAGRAMA = RAIZ / "docs" / "diagramas" / "infraestrutura.puml"


def _servicos_do_compose() -> list[str]:
    with (RAIZ / "docker-compose.yml").open(encoding="utf-8") as arquivo:
        return sorted(yaml.safe_load(arquivo)["services"])


def test_todo_servico_do_compose_esta_no_diagrama() -> None:
    """Acrescentou um serviço ao compose? Ele entra em `infraestrutura.puml`."""
    texto = DIAGRAMA.read_text(encoding="utf-8")
    declarados = set(re.findall(r'"\s*([a-z]+)\\n', texto))
    assert set(_servicos_do_compose()) <= declarados


def test_dois_diagramas_local_e_aws() -> None:
    texto = DIAGRAMA.read_text(encoding="utf-8")
    assert re.findall(r"^@startuml (\S+)$", texto, re.MULTILINE) == [
        "infraestrutura",
        "infraestrutura_aws",
    ]
    assert texto.count("@enduml") == 2
