"""Especificação dos casos de teste — `analysis/gerar_casos_de_teste.py`."""

from __future__ import annotations

from pathlib import Path

from analysis.gerar_casos_de_teste import (
    DESTINO,
    arquivos_citados,
    arquivos_de_teste,
    casos_frontend,
    casos_python,
    gerar,
)


def test_casos_de_teste_versionado_esta_em_dia() -> None:
    """Mudou um teste ou `context/06` e não regerou? `python -m analysis.gerar_casos_de_teste`."""
    assert DESTINO.read_text(encoding="utf-8") == gerar()


def test_toda_citacao_de_06_acha_arquivo() -> None:
    assert "arquivo não encontrado" not in gerar()


def test_casos_python_pega_funcoes_e_classes(tmp_path: Path) -> None:
    arquivo = tmp_path / "test_artificial.py"
    arquivo.write_text(
        '"""Módulo."""\n\n'
        "def test_um() -> None:\n"
        '    """Primeira linha.\n\n    Resto."""\n\n'
        "async def test_dois() -> None:\n    pass\n\n"
        "def auxiliar() -> None:\n    pass\n\n"
        "class TestGrupo:\n    def test_tres(self) -> None:\n        pass\n",
        encoding="utf-8",
    )
    casos = casos_python(arquivo)
    assert [(c.nome, c.descricao) for c in casos] == [
        ("test_um", "Primeira linha."),
        ("test_dois", ""),
        ("TestGrupo::test_tres", ""),
    ]


def test_casos_frontend_pega_it_com_describe(tmp_path: Path) -> None:
    arquivo = tmp_path / "x.test.ts"
    arquivo.write_text(
        'describe("grupo", () => {\n  it("faz A", () => {});\n  test(\'faz B\', () => {});\n});\n',
        encoding="utf-8",
    )
    assert [c.nome for c in casos_frontend(arquivo)] == ["grupo > faz A", "grupo > faz B"]


def test_citacao_pelo_padrao_do_frontend() -> None:
    nomes = {
        p.name for p in arquivos_citados("frontend/src/stream/*.test.ts(x)", arquivos_de_teste())
    }
    assert nomes == {"estado.test.ts", "useStream.test.tsx"}
