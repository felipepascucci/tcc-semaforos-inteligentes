"""Tabelas do capítulo 5 em Markdown e em LaTeX — `context/07` §4.

Só formatação. Os números chegam prontos de `analysis/gerar_resultados_tcc.py`;
aqui eles ganham vírgula decimal, sinal e unidade, e viram duas saídas da mesma
fonte: Markdown, para ler no repositório, e LaTeX (`booktabs`), para colar no
texto do TCC sem redigitar nada.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field


def num(valor: float | None, casas: int = 1) -> str:
    """Número com vírgula decimal, como no resto do TCC. `—` se faltar."""
    if valor is None or math.isnan(valor):
        return "—"
    return f"{valor:.{casas}f}".replace(".", ",")


def pct(valor: float | None, casas: int = 1) -> str:
    """Fração como percentual sem sinal (para grandezas cujo nome dá o sentido)."""
    return "—" if valor is None or math.isnan(valor) else f"{num(valor * 100, casas)}%"


def pct_sinal(valor: float | None, casas: int = 1) -> str:
    """Fração como percentual com sinal (para variações que vão nos dois sentidos)."""
    if valor is None or math.isnan(valor):
        return "—"
    sinal = "+" if valor > 0 else ("-" if valor < 0 else "")
    return f"{sinal}{num(abs(valor) * 100, casas)}%"


def p_valor(valor: float | None) -> str:
    """Valor p com três casas, ou `< 0,001`."""
    if valor is None or math.isnan(valor):
        return "—"
    return "< 0,001" if valor < 0.001 else num(valor, 3)


def intervalo(ic: tuple[float, float], casas: int = 1, *, percentual: bool = False) -> str:
    """IC como `[a; b]`, em unidade ou em percentual."""
    if percentual:
        return f"[{pct(ic[0], casas)}; {pct(ic[1], casas)}]"
    return f"[{num(ic[0], casas)}; {num(ic[1], casas)}]"


_ESCAPES_LATEX = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "δ": r"$\delta$",
    "≥": r"$\geq$",
    "≤": r"$\leq$",
    "<": r"$<$",
    ">": r"$>$",
}


def escapar_latex(texto: str) -> str:
    """Escapa os caracteres especiais do LaTeX, um a um."""
    return "".join(_ESCAPES_LATEX.get(caractere, caractere) for caractere in texto)


@dataclass(frozen=True)
class Tabela:
    """Uma tabela do capítulo, com as duas saídas.

    Attributes:
        codigo: `T1`, `T2`, ... — o nome de `context/07` §4.
        titulo: Legenda.
        cabecalho: Rótulos das colunas.
        linhas: Células, já formatadas como texto.
        alinhamento: `l`, `r` ou `c` por coluna; padrão: texto à esquerda nas
            duas primeiras, números à direita no resto.
        notas: Parágrafos que acompanham a tabela (fonte, regra, ressalva).
    """

    codigo: str
    titulo: str
    cabecalho: Sequence[str]
    linhas: Sequence[Sequence[str]]
    alinhamento: str = ""
    notas: Sequence[str] = field(default_factory=tuple)

    def _alinhamento(self) -> str:
        if self.alinhamento:
            return self.alinhamento
        return "".join("l" if i < 2 else "r" for i in range(len(self.cabecalho)))

    def markdown(self) -> str:
        """A tabela em Markdown, com título e notas."""
        separador = {"l": "---", "r": "---:", "c": ":---:"}
        partes = [
            f"### {self.codigo} — {self.titulo}",
            "",
            "| " + " | ".join(self.cabecalho) + " |",
            "| " + " | ".join(separador[a] for a in self._alinhamento()) + " |",
            *("| " + " | ".join(linha) + " |" for linha in self.linhas),
        ]
        if self.notas:
            partes += ["", *self.notas]
        return "\n".join(partes) + "\n"

    def latex(self) -> str:
        r"""A tabela em LaTeX, com `booktabs`, pronta para `\input`."""
        corpo = [
            " & ".join(escapar_latex(celula) for celula in linha) + r" \\" for linha in self.linhas
        ]
        return (
            "\n".join(
                [
                    r"\begin{table}[htbp]",
                    r"\centering",
                    rf"\caption{{{escapar_latex(self.titulo)}}}",
                    rf"\label{{tab:{self.codigo.lower()}}}",
                    r"\small",
                    rf"\begin{{tabular}}{{{self._alinhamento()}}}",
                    r"\toprule",
                    " & ".join(escapar_latex(c) for c in self.cabecalho) + r" \\",
                    r"\midrule",
                    *corpo,
                    r"\bottomrule",
                    r"\end{tabular}",
                    r"\end{table}",
                ]
            )
            + "\n"
        )
