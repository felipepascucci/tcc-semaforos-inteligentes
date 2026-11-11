"""Matriz de confusão e métricas por classe da política de desempate de P19.

    python -m analysis.metricas_politica

Feito para a Seção 4 do Guia do Usuário v2.0 (entregável da qualificação), que
pede acurácia, precisão, revocação, F1 e matriz de confusão. **Só lê**: carrega
os pesos versionados pelo mesmo carregador da inferência
(`adapters.configuracao.carregar_politica`), os atributos pelo mesmo leitor do
treino (`analysis.treino_politica.ler_conjuntos`) e aplica a regra de P19
(`score > 0` escolhe A). Não ajusta nada, não toca no YAML nem em
`analysis/data/bloco10_treino/`. As saídas vão para
`analysis/data/bloco10_treino_metricas/`:

- `predicoes.csv`: uma linha por exemplo treinável (empates ficam de fora,
  como no treino), com o score e a escolha do modelo;
- `matriz_confusao.csv`: rótulo de referência contra escolha do modelo, por divisão;
- `metricas.csv`: acurácia, e precisão, revocação, F1 e suporte por classe,
  com as médias macro, por divisão;
- `relatorio.md`: as mesmas tabelas, para leitura.

**As classes.** A é o VE do corredor (o primeiro da disputa), B o outro. O
rótulo é a escolha que minimiza o maior tempo de travessia dos dois, medida
pela bifurcação (10.4). Não há classe "positiva" natural; por isso as métricas
saem para as duas.

**O que estes números não são.** A divisão `validacao` (seeds 241..250) também
escolheu o λ da regularização, então não é um teste cego; a escolha mexe pouco
no acerto (66,7% para todo λ ≤ 0,01, `selecao_lambda.csv`). O teste
independente da política é H4 (seeds 1..50 do cenário de avaliação), que não
tem rótulo de bifurcação e por isso não tem matriz de confusão.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from adapters.configuracao import carregar_politica
from adapters.terminal import saida_utf8
from analysis.resumo_rotulos import ARQUIVO_ROTULOS, TREINAVEIS, divisao_de_seeds
from analysis.treino_politica import DADOS, RAIZ, Conjunto, escolhas, ler_conjuntos

SAIDA = RAIZ / "analysis" / "data" / "bloco10_treino_metricas"

#: As classes, na ordem das tabelas. `+1` é A e `-1` é B, como em `Conjunto.y`.
CLASSES = ("A", "B")
_CODIGO = {"A": 1.0, "B": -1.0}

#: Colunas de identificação que acompanham cada predição.
IDENTIFICACAO = ("seed", "t_s", "id_semaforo", "ve_a", "ve_b", "tipo_a", "tipo_b")


def identificacao(caminho: Path, divisao: dict[str, tuple[int, int]]) -> dict[str, pd.DataFrame]:
    """As colunas de identificação dos exemplos, com o mesmo filtro e ordem de `ler_conjuntos`."""
    tabela = pd.read_csv(caminho, dtype={"rotulo": str})
    tabela = tabela[tabela["rotulo"].isin(TREINAVEIS)]
    return {
        nome: tabela[tabela["seed"].between(inicio, fim)][list(IDENTIFICACAO)].reset_index(
            drop=True
        )
        for nome, (inicio, fim) in divisao.items()
    }


def matriz_confusao(y: np.ndarray, previsto: np.ndarray) -> pd.DataFrame:
    """Contagens de rótulo contra escolha, com as classes na ordem de `CLASSES`."""
    return pd.DataFrame(
        [
            [int(((y == _CODIGO[real]) & (previsto == _CODIGO[esc])).sum()) for esc in CLASSES]
            for real in CLASSES
        ],
        index=pd.Index(CLASSES, name="rotulo"),
        columns=pd.Index(CLASSES, name="escolha_modelo"),
    )


def _razao(numerador: int, denominador: int) -> float:
    """`numerador / denominador`, ou NaN se o denominador é zero (métrica indefinida)."""
    return numerador / denominador if denominador else float("nan")


def metricas(matriz: pd.DataFrame) -> pd.DataFrame:
    """Precisão, revocação, F1 e suporte por classe, as médias macro e a acurácia."""
    total = int(matriz.to_numpy().sum())
    linhas = []
    for classe in CLASSES:
        acertos = int(matriz.loc[classe, classe])
        precisao = _razao(acertos, int(matriz[classe].sum()))
        revocacao = _razao(acertos, int(matriz.loc[classe].sum()))
        f1 = (
            2 * precisao * revocacao / (precisao + revocacao)
            if precisao + revocacao > 0
            else float("nan")
        )
        linhas.append(
            {
                "classe": classe,
                "precisao": precisao,
                "revocacao": revocacao,
                "f1": f1,
                "suporte": int(matriz.loc[classe].sum()),
                "escolhidos": int(matriz[classe].sum()),
            }
        )
    tabela = pd.DataFrame(linhas)
    macro = {
        "classe": "macro",
        "precisao": tabela["precisao"].mean(),
        "revocacao": tabela["revocacao"].mean(),
        "f1": tabela["f1"].mean(),
        "suporte": total,
        "escolhidos": total,
    }
    acuracia = _razao(int(np.trace(matriz.to_numpy())), total)
    tabela = pd.concat([tabela, pd.DataFrame([macro])], ignore_index=True)
    tabela["acuracia"] = acuracia
    return tabela


def predicoes(
    conjunto: Conjunto, pesos: np.ndarray, ident: pd.DataFrame, divisao: str
) -> pd.DataFrame:
    """Uma linha por exemplo: identificação, score, rótulo e escolha do modelo."""
    if len(ident) != len(conjunto):
        raise ValueError(f"{divisao}: {len(ident)} identificações para {len(conjunto)} exemplos")
    score = conjunto.x @ pesos
    escolha = escolhas(pesos, conjunto.x)
    tabela = ident.copy()
    tabela.insert(0, "divisao", divisao)
    tabela["score"] = score
    tabela["rotulo"] = np.where(conjunto.y > 0, "A", "B")
    tabela["escolha_modelo"] = np.where(escolha > 0, "A", "B")
    tabela["acerto"] = tabela["rotulo"] == tabela["escolha_modelo"]
    return tabela


def _pct(valor: float) -> str:
    return "—" if np.isnan(valor) else f"{100 * valor:.1f}%".replace(".", ",")


def gerar_relatorio(
    matrizes: dict[str, pd.DataFrame], tabelas: dict[str, pd.DataFrame], origem: str
) -> str:
    """O relatório em Markdown, com as tabelas da matriz e das métricas."""
    linhas = [
        "# Política de desempate (P19) — matriz de confusão e métricas por classe",
        "",
        "> Gerado por `python -m analysis.metricas_politica`. Nenhum número foi digitado à mão.",
        "",
        f"Pesos: `backend/config/politica_desempate.yaml`. Rótulos: `{origem}`.",
        "A = VE do corredor; B = o outro VE da disputa. Empates ficam de fora, como no treino.",
        "",
    ]
    for nome, matriz in matrizes.items():
        tabela = tabelas[nome]
        linhas += [
            f"## Divisão `{nome}` ({int(matriz.to_numpy().sum())} exemplos)",
            "",
            "| Rótulo \\ escolha do modelo | A | B | Total |",
            "| --- | ---: | ---: | ---: |",
        ]
        for classe in CLASSES:
            a, b = (int(matriz.loc[classe, c]) for c in CLASSES)
            linhas.append(f"| {classe} | {a} | {b} | {a + b} |")
        linhas += [
            f"| Total | {int(matriz['A'].sum())} | {int(matriz['B'].sum())} "
            f"| {int(matriz.to_numpy().sum())} |",
            "",
            f"Acurácia: {_pct(float(tabela['acuracia'].iloc[0]))}",
            "",
            "| Classe | Precisão | Revocação | F1 | Suporte |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for _, linha in tabela.iterrows():
            linhas.append(
                f"| {linha['classe']} | {_pct(linha['precisao'])} | {_pct(linha['revocacao'])} "
                f"| {_pct(linha['f1'])} | {int(linha['suporte'])} |"
            )
        linhas.append("")
    linhas += [
        "## O que isto não é",
        "",
        "A divisão `validacao` também escolheu o λ, então não é teste cego. O teste",
        "independente da política é H4 (`analysis/saida/h4.md`), sem rótulo de bifurcação.",
    ]
    return "\n".join(linhas)


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada: `python -m analysis.metricas_politica`."""
    saida_utf8()
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument("--dados", type=Path, default=DADOS)
    analisador.add_argument("--saida", type=Path, default=SAIDA)
    opcoes = analisador.parse_args(argv)

    divisao = divisao_de_seeds()
    caminho = opcoes.dados / ARQUIVO_ROTULOS
    conjuntos = ler_conjuntos(caminho, divisao)
    ident = identificacao(caminho, divisao)
    pesos = np.asarray(carregar_politica().vetor(), dtype=float)

    todas, matrizes, tabelas = [], {}, {}
    for nome, conjunto in conjuntos.items():
        tabela = predicoes(conjunto, pesos, ident[nome], nome)
        todas.append(tabela)
        matrizes[nome] = matriz_confusao(conjunto.y, escolhas(pesos, conjunto.x))
        tabelas[nome] = metricas(matrizes[nome])

    opcoes.saida.mkdir(parents=True, exist_ok=True)
    # LF explícito, como no treino: o arquivo não muda com a máquina.
    pd.concat(todas, ignore_index=True).to_csv(
        opcoes.saida / "predicoes.csv", index=False, lineterminator="\n"
    )
    pd.concat([m.reset_index().assign(divisao=n) for n, m in matrizes.items()], ignore_index=True)[
        ["divisao", "rotulo", *CLASSES]
    ].to_csv(opcoes.saida / "matriz_confusao.csv", index=False, lineterminator="\n")
    pd.concat([t.assign(divisao=n) for n, t in tabelas.items()], ignore_index=True)[
        ["divisao", "classe", "precisao", "revocacao", "f1", "suporte", "escolhidos", "acuracia"]
    ].to_csv(opcoes.saida / "metricas.csv", index=False, lineterminator="\n")
    try:
        origem = caminho.resolve().relative_to(RAIZ).as_posix()
    except ValueError:
        origem = caminho.as_posix()
    relatorio = gerar_relatorio(matrizes, tabelas, origem)
    (opcoes.saida / "relatorio.md").write_text(relatorio + "\n", encoding="utf-8", newline="\n")
    print(relatorio)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
