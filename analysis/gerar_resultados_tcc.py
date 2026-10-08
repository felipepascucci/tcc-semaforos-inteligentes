"""Capítulo 5 inteiro, com um comando — Bloco 9 (`context/07` §2).

    python -m analysis.gerar_resultados_tcc
    python -m analysis.gerar_resultados_tcc --dados analysis/data/bloco8 --saida analysis/saida

Lê os CSV do lote do Bloco 8 e escreve em `--saida`:

- `resultados.md` — caracterização das execuções, T1 a T6, a análise de H4 e o
  que ficou pendente, em Markdown;
- `tabelas/T*.tex` — as mesmas tabelas em LaTeX (`booktabs`);
- `comparacoes.csv` — toda comparação pareada, com p bruto e p de Holm;
- `figuras/F*.pdf` — F1 a F6 (`context/07` §5);
- `h4.md` — o relatório da entrega 10.8.

**Nenhum número do capítulo é digitado à mão.** Se o dado não existe, a tabela
diz que não existe, e o pipeline não inventa um valor no lugar
(`context/07` §1).

AS REGRAS DE VEREDITO, DECLARADAS ANTES DOS DADOS DO BLOCO 8

- **H1** (P1): em `moderado` e em `intenso`, a redução da travessia do VE no
  braço `PREEMPCAO` contra o `FIXO` — média, sobre as seeds, da redução
  relativa de cada seed — é de pelo menos 25% **e** o Wilcoxon tem p de Holm
  abaixo de alfa. Os dois cenários: ACEITA; um: PARCIAL; nenhum: REJEITADA. O
  `leve` é medido sem meta.
- **H2** (P17): em `moderado` e em `intenso`, a mitigação
  `(PREEMPCAO - COMPENSADA) / (PREEMPCAO - FIXO)`, com as médias da espera
  transversal entre as seeds, é de pelo menos 15%. Os dois: ACEITA; senão,
  REJEITADA (a T6 de `context/07` não prevê PARCIAL para H2). O IC 95% e o p da
  comparação `COMPENSADA x PREEMPCAO` vão ao lado.
- **H3**: p95 da latência fim a fim de bancada abaixo de 200 ms, na sessão das
  100 passagens (`context/07` T6).
- **RNF01**: o pior p95 da latência de decisão, entre todas as execuções com
  motor, abaixo de 100 ms.
- **H4** (P19): `analysis/analise_h4.veredito`, com o p de Holm desta família.

**A família de Holm é o capítulo inteiro**: toda comparação de T1, de T3 e a de
H4. É a leitura mais conservadora de `context/07` §3.4 ("4 cenários x várias
métricas").
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

from adapters.terminal import saida_utf8
from analysis import analise_h4, figuras
from analysis.carregar import (
    BANCADA_PADRAO,
    BASELINE,
    CALIBRACAO_PADRAO,
    COMPENSADA,
    DADOS_PADRAO,
    ML,
    PREEMPCAO,
    Dados,
    DadosInvalidosError,
    TravessiaPareada,
    fila_maxima_transversal,
    ler_caracterizacao,
    ler_pasta,
    por_seed,
    travessia_pareada,
)
from analysis.estatistica import (
    ALFA,
    REAMOSTRAGENS,
    ComparacaoPareada,
    comparar_pareado,
    holm,
    ic_bootstrap,
    magnitude_cliff,
    mediana_iqr,
)
from analysis.resumo_bancada import LIMIAR_H3_MS, ler_amostras
from analysis.tabelas import Tabela, intervalo, num, p_valor, pct, pct_sinal
from sim.controlador.coletor import percentil

RAIZ = Path(__file__).resolve().parents[1]
SAIDA_PADRAO = RAIZ / "analysis" / "saida"
TRACO_PADRAO = RAIZ / "analysis" / "data" / "bloco8_traco"

#: Meta de H1 (decisão P1) e os cenários em que vale.
META_H1 = 0.25
CENARIOS_H1 = ("moderado", "intenso")

#: Meta de H2 (P17) e os cenários em que vale.
META_H2 = 0.15
CENARIOS_H2 = ("moderado", "intenso")

#: Orçamento do RNF01 para o p95 da latência de decisão.
ORCAMENTO_RNF01_MS = 100.0

#: A sessão da ponte das 100 passagens que sustentam H3 (`context/07` T6,
#: `analysis/data/resumo_bancada_2026-10-07.md`). É o endereço da medição, e
#: não um resultado: os números saem de `latencia_bancada.csv`.
SESSAO_H3 = "2026-10-07T16:18:08.177357+00:00"

#: O cruzamento e o VE das figuras F3, F4 e F6, **escolhidos antes de ver as
#: figuras**: o primeiro cruzamento da rota do corredor e o primeiro VE da
#: execução. Escolher depois de olhar seria escolher o exemplo que mais
#: favorece o modelo.
CRUZAMENTO_FIGURAS = "CRUZ_01"

#: O `context/07` §3.3 pede "redução vs. FIXO"; a coluna diz sobre qual braço.
ACEITA, PARCIAL, REJEITADA = "ACEITA", "PARCIAL", "REJEITADA"


@dataclass(frozen=True)
class Comparacao:
    """Uma comparação pareada da família de Holm.

    Attributes:
        tabela: Onde ela aparece (`T1`, `T3`, `H4`).
        cenario: Cenário.
        metrica: O que se compara.
        alvo: Braço tratado.
        base: Braço de controle.
        resultado: Os quatro itens de `context/07` §3.3.
        p_holm: p de Wilcoxon ajustado na família inteira.
    """

    tabela: str
    cenario: str
    metrica: str
    alvo: str
    base: str
    resultado: ComparacaoPareada
    p_holm: float = math.nan

    @property
    def chave(self) -> tuple[str, str, str, str]:
        """Identifica a comparação para achar o p ajustado."""
        return (self.tabela, self.cenario, self.alvo, self.base)


@dataclass(frozen=True)
class ReducaoH1:
    """A redução da travessia de um braço contra o `FIXO`, num cenário.

    Attributes:
        cenario: Cenário.
        modo: Braço.
        por_seed: Redução relativa de cada seed, em fração.
        media: Média das reduções — o número que se compara com a meta.
        ic: IC 95% da média, por bootstrap das seeds.
    """

    cenario: str
    modo: str
    por_seed: tuple[float, ...]
    media: float
    ic: tuple[float, float]


@dataclass(frozen=True)
class MitigacaoH2:
    """Custo transversal da preempção e o quanto E7 devolve, num cenário.

    Attributes:
        cenario: Cenário.
        seeds: Seeds com os três braços.
        espera: Média da espera transversal entre as seeds, por braço.
        custo: `(PREEMPCAO - FIXO) / FIXO`.
        mitigacao: `(PREEMPCAO - COMPENSADA) / (PREEMPCAO - FIXO)` (P17).
        ic_mitigacao: IC 95% da mitigação, por bootstrap das seeds.
    """

    cenario: str
    seeds: int
    espera: Mapping[str, float]
    custo: float
    mitigacao: float
    ic_mitigacao: tuple[float, float]


@dataclass
class Resultados:
    """Tudo o que o capítulo reporta, antes de virar texto."""

    dados: Dados
    travessias: dict[str, TravessiaPareada]
    reducoes: dict[tuple[str, str], ReducaoH1]
    mitigacoes: dict[str, MitigacaoH2]
    comparacoes: list[Comparacao]
    h4: analise_h4.ResultadoH4 | None
    vc: dict[str, float]
    bancada: list[float]

    def comparacao(self, tabela: str, cenario: str, alvo: str, base: str) -> Comparacao | None:
        """A comparação pedida, já com o p de Holm, ou `None`."""
        return next((c for c in self.comparacoes if c.chave == (tabela, cenario, alvo, base)), None)


# ---------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------


def _reducao(
    base: np.ndarray, alvo: np.ndarray, reamostragens: int
) -> tuple[tuple[float, ...], float, tuple[float, float]]:
    reducoes = (base - alvo) / base
    return (
        tuple(float(r) for r in reducoes),
        float(reducoes.mean()),
        ic_bootstrap(
            reducoes.size, lambda i: float(reducoes[i].mean()), reamostragens=reamostragens
        ),
    )


def _mitigacao(f: np.ndarray, p: np.ndarray, c: np.ndarray) -> float:
    acrescimo = p.mean() - f.mean()
    return math.nan if abs(acrescimo) < 1e-12 else float((p.mean() - c.mean()) / acrescimo)


def calcular(
    dados: Dados,
    *,
    vc: Mapping[str, float] | None = None,
    bancada: Sequence[float] = (),
    reamostragens: int = REAMOSTRAGENS,
) -> Resultados:
    """Calcula T1, T3, H2, H4 e a família de Holm.

    Args:
        dados: A pasta do lote, lida.
        vc: v/c medido por cenário, para a caracterização e a F5.
        bancada: Latências fim a fim da sessão de H3, em ms.
        reamostragens: Reamostras do bootstrap (os testes usam menos).
    """
    travessias: dict[str, TravessiaPareada] = {}
    reducoes: dict[tuple[str, str], ReducaoH1] = {}
    mitigacoes: dict[str, MitigacaoH2] = {}
    comparacoes: list[Comparacao] = []

    for cenario in dados.cenarios():
        modos = dados.modos(cenario)
        if BASELINE not in modos:
            continue
        pareada = travessia_pareada(dados, cenario, modos)
        travessias[cenario] = pareada
        base = pareada.por_seed[BASELINE].to_numpy()
        for modo in modos:
            if modo == BASELINE or pareada.por_seed.empty:
                continue
            alvo = pareada.por_seed[modo].to_numpy()
            comparacoes.append(
                Comparacao(
                    "T1",
                    cenario,
                    "travessia do VE (s)",
                    modo,
                    BASELINE,
                    comparar_pareado(alvo, base, reamostragens=reamostragens),
                )
            )
            por_seed_r, media, ic = _reducao(base, alvo, reamostragens)
            reducoes[(cenario, modo)] = ReducaoH1(cenario, modo, por_seed_r, media, ic)

        espera = por_seed(dados, cenario, "tempo_espera_medio_transversal_s", modos)
        if espera.empty:
            continue
        for modo in modos:
            if modo == BASELINE:
                continue
            comparacoes.append(
                Comparacao(
                    "T3",
                    cenario,
                    "espera transversal (s)",
                    modo,
                    BASELINE,
                    comparar_pareado(
                        espera[modo].to_numpy(),
                        espera[BASELINE].to_numpy(),
                        reamostragens=reamostragens,
                    ),
                )
            )
        if {PREEMPCAO, COMPENSADA} <= set(modos):
            f, p, c = (espera[m].to_numpy() for m in (BASELINE, PREEMPCAO, COMPENSADA))
            comparacoes.append(
                Comparacao(
                    "T3",
                    cenario,
                    "espera transversal (s)",
                    COMPENSADA,
                    PREEMPCAO,
                    comparar_pareado(c, p, reamostragens=reamostragens),
                )
            )
            mitigacoes[cenario] = MitigacaoH2(
                cenario=cenario,
                seeds=len(espera),
                espera={m: float(espera[m].mean()) for m in modos},
                custo=float((p.mean() - f.mean()) / f.mean()),
                mitigacao=_mitigacao(f, p, c),
                ic_mitigacao=ic_bootstrap(
                    len(espera),
                    lambda i, f=f, p=p, c=c: _mitigacao(f[i], p[i], c[i]),
                    reamostragens=reamostragens,
                ),
            )

    h4 = None
    if analise_h4.CENARIO_H4 in dados.cenarios() and set(analise_h4.BRACOS_H4) <= set(
        dados.modos(analise_h4.CENARIO_H4)
    ):
        h4 = analise_h4.analisar(dados, reamostragens=reamostragens)
        if h4.comparacao is not None:
            comparacoes.append(
                Comparacao(
                    "H4",
                    analise_h4.CENARIO_H4,
                    "tempo do VE mais prejudicado (s)",
                    ML,
                    PREEMPCAO,
                    h4.comparacao,
                )
            )

    ajustados = holm([c.resultado.p_wilcoxon for c in comparacoes])
    comparacoes = [replace(c, p_holm=p) for c, p in zip(comparacoes, ajustados, strict=True)]
    return Resultados(
        dados=dados,
        travessias=travessias,
        reducoes=reducoes,
        mitigacoes=mitigacoes,
        comparacoes=comparacoes,
        h4=h4,
        vc=dict(vc or {}),
        bancada=list(bancada),
    )


# ---------------------------------------------------------------------------
# Vereditos (T6)
# ---------------------------------------------------------------------------


def atinge_h1(resultados: Resultados, cenario: str) -> bool | None:
    """Se o cenário atinge a meta de H1; `None` se faltar o dado."""
    reducao = resultados.reducoes.get((cenario, PREEMPCAO))
    comparacao = resultados.comparacao("T1", cenario, PREEMPCAO, BASELINE)
    if reducao is None or comparacao is None:
        return None
    return reducao.media >= META_H1 and comparacao.p_holm < ALFA


def veredito_h1(resultados: Resultados) -> str:
    """ACEITA, PARCIAL ou REJEITADA; `—` se faltar algum dos dois cenários."""
    atingidos = [atinge_h1(resultados, c) for c in CENARIOS_H1]
    if any(a is None for a in atingidos):
        return "—"
    quantos = sum(bool(a) for a in atingidos)
    return ACEITA if quantos == len(CENARIOS_H1) else (PARCIAL if quantos else REJEITADA)


def veredito_h2(resultados: Resultados) -> str:
    """ACEITA ou REJEITADA; `—` se faltar algum dos dois cenários."""
    mitigacoes = [resultados.mitigacoes.get(c) for c in CENARIOS_H2]
    if any(m is None or math.isnan(m.mitigacao) for m in mitigacoes):
        return "—"
    return ACEITA if all(m.mitigacao >= META_H2 for m in mitigacoes if m) else REJEITADA


def _com_motor(dados: Dados) -> pd.DataFrame:
    return dados.execucoes[dados.execucoes["modo"] != BASELINE]


def pior_p95(dados: Dados) -> float:
    """O pior p95 da latência de decisão entre as execuções com motor."""
    com_motor = _com_motor(dados)
    return float(com_motor["latencia_p95_ms"].max()) if not com_motor.empty else math.nan


# ---------------------------------------------------------------------------
# Tabelas
# ---------------------------------------------------------------------------


def _rotulo_cenario(cenario: str, vc: Mapping[str, float]) -> str:
    return f"{cenario} (v/c {num(vc[cenario], 2)})" if cenario in vc else cenario


def tabela_t1(r: Resultados) -> Tabela:
    """T1 — tempo de deslocamento do VE por cenário e braço."""
    linhas = []
    for cenario, pareada in r.travessias.items():
        for modo in pareada.modos:
            mediana, iqr = mediana_iqr(pareada.por_seed[modo].to_numpy())
            comparacao = r.comparacao("T1", cenario, modo, BASELINE)
            reducao = r.reducoes.get((cenario, modo))
            linhas.append(
                [
                    _rotulo_cenario(cenario, r.vc),
                    modo,
                    str(len(pareada.por_seed)),
                    num(mediana),
                    num(iqr),
                    pct(reducao.media) if reducao else "—",
                    intervalo(reducao.ic, percentual=True) if reducao else "—",
                    p_valor(comparacao.resultado.p_wilcoxon) if comparacao else "—",
                    p_valor(comparacao.p_holm) if comparacao else "—",
                    (
                        f"{num(comparacao.resultado.delta, 2)} ({comparacao.resultado.magnitude})"
                        if comparacao
                        else "—"
                    ),
                ]
            )
    descartados = sum(p.ves_descartados for p in r.travessias.values())
    return Tabela(
        "T1",
        "Tempo de deslocamento do VE por cenário e braço",
        (
            "Cenário",
            "Modo",
            "n",
            "Mediana (s)",
            "IQR (s)",
            "Redução vs. FIXO",
            "IC 95% da redução",
            "p Wilcoxon",
            "p Holm",
            "Cliff's δ",
        ),
        linhas,
        notas=(
            "n é o número de seeds pareadas; cada uma entra com a travessia média dos VEs "
            "presentes em todos os braços do cenário (`analysis/carregar.py`). "
            f"VEs fora da interseção: {descartados}.",
            "Redução: média, sobre as seeds, de (FIXO - braço) / FIXO; IC por bootstrap "
            "percentil das seeds. Wilcoxon bilateral; p de Holm sobre a família do capítulo. "
            "δ = P(braço > FIXO) - P(braço < FIXO): negativo é travessia menor.",
        ),
    )


def tabela_t1_secundaria(r: Resultados) -> Tabela:
    """T1b — o teste secundário e a diferença em segundos, para cada linha de T1."""
    linhas = [
        [
            _rotulo_cenario(c.cenario, r.vc),
            c.alvo,
            num(c.resultado.mediana_diferenca),
            intervalo(c.resultado.ic_mediana_diferenca),
            num(c.resultado.t, 2),
            p_valor(c.resultado.p_t),
            p_valor(c.resultado.p_shapiro),
        ]
        for c in r.comparacoes
        if c.tabela == "T1"
    ]
    return Tabela(
        "T1b",
        "Diferença pareada da travessia do VE e o teste secundário",
        (
            "Cenário",
            "Modo",
            "Mediana da diferença (s)",
            "IC 95%",
            "t pareado",
            "p (t)",
            "Shapiro-Wilk (dif.)",
        ),
        linhas,
        notas=(
            "Diferença por seed: braço - FIXO. O t pareado é o teste secundário; o Shapiro-Wilk "
            "das diferenças é informado para o leitor julgar a normalidade, e não escolhe o "
            "teste (`context/07` §3.2).",
        ),
    )


def tabela_t2(r: Resultados) -> Tabela:
    """T2 — latência de decisão (simulação) e fim a fim (bancada)."""
    linhas = []
    latencias = r.dados.latencias
    if not latencias.empty:
        for modo, grupo in latencias.groupby("modo", sort=False):
            valores = grupo["latencia_ms"].astype(float).tolist()
            linhas.append(_linha_latencia("SIMULACAO (decisão)", str(modo), valores))
    com_motor = _com_motor(r.dados)
    if not com_motor.empty:
        linhas.append(
            [
                "SIMULACAO (decisão)",
                "pior execução",
                f"{len(com_motor)} execuções",
                "—",
                "—",
                "—",
                num(float(com_motor["latencia_p95_ms"].max()), 3),
                num(float(com_motor["latencia_p99_ms"].max()), 3),
                num(float(com_motor["latencia_max_ms"].max()), 3),
            ]
        )
    if r.bancada:
        linhas.append(_linha_latencia("HARDWARE (fim a fim)", "bancada", r.bancada))
    return Tabela(
        "T2",
        "Latência do sistema",
        (
            "Ambiente",
            "Modo",
            "n",
            "Mín (ms)",
            "Mediana (ms)",
            "Média (ms)",
            "p95 (ms)",
            "p99 (ms)",
            "Máx (ms)",
        ),
        linhas,
        notas=(
            "SIMULACAO: latência de **decisão** (RNF01), `motor.avaliar()` cronometrado; as "
            "linhas por modo juntam as decisões das execuções exemplares (`latencias.csv`), e a "
            "linha *pior execução* traz o maior p95, p99 e máximo entre todas as execuções com "
            "motor (`execucoes.csv`). HARDWARE: latência **fim a fim** de H3, da leitura da tag "
            f"ao `PREEMP_INI`, sessão `{SESSAO_H3}`. São grandezas diferentes (`context/07` §1, "
            "nota de T2). Percentis pelo posto mais próximo.",
        ),
    )


def _linha_latencia(ambiente: str, modo: str, valores: Sequence[float]) -> list[str]:
    return [
        ambiente,
        modo,
        str(len(valores)),
        num(min(valores), 3),
        num(statistics.median(valores), 3),
        num(statistics.fmean(valores), 3),
        num(percentil(valores, 95), 3),
        num(percentil(valores, 99), 3),
        num(max(valores), 3),
    ]


def tabela_t3(r: Resultados) -> Tabela:
    """T3 — impacto nas vias transversais."""
    fila = fila_maxima_transversal(r.dados)
    linhas = []
    for cenario in r.dados.cenarios():
        modos = r.dados.modos(cenario)
        espera = por_seed(r.dados, cenario, "tempo_espera_medio_transversal_s", modos)
        execucoes = r.dados.execucoes[r.dados.execucoes["cenario"] == cenario]
        for modo in modos:
            daquele = execucoes[execucoes["modo"] == modo]
            filas = fila[(fila["cenario"] == cenario) & (fila["modo"] == modo)]["fila_maxima"]
            vazao = daquele["veiculos_completos"] / (daquele["duracao_s"] / 3600.0)
            comparacao = r.comparacao("T3", cenario, modo, BASELINE)
            media = float(espera[modo].mean()) if modo in espera else math.nan
            base = float(espera[BASELINE].mean()) if BASELINE in espera else math.nan
            linhas.append(
                [
                    _rotulo_cenario(cenario, r.vc),
                    modo,
                    num(media, 2),
                    num(float(filas.median()) if not filas.empty else math.nan, 1),
                    num(float(vazao.mean()) if not vazao.empty else math.nan, 0),
                    "—" if modo == BASELINE else pct_sinal((media - base) / base),
                    p_valor(comparacao.resultado.p_wilcoxon) if comparacao else "—",
                    p_valor(comparacao.p_holm) if comparacao else "—",
                ]
            )
    return Tabela(
        "T3",
        "Impacto nas vias transversais",
        (
            "Cenário",
            "Modo",
            "Espera média transversal (s)",
            "Fila máxima (veíc.)",
            "Throughput (veíc./h)",
            "Δ vs. FIXO",
            "p Wilcoxon",
            "p Holm",
        ),
        linhas,
        notas=(
            "Espera: média entre as seeds de `tempo_espera_medio_transversal_s` (a hora inteira, "
            "aquecimento descartado; P17). Fila máxima: mediana entre as seeds do maior pico de "
            "fila entre os acessos transversais. Throughput: veículos que completaram a rota por "
            "hora simulada, na malha inteira.",
        ),
    )


def tabela_h2(r: Resultados) -> Tabela:
    """T3b — a mitigação de H2 por cenário, com IC e o teste COMPENSADA x PREEMPCAO."""
    linhas = []
    for cenario, m in r.mitigacoes.items():
        comparacao = r.comparacao("T3", cenario, COMPENSADA, PREEMPCAO)
        linhas.append(
            [
                _rotulo_cenario(cenario, r.vc),
                str(m.seeds),
                pct_sinal(m.custo),
                pct_sinal(m.mitigacao),
                intervalo(m.ic_mitigacao, percentual=True),
                p_valor(comparacao.resultado.p_wilcoxon) if comparacao else "—",
                p_valor(comparacao.p_holm) if comparacao else "—",
                (
                    ("atinge" if m.mitigacao >= META_H2 else "não atinge")
                    if cenario in CENARIOS_H2
                    else "sem meta"
                ),
            ]
        )
    return Tabela(
        "T3b",
        "Mitigação do acréscimo de espera transversal pela compensação (H2)",
        (
            "Cenário",
            "Seeds",
            "Custo da preempção",
            "Mitigação",
            "IC 95%",
            "p (COMP. x PREEMP.)",
            "p Holm",
            f"Meta ≥ {pct(META_H2, 0)}",
        ),
        linhas,
        notas=(
            "Custo: (PREEMPCAO - FIXO) / FIXO. Mitigação: (PREEMPCAO - COMPENSADA) / "
            "(PREEMPCAO - FIXO), com as médias entre as seeds (P17). A meta vale em `moderado` e "
            "`intenso`; nos demais, e onde o acréscimo é próximo de zero, a fração é instável e "
            "é só descritiva.",
        ),
    )


def tabela_t4(r: Resultados) -> Tabela:
    """T4 — o que o lote registra da priorização (ver a nota: T4 adaptada)."""
    linhas = []
    conflitos = r.dados.conflitos
    for cenario in r.dados.cenarios():
        for modo in r.dados.modos(cenario):
            if modo == BASELINE:
                continue
            ves = r.dados.ves[(r.dados.ves["cenario"] == cenario) & (r.dados.ves["modo"] == modo)]
            execucoes = r.dados.execucoes[
                (r.dados.execucoes["cenario"] == cenario) & (r.dados.execucoes["modo"] == modo)
            ]
            episodios = (
                conflitos[(conflitos["cenario"] == cenario) & (conflitos["modo"] == modo)]
                if not conflitos.empty
                else pd.DataFrame()
            )
            sem_parada = int((ves["paradas"] == 0).sum())
            linhas.append(
                [
                    _rotulo_cenario(cenario, r.vc),
                    modo,
                    str(len(ves)),
                    f"{sem_parada} ({pct(sem_parada / len(ves)) if len(ves) else '—'})",
                    str(len(episodios)),
                    str(int(execucoes["violacoes"].sum())),
                ]
            )
    return Tabela(
        "T4",
        "Priorização: travessias sem parada, conflitos adiados e abortos",
        ("Cenário", "Modo", "VEs", "Sem parada (RF03)", "Conflitos adiados", "Abortos"),
        linhas,
        notas=(
            "**T4 adaptada ao que o lote registra.** O `context/07` §4 prevê as colunas "
            "*priorizações solicitadas*, *sucesso*, *conflito adiado*, *timeout* e *abortado*, "
            "que viriam de `log_prioridade`; a simulação não grava `log_prioridade`, e o lote "
            "não conta pedidos de priorização nem timeouts de E6. O que existe: VEs que "
            "completaram a rota e quantos não pararam (`waitingCount = 0`, o critério do RF03); "
            "episódios de disputa entre VEs, em cada um dos quais um VE é adiado "
            "(`conflitos_por_execucao.csv`); e abortos, que o executor só faz por violação de "
            "invariante (`executor.decidir_e_aplicar`).",
        ),
    )


def tabela_t5(r: Resultados) -> Tabela:
    """T5 — segurança, por cenário e braço."""
    descartes = r.dados.descartes
    reprovadas = (
        descartes[descartes["tipo"].isin(["DESCARTE", "FALHA"])]
        if not descartes.empty and "tipo" in descartes.columns
        else pd.DataFrame(columns=["cenario", "modo"])
    )
    linhas = []
    for cenario in r.dados.cenarios():
        for modo in r.dados.modos(cenario):
            execucoes = r.dados.execucoes[
                (r.dados.execucoes["cenario"] == cenario) & (r.dados.execucoes["modo"] == modo)
            ]
            descartadas = int(
                ((reprovadas["cenario"] == cenario) & (reprovadas["modo"] == modo)).sum()
            )
            linhas.append(
                [
                    _rotulo_cenario(cenario, r.vc),
                    modo,
                    str(len(execucoes)),
                    str(int(execucoes["colisoes"].sum())),
                    str(int(execucoes["violacoes"].sum())),
                    str(int(execucoes["teleportes"].sum())),
                    str(descartadas),
                ]
            )
    return Tabela(
        "T5",
        "Segurança",
        (
            "Cenário",
            "Modo",
            "Execuções válidas",
            "Colisões",
            "Violações I1-I5",
            "Teleportes",
            "Descartadas",
        ),
        linhas,
        notas=(
            "Todas devem ser zero (`context/07` §4). Descartadas: execuções que "
            "`validar_execucao()` reprovou, registradas em `descartes.csv` e fora das demais "
            "tabelas (`context/06` §4).",
        ),
    )


def tabela_t6(r: Resultados) -> Tabela:
    """T6 — verificação das hipóteses."""

    def resultado_h1(cenario: str) -> str:
        reducao = r.reducoes.get((cenario, PREEMPCAO))
        comparacao = r.comparacao("T1", cenario, PREEMPCAO, BASELINE)
        if reducao is None or comparacao is None:
            return f"{cenario}: —"
        return (
            f"{cenario}: {pct(reducao.media)} {intervalo(reducao.ic, percentual=True)}, "
            f"p Holm {p_valor(comparacao.p_holm)}"
        )

    def resultado_h2(cenario: str) -> str:
        m = r.mitigacoes.get(cenario)
        if m is None:
            return f"{cenario}: —"
        return f"{cenario}: {pct_sinal(m.mitigacao)} {intervalo(m.ic_mitigacao, percentual=True)}"

    p95 = pior_p95(r.dados)
    linhas = [
        [
            "H1",
            f"Redução ≥ {pct(META_H1, 0)} em moderado e intenso, braço PREEMPCAO (P1)",
            "; ".join(resultado_h1(c) for c in CENARIOS_H1),
            veredito_h1(r),
        ],
        ["H1 (exploratório)", "leve — sem meta", resultado_h1("leve"), "n/a"],
        [
            "H2",
            f"Mitigação ≥ {pct(META_H2, 0)} do acréscimo em moderado e intenso (P17)",
            "; ".join(resultado_h2(c) for c in CENARIOS_H2),
            veredito_h2(r),
        ],
    ]
    if r.bancada:
        p95_bancada = percentil(r.bancada, 95)
        linhas.append(
            [
                "H3",
                f"p95 fim a fim < {num(LIMIAR_H3_MS, 0)} ms, bancada",
                f"p95 {num(p95_bancada)} ms, n = {len(r.bancada)}",
                ACEITA if p95_bancada < LIMIAR_H3_MS else REJEITADA,
            ]
        )
    linhas.append(
        [
            "RNF01",
            f"p95 da decisão < {num(ORCAMENTO_RNF01_MS, 0)} ms",
            f"pior p95 entre as execuções: {num(p95, 3)} ms",
            "—" if math.isnan(p95) else ("ATENDE" if p95 < ORCAMENTO_RNF01_MS else "NÃO ATENDE"),
        ]
    )
    if r.h4 is not None and r.h4.comparacao is not None:
        comparacao = r.comparacao("H4", analise_h4.CENARIO_H4, ML, PREEMPCAO)
        p_holm = comparacao.p_holm if comparacao else math.nan
        c = r.h4.comparacao
        linhas.append(
            [
                "H4",
                "PREEMPCAO_ML reduz o tempo do VE mais prejudicado — direcional, sem meta (P19)",
                f"mediana da diferença {num(c.mediana_diferenca)} s "
                f"{intervalo(c.ic_mediana_diferenca)}, δ {num(c.delta, 2)}, "
                f"p Holm {p_valor(p_holm)}",
                analise_h4.veredito(c, p_holm),
            ]
        )
    else:
        linhas.append(["H4", "PREEMPCAO_ML x PREEMPCAO (P19)", "sem os dois braços nos dados", "—"])
    return Tabela(
        "T6",
        "Verificação das hipóteses",
        ("Hipótese", "Critério", "Resultado medido", "Veredito"),
        linhas,
        alinhamento="llll",
        notas=(
            "Regras de veredito no docstring de `analysis/gerar_resultados_tcc.py`, declaradas "
            "antes dos dados do Bloco 8.",
        ),
    )


# ---------------------------------------------------------------------------
# Caracterização (`context/07` §6, itens 1 e 2)
# ---------------------------------------------------------------------------


def caracterizacao(r: Resultados) -> list[str]:
    """Quantas execuções, de que código, e o que foi descartado."""
    execucoes = r.dados.execucoes
    contagem = execucoes.groupby(["cenario", "modo"]).size()
    seeds = sorted(int(s) for s in execucoes["seed"].unique())
    versoes = r.dados.versoes
    linhas = [
        "## 1. Caracterização das execuções",
        "",
        f"- Pasta dos dados: `{r.dados.pasta.as_posix()}`",
        f"- Execuções válidas: {len(execucoes)}",
        f"- Seeds: {seeds[0]}..{seeds[-1]} ({len(seeds)})" if seeds else "- Seeds: —",
        f"- Versão do código: {', '.join(f'`{v}`' for v in versoes)}",
        "",
    ]
    if len(versoes) > 1 or any(v.endswith("-suja") for v in versoes):
        linhas += [
            "> **Atenção:** as execuções não vieram todas de um mesmo commit limpo. O capítulo",
            "> só pode usar dado de um único código versionado (`CLAUDE.md`).",
            "",
        ]
    linhas += ["| Cenário | Modo | Execuções |", "| --- | --- | ---: |"]
    linhas += [f"| {c} | {m} | {n} |" for (c, m), n in contagem.items()]
    descartes = r.dados.descartes
    linhas += ["", f"Registros em `descartes.csv`: {len(descartes)}"]
    if not descartes.empty and "tipo" in descartes.columns:
        por_tipo = descartes.groupby("tipo").size()
        linhas.append("; ".join(f"{tipo}: {n}" for tipo, n in por_tipo.items()))
    return [*linhas, ""]


# ---------------------------------------------------------------------------
# Figuras
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Traco:
    """Os CSV de `sim/controlador/traco.py`, se existirem."""

    ve: pd.DataFrame
    fila: pd.DataFrame
    sinal: pd.DataFrame
    viagens: pd.DataFrame


def ler_traco(pasta: Path) -> Traco | None:
    """Lê a pasta do traço; `None` se ela não existir ou estiver incompleta."""
    arquivos = ("traco_ve.csv", "traco_fila.csv.gz", "traco_sinal.csv", "traco_viagens.csv")
    if not all((pasta / a).is_file() for a in arquivos):
        return None
    return Traco(*(pd.read_csv(pasta / a) for a in arquivos))


def fidelidade_do_traco(traco: Traco, dados: Dados) -> tuple[int, int, float]:
    """Confere o traço contra o lote: `(VEs comparados, divergentes, maior diferença em s)`.

    O traço roda a mesma (cenário, seed) com o mesmo laço; os tempos de VE têm
    de ser os mesmos do lote, ou a figura não ilustra o experimento.
    """
    chaves = ["cenario", "modo", "seed", "id_veiculo"]
    juntos = traco.viagens.merge(
        dados.ves[[*chaves, "tempo_viagem_s"]],
        on=chaves,
        how="outer",
        suffixes=("_traco", "_lote"),
        indicator=True,
    )
    juntos = juntos[
        juntos["modo"].isin(traco.viagens["modo"].unique())
        & juntos["seed"].isin(traco.viagens["seed"].unique())
        & juntos["cenario"].isin(traco.viagens["cenario"].unique())
    ]
    ambos = juntos[juntos["_merge"] == "both"]
    diferencas = (ambos["tempo_viagem_s_traco"] - ambos["tempo_viagem_s_lote"]).abs()
    divergentes = int((diferencas > 0.01).sum() + (juntos["_merge"] != "both").sum())
    return len(juntos), divergentes, float(diferencas.max()) if not diferencas.empty else math.nan


def gerar_figuras(r: Resultados, traco: Traco | None, pasta: Path) -> tuple[list[Path], list[str]]:
    """Gera F1 a F6 no que o dado permite; devolve os arquivos e as pendências."""
    feitas: list[Path] = []
    pendencias: list[str] = []
    por_cenario = {c: t.por_seed for c, t in r.travessias.items() if not t.por_seed.empty}
    if por_cenario:
        feitas.append(figuras.f1_travessia(por_cenario, pasta / "F1_travessia_ve.pdf"))
    if not r.dados.latencias.empty:
        feitas.append(figuras.f2_latencia(r.dados.latencias, pasta / "F2_latencia_decisao.pdf"))
    else:
        pendencias.append(
            "F2: sem `latencias.csv` na pasta dos dados (só existe onde o lote rodou)."
        )
    reducoes = {c: red.por_seed for (c, m), red in r.reducoes.items() if m == PREEMPCAO}
    if reducoes and r.vc:
        feitas.append(
            figuras.f5_reducao_saturacao(
                reducoes, r.vc, META_H1, pasta / "F5_reducao_saturacao.pdf"
            )
        )
    if traco is None:
        pendencias.append(
            "F3, F4 e F6: sem o traço. Gere com `python -m sim.controlador.traco --cenario "
            f"intenso --seed 1 --saida {TRACO_PADRAO.relative_to(RAIZ).as_posix()}`."
        )
        return feitas, pendencias

    ves = sorted(traco.viagens.loc[traco.viagens["modo"] == BASELINE, "id_veiculo"].unique())
    if ves:
        feitas.append(figuras.f3_espaco_tempo(traco.ve, ves[0], pasta / "F3_espaco_tempo.pdf"))
    trechos = [
        t for t in figuras.intervalos_de_preempcao(traco.sinal, PREEMPCAO, CRUZAMENTO_FIGURAS)
    ]
    if trechos:
        inicio, fim = trechos[0]
        feitas.append(
            figuras.f4_fila_transversal(
                traco.fila,
                traco.sinal,
                CRUZAMENTO_FIGURAS,
                (inicio - 60, inicio + 240),
                pasta / "F4_fila_transversal.pdf",
            )
        )
        feitas.append(
            figuras.f6_fases(
                traco.sinal,
                PREEMPCAO,
                CRUZAMENTO_FIGURAS,
                (inicio - 20, fim + 40),
                pasta / "F6_fases.pdf",
            )
        )
    else:
        pendencias.append(f"F4 e F6: nenhuma preempção em {CRUZAMENTO_FIGURAS} no traço.")
    return feitas, pendencias


# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------


def escrever_comparacoes(r: Resultados, destino: Path) -> None:
    """Toda comparação pareada, legível por máquina."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(
            (
                "tabela",
                "cenario",
                "metrica",
                "alvo",
                "base",
                "n",
                "mediana_base",
                "iqr_base",
                "mediana_alvo",
                "iqr_alvo",
                "mediana_diferenca",
                "ic95_inf",
                "ic95_sup",
                "w",
                "p_wilcoxon",
                "p_holm",
                "t",
                "p_t",
                "p_shapiro",
                "cliff_delta",
                "magnitude",
            )
        )
        for c in r.comparacoes:
            x = c.resultado
            escritor.writerow(
                (
                    c.tabela,
                    c.cenario,
                    c.metrica,
                    c.alvo,
                    c.base,
                    x.n,
                    *(
                        f"{v:.6g}"
                        for v in (
                            x.mediana_base,
                            x.iqr_base,
                            x.mediana_alvo,
                            x.iqr_alvo,
                            x.mediana_diferenca,
                            *x.ic_mediana_diferenca,
                            x.w,
                            x.p_wilcoxon,
                            c.p_holm,
                            x.t,
                            x.p_t,
                        )
                    ),
                    "" if x.p_shapiro is None else f"{x.p_shapiro:.6g}",
                    f"{x.delta:.6g}",
                    magnitude_cliff(x.delta),
                )
            )


def gerar(
    dados: Dados,
    saida: Path,
    *,
    vc: Mapping[str, float] | None = None,
    bancada: Sequence[float] = (),
    traco: Traco | None = None,
    reamostragens: int = REAMOSTRAGENS,
    com_figuras: bool = True,
) -> Path:
    """Calcula tudo e escreve a pasta de saída. Devolve o caminho de `resultados.md`."""
    r = calcular(dados, vc=vc, bancada=bancada, reamostragens=reamostragens)
    tabelas = [
        tabela_t1(r),
        tabela_t1_secundaria(r),
        tabela_t2(r),
        tabela_t3(r),
        tabela_h2(r),
        tabela_t4(r),
        tabela_t5(r),
        tabela_t6(r),
    ]
    (saida / "tabelas").mkdir(parents=True, exist_ok=True)
    for tabela in tabelas:
        (saida / "tabelas" / f"{tabela.codigo}.tex").write_text(tabela.latex(), encoding="utf-8")
    escrever_comparacoes(r, saida / "comparacoes.csv")

    feitas: list[Path] = []
    pendencias: list[str] = []
    if com_figuras:
        feitas, pendencias = gerar_figuras(r, traco, saida / "figuras")
    if traco is not None:
        comparados, divergentes, maior = fidelidade_do_traco(traco, dados)
        aviso = "confere" if divergentes == 0 else "**DIVERGE: as figuras não ilustram o lote**"
        pendencias.append(
            f"Traço x lote: {comparados} VEs comparados, {divergentes} divergentes "
            f"(maior diferença {num(maior, 2)} s) — {aviso}."
        )

    p_h4 = r.comparacao("H4", analise_h4.CENARIO_H4, ML, PREEMPCAO)
    if r.h4 is not None:
        (saida / "h4.md").write_text(
            analise_h4.gerar_markdown(r.h4, p_h4.p_holm if p_h4 else None), encoding="utf-8"
        )

    texto = [
        "# Capítulo 5 — resultados gerados",
        "",
        "> Gerado por `python -m analysis.gerar_resultados_tcc`. Nenhum número deste",
        "> arquivo foi digitado à mão; as tabelas em LaTeX estão em `tabelas/`.",
        "",
        *caracterizacao(r),
        "## 2. Tabelas",
        "",
        *(t.markdown() for t in tabelas),
        "## 3. H4 — disputas e o que o modelo decidiu",
        "",
        *(analise_h4.secao_contagens(r.h4) if r.h4 is not None else ["Sem dados de H4."]),
        "",
        "Relatório completo em `h4.md`.",
        "",
        "## 4. Figuras",
        "",
        *(f"- `{p.relative_to(saida).as_posix()}`" for p in feitas),
        "",
    ]
    if pendencias:
        texto += ["## 5. Pendências e conferências", "", *(f"- {p}" for p in pendencias), ""]
    destino = saida / "resultados.md"
    destino.write_text("\n".join(texto), encoding="utf-8")
    return destino


def main(argumentos: Sequence[str] | None = None) -> int:
    saida_utf8()
    analisador = argparse.ArgumentParser(description="Gera o capítulo 5 (Bloco 9).")
    analisador.add_argument("--dados", type=Path, default=DADOS_PADRAO)
    analisador.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    analisador.add_argument("--calibracao", type=Path, default=CALIBRACAO_PADRAO)
    analisador.add_argument("--bancada", type=Path, default=BANCADA_PADRAO)
    analisador.add_argument("--sessao-h3", default=SESSAO_H3)
    analisador.add_argument("--traco", type=Path, default=TRACO_PADRAO)
    analisador.add_argument("--reamostragens", type=int, default=REAMOSTRAGENS)
    analisador.add_argument("--sem-figuras", action="store_true")
    opcoes = analisador.parse_args(argumentos)

    try:
        dados = ler_pasta(opcoes.dados)
    except DadosInvalidosError as erro:
        print(f"não dá para gerar o capítulo: {erro}")
        return 1
    bancada = [
        a.latencia_total_ms for a in ler_amostras(opcoes.bancada) if a.sessao == opcoes.sessao_h3
    ]
    destino = gerar(
        dados,
        opcoes.saida,
        vc=ler_caracterizacao(opcoes.calibracao),
        bancada=bancada,
        traco=ler_traco(opcoes.traco),
        reamostragens=opcoes.reamostragens,
        com_figuras=not opcoes.sem_figuras,
    )
    print(destino.read_text(encoding="utf-8"))
    print(f"capítulo 5 em {opcoes.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
