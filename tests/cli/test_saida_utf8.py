"""Os `python -m` do projeto não caem com a saída redirecionada no Windows.

Com a saída em arquivo ou pipe, o Python do Windows escreve em cp1252, que não
tem `≥`, `→`, `λ` nem `δ`. O `--help` de `bridge.demo`, `analysis.resumo_bancada`
e `analysis.treino_politica` levantava `UnicodeEncodeError` assim. A correção é
`adapters.terminal.saida_utf8()` no início de todo `main()`.

O teste força `PYTHONIOENCODING=cp1252`, que reproduz o caso do Windows em
qualquer sistema, roda cada `--help` com a saída capturada e confere que o texto
chega inteiro, em UTF-8.
"""

from __future__ import annotations

import ast
import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

from adapters.terminal import saida_utf8

RAIZ = Path(__file__).resolve().parents[2]

#: Pastas dos `python -m` de linha de comando.
PASTAS = ("analysis", "bridge", "sim", "db")

#: Têm `__main__` mas não `--help`: rodá-los com `--help` faria o trabalho deles.
SEM_ARGPARSE = {"sim.rede.exportar_mapa"}

#: O caractere fora do cp1252 que derrubava cada `--help` (achado de 2026-10-07).
QUEBRAVAM = {
    "bridge.demo": "→",
    "analysis.resumo_bancada": "≥",
    "analysis.treino_politica": "λ",
}


def _executaveis() -> list[str]:
    """Os módulos com `if __name__ == "__main__"`, fora das pastas de teste."""
    modulos = []
    for pasta in PASTAS:
        for caminho in sorted((RAIZ / pasta).rglob("*.py")):
            if "tests" in caminho.parts:
                continue
            if '__name__ == "__main__"' in caminho.read_text(encoding="utf-8"):
                modulos.append(".".join(caminho.relative_to(RAIZ).with_suffix("").parts))
    return modulos


EXECUTAVEIS = _executaveis()


def test_achou_os_executaveis() -> None:
    """Guarda contra o teste passar por não achar módulo nenhum."""
    assert len(EXECUTAVEIS) >= 20
    assert set(QUEBRAVAM) <= set(EXECUTAVEIS)


@pytest.mark.parametrize("modulo", EXECUTAVEIS)
def test_main_de_todo_executavel_chama_saida_utf8(modulo: str) -> None:
    """A correção vale para todo `python -m`, inclusive os que ainda vão surgir."""
    caminho = RAIZ / Path(*modulo.split(".")).with_suffix(".py")
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    main = next(no for no in arvore.body if isinstance(no, ast.FunctionDef) and no.name == "main")
    chamadas = {
        no.func.id
        for no in ast.walk(main)
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
    }

    assert "saida_utf8" in chamadas


@pytest.mark.parametrize("modulo", sorted(set(EXECUTAVEIS) - SEM_ARGPARSE))
def test_help_com_saida_capturada_em_cp1252_nao_cai(modulo: str) -> None:
    ambiente = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    ambiente.pop("PYTHONUTF8", None)
    resultado = subprocess.run(
        [sys.executable, "-m", modulo, "--help"],
        cwd=RAIZ,
        env=ambiente,
        capture_output=True,
        timeout=120,
        check=False,
    )
    erro = resultado.stderr.decode("utf-8", errors="replace")
    if "ModuleNotFoundError" in erro:
        pytest.skip(f"dependência opcional ausente: {erro.strip().splitlines()[-1]}")

    assert resultado.returncode == 0, erro
    texto = resultado.stdout.decode("utf-8")
    assert "usage:" in texto
    if modulo in QUEBRAVAM:
        assert QUEBRAVAM[modulo] in texto


def test_saida_utf8_troca_a_codificacao_dos_dois_fluxos(monkeypatch: pytest.MonkeyPatch) -> None:
    brutos = {nome: io.BytesIO() for nome in ("stdout", "stderr")}
    for nome, bruto in brutos.items():
        monkeypatch.setattr(sys, nome, io.TextIOWrapper(bruto, encoding="cp1252"))

    saida_utf8()
    for nome in brutos:
        fluxo = getattr(sys, nome)
        fluxo.write("λ ≥ →")
        fluxo.flush()

    assert all(bruto.getvalue() == "λ ≥ →".encode() for bruto in brutos.values())
