"""Os diagramas só usam caracteres que o PDF do PlantUML consegue desenhar.

O PDF do PlantUML escreve o texto com as fontes padrão do PDF, no conjunto
WinAnsi (cp1252): acentos, "·" e "« »" saem, mas "→", "≤", "≥" e "≠" somem sem
aviso, e "[tempo no verde ≥ verde_min]" vira "[tempo no verde  verde_min]"
(achado na revisão dos PDFs, 2026-10-08). O PNG desenha tudo, e por isso o
defeito só aparece no PDF. Comentários (`'`) não são desenhados e ficam livres.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PASTA = Path(__file__).resolve().parents[2] / "docs" / "diagramas"


def _fora_do_winansi(texto: str) -> list[tuple[int, str]]:
    achados = []
    for numero, linha in enumerate(texto.splitlines(), 1):
        if linha.lstrip().startswith("'"):
            continue
        for caractere in linha:
            try:
                caractere.encode("cp1252")
            except UnicodeEncodeError:
                achados.append((numero, f"U+{ord(caractere):04X}"))
    return achados


@pytest.mark.parametrize("diagrama", sorted(PASTA.glob("*.puml")), ids=lambda p: p.name)
def test_diagrama_so_tem_caracteres_que_o_pdf_desenha(diagrama: Path) -> None:
    """Use `->`, `<=`, `>=` e `!=` no lugar de `→`, `≤`, `≥` e `≠`."""
    assert _fora_do_winansi(diagrama.read_text(encoding="utf-8")) == []


def test_o_detector_pega_a_seta() -> None:
    assert _fora_do_winansi("A --> B : x → y\n' comentário com → fica livre") == [(1, "U+2192")]
