"""Saída de texto dos `python -m` do projeto em UTF-8.

No Windows, quando a saída de um programa vai para arquivo ou pipe, o Python a
codifica na página de código do sistema (cp1252), e não em UTF-8. Os textos do
projeto têm `≥`, `→`, `λ` e `δ`, que o cp1252 não representa. O resultado era
`UnicodeEncodeError` no `--help` de `bridge.demo`, `analysis.resumo_bancada` e
`analysis.treino_politica` com a saída redirecionada, e o mesmo risco em
qualquer relatório impresso. No console direto funcionava, porque o console do
Windows recebe Unicode por outro caminho, e por isso o defeito só aparecia
redirecionando.

A correção é uma só, chamada no início de todo `main()`: reconfigurar
`stdout` e `stderr` para UTF-8. Um terminal que espere outra codificação mostra
acento trocado, mas nenhum programa cai por causa de um caractere.
"""

from __future__ import annotations

import sys


def saida_utf8() -> None:
    """Passa `sys.stdout` e `sys.stderr` a UTF-8, se ainda não estiverem."""
    for fluxo in (sys.stdout, sys.stderr):
        reconfigurar = getattr(fluxo, "reconfigure", None)
        if reconfigurar is not None:
            reconfigurar(encoding="utf-8")
