"""`versao_do_codigo()` marca árvore suja — `sim/controlador/executor.py`.

Pendência da 10.4 que valia antes do Bloco 8 (`context/09`): a versão gravada em
cada execução lia só o `HEAD`, e uma execução com código fora do commit saía
com a versão de um commit que não era o dela. Testado num repositório
temporário, não no do projeto.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sim.controlador.executor import versao_do_codigo


def _git(raiz: Path, *argumentos: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=teste", "-c", "user.email=teste@exemplo", *argumentos],
        cwd=raiz,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def repositorio(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    for caminho in ("sim/motor.py", "analysis/data/execucoes.csv", "docs/plano.md", "README.md"):
        (tmp_path / caminho).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / caminho).write_text("versão 1\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("saida/\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "inicial")
    return tmp_path


def _head(raiz: Path) -> str:
    return _git(raiz, "rev-parse", "--short", "HEAD")


def test_arvore_limpa_da_o_commit(repositorio: Path) -> None:
    assert versao_do_codigo(repositorio) == _head(repositorio)


def test_codigo_modificado_marca_suja(repositorio: Path) -> None:
    (repositorio / "sim" / "motor.py").write_text("versão 2\n", encoding="utf-8")

    assert versao_do_codigo(repositorio) == f"{_head(repositorio)}-suja"


def test_arquivo_novo_de_codigo_marca_suja(repositorio: Path) -> None:
    (repositorio / "sim" / "politica_nova.py").write_text("x = 1\n", encoding="utf-8")

    assert versao_do_codigo(repositorio).endswith("-suja")


def test_mudanca_staged_marca_suja(repositorio: Path) -> None:
    (repositorio / "sim" / "motor.py").write_text("versão 2\n", encoding="utf-8")
    _git(repositorio, "add", ".")

    assert versao_do_codigo(repositorio).endswith("-suja")


def test_dados_documentacao_e_ignorados_nao_contam(repositorio: Path) -> None:
    """O lote escreve em `analysis/data/` no meio da rodada: isso não suja a versão."""
    (repositorio / "analysis" / "data" / "execucoes.csv").write_text("linha\n", encoding="utf-8")
    (repositorio / "analysis" / "data" / "nova.csv").write_text("linha\n", encoding="utf-8")
    (repositorio / "docs" / "plano.md").write_text("versão 2\n", encoding="utf-8")
    (repositorio / "README.md").write_text("versão 2\n", encoding="utf-8")
    (repositorio / "saida").mkdir()
    (repositorio / "saida" / "tripinfo.xml").write_text("<x/>\n", encoding="utf-8")

    assert versao_do_codigo(repositorio) == _head(repositorio)


def test_fora_de_repositorio(tmp_path: Path) -> None:
    assert versao_do_codigo(tmp_path) == "desconhecida"
