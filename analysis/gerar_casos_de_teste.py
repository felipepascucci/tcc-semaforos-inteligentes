"""Especificação dos casos de teste — `docs/casos_de_teste.md` (`context/08` §5).

    python -m analysis.gerar_casos_de_teste

Gerada, e não escrita à mão, para não divergir do que existe:

* **o que se testa e o critério** vêm de `context/06` — a tabela de
  rastreabilidade (§2), os invariantes (§3) e o checklist da bancada (§6),
  lidos do arquivo;
* **os casos de cada arquivo** vêm da própria suíte: as funções `test_*` dos
  arquivos Python, lidas pelo AST, com a primeira linha da docstring, e os
  `it(...)`/`test(...)` dos `*.test.ts(x)` do frontend.

`analysis/tests/test_gerar_casos_de_teste.py` falha se o arquivo versionado
ficar para trás de um teste ou de `06`. O resultado de cada caso (passou ou
não) não está aqui: é do relatório de validação, que roda as suítes.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from adapters.terminal import saida_utf8
from analysis.gerar_relatorio_validacao import (
    TESTES_DOS_INVARIANTES,
    Requisito,
    ler_checklist,
    ler_rastreabilidade,
    tabela_da_secao,
)

RAIZ: Final = Path(__file__).resolve().parents[1]
DESTINO: Final = RAIZ / "docs" / "casos_de_teste.md"
CONTEXTO_06: Final = RAIZ / "context" / "06-testes-e-validacao.md"

#: Onde moram os testes (as `testpaths` do `pyproject.toml`, e o frontend).
PASTAS_DE_TESTE: Final = ("backend/tests", "bridge/tests", "sim/tests", "analysis/tests", "tests")
PASTA_FRONTEND: Final = "frontend/src"

#: A linha dos invariantes "no firmware" de `06` §3: o firmware contra o dublê e o verificador.
TESTES_DO_FIRMWARE: Final = (
    "tests/firmware/test_firmware_uno.py",
    "bridge/tests/test_verificar.py",
)

#: Itens do checklist que são julgados pelo dado gravado, e por qual módulo.
JULGADO_POR: Final = {
    **dict.fromkeys(("1", "2", "3", "5", "5b", "9", "10", "11", "12", "15"), "checklist_bancada"),
    **dict.fromkeys(("4", "7", "7b"), "resumo_bancada"),
}


@dataclass(frozen=True)
class Caso:
    """Um caso de teste encontrado no código."""

    nome: str
    descricao: str


def _relativo(caminho: Path) -> str:
    return caminho.relative_to(RAIZ).as_posix()


def arquivos_de_teste() -> list[Path]:
    """Todo arquivo de teste do repositório, Python e frontend, em ordem estável."""
    python = [
        caminho
        for pasta in PASTAS_DE_TESTE
        for caminho in (RAIZ / pasta).rglob("test_*.py")
        if "__pycache__" not in caminho.parts
    ]
    frontend = [
        caminho
        for caminho in (RAIZ / PASTA_FRONTEND).rglob("*.test.ts*")
        if "node_modules" not in caminho.parts
    ]
    return sorted({*python, *frontend}, key=_relativo)


def casos_python(caminho: Path) -> list[Caso]:
    """As funções `test_*` do módulo e das classes `Test*`, com a docstring."""
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    casos = []

    def visitar(corpo: Sequence[ast.stmt], prefixo: str = "") -> None:
        for no in corpo:
            if isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef) and no.name.startswith(
                "test_"
            ):
                doc = ast.get_docstring(no) or ""
                casos.append(Caso(prefixo + no.name, doc.strip().splitlines()[0] if doc else ""))
            elif isinstance(no, ast.ClassDef) and no.name.startswith("Test"):
                visitar(no.body, f"{no.name}::")

    visitar(arvore.body)
    return casos


_IT = re.compile(r"""\b(?:it|test)\(\s*(["'`])(.+?)\1""")
_DESCRIBE = re.compile(r"""\bdescribe\(\s*(["'`])(.+?)\1""")


def casos_frontend(caminho: Path) -> list[Caso]:
    """Os `it(...)` e `test(...)` do arquivo, com o `describe` em que estão."""
    casos = []
    grupo = ""
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if casamento := _DESCRIBE.search(linha):
            grupo = casamento[2]
        elif casamento := _IT.search(linha):
            casos.append(Caso(f"{grupo} > {casamento[2]}" if grupo else casamento[2], ""))
    return casos


def casos_do_arquivo(caminho: Path) -> list[Caso]:
    return casos_python(caminho) if caminho.suffix == ".py" else casos_frontend(caminho)


def arquivos_citados(nome: str, todos: Sequence[Path]) -> list[Path]:
    """Os arquivos que a citação de `06` nomeia: pelo caminho, pelo nome ou pelo padrão."""
    if nome.startswith("frontend/"):
        padrao = re.escape(nome).replace(r"\*", "[^/]*").replace(r"\(x\)", "x?")
        return [c for c in todos if re.fullmatch(padrao, _relativo(c))]
    if "/" in nome:
        return [c for c in todos if _relativo(c) == nome]
    return [c for c in todos if c.name == nome]


def _limpo(texto: str) -> str:
    return texto.replace("|", "\\|")


def _secao_requisito(n: int, req: Requisito, todos: Sequence[Path]) -> list[str]:
    linhas = [
        f"### CT-{n:02d} · {req.codigo}",
        "",
        f"- **Caso:** {req.caso}",
        f"- **Critério de aprovação:** {req.criterio}",
        f"- **Onde:** {req.arquivo}",
        "",
    ]
    for citado in req.arquivos_de_teste:
        arquivos = arquivos_citados(citado, todos)
        if not arquivos:
            linhas += [f"`{citado}`: **arquivo não encontrado no repositório.**", ""]
            continue
        for arquivo in arquivos:
            casos = casos_do_arquivo(arquivo)
            linhas += [f"`{_relativo(arquivo)}` — {len(casos)} caso(s):", ""]
            linhas += [
                f"- `{caso.nome}`" + (f" — {caso.descricao}" if caso.descricao else "")
                for caso in casos
            ]
            linhas.append("")
    if req.bancada:
        linhas += ["Bancada: ver o checklist (seção 3).", ""]
    return linhas


def _sem_registro(texto: str) -> str:
    """A verificação do checklist sem o registro da execução, que começa na data em negrito."""
    return re.split(r"\s\*\*20\d\d-\d\d-\d\d", texto, maxsplit=1)[0].strip()


def gerar() -> str:
    todos = arquivos_de_teste()
    rastreabilidade = ler_rastreabilidade(CONTEXTO_06)
    linhas = [
        "# Especificação dos casos de teste",
        "",
        "<!-- Gerado por `python -m analysis.gerar_casos_de_teste`. Não edite à mão: mude",
        "     `context/06` ou os testes e gere de novo. -->",
        "",
        "O que se testa e o critério de aprovação vêm de `context/06` (§2, §3 e §6). Os",
        "casos listados em cada requisito são os que existem no código, lidos dos arquivos",
        "de teste. O resultado de cada um está no relatório de validação",
        "(`docs/relatorios/validacao_AAAAMMDD.md`), que roda as suítes.",
        "",
        "Marcas que tiram um teste da suíte padrão (`pyproject.toml`): `sumo` (exige o",
        "SUMO) e `hardware` (exige a bancada). `banco` sobe um PostgreSQL efêmero e exige",
        "o Docker. O frontend roda no Vitest (`npm test` em `frontend/`).",
        "",
        "## 1. Requisitos",
        "",
    ]
    for n, req in enumerate(rastreabilidade, 1):
        linhas += _secao_requisito(n, req, todos)

    texto_06 = CONTEXTO_06.read_text(encoding="utf-8")
    linhas += ["## 2. Invariantes de segurança", ""]
    for inv, teste, metodo in tabela_da_secao(texto_06, "## 3. Testes de invariantes"):
        arquivos = TESTES_DOS_INVARIANTES.get(inv, TESTES_DO_FIRMWARE if "firmware" in inv else ())
        linhas += [
            f"### {inv} — {teste}",
            "",
            f"- **Método:** {metodo}",
            "- **Arquivos:** " + (", ".join(f"`{a}`" for a in arquivos) or "—"),
            "",
        ]

    linhas += [
        "## 3. Aceitação do protótipo físico",
        "",
        "O roteiro de `context/06` §6, sem o registro de cada execução (que fica em `06`",
        'e no relatório de validação). "Pelo dado": o módulo que julga o item sobre a',
        "telemetria gravada; os demais são observação de quem está na bancada.",
        "",
        "| # | Verificação | Pelo dado |",
        "| --- | --- | --- |",
    ]
    linhas += [
        f"| {item.item} | {_limpo(_sem_registro(item.verificacao))} | "
        + (f"`analysis.{JULGADO_POR[item.item]}`" if item.item in JULGADO_POR else "observação")
        + " |"
        for item in ler_checklist(CONTEXTO_06)
    ]
    linhas += ["", "## 4. Inventário da suíte", ""]
    linhas += ["| Arquivo | Casos |", "| --- | ---: |"]
    total = 0
    for arquivo in todos:
        n = len(casos_do_arquivo(arquivo))
        total += n
        linhas.append(f"| `{_relativo(arquivo)}` | {n} |")
    linhas += [
        "",
        f"{len(todos)} arquivos, {total} funções de teste. Um teste parametrizado ou com",
        "Hypothesis conta uma vez aqui e roda várias vezes na suíte.",
    ]
    return "\n".join(linhas).rstrip() + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada: `python -m analysis.gerar_casos_de_teste`."""
    saida_utf8()
    import argparse

    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    DESTINO.write_bytes(gerar().encode("utf-8"))
    print(f"escrito: {_relativo(DESTINO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
