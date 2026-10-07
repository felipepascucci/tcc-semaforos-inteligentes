"""Resumo dos rótulos da bifurcação — entrega 10.4 do Bloco 10.

    python -m analysis.resumo_rotulos --dados analysis/data/bloco10_rotulos

Descreve o conjunto que a 10.5 vai usar para treinar: quantas disputas viraram
exemplo em cada divisão por seed (treino e validação, de `cenarios.yaml`),
quantas empataram ou foram descartadas, e com que frequência o E8 determinístico
já faz a escolha que o minimax prefere.

**Isto não é resultado de H4.** As seeds são as de treino, fora do intervalo do
Bloco 8, e o que aparece aqui é o quanto o E8 erra *no conjunto de treino*, pela
régua do rótulo. H4 é testada no Bloco 8, com o braço `PREEMPCAO_ML` rodando de
verdade, nas seeds 1..50 do cenário de avaliação. O número daqui serve para
dimensionar o modelo e para saber se há o que aprender.
"""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
DADOS = RAIZ / "analysis" / "data" / "bloco10_rotulos"
CENARIOS_YAML = RAIZ / "sim" / "config" / "cenarios.yaml"
ARQUIVO_ROTULOS = "rotulos.csv"

#: Piso de P19 para um conjunto de treino.
PISO_EXEMPLOS = 100

TREINAVEIS = ("A", "B")


@dataclass(frozen=True)
class Rotulo:
    """Uma linha de `rotulos.csv`, só com o que o resumo usa."""

    seed: int
    id_semaforo: str
    escolha_e8: str
    minimax_se_a_s: float | None
    minimax_se_b_s: float | None
    replay_fiel: bool
    rotulo: str
    motivo_descarte: str

    @property
    def treinavel(self) -> bool:
        """Se a disputa tem escolha melhor e vira exemplo de treino."""
        return self.rotulo in TREINAVEIS

    @property
    def margem_s(self) -> float | None:
        """Quanto o minimax melhora escolhendo certo, em segundos."""
        if self.minimax_se_a_s is None or self.minimax_se_b_s is None:
            return None
        return round(abs(self.minimax_se_a_s - self.minimax_se_b_s), 1)

    @property
    def custo_do_e8_s(self) -> float | None:
        """Quanto o E8 perde para o rótulo, em segundos; zero quando acerta."""
        if not self.treinavel or self.margem_s is None:
            return None
        return 0.0 if self.escolha_e8 == self.rotulo else self.margem_s


def _numero(texto: str) -> float | None:
    return float(texto) if texto else None


def ler_rotulos(caminho: Path) -> tuple[Rotulo, ...]:
    """Lê `rotulos.csv`; vazio se o arquivo não existir."""
    if not caminho.is_file():
        return ()
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return tuple(
            Rotulo(
                seed=int(linha["seed"]),
                id_semaforo=linha["id_semaforo"],
                escolha_e8=linha["escolha_e8"],
                minimax_se_a_s=_numero(linha["minimax_se_a_s"]),
                minimax_se_b_s=_numero(linha["minimax_se_b_s"]),
                replay_fiel=linha["replay_fiel"] == "1",
                rotulo=linha["rotulo"],
                motivo_descarte=linha["motivo_descarte"],
            )
            for linha in csv.DictReader(arquivo)
        )


def divisao_de_seeds(caminho: Path = CENARIOS_YAML) -> dict[str, tuple[int, int]]:
    """A divisão treino/validação de `execucao.seeds_treino_ml`."""
    with caminho.open(encoding="utf-8") as arquivo:
        configuracao = yaml.safe_load(arquivo)
    return {
        nome: (int(faixa[0]), int(faixa[1]))
        for nome, faixa in configuracao["execucao"]["seeds_treino_ml"].items()
    }


def _distribuicao(valores: Sequence[object]) -> str:
    contagem = Counter(str(valor) for valor in valores)
    if not contagem:
        return "—"
    return ", ".join(
        f"{categoria}: {quantas}"
        for categoria, quantas in sorted(contagem.items(), key=lambda par: (-par[1], par[0]))
    )


def _quartis(valores: Sequence[float]) -> str:
    if not valores:
        return "—"
    if len(valores) < 2:
        return f"{valores[0]:.1f}"
    q1, mediana, q3 = statistics.quantiles(valores, n=4)
    return f"Q1 {q1:.1f} · mediana {mediana:.1f} · Q3 {q3:.1f} · máx {max(valores):.1f}"


def _secao(nome: str, rotulos: Sequence[Rotulo]) -> list[str]:
    treinaveis = [rotulo for rotulo in rotulos if rotulo.treinavel]
    acertos = sum(1 for rotulo in treinaveis if rotulo.escolha_e8 == rotulo.rotulo)
    custos = [r.custo_do_e8_s for r in treinaveis if r.custo_do_e8_s is not None]
    linhas = [
        f"## {nome}",
        "",
        f"Disputas bifurcadas: {len(rotulos)}",
        f"Rótulos: {_distribuicao([rotulo.rotulo for rotulo in rotulos])}",
        f"**Exemplos de treino (A ou B): {len(treinaveis)}**"
        + ("" if len(treinaveis) >= PISO_EXEMPLOS else f" — abaixo do piso de {PISO_EXEMPLOS}"),
        f"Por cruzamento: {_distribuicao([rotulo.id_semaforo for rotulo in treinaveis])}",
        f"Rótulo A / B: {_distribuicao([rotulo.rotulo for rotulo in treinaveis])}",
    ]
    if treinaveis:
        linhas += [
            f"E8 faz a escolha do rótulo em {acertos} de {len(treinaveis)} "
            f"({100.0 * acertos / len(treinaveis):.1f}%)",
            "Margem do minimax entre as escolhas, em s: "
            + _quartis([r.margem_s for r in treinaveis if r.margem_s is not None]),
            "Custo do E8 pela régua do rótulo, média por exemplo: "
            f"{statistics.fmean(custos):.2f} s",
        ]
    linhas.append("")
    return linhas


def gerar_relatorio(rotulos: Sequence[Rotulo], divisao: dict[str, tuple[int, int]]) -> str:
    """Monta o relatório de texto."""
    linhas = ["# Rótulos da bifurcação — entrega 10.4", ""]
    if not rotulos:
        linhas.append("Nenhum rótulo encontrado. Rode `python -m sim.controlador.rotulagem` antes.")
        return "\n".join(linhas)

    infieis = [rotulo for rotulo in rotulos if not rotulo.replay_fiel]
    descartes = [rotulo.motivo_descarte for rotulo in rotulos if rotulo.rotulo == "DESCARTADA"]
    linhas += [
        f"Seeds: {len({rotulo.seed for rotulo in rotulos})} · disputas: {len(rotulos)}",
        f"Reexecução fiel: {len(rotulos) - len(infieis)} de {len(rotulos)}",
        f"Motivos de descarte: {_distribuicao(descartes)}",
        "",
    ]
    fora = [r for r in rotulos if not any(a <= r.seed <= b for a, b in divisao.values())]
    for nome, (inicio, fim) in divisao.items():
        linhas += _secao(
            f"{nome.capitalize()} (seeds {inicio}..{fim})",
            [rotulo for rotulo in rotulos if inicio <= rotulo.seed <= fim],
        )
    if fora:
        linhas += _secao("Fora da divisão", fora)

    linhas += [
        "## O que isto não é",
        "",
        "Não é resultado de H4. É o conjunto de treino descrito pela régua do rótulo; "
        "H4 é testada no Bloco 8, com o braço PREEMPCAO_ML nas seeds 1..50 do cenário "
        "de avaliação.",
    ]
    return "\n".join(linhas)


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada: `python -m analysis.resumo_rotulos`."""
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument("--dados", type=Path, default=DADOS)
    analisador.add_argument("--saida", type=Path, default=None)
    opcoes = analisador.parse_args(argv)

    relatorio = gerar_relatorio(ler_rotulos(opcoes.dados / ARQUIVO_ROTULOS), divisao_de_seeds())
    if opcoes.saida is not None:
        opcoes.saida.parent.mkdir(parents=True, exist_ok=True)
        opcoes.saida.write_text(relatorio + "\n", encoding="utf-8")
    print(relatorio)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
