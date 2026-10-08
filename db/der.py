"""DER do banco em PlantUML, gerado dos models — `context/08` §5.

    python -m db.der                 # escreve docs/diagramas/der.puml
    python -m db.der --verificar     # falha se o arquivo estiver desatualizado

O `context/08` §5 previa o DER pelo `eralchemy2`, que não está na stack de
`context/02` §2 e exige o Graphviz. O DER sai, em vez disso, do mesmo
`Base.metadata` que o Alembic usa, escrito como diagrama de entidades do
PlantUML — a ferramenta dos outros diagramas. Sem dependência nova, e com a
mesma garantia: o diagrama é o banco, e não um desenho dele. Um teste confere
que o arquivo versionado é o que este módulo gera.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import Enum, MetaData, Table

from adapters.terminal import saida_utf8

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "docs" / "diagramas" / "der.puml"


def _metadata() -> MetaData:
    import app.models  # import local: registra todas as tabelas no metadata

    return app.models.Base.metadata


def _tipo(coluna: object) -> str:
    tipo = getattr(coluna, "type", None)
    if isinstance(tipo, Enum):
        return f"ENUM {tipo.name}" if tipo.name else "ENUM"
    try:
        return str(tipo)
    except Exception:  # tipo sem compilação genérica (enum do Postgres, por exemplo)
        return type(tipo).__name__


def _entidade(tabela: Table) -> list[str]:
    linhas = [f"entity {tabela.name} {{"]
    chaves = [c for c in tabela.columns if c.primary_key]
    demais = [c for c in tabela.columns if not c.primary_key]
    for coluna in chaves:
        linhas.append(f"  * {coluna.name} : {_tipo(coluna)} <<PK>>")
    if chaves:
        linhas.append("  --")
    for coluna in demais:
        marcas = []
        if coluna.foreign_keys:
            marcas.append("<<FK>>")
        if coluna.unique:
            marcas.append("<<UQ>>")
        obrigatorio = "* " if not coluna.nullable else ""
        sufixo = f" {' '.join(marcas)}" if marcas else ""
        linhas.append(f"  {obrigatorio}{coluna.name} : {_tipo(coluna)}{sufixo}")
    linhas.append("}")
    return linhas


def gerar(metadata: MetaData | None = None) -> str:
    """O texto do `der.puml`, em ordem estável (tabelas e relações por nome)."""
    metadata = metadata or _metadata()
    tabelas = sorted(metadata.tables.values(), key=lambda t: t.name)
    linhas = [
        "@startuml der",
        "' GERADO por `python -m db.der` a partir de app.models. Não editar à mão.",
        "hide circle",
        "skinparam linetype ortho",
        "skinparam monochrome true",
        "",
    ]
    for tabela in tabelas:
        linhas += [*_entidade(tabela), ""]
    relacoes = sorted(
        (chave.column.table.name, tabela.name, coluna.name, coluna.nullable)
        for tabela in tabelas
        for coluna in tabela.columns
        for chave in coluna.foreign_keys
    )
    for origem, destino, coluna, opcional in relacoes:
        cardinalidade = "o{" if opcional else "|{"
        linhas.append(f"{origem} ||--{cardinalidade} {destino} : {coluna}")
    linhas += ["", "@enduml", ""]
    return "\n".join(linhas)


def main(argumentos: Sequence[str] | None = None) -> int:
    saida_utf8()
    analisador = argparse.ArgumentParser(description="Gera o DER em PlantUML (context/08 §5).")
    analisador.add_argument("--destino", type=Path, default=DESTINO)
    analisador.add_argument(
        "--verificar", action="store_true", help="falha se o arquivo estiver desatualizado"
    )
    opcoes = analisador.parse_args(argumentos)

    texto = gerar()
    if opcoes.verificar:
        atual = opcoes.destino.read_text(encoding="utf-8") if opcoes.destino.is_file() else ""
        if atual != texto:
            print(f"{opcoes.destino} está desatualizado. Rode `python -m db.der`.")
            return 1
        print(f"{opcoes.destino} em dia.")
        return 0
    opcoes.destino.parent.mkdir(parents=True, exist_ok=True)
    opcoes.destino.write_text(texto, encoding="utf-8", newline="\n")
    print(f"DER em {opcoes.destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
