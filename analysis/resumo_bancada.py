"""Resumo das passagens de bancada: RNF05 e H3 — `context/06` §6, itens 4 e 7b.

    python -m analysis.resumo_bancada                 # a última sessão da ponte
    python -m analysis.resumo_bancada --sessao <iso>  # uma sessão (repetível)
    python -m analysis.resumo_bancada --todas

Lê os dois CSV que a ponte grava com `--porta-veiculo` (`bridge/latencia.py`):

* `deteccoes_bancada.csv` — uma linha por leitura que o emissor imprimiu, com o
  evento de decisão do UNO para ela ou `SEM_DECISAO`. **RNF05**: das leituras,
  quantas viraram evento de decisão com a rua certa (o casamento já é por rua),
  com o critério de ≥ 95 em 100. `RECUSADO` não traz rua e aparece aqui como
  `SEM_DECISAO`: conta como falha, como o item 4 pede.
* `latencia_bancada.csv` — uma linha por leitura que virou `PREEMP_INI`.
  **H3**: p95 de `latencia_total_ms` < 200 ms, com n, mín, mediana e máx, e
  também média e p99 para a tabela de `context/07` §5.

Percentis pelo posto mais próximo (`sim/controlador/coletor.py`): o valor
informado é uma medição que aconteceu, como o `percentile_disc` do backend.

Uma "sessão" é uma execução da ponte. Se a rodada precisou reiniciar a ponte,
passe as sessões dela com `--sessao`.
"""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from sim.controlador.coletor import percentil

RAIZ = Path(__file__).resolve().parents[1]
CSV_DETECCOES = RAIZ / "analysis" / "data" / "deteccoes_bancada.csv"
CSV_LATENCIA = RAIZ / "analysis" / "data" / "latencia_bancada.csv"

#: RNF05: em 100 passagens, ≥ 95 chegam ao UNO com a rua certa (`context/06` §6).
PASSAGENS_PREVISTAS = 100
TAXA_MINIMA_RNF05 = 0.95

#: H3: o p95 da latência fim a fim fica abaixo disto (`context/07` §6).
LIMIAR_H3_MS = 200.0

SEM_DECISAO = "SEM_DECISAO"
PREEMP_INI = "PREEMP_INI"


@dataclass(frozen=True)
class Leitura:
    """Uma linha de `deteccoes_bancada.csv`, só com o que o resumo usa."""

    sessao: str
    rua: int
    desfecho: str
    versao_codigo: str

    @property
    def chegou(self) -> bool:
        """Se a leitura virou evento de decisão no UNO — sucesso do RNF05."""
        return self.desfecho != SEM_DECISAO


@dataclass(frozen=True)
class AmostraH3:
    """Uma linha de `latencia_bancada.csv`, só com o que o resumo usa."""

    sessao: str
    latencia_total_ms: float
    versao_codigo: str


def _linhas(caminho: Path) -> list[dict[str, str]]:
    if not caminho.is_file():
        return []
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


def ler_leituras(caminho: Path) -> tuple[Leitura, ...]:
    """Lê `deteccoes_bancada.csv`; vazio se o arquivo não existir."""
    return tuple(
        Leitura(
            sessao=linha["sessao"],
            rua=int(linha["rua"]),
            desfecho=linha["desfecho"],
            versao_codigo=linha["versao_codigo"],
        )
        for linha in _linhas(caminho)
    )


def ler_amostras(caminho: Path) -> tuple[AmostraH3, ...]:
    """Lê `latencia_bancada.csv`; vazio se o arquivo não existir."""
    return tuple(
        AmostraH3(
            sessao=linha["sessao"],
            latencia_total_ms=float(linha["latencia_total_ms"]),
            versao_codigo=linha["versao_codigo"],
        )
        for linha in _linhas(caminho)
    )


def ultima_sessao(leituras: Iterable[Leitura]) -> str | None:
    """A sessão mais recente: os carimbos são ISO 8601 em UTC e ordenam como texto."""
    return max((leitura.sessao for leitura in leituras), default=None)


def _distribuicao(valores: Iterable[object]) -> str:
    contagem = Counter(str(valor) for valor in valores)
    if not contagem:
        return "—"
    return ", ".join(
        f"{categoria}: {quantas}"
        for categoria, quantas in sorted(contagem.items(), key=lambda par: (-par[1], par[0]))
    )


def _veredito(atende: bool) -> str:
    return "**atende**" if atende else "**não atende**"


def _ms(valor: float) -> str:
    return f"{valor:.1f} ms"


def _secao_rnf05(leituras: Sequence[Leitura]) -> list[str]:
    linhas = ["## RNF05 — leituras que chegam ao UNO com a rua certa", ""]
    if not leituras:
        return [*linhas, "Nenhuma leitura do emissor nas sessões escolhidas.", ""]
    chegaram = sum(1 for leitura in leituras if leitura.chegou)
    taxa = chegaram / len(leituras)
    linhas += [
        f"Leituras impressas pelo emissor (denominador): {len(leituras)}",
        f"Viraram evento de decisão com a rua certa: {chegaram} ({100.0 * taxa:.1f}%)",
        f"Desfechos: {_distribuicao(leitura.desfecho for leitura in leituras)}",
    ]
    for rua in sorted({leitura.rua for leitura in leituras}):
        da_rua = [leitura for leitura in leituras if leitura.rua == rua]
        linhas.append(
            f"- RUA{rua}: {sum(1 for leitura in da_rua if leitura.chegou)} de {len(da_rua)}"
        )
    linhas.append("")
    if len(leituras) < PASSAGENS_PREVISTAS:
        linhas.append(
            f"Rodada incompleta: {len(leituras)} de {PASSAGENS_PREVISTAS} passagens previstas. "
            "Sem veredito."
        )
    else:
        linhas.append(
            f"Critério (≥ {100 * TAXA_MINIMA_RNF05:.0f}%): {_veredito(taxa >= TAXA_MINIMA_RNF05)}."
        )
    return [*linhas, ""]


def _secao_h3(amostras: Sequence[AmostraH3], preemp_ini_nas_leituras: int) -> list[str]:
    linhas = ["## H3 — latência fim a fim (leitura da tag → PREEMP_INI)", ""]
    if not amostras:
        return [*linhas, "Nenhuma amostra de H3 nas sessões escolhidas.", ""]
    valores = [amostra.latencia_total_ms for amostra in amostras]
    p95 = percentil(valores, 95)
    linhas += [
        "| n | Mín | Mediana | Média | p95 | p99 | Máx |",
        "|---|---|---|---|---|---|---|",
        f"| {len(valores)} | {_ms(min(valores))} | {_ms(percentil(valores, 50))} | "
        f"{_ms(statistics.fmean(valores))} | {_ms(p95)} | {_ms(percentil(valores, 99))} | "
        f"{_ms(max(valores))} |",
        "",
        f"Critério (p95 < {LIMIAR_H3_MS:.0f} ms): {_veredito(p95 < LIMIAR_H3_MS)}.",
    ]
    if preemp_ini_nas_leituras != len(amostras):
        linhas.append(
            f"**Atenção:** {preemp_ini_nas_leituras} leituras com desfecho PREEMP_INI em "
            f"`deteccoes_bancada.csv`, mas {len(amostras)} amostras em "
            "`latencia_bancada.csv`. Os dois arquivos deviam concordar."
        )
    return [*linhas, ""]


def gerar_relatorio(
    leituras: Sequence[Leitura], amostras: Sequence[AmostraH3], sessoes: Sequence[str]
) -> str:
    """Monta o relatório de texto das sessões escolhidas."""
    linhas = ["# Passagens de bancada — RNF05 e H3", ""]
    if not sessoes:
        linhas.append(
            "Nenhuma sessão encontrada. Meça com "
            "`python -m bridge.main --porta COM3 --porta-veiculo <COM do emissor>`."
        )
        return "\n".join(linhas)

    escolhidas = set(sessoes)
    leituras = [leitura for leitura in leituras if leitura.sessao in escolhidas]
    amostras = [amostra for amostra in amostras if amostra.sessao in escolhidas]
    versoes = {leitura.versao_codigo for leitura in leituras} | {
        amostra.versao_codigo for amostra in amostras
    }
    linhas += [
        f"Sessões da ponte: {', '.join(sorted(escolhidas))}",
        f"Versão do código: {', '.join(sorted(versoes)) or '—'}",
        "Condição: emissor no USB do notebook (decisão de 2026-10-06, `context/09`).",
        "",
    ]
    linhas += _secao_rnf05(leituras)
    preemp_ini = sum(1 for leitura in leituras if leitura.desfecho == PREEMP_INI)
    linhas += _secao_h3(amostras, preemp_ini)
    return "\n".join(linhas).rstrip() + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada: `python -m analysis.resumo_bancada`."""
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument("--deteccoes", type=Path, default=CSV_DETECCOES)
    analisador.add_argument("--latencia", type=Path, default=CSV_LATENCIA)
    grupo = analisador.add_mutually_exclusive_group()
    grupo.add_argument("--sessao", action="append", default=None, help="repetível")
    grupo.add_argument("--todas", action="store_true", help="todas as sessões dos arquivos")
    analisador.add_argument("--saida", type=Path, default=None)
    opcoes = analisador.parse_args(argv)

    leituras = ler_leituras(opcoes.deteccoes)
    amostras = ler_amostras(opcoes.latencia)
    if opcoes.todas:
        sessoes = sorted({leitura.sessao for leitura in leituras})
    elif opcoes.sessao:
        sessoes = list(opcoes.sessao)
    else:
        ultima = ultima_sessao(leituras)
        sessoes = [] if ultima is None else [ultima]

    relatorio = gerar_relatorio(leituras, amostras, sessoes)
    if opcoes.saida is not None:
        opcoes.saida.parent.mkdir(parents=True, exist_ok=True)
        opcoes.saida.write_text(relatorio, encoding="utf-8")
    print(relatorio, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
