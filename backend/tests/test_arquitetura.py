"""RNF07 — `core/` não importa framework nem I/O (`context/06` §2).

Este teste é barato e evita a erosão da regra principal do projeto
(`context/01` §1). Ele não checa estilo: checa que o motor avaliado na
simulação é agnóstico ao atuador, e que o modelo de P19 entra nele como dado,
com inferência pura (`core/priorizacao/politica.py`), e não como framework.
Desde 2026-10-05 o protótipo não roda o motor (`context/00` §3), então o teste
não sustenta mais a frase "o mesmo motor roda na simulação e no protótipo".
Sustenta o que continua valendo: o núcleo não sabe de que lado está o atuador.

A verificação é via AST, não por convenção nem por revisão: um `import traci`
dentro de `core/` quebra a suite, e quem escreveu descobre em segundos em vez de
descobrir na banca.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

RAIZ_CORE = Path(__file__).resolve().parents[1] / "core"

#: Proibidos por `context/01` §1 e pelo contrato §2.
FRAMEWORKS_E_IO = {
    "traci",
    "libsumo",
    "sumolib",
    "serial",  # pyserial
    "sqlalchemy",
    "alembic",
    "psycopg",
    "fastapi",
    "starlette",
    "uvicorn",
    "pydantic",
    "httpx",
    "requests",
    "yaml",  # ler arquivo é I/O: a carga vive em adapters/configuracao.py
    "structlog",
    "logging",
    "socket",
    "sqlite3",
    "subprocess",
    "urllib",
}

#: `core/` também não pode depender das camadas de fora.
CAMADAS_EXTERNAS = {"app", "adapters", "sim", "bridge", "db", "analysis"}

#: Funções que fazem I/O sem precisar de import.
CHAMADAS_PROIBIDAS = {"open", "input", "print"}


def _modulos_do_core() -> list[Path]:
    return sorted(RAIZ_CORE.rglob("*.py"))


def _raiz_do_modulo(nome: str) -> str:
    return nome.split(".")[0]


def _importes(arvore: ast.AST) -> set[str]:
    encontrados: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            encontrados.update(_raiz_do_modulo(alias.name) for alias in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
            encontrados.add(_raiz_do_modulo(no.module))
    return encontrados


def test_existe_codigo_para_verificar() -> None:
    """Guarda contra o teste passar por não achar arquivo nenhum."""
    assert len(_modulos_do_core()) >= 8


@pytest.mark.parametrize("caminho", _modulos_do_core(), ids=lambda p: p.name)
def test_modulo_do_core_nao_importa_framework_nem_io(caminho: Path) -> None:
    arvore = ast.parse(caminho.read_text(encoding="utf-8"), filename=str(caminho))
    proibidos = _importes(arvore) & FRAMEWORKS_E_IO

    assert not proibidos, (
        f"{caminho.relative_to(RAIZ_CORE.parent)} importa {sorted(proibidos)}. "
        "O núcleo precisa ser testável sem SUMO instalado e sem hardware ligado "
        "(context/01 §1). Se precisou disso, o desenho está errado — mova para "
        "adapters/."
    )


@pytest.mark.parametrize("caminho", _modulos_do_core(), ids=lambda p: p.name)
def test_modulo_do_core_nao_depende_das_camadas_de_fora(caminho: Path) -> None:
    arvore = ast.parse(caminho.read_text(encoding="utf-8"), filename=str(caminho))
    proibidos = _importes(arvore) & CAMADAS_EXTERNAS

    assert not proibidos, (
        f"{caminho.relative_to(RAIZ_CORE.parent)} importa {sorted(proibidos)}. "
        "A dependência é sempre de fora para dentro: adapters e app conhecem o "
        "core, nunca o contrário."
    )


@pytest.mark.parametrize("caminho", _modulos_do_core(), ids=lambda p: p.name)
def test_modulo_do_core_nao_chama_io_direto(caminho: Path) -> None:
    """`open()` e `print()` não precisam de import — e escapariam da checagem acima."""
    arvore = ast.parse(caminho.read_text(encoding="utf-8"), filename=str(caminho))

    encontradas = {
        no.func.id
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call)
        and isinstance(no.func, ast.Name)
        and no.func.id in CHAMADAS_PROIBIDAS
    }

    assert not encontradas, (
        f"{caminho.relative_to(RAIZ_CORE.parent)} chama {sorted(encontradas)}. "
        "O núcleo não lê, não escreve e não imprime: ele recebe estado e devolve "
        "comandos."
    )


def test_motor_nao_usa_distancia_euclidiana() -> None:
    """E1 exige distância **ao longo da rota** (`context/01` §5.2).

    `math.dist` e `math.hypot` sobre a posição do VE dariam a distância em linha
    reta, e priorizariam um cruzamento perto no mapa por onde o veículo nem vai
    passar. É o erro clássico que o próprio `context/` manda evitar pelo nome.
    """
    for caminho in _modulos_do_core():
        arvore = ast.parse(caminho.read_text(encoding="utf-8"), filename=str(caminho))
        for no in ast.walk(arvore):
            if isinstance(no, ast.Attribute) and no.attr in {"dist", "hypot"}:
                pytest.fail(
                    f"{caminho.name} usa math.{no.attr} — E1 exige distância ao "
                    "longo da rota, nunca euclidiana"
                )
