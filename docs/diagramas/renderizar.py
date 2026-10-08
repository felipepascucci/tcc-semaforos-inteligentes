"""Renderiza os diagramas PlantUML em PDF e PNG — `context/08` §5.

    python docs/diagramas/renderizar.py

Os `.puml` desta pasta são a fonte; os `.pdf` (vetoriais, para o texto do TCC)
e os `.png` (para slides) saem ao lado de cada um, com o nome do `@startuml`.

Usa a imagem Docker oficial do PlantUML, com a versão fixada abaixo, e não
instala nada no Windows: sem Java nem PlantUML no sistema (decisão de
2026-10-08, `context/09`). Precisa só do Docker Desktop no ar. `-failfast2`
faz um erro de sintaxe derrubar o comando, em vez de virar uma imagem com a
mensagem de erro desenhada.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PASTA = Path(__file__).resolve().parent

#: A versão do PlantUML que gerou os arquivos versionados. Trocar a versão pode
#: mudar o desenho; fixá-la é o que torna o render reprodutível.
IMAGEM = "plantuml/plantuml:1.2026.8"

FORMATOS = ("pdf", "png")


def comando(formato: str) -> list[str]:
    """O `docker run` que renderiza todos os `.puml` da pasta num formato."""
    return [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{PASTA}:/data",
        IMAGEM,
        f"-t{formato}",
        "-failfast2",
        "/data/*.puml",
    ]


def main() -> int:
    """Ponto de entrada: `python docs/diagramas/renderizar.py`."""
    for formato in FORMATOS:
        print("$", " ".join(comando(formato)), flush=True)
        resultado = subprocess.run(comando(formato), check=False)
        if resultado.returncode != 0:
            print(f"falhou ao gerar {formato} (código {resultado.returncode})", file=sys.stderr)
            return resultado.returncode
    gerados = sorted(p.name for formato in FORMATOS for p in PASTA.glob(f"*.{formato}"))
    print("gerados:", ", ".join(gerados))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
