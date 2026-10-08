"""Análise de H4 — entrega 10.8 do Bloco 10 (`context/07` §3.3.1, `context/10` §8).

    python -m analysis.analise_h4
    python -m analysis.analise_h4 --dados analysis/data/bloco8 --saida analysis/saida/h4.md

> **H4:** uma política aprendida para escolher entre VEs em conflito reduz o
> tempo de travessia do VE mais prejudicado, em cenários com múltiplos VEs, em
> relação ao desempate determinístico de E8.

Compara o braço `PREEMPCAO_ML` com o `PREEMPCAO`, pareado por seed, no
`multiplas_emergencias`. É hipótese **comparativa direcional, sem meta
percentual** (P19): o veredito sai do teste e do tamanho de efeito, e "nulo" é
veredito legítimo, declarado antes de qualquer treino.

O QUE A ANÁLISE DECLARA, NESTA ORDEM (`context/07` §3.3.1)

1. Quantas disputas houve em cada braço e **quantas eram de mesmo nível** de
   criticidade — só nelas os braços podem decidir diferente (P20).
2. No `PREEMPCAO_ML`, **quantas o modelo de fato decidiu**
   (`decidida_pelo_modelo`) e **em quantas escolheu diferente do E8**
   (`modelo_divergiu_do_e8`). Um episódio sem divergência decorreu igual nos
   dois braços no que dependeu do modelo.
3. O teste pareado sobre o tempo do VE mais prejudicado: Wilcoxon (principal),
   t pareado (secundário), Cliff's δ e IC 95% por bootstrap.

A GUARDA DE OSCILAÇÃO TAMBÉM SEPARA OS BRAÇOS

Achado da 10.7 (`context/10` §3): no `PREEMPCAO` o E8 só aplica "preempção em
curso vence" depois de tipo e ETA; no `PREEMPCAO_ML` a guarda vem antes do
modelo. Numa disputa de mesmo nível aberta com preempção em curso, o E8 ainda
pode trocar o VE do verde, e o braço de ML não troca. Então **a diferença entre
os braços não é só o modelo**: é o modelo mais a posição da guarda. A análise
não tem como separar as duas fontes com o dado do lote — o coletor não registra
se o E8 trocou o verde —, e por isso conta e declara as disputas de mesmo nível
abertas sob preempção em curso em cada braço, que é o conjunto em que a guarda
pode ter agido diferente. A frase que o texto pode afirmar é "a política
aprendida, **com a guarda à frente dela**, contra o E8".
"""

from __future__ import annotations

import argparse
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from adapters.terminal import saida_utf8
from analysis.carregar import (
    DADOS_PADRAO,
    ML,
    PREEMPCAO,
    Dados,
    DadosInvalidosError,
    ler_pasta,
    pior_ve_pareado,
)
from analysis.estatistica import ALFA, ComparacaoPareada, comparar_pareado

#: Cenário de H4: o único do experimento com mais de um VE simultâneo
#: (`context/04` §6).
CENARIO_H4 = "multiplas_emergencias"

#: Os dois braços, na ordem (base, alvo).
BRACOS_H4 = (PREEMPCAO, ML)

FAVORAVEL = "FAVORÁVEL"
NULO = "NULO"
#: Não previsto na T6 (`context/07`), que só lista FAVORÁVEL e NULO. Um efeito
#: significativo **contra** o modelo não é nulo, e chamá-lo assim esconderia o
#: resultado; fica com o nome do que é.
DESFAVORAVEL = "DESFAVORÁVEL"


@dataclass(frozen=True)
class ContagemDisputas:
    """O denominador de `context/07` §3.3.1, num braço.

    Attributes:
        modo: Braço.
        execucoes: Execuções do braço no cenário de H4.
        disputas: Episódios de disputa entre VEs.
        mesmo_nivel: Dos quais, entre VEs de mesma criticidade.
        mesmo_nivel_decidiveis: Mesmo nível e sem preempção em curso na abertura.
        mesmo_nivel_sob_preempcao: Mesmo nível e com preempção em curso na
            abertura — onde a guarda de oscilação age diferente nos dois braços.
        decididas_pelo_modelo: Episódios em que o modelo decidiu em algum passo.
        divergentes_do_e8: Desses, em quantos o modelo escolheu diferente do E8.
        execucoes_com_divergencia: Execuções com ao menos uma divergência.
    """

    modo: str
    execucoes: int
    disputas: int
    mesmo_nivel: int
    mesmo_nivel_decidiveis: int
    mesmo_nivel_sob_preempcao: int
    decididas_pelo_modelo: int
    divergentes_do_e8: int
    execucoes_com_divergencia: int


def _coluna_binaria(tabela: pd.DataFrame, coluna: str) -> pd.Series:
    if coluna not in tabela.columns:
        return pd.Series(0, index=tabela.index)
    return tabela[coluna].fillna(0).astype(int)


def contar_disputas(dados: Dados, modo: str, cenario: str = CENARIO_H4) -> ContagemDisputas:
    """Conta as disputas de um braço, a partir de `conflitos_por_execucao.csv`.

    Raises:
        DadosInvalidosError: se o CSV de conflitos não tiver `mesmo_nivel`, que
            é a coluna pela qual H4 se estratifica (P20). Dado anterior à P20
            não serve para H4.
    """
    execucoes = dados.execucoes[
        (dados.execucoes["cenario"] == cenario) & (dados.execucoes["modo"] == modo)
    ]
    conflitos = dados.conflitos
    if conflitos.empty:
        conflitos = pd.DataFrame(columns=["cenario", "modo", "seed", "mesmo_nivel"])
    if "mesmo_nivel" not in conflitos.columns:
        raise DadosInvalidosError(
            "conflitos_por_execucao.csv sem `mesmo_nivel`: dado anterior à P20 não serve a H4"
        )
    do_braco = conflitos[(conflitos["cenario"] == cenario) & (conflitos["modo"] == modo)]
    mesmo = _coluna_binaria(do_braco, "mesmo_nivel") == 1
    decidivel = _coluna_binaria(do_braco, "decidivel") == 1
    em_curso = (
        do_braco["preempcao_em_curso"].fillna("").astype(str).str.len() > 0
        if "preempcao_em_curso" in do_braco.columns
        else pd.Series(False, index=do_braco.index)
    )
    decidida = _coluna_binaria(do_braco, "decidida_pelo_modelo") == 1
    divergiu = _coluna_binaria(do_braco, "modelo_divergiu_do_e8") == 1
    return ContagemDisputas(
        modo=modo,
        execucoes=len(execucoes),
        disputas=len(do_braco),
        mesmo_nivel=int(mesmo.sum()),
        mesmo_nivel_decidiveis=int((mesmo & decidivel).sum()),
        mesmo_nivel_sob_preempcao=int((mesmo & em_curso).sum()),
        decididas_pelo_modelo=int(decidida.sum()),
        divergentes_do_e8=int(divergiu.sum()),
        execucoes_com_divergencia=int(do_braco.loc[divergiu, "seed"].nunique()),
    )


@dataclass(frozen=True)
class ResultadoH4:
    """Tudo o que a 10.8 reporta.

    Attributes:
        contagens: Denominador por braço.
        comparacao: Teste principal, sobre todas as seeds pareadas.
        pares_comuns: Pares de VEs comparados, somados sobre as seeds.
        pares_descartados: Pares incompletos em algum braço.
        seeds_identicas: Seeds em que o VE mais prejudicado teve o mesmo tempo
            nos dois braços.
        seeds_com_divergencia: Seeds em que o modelo divergiu do E8 ao menos uma
            vez (no braço de ML).
        exploratoria: O mesmo teste só nas seeds com divergência, ou `None`.
            **Exploratória e fora da família de Holm**: o subconjunto é escolhido
            por uma variável que só existe no braço de ML, e a guarda de
            oscilação separa os braços também fora dele.
        por_seed: Os valores pareados, para a tabela e as figuras.
    """

    contagens: tuple[ContagemDisputas, ...]
    comparacao: ComparacaoPareada | None
    pares_comuns: int
    pares_descartados: int
    seeds_identicas: int
    seeds_com_divergencia: tuple[int, ...]
    exploratoria: ComparacaoPareada | None
    por_seed: pd.DataFrame


def analisar(dados: Dados, *, reamostragens: int | None = None) -> ResultadoH4:
    """Roda a análise de H4 sobre uma pasta do lote."""
    base, alvo = BRACOS_H4
    contagens = tuple(contar_disputas(dados, modo) for modo in BRACOS_H4)
    pareado = pior_ve_pareado(dados, CENARIO_H4, BRACOS_H4)
    tabela = pareado.por_seed
    extra = {} if reamostragens is None else {"reamostragens": reamostragens}

    comparacao = (
        comparar_pareado(tabela[alvo].to_numpy(), tabela[base].to_numpy(), **extra)
        if not tabela.empty
        else None
    )

    sem_coluna = dados.conflitos.empty or "modelo_divergiu_do_e8" not in dados.conflitos.columns
    seeds_div: tuple[int, ...] = ()
    if not sem_coluna:
        c = dados.conflitos
        marcadas = c[
            (c["cenario"] == CENARIO_H4)
            & (c["modo"] == alvo)
            & (c["modelo_divergiu_do_e8"].fillna(0).astype(int) == 1)
        ]
        seeds_div = tuple(sorted(int(s) for s in marcadas["seed"].unique()))

    subconjunto = tabela.loc[tabela.index.isin(seeds_div)]
    exploratoria = (
        comparar_pareado(subconjunto[alvo].to_numpy(), subconjunto[base].to_numpy(), **extra)
        if len(subconjunto) >= 2
        else None
    )
    identicas = (
        int(np.isclose(tabela[alvo].to_numpy(), tabela[base].to_numpy()).sum())
        if not tabela.empty
        else 0
    )
    return ResultadoH4(
        contagens=contagens,
        comparacao=comparacao,
        pares_comuns=pareado.pares_comuns,
        pares_descartados=pareado.pares_descartados,
        seeds_identicas=identicas,
        seeds_com_divergencia=seeds_div,
        exploratoria=exploratoria,
        por_seed=tabela,
    )


def veredito(comparacao: ComparacaoPareada | None, p_ajustado: float) -> str:
    """FAVORÁVEL, NULO ou DESFAVORÁVEL, pela regra declarada antes dos dados.

    FAVORÁVEL exige p ajustado (Holm) abaixo de alfa **e** o VE mais prejudicado
    mais rápido no braço de ML (mediana das diferenças e δ negativos). Com p
    ajustado abaixo de alfa no sentido oposto, DESFAVORÁVEL. O resto é NULO.
    """
    if comparacao is None or math.isnan(p_ajustado) or p_ajustado >= ALFA:
        return NULO
    if comparacao.mediana_diferenca < 0 and comparacao.delta < 0:
        return FAVORAVEL
    if comparacao.mediana_diferenca > 0 and comparacao.delta > 0:
        return DESFAVORAVEL
    return NULO


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def _n(valor: float, casas: int = 1) -> str:
    return "—" if math.isnan(valor) else f"{valor:.{casas}f}".replace(".", ",")


def _p(valor: float | None) -> str:
    if valor is None or math.isnan(valor):
        return "—"
    return "< 0,001" if valor < 0.001 else _n(valor, 3)


def _ic(ic: tuple[float, float], casas: int = 1) -> str:
    return f"[{_n(ic[0], casas)}; {_n(ic[1], casas)}]"


def secao_contagens(resultado: ResultadoH4) -> list[str]:
    """Tabela do denominador (itens 1 e 2 de `context/07` §3.3.1)."""
    linhas = [
        "| Braço | Execuções | Disputas | Mesmo nível | Mesmo nível, decidíveis |"
        " Mesmo nível, sob preempção em curso | Decididas pelo modelo |"
        " Modelo ≠ E8 | Execuções com divergência |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for c in resultado.contagens:
        do_modelo = c.modo == ML
        linhas.append(
            f"| `{c.modo}` | {c.execucoes} | {c.disputas} | {c.mesmo_nivel} | "
            f"{c.mesmo_nivel_decidiveis} | {c.mesmo_nivel_sob_preempcao} | "
            f"{c.decididas_pelo_modelo if do_modelo else '—'} | "
            f"{c.divergentes_do_e8 if do_modelo else '—'} | "
            f"{c.execucoes_com_divergencia if do_modelo else '—'} |"
        )
    return linhas


def secao_teste(comparacao: ComparacaoPareada | None, p_ajustado: float) -> list[str]:
    """Tabela do teste pareado (item 3)."""
    if comparacao is None:
        return ["Sem seeds pareadas nos dois braços: o teste não roda."]
    c = comparacao
    return [
        "| n | Mediana `PREEMPCAO` (IQR) | Mediana `PREEMPCAO_ML` (IQR) |"
        " Mediana da diferença (IC 95%) | p Wilcoxon | p Holm | p t pareado |"
        " Shapiro (dif.) | Cliff's δ |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| {c.n} | {_n(c.mediana_base)} s ({_n(c.iqr_base)}) | "
        f"{_n(c.mediana_alvo)} s ({_n(c.iqr_alvo)}) | "
        f"{_n(c.mediana_diferenca)} s {_ic(c.ic_mediana_diferenca)} | "
        f"{_p(c.p_wilcoxon)} | {_p(p_ajustado)} | {_p(c.p_t)} | {_p(c.p_shapiro)} | "
        f"{_n(c.delta, 3)} ({c.magnitude}) |",
    ]


def gerar_markdown(resultado: ResultadoH4, p_ajustado: float | None = None) -> str:
    """Relatório da 10.8.

    Args:
        resultado: A análise.
        p_ajustado: p de Wilcoxon ajustado por Holm na família do capítulo. Se
            `None` (o script rodando sozinho), H4 é a única comparação e o
            ajustado é o bruto.
    """
    comparacao = resultado.comparacao
    if p_ajustado is None:
        p_ajustado = comparacao.p_wilcoxon if comparacao else float("nan")
    linhas = [
        "# H4 — política aprendida x E8 (entrega 10.8)",
        "",
        "> Gerado por `python -m analysis.analise_h4`. Nenhum número foi digitado à mão.",
        "",
        f"Cenário `{CENARIO_H4}`, braço `{ML}` contra `{PREEMPCAO}`, pareado por seed.",
        "Variável de resposta: por execução, a média, sobre os pares de VEs que",
        "chegaram nos dois braços, do tempo do VE mais prejudicado do par.",
        f"Pares comparados: {resultado.pares_comuns}; descartados por um VE não ter",
        f"chegado em algum braço: {resultado.pares_descartados}.",
        "",
        "## 1. Quantas disputas o modelo de fato decidiu",
        "",
        *secao_contagens(resultado),
        "",
        "*Sob preempção em curso* é onde a guarda de oscilação age diferente nos",
        "dois braços: no `PREEMPCAO` o E8 a aplica por último, e no `PREEMPCAO_ML`",
        "ela vem antes do modelo. A diferença entre os braços é, portanto, o modelo",
        "**mais** a posição da guarda.",
        "",
        "## 2. Teste pareado — o VE mais prejudicado",
        "",
        *secao_teste(comparacao, p_ajustado),
        "",
        f"Seeds com o mesmo valor nos dois braços: {resultado.seeds_identicas}.",
        f"Seeds em que o modelo divergiu do E8 ao menos uma vez: "
        f"{len(resultado.seeds_com_divergencia)}.",
        "",
    ]
    if resultado.exploratoria is not None:
        linhas += [
            "### Exploratória: só as seeds com divergência",
            "",
            "Fora da família de Holm. O subconjunto é escolhido por uma variável",
            "que só existe no braço de ML, e a guarda separa os braços também fora",
            "dele: serve para descrever, não para decidir H4.",
            "",
            *secao_teste(resultado.exploratoria, resultado.exploratoria.p_wilcoxon),
            "",
        ]
    linhas += [
        "## 3. Veredito",
        "",
        f"**{veredito(comparacao, p_ajustado)}** — regra declarada antes dos dados:",
        f"FAVORÁVEL com p de Holm < {_n(ALFA, 2)} e o VE mais prejudicado mais rápido",
        "no braço de ML (mediana das diferenças e δ negativos); NULO caso contrário.",
        "Um efeito significativo no sentido oposto é reportado como DESFAVORÁVEL.",
        "",
    ]
    return "\n".join(linhas) + "\n"


def main(argumentos: Sequence[str] | None = None) -> int:
    saida_utf8()
    analisador = argparse.ArgumentParser(description="Análise de H4 (entrega 10.8).")
    analisador.add_argument("--dados", type=Path, default=DADOS_PADRAO)
    analisador.add_argument("--saida", type=Path, default=None, help="arquivo .md")
    opcoes = analisador.parse_args(argumentos)

    try:
        dados = ler_pasta(opcoes.dados)
        resultado = analisar(dados)
    except DadosInvalidosError as erro:
        print(f"não dá para analisar H4: {erro}")
        return 1
    texto = gerar_markdown(resultado)
    if opcoes.saida is not None:
        opcoes.saida.parent.mkdir(parents=True, exist_ok=True)
        opcoes.saida.write_text(texto, encoding="utf-8")
    print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
