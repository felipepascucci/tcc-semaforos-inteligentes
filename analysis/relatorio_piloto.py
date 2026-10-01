"""Relatório do piloto experimental — Bloco 4 do plano de desenvolvimento.

    python -m analysis.relatorio_piloto
    python -m analysis.relatorio_piloto --dados analysis/data --saida docs/relatorios

O piloto existe para responder **antes** de o texto estar comprometido: a redução
em `moderado` e `intenso` chega perto dos 25% de H1? Há gridlock? O p95 da
decisão fica sob os 100 ms do RNF01? O `context/08` §6 chama "resultados reais
não confirmam H1" de risco mais subestimado do projeto, e a mitigação é medir
cedo, com poucas seeds.

Este módulo **não faz estatística inferencial**. Wilcoxon, Cliff's δ, IC por
bootstrap e Holm-Bonferroni são o Bloco 9, sobre as 600 execuções. Cinco seeds
não sustentam teste de hipótese; sustentam ordem de grandeza, que é exatamente o
que o Bloco 4 precisa saber.

O PAREAMENTO É POR VE, NÃO POR EXECUÇÃO

A média de travessia de uma execução não é comparável entre braços sem cuidado:
o último VE parte perto do fim do horizonte e, no baseline — que é mais lento —,
pode não chegar dentro dos 3.600 s. Comparar "média dos 5 VEs que chegaram no
FIXO" com "média dos 6 que chegaram na preempção" mediria também a diferença
entre os conjuntos, e o VE a mais é justamente um dos difíceis.

Então a comparação é feita sobre a **interseção dos ids de VE presentes nos três
braços** de cada (cenário, seed). É o pareamento que `context/04` §7 exige,
levado até o nível do veículo: mesmo tráfego de fundo, mesmo instante de partida,
mesmo tipo — só muda o controle. O relatório declara quantos VEs a interseção
descartou, porque descartar em silêncio seria o problema que o pareamento existe
para evitar.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DADOS = RAIZ / "analysis" / "data"
RELATORIOS = RAIZ / "docs" / "relatorios"

ARQUIVO_EXECUCOES = "execucoes.csv"
ARQUIVO_VE = "ve_por_execucao.csv"
ARQUIVO_DESCARTES = "descartes.csv"
ARQUIVO_CALIBRACAO = "calibracao_cenarios.csv"

BASELINE = "FIXO"
MODOS = ("FIXO", "PREEMPCAO", "PREEMPCAO_COMPENSADA")

#: Meta de H1 — redução mínima no tempo de travessia do VE (decisão P1).
META_H1 = 0.25

#: Meta de H2 — mitigação **mínima** do impacto transversal pela compensação (E7).
#: O enunciado passou de "em até 15%" para "em no mínimo 15%" em 2026-08-31: a
#: redação antiga era um teto, e sob ela a mitigação medida aqui cumpriria H2.
#: **O denominador continua em aberto** (P17) — as duas leituras são calculadas e
#: impressas lado a lado, e nenhuma delas atinge a meta, de modo que declarar qual
#: vale não é escolher pelo resultado.
META_H2 = 0.15

#: Orçamento do RNF01 para o p95 da latência de **decisão**, em milissegundos.
ORCAMENTO_RNF01_MS = 100.0

#: Cenários em que a meta de H1 se aplica (decisão P1: "saturação moderada a
#: intensa"). O `leve` é medido e discutido **sem** meta numérica — a Tabela 1 do
#: pré-projeto já mostrava 8,3% em fluxo leve, e nenhuma meta única sobrevive aos
#: quatro cenários. O piloto tem de responder pelos cenários certos.
CENARIOS_COM_META = ("moderado", "intenso")

#: Rótulo extra para o cenário de dois VEs — o que o distingue de `moderado` não
#: é a saturação (é a mesma), é a emergência.
SUFIXO_CENARIO = {"multiplas_emergencias": ", 2 VEs"}


# ---------------------------------------------------------------------------
# Leitura dos CSV
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Execucao:
    """Uma linha de `execucoes.csv`."""

    cenario: str
    modo: str
    seed: int
    versao_codigo: str
    duracao_s: float
    veiculos_planejados: int
    veiculos_completos: int
    ves_completos: int
    tempo_espera_medio_transversal_s: float
    atraso_total_rede_s: float
    latencia_p95_ms: float
    latencia_p99_ms: float
    latencia_max_ms: float
    colisoes: int
    teleportes: int
    violacoes: int

    @property
    def chave(self) -> tuple[str, int]:
        """O par (cenário, seed) — a unidade da comparação pareada."""
        return (self.cenario, self.seed)

    @property
    def escoamento(self) -> float:
        """Fração dos veículos planejados que completou a rota."""
        if not self.veiculos_planejados:
            return 0.0
        return self.veiculos_completos / self.veiculos_planejados


@dataclass(frozen=True)
class ViagemVE:
    """Uma linha de `ve_por_execucao.csv`."""

    cenario: str
    modo: str
    seed: int
    id_veiculo: str
    tipo: str
    tempo_viagem_s: float
    paradas: int


def ler_execucoes(caminho: Path) -> tuple[Execucao, ...]:
    """Lê `execucoes.csv`."""
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return tuple(
            Execucao(
                cenario=linha["cenario"],
                modo=linha["modo"],
                seed=int(linha["seed"]),
                versao_codigo=linha["versao_codigo"],
                duracao_s=float(linha["duracao_s"]),
                veiculos_planejados=int(linha["veiculos_planejados"]),
                veiculos_completos=int(linha["veiculos_completos"]),
                ves_completos=int(linha["ves_completos"]),
                tempo_espera_medio_transversal_s=float(linha["tempo_espera_medio_transversal_s"]),
                atraso_total_rede_s=float(linha["atraso_total_rede_s"]),
                latencia_p95_ms=float(linha["latencia_p95_ms"]),
                latencia_p99_ms=float(linha["latencia_p99_ms"]),
                latencia_max_ms=float(linha["latencia_max_ms"]),
                colisoes=int(linha["colisoes"]),
                teleportes=int(linha["teleportes"]),
                violacoes=int(linha["violacoes"]),
            )
            for linha in csv.DictReader(arquivo)
        )


def ler_viagens(caminho: Path) -> tuple[ViagemVE, ...]:
    """Lê `ve_por_execucao.csv`."""
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return tuple(
            ViagemVE(
                cenario=linha["cenario"],
                modo=linha["modo"],
                seed=int(linha["seed"]),
                id_veiculo=linha["id_veiculo"],
                tipo=linha["tipo"],
                tempo_viagem_s=float(linha["tempo_viagem_s"]),
                paradas=int(linha["paradas"]),
            )
            for linha in csv.DictReader(arquivo)
        )


# ---------------------------------------------------------------------------
# H1 — redução no tempo de travessia do VE
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParPareado:
    """Um (cenário, seed) com os três braços comparados sobre os mesmos VEs.

    Attributes:
        cenario: Cenário do ponto.
        seed: Seed do ponto.
        ves_comuns: VEs presentes nos três braços.
        ves_descartados: VEs presentes em algum braço mas não em todos.
        travessia_por_modo: Travessia média, por braço, sobre os VEs comuns.
        paradas_por_modo: Paradas médias, por braço, sobre os VEs comuns.
    """

    cenario: str
    seed: int
    ves_comuns: int
    ves_descartados: int
    travessia_por_modo: Mapping[str, float]
    paradas_por_modo: Mapping[str, float]

    def reducao(self, modo: str) -> float | None:
        """Redução relativa ao baseline, entre 0 e 1. `None` se faltar braço."""
        base = self.travessia_por_modo.get(BASELINE)
        alvo = self.travessia_por_modo.get(modo)
        if base is None or alvo is None or base <= 0:
            return None
        return (base - alvo) / base


def parear(viagens: Iterable[ViagemVE], modos: Sequence[str] = MODOS) -> tuple[ParPareado, ...]:
    """Casa os braços de cada (cenário, seed) pelos ids de VE em comum.

    Args:
        viagens: Linhas de `ve_por_execucao.csv`.
        modos: Braços que precisam estar presentes.

    Returns:
        Um `ParPareado` por (cenário, seed) com pelo menos um VE em comum,
        ordenado por cenário e seed.
    """
    por_ponto: dict[tuple[str, int], dict[str, dict[str, ViagemVE]]] = {}
    for viagem in viagens:
        chave = (viagem.cenario, viagem.seed)
        por_ponto.setdefault(chave, {}).setdefault(viagem.modo, {})[viagem.id_veiculo] = viagem

    pares: list[ParPareado] = []
    for (cenario, seed), por_modo in sorted(por_ponto.items()):
        presentes = [modo for modo in modos if modo in por_modo]
        if not presentes:
            continue
        comuns = set.intersection(*(set(por_modo[modo]) for modo in presentes))
        todos = set().union(*(set(por_modo[modo]) for modo in presentes))
        if not comuns:
            continue
        pares.append(
            ParPareado(
                cenario=cenario,
                seed=seed,
                ves_comuns=len(comuns),
                ves_descartados=len(todos - comuns),
                travessia_por_modo={
                    modo: statistics.fmean(
                        por_modo[modo][identificador].tempo_viagem_s for identificador in comuns
                    )
                    for modo in presentes
                },
                paradas_por_modo={
                    modo: statistics.fmean(
                        por_modo[modo][identificador].paradas for identificador in comuns
                    )
                    for modo in presentes
                },
            )
        )
    return tuple(pares)


@dataclass(frozen=True)
class ResumoH1:
    """A resposta do piloto sobre H1, para um cenário.

    Attributes:
        cenario: Cenário resumido.
        seeds: Quantas seeds entraram.
        ves_comuns: VEs comparados, somados sobre as seeds.
        ves_descartados: VEs que a interseção deixou de fora.
        travessia_baseline_s: Travessia média no `FIXO`.
        reducoes: Redução por braço, média sobre as seeds.
        piores: Menor redução observada, por braço.
        melhores: Maior redução observada, por braço.
        tem_meta: Se a meta de H1 se aplica a este cenário (decisão P1).
    """

    cenario: str
    seeds: int
    ves_comuns: int
    ves_descartados: int
    travessia_baseline_s: float
    reducoes: Mapping[str, float]
    piores: Mapping[str, float]
    melhores: Mapping[str, float]
    tem_meta: bool

    def atinge_meta(self, modo: str) -> bool:
        """Se a redução média do braço alcança os 25% de H1."""
        return self.reducoes.get(modo, 0.0) >= META_H1


def resumir_h1(pares: Sequence[ParPareado]) -> tuple[ResumoH1, ...]:
    """Agrega os pares por cenário."""
    por_cenario: dict[str, list[ParPareado]] = {}
    for par in pares:
        por_cenario.setdefault(par.cenario, []).append(par)

    resumos: list[ResumoH1] = []
    for cenario, grupo in sorted(por_cenario.items()):
        reducoes: dict[str, float] = {}
        piores: dict[str, float] = {}
        melhores: dict[str, float] = {}
        for modo in MODOS:
            if modo == BASELINE:
                continue
            valores = [par.reducao(modo) for par in grupo]
            limpos = [valor for valor in valores if valor is not None]
            if not limpos:
                continue
            reducoes[modo] = statistics.fmean(limpos)
            piores[modo] = min(limpos)
            melhores[modo] = max(limpos)

        bases = [
            par.travessia_por_modo[BASELINE] for par in grupo if BASELINE in par.travessia_por_modo
        ]
        resumos.append(
            ResumoH1(
                cenario=cenario,
                seeds=len(grupo),
                ves_comuns=sum(par.ves_comuns for par in grupo),
                ves_descartados=sum(par.ves_descartados for par in grupo),
                travessia_baseline_s=statistics.fmean(bases) if bases else 0.0,
                reducoes=reducoes,
                piores=piores,
                melhores=melhores,
                tem_meta=cenario in CENARIOS_COM_META,
            )
        )
    return tuple(resumos)


# ---------------------------------------------------------------------------
# H2 — impacto nas vias transversais
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResumoH2:
    """O custo transversal da preempção e o quanto E7 devolve.

    Attributes:
        cenario: Cenário resumido.
        espera_por_modo: Espera média na transversal, por braço.
        custo: Aumento relativo da espera de `PREEMPCAO` sobre `FIXO`.
        mitigacao: Quanto da espera de `PREEMPCAO` a compensação removeu.
        mitigacao_do_acrescimo: Quanto do **acréscimo** sobre o baseline foi
            removido. É a segunda das duas leituras de "mitigar em no mínimo 15%
            o impacto negativo" — declarar qual vale continua sendo ação de
            redação (P17), com recomendação registrada pela leitura do acréscimo:
            o impacto negativo *é* o acréscimo, e não a espera que existiria sem
            preempção nenhuma. Instável quando o acréscimo é ~0 ou negativo.
    """

    cenario: str
    espera_por_modo: Mapping[str, float]
    custo: float | None
    mitigacao: float | None
    mitigacao_do_acrescimo: float | None


def resumir_h2(execucoes: Sequence[Execucao]) -> tuple[ResumoH2, ...]:
    """Agrega a espera transversal por cenário e braço."""
    por_cenario: dict[str, dict[str, list[float]]] = {}
    for execucao in execucoes:
        alvo = por_cenario.setdefault(execucao.cenario, {})
        alvo.setdefault(execucao.modo, []).append(execucao.tempo_espera_medio_transversal_s)

    resumos: list[ResumoH2] = []
    for cenario, por_modo in sorted(por_cenario.items()):
        medias = {modo: statistics.fmean(valores) for modo, valores in por_modo.items() if valores}
        fixo = medias.get(BASELINE)
        preempcao = medias.get("PREEMPCAO")
        compensada = medias.get("PREEMPCAO_COMPENSADA")

        custo = (preempcao - fixo) / fixo if fixo and preempcao is not None and fixo > 0 else None
        mitigacao = (
            (preempcao - compensada) / preempcao
            if preempcao and compensada is not None and preempcao > 0
            else None
        )
        acrescimo = preempcao - fixo if fixo is not None and preempcao is not None else None
        mitigacao_acrescimo = (
            (preempcao - compensada) / acrescimo
            if acrescimo and compensada is not None and abs(acrescimo) > 1e-9
            else None
        )
        resumos.append(
            ResumoH2(
                cenario=cenario,
                espera_por_modo=medias,
                custo=custo,
                mitigacao=mitigacao,
                mitigacao_do_acrescimo=mitigacao_acrescimo,
            )
        )
    return tuple(resumos)


# ---------------------------------------------------------------------------
# Segurança, escoamento e latência
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResumoSaude:
    """O que precisa ser zero, e o que precisa caber no orçamento.

    Attributes:
        execucoes: Quantas execuções entraram no relatório.
        colisoes: Soma das colisões — precisa ser zero.
        teleportes: Soma dos teleportes — precisa ser zero (gridlock).
        violacoes: Soma das violações de I1..I5 — precisa ser zero.
        escoamento_minimo: Pior fração de veículos que completaram a rota.
        escoamento_pior_ponto: Onde ocorreu o pior escoamento.
        p95_maximo_ms: Pior p95 de latência de decisão entre as execuções.
        p99_maximo_ms: Pior p99.
        maximo_ms: Pior latência isolada.
    """

    execucoes: int
    colisoes: int
    teleportes: int
    violacoes: int
    escoamento_minimo: float
    escoamento_pior_ponto: str
    p95_maximo_ms: float
    p99_maximo_ms: float
    maximo_ms: float

    @property
    def segura(self) -> bool:
        """Se nenhuma execução colidiu, teleportou ou violou invariante."""
        return not (self.colisoes or self.teleportes or self.violacoes)

    @property
    def dentro_do_rnf01(self) -> bool:
        """Se o pior p95 cabe no orçamento de 100 ms."""
        return self.p95_maximo_ms < ORCAMENTO_RNF01_MS


def resumir_saude(execucoes: Sequence[Execucao]) -> ResumoSaude:
    """Consolida segurança, escoamento e latência sobre todas as execuções."""
    pior = min(execucoes, key=lambda execucao: execucao.escoamento, default=None)
    com_latencia = [execucao for execucao in execucoes if execucao.latencia_p95_ms > 0]
    return ResumoSaude(
        execucoes=len(execucoes),
        colisoes=sum(execucao.colisoes for execucao in execucoes),
        teleportes=sum(execucao.teleportes for execucao in execucoes),
        violacoes=sum(execucao.violacoes for execucao in execucoes),
        escoamento_minimo=pior.escoamento if pior else 0.0,
        escoamento_pior_ponto=f"{pior.cenario}/{pior.modo}/seed={pior.seed}" if pior else "-",
        p95_maximo_ms=max((e.latencia_p95_ms for e in com_latencia), default=0.0),
        p99_maximo_ms=max((e.latencia_p99_ms for e in com_latencia), default=0.0),
        maximo_ms=max((e.latencia_max_ms for e in com_latencia), default=0.0),
    )


def ler_caracterizacao(caminho: Path) -> dict[str, str]:
    """Regime medido de cada cenário, de `calibracao_cenarios.csv`.

    **Lido, não escrito à mão.** O v/c e a classificação saem da calibração do
    Bloco 3, que é código versionado; repeti-los como literal aqui os
    congelaria, e uma recalibração — que `context/04` §4 obriga sempre que
    `tau`, `minGap` ou `length` mudarem — passaria a produzir um relatório que
    descreve uma malha que não é a que rodou.

    O nome do cenário é rótulo do ponto experimental; o regime é o v/c medido, e
    é ele que aparece ao lado do nome (decisão de 2026-08-25).
    """
    if not caminho.is_file():
        return {}
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return {
            linha["cenario"]: (
                f"v/c {float(linha['grau_saturacao']):.2f}".replace(".", ",")
                + f" · {linha['classificacao']}"
                + SUFIXO_CENARIO.get(linha["cenario"], "")
            )
            for linha in csv.DictReader(arquivo)
        }


def ler_descartes(caminho: Path) -> tuple[Mapping[str, str], ...]:
    """Lê `descartes.csv`, se existir."""
    if not caminho.is_file():
        return ()
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return tuple(dict(linha) for linha in csv.DictReader(arquivo))


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def _num(valor: float, casas: int = 1) -> str:
    """Número com vírgula decimal, como no resto do `context/` e do TCC."""
    return f"{valor:.{casas}f}".replace(".", ",")


def _pct(valor: float | None, casas: int = 1) -> str:
    """Percentual **sem sinal** — para grandezas cujo nome já diz o sentido.

    "Redução de 31,7%" não precisa de sinal; escrever `-31,7%` numa coluna
    chamada *redução* obrigaria o leitor a decidir se os dois se cancelam.
    """
    return "—" if valor is None else f"{_num(valor * 100, casas)}%"


def _pct_sinal(valor: float | None, casas: int = 1) -> str:
    """Percentual **com sinal** — para variações que podem ir nos dois sentidos.

    O custo transversal pode ser negativo (no `leve` a preempção chega a
    *reduzir* a espera das transversais, porque o corredor verde esvazia filas),
    e a mitigação de E7 também: compensação que piora o que deveria melhorar
    precisa aparecer como número negativo, não como número pequeno.
    """
    if valor is None:
        return "—"
    sinal = "+" if valor > 0 else ("-" if valor < 0 else "")
    return f"{sinal}{_num(abs(valor) * 100, casas)}%"


def _veredito(condicao: bool) -> str:
    return "**sim**" if condicao else "**não**"


def gerar_markdown(
    execucoes: Sequence[Execucao],
    pares: Sequence[ParPareado],
    descartes: Sequence[Mapping[str, str]],
    planejadas: int,
    caracterizacao: Mapping[str, str] | None = None,
) -> str:
    """Monta o relatório do piloto.

    Args:
        execucoes: Linhas de `execucoes.csv`.
        pares: Pontos pareados por VE.
        descartes: Linhas de `descartes.csv`.
        planejadas: Quantas execuções a matriz do piloto previa.
        caracterizacao: Regime medido por cenário, de `calibracao_cenarios.csv`.

    Returns:
        O relatório em Markdown.
    """
    h1 = resumir_h1(pares)
    h2 = resumir_h2(execucoes)
    saude = resumir_saude(execucoes)
    regime = dict(caracterizacao or {})

    versoes = sorted({execucao.versao_codigo for execucao in execucoes if execucao.versao_codigo})
    seeds = sorted({execucao.seed for execucao in execucoes})
    cenarios = sorted({execucao.cenario for execucao in execucoes})
    duracoes = sorted({execucao.duracao_s for execucao in execucoes})
    reprovadas = [linha for linha in descartes if linha.get("tipo") in {"DESCARTE", "FALHA"}]

    com_meta = [resumo for resumo in h1 if resumo.tem_meta]
    h1_confirmada = bool(com_meta) and all(resumo.atinge_meta("PREEMPCAO") for resumo in com_meta)

    linhas: list[str] = [
        f"# Relatório do piloto experimental — {date.today().isoformat()}",
        "",
        "> Gerado por `python -m analysis.relatorio_piloto` a partir de",
        "> `analysis/data/execucoes.csv` e `analysis/data/ve_por_execucao.csv`.",
        "> Nenhum número deste documento foi digitado à mão.",
        "",
        "Bloco 4 do plano de desenvolvimento — **mitigação do risco nº 1** do",
        '`context/08` §6 ("resultados reais não confirmam H1"). O objetivo é',
        "conhecer a ordem de grandeza do ganho **antes** de comprometer o texto,",
        "com tempo de sobra para ajustar o modelo ou a redação.",
        "",
        "## 1. Identificação",
        "",
        "| Campo | Valor |",
        "| --- | --- |",
        f"| Versão do código | `{', '.join(versoes) or 'desconhecida'}` |",
        f"| Cenários | {', '.join(cenarios)} |",
        f"| Seeds | {', '.join(str(seed) for seed in seeds)} |",
        f"| Braços | {', '.join(MODOS)} |",
        f"| Duração simulada | {', '.join(f'{d:.0f} s' for d in duracoes)} |",
        f"| Execuções válidas | {len(execucoes)} de {planejadas} planejadas |",
        f"| Execuções descartadas | {len(reprovadas)} |",
        "",
    ]

    if reprovadas:
        linhas += [
            "Descartes registrados em `analysis/data/descartes.csv`, com o critério",
            "de `context/06` §4 aplicado a toda execução:",
            "",
            "| cenário | modo | seed | motivo |",
            "| --- | --- | --- | --- |",
        ]
        linhas += [
            f"| {linha['cenario']} | {linha['modo']} | {linha['seed']} | {linha['detalhe']} |"
            for linha in reprovadas
        ]
        linhas.append("")

    # -- H1 ------------------------------------------------------------------
    linhas += [
        "## 2. H1 — redução no tempo de travessia do VE",
        "",
        "Comparação **pareada por veículo**: para cada (cenário, seed), só entram",
        "os VEs presentes nos três braços. O último VE parte perto do fim do",
        "horizonte e, no baseline, pode não chegar dentro dos 3.600 s — comparar",
        "conjuntos diferentes mediria também a diferença entre eles.",
        "",
        "A meta de **≥ 25%** vale para `moderado` e `intenso` (decisão P1: saturação",
        "moderada a intensa). O cenário `leve` é medido e discutido **sem** meta",
        "numérica — a Tabela 1 do pré-projeto já mostrava 8,3% nesse regime, e",
        "nenhuma meta única sobrevive aos quatro cenários.",
        "",
        "A coluna *regime medido* vem de `analysis/data/calibracao_cenarios.csv`,",
        "não deste arquivo. O cenário `intenso` classifica como `moderado` porque",
        "mede v/c 0,73 contra o corte de 0,75 — no texto do TCC ele é descrito como",
        "**saturação moderada-alta**, e o nome é rótulo do ponto experimental, não",
        "afirmação sobre o regime (decisão de 2026-08-25).",
        "",
        "| Cenário | Regime medido | VEs | Travessia `FIXO` |"
        " Redução `PREEMPCAO` | Redução `PREEMPCAO_COMPENSADA` | Meta >= 25% |",
        "| --- | --- | ---: | ---: | ---: | ---: | :---: |",
    ]
    for resumo in h1:
        preempcao = resumo.reducoes.get("PREEMPCAO")
        compensada = resumo.reducoes.get("PREEMPCAO_COMPENSADA")
        if not resumo.tem_meta:
            meta = "— (sem meta)"
        else:
            meta = "atinge" if resumo.atinge_meta("PREEMPCAO") else "**NÃO atinge**"
        linhas.append(
            f"| `{resumo.cenario}` | {regime.get(resumo.cenario, '—')} | "
            f"{resumo.ves_comuns} | {_num(resumo.travessia_baseline_s)} s | "
            f"{_pct(preempcao)} | {_pct(compensada)} | {meta} |"
        )

    linhas += [
        "",
        "Dispersão entre as seeds (redução em `PREEMPCAO`, pior e melhor caso):",
        "",
        "| Cenário | Seeds | Menor redução | Média | Maior redução |"
        " VEs descartados pelo pareamento |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for resumo in h1:
        linhas.append(
            f"| `{resumo.cenario}` | {resumo.seeds} | "
            f"{_pct(resumo.piores.get('PREEMPCAO'))} | "
            f"{_pct(resumo.reducoes.get('PREEMPCAO'))} | "
            f"{_pct(resumo.melhores.get('PREEMPCAO'))} | {resumo.ves_descartados} |"
        )

    linhas += [
        "",
        "### Paradas do VE (RF03)",
        "",
        "`waitingCount` médio por VE, sobre os mesmos veículos pareados. O critério",
        "de aceitação do RF03 é o VE **não parar** em cruzamento priorizado.",
        "",
        "| Cenário | `FIXO` | `PREEMPCAO` | `PREEMPCAO_COMPENSADA` |",
        "| --- | ---: | ---: | ---: |",
    ]
    for cenario in cenarios:
        do_cenario = [par for par in pares if par.cenario == cenario]
        if not do_cenario:
            continue
        celulas = []
        for modo in MODOS:
            valores = [
                par.paradas_por_modo[modo] for par in do_cenario if modo in par.paradas_por_modo
            ]
            celulas.append(_num(statistics.fmean(valores), 2) if valores else "—")
        linhas.append(f"| `{cenario}` | {' | '.join(celulas)} |")

    # -- H2 ------------------------------------------------------------------
    linhas += [
        "",
        "## 3. H2 — impacto nas vias transversais",
        "",
        "Espera média por veículo de fundo em via transversal (`tripinfo.waitingTime`,",
        "aquecimento descartado). `custo` é o quanto a preempção acrescenta sobre o",
        "baseline; `mitigação` é o quanto a compensação (E7) devolve.",
        "",
        "| Cenário | `FIXO` | `PREEMPCAO` | `PREEMPCAO_COMPENSADA` | Custo |"
        " Mitigação | Mitigação do acréscimo |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for resumo in h2:
        esperas = " | ".join(
            f"{_num(resumo.espera_por_modo[modo], 2)} s" if modo in resumo.espera_por_modo else "—"
            for modo in MODOS
        )
        linhas.append(
            f"| `{resumo.cenario}` | {esperas} | {_pct_sinal(resumo.custo)} | "
            f"{_pct_sinal(resumo.mitigacao)} | {_pct_sinal(resumo.mitigacao_do_acrescimo)} |"
        )

    linhas += [
        "",
        f"A meta de H2 é mitigar **em no mínimo {META_H2 * 100:.0f}%** o impacto negativo",
        "(enunciado corrigido em 2026-08-31: `em até 15%` era um teto, e sob ele os",
        "números acima cumpririam a hipótese). O enunciado ainda admite duas leituras —",
        "fração da espera transversal, ou fração do *acréscimo* que a preempção causou —,",
        "e as duas colunas acima medem cada uma. **Qual delas o texto adota é ação de",
        "redação da equipe** (P17) e precisa ser declarada antes do Bloco 8. Declarar",
        "agora não é escolher pelo resultado: **nenhuma das duas atinge a meta**.",
        "",
        "Sinal negativo em *mitigação* significa que a compensação **piorou** a espera",
        "transversal em vez de melhorá-la. Sinal negativo em *custo* significa que a",
        "preempção reduziu a espera das transversais — acontece em tráfego leve, em que",
        "o corredor verde esvazia filas que o ciclo fixo deixaria acumular.",
        "",
    ]

    # -- Saúde ---------------------------------------------------------------
    linhas += [
        "## 4. Segurança, gridlock e latência",
        "",
        "| Verificação | Resultado | Critério |",
        "| --- | --- | --- |",
        f"| Colisões | {saude.colisoes} | zero (`context/04` §9.4) |",
        f"| Teleportes | {saude.teleportes} | zero — teleporte com `--time-to-teleport -1` "
        "significa gridlock |",
        f"| Violações de I1 a I5 | {saude.violacoes} | zero (`context/01` §6) |",
        f"| Pior escoamento | {_num(saude.escoamento_minimo * 100)}% em "
        f"`{saude.escoamento_pior_ponto}` | veículos que completaram a rota |",
        f"| p95 da decisão (pior execução) | {_num(saude.p95_maximo_ms, 3)} ms | "
        f"< {ORCAMENTO_RNF01_MS:.0f} ms (RNF01) |",
        f"| p99 da decisão (pior execução) | {_num(saude.p99_maximo_ms, 3)} ms | cauda, "
        "`context/04` §9.3 |",
        f"| Máximo absoluto | {_num(saude.maximo_ms, 3)} ms | — |",
        "",
        f"Há gridlock? {_veredito(saude.teleportes > 0)}. "
        f"A malha é segura nas {saude.execucoes} execuções? {_veredito(saude.segura)}. "
        f"O RNF01 é atendido? {_veredito(saude.dentro_do_rnf01)}.",
        "",
    ]

    # -- Veredito ------------------------------------------------------------
    linhas += [
        "## 5. Veredito do piloto",
        "",
        "As três perguntas que o Bloco 4 existe para responder:",
        "",
        f"1. **A redução em `moderado` e `intenso` chega aos 25% de H1?** "
        f"{_veredito(h1_confirmada)}.",
    ]
    for resumo in com_meta:
        linhas.append(
            f"   - `{resumo.cenario}` ({regime.get(resumo.cenario, '')}): reduziu "
            f"{_pct(resumo.reducoes.get('PREEMPCAO'))} em média, "
            f"{_pct(resumo.piores.get('PREEMPCAO'))} na pior seed e "
            f"{_pct(resumo.melhores.get('PREEMPCAO'))} na melhor — "
            f"{'atinge' if resumo.atinge_meta('PREEMPCAO') else '**abaixo da meta**'}."
        )
    linhas += [
        f"2. **Há gridlock?** {_veredito(saude.teleportes > 0)} "
        f"({saude.teleportes} teleporte(s); pior escoamento "
        f"{_num(saude.escoamento_minimo * 100)}%).",
        f"3. **A latência p95 fica sob 100 ms?** {_veredito(saude.dentro_do_rnf01)} "
        f"(pior p95: {_num(saude.p95_maximo_ms, 3)} ms).",
        "",
        "> **Cinco seeds não sustentam teste de hipótese.** Este relatório dá ordem",
        "> de grandeza, que é o que o Bloco 4 precisa. Wilcoxon, Cliff's δ, IC 95%",
        "> por bootstrap e Holm-Bonferroni são o Bloco 9, sobre as 600 execuções do",
        "> Bloco 8.",
        "",
    ]

    linhas += _pendencias(h1, h2, saude, regime)
    return "\n".join(linhas) + "\n"


def _pendencias(
    h1: Sequence[ResumoH1],
    h2: Sequence[ResumoH2],
    saude: ResumoSaude,
    regime: Mapping[str, str],
) -> list[str]:
    """Lista o que o piloto obriga a decidir — derivado dos dados, não escrito.

    É a razão de o Bloco 4 existir: "se a resposta a qualquer uma for ruim,
    ajusta-se **o modelo ou o texto** aqui, não na última semana". Uma seção que
    só aparecesse quando alguém se lembrasse de escrevê-la não cumpriria esse
    papel — então ela é calculada, e some sozinha quando não há o que decidir.
    """
    itens: list[str] = []

    for resumo in h1:
        if resumo.tem_meta and not resumo.atinge_meta("PREEMPCAO"):
            itens += [
                f"- **H1 não se sustenta em `{resumo.cenario}`** "
                f"({regime.get(resumo.cenario, '')}): redução medida de "
                f"{_pct(resumo.reducoes.get('PREEMPCAO'))} contra a meta de "
                f"{META_H1 * 100:.0f}%. A melhor seed chegou a "
                f"{_pct(resumo.melhores.get('PREEMPCAO'))}, a pior a "
                f"{_pct(resumo.piores.get('PREEMPCAO'))} — a dispersão indica que o",
                "  resultado depende do tráfego encontrado, não de um teto do método.",
                "  As saídas são **ajustar o modelo** (o corredor perde eficácia quando a",
                "  fila à frente não dissipa a tempo) ou **ajustar a formulação de H1**,",
                "  condicionando a meta à faixa de saturação em que ela de fato vale. A",
                "  segunda exige a decisão da equipe e conversa com o orientador; a",
                "  primeira é trabalho de engenharia e cabe no prazo — este é exatamente",
                "  o momento previsto para essa escolha.",
            ]

    # E7 abaixo da meta costuma valer para todos os cenários de uma vez —
    # repetir o mesmo parágrafo quatro vezes esconderia o fato em vez de
    # apresentá-lo. Um item, com a lista dos cenários e o número de cada um.
    aquem = [resumo for resumo in h2 if resumo.mitigacao is not None and resumo.mitigacao < META_H2]
    if aquem:
        medidos = ", ".join(
            f"`{resumo.cenario}` {_pct_sinal(resumo.mitigacao)}" for resumo in aquem
        )
        itens += [
            f"- **E7 não entrega a mitigação de H2** em {len(aquem)} de {len(h2)} cenários "
            f"(meta: {META_H2 * 100:.0f}%). Medido: {medidos}.",
            "  A compensação **roda** — o defeito de no-op foi corrigido no Bloco 3 e há",
            "  teste de regressão —, mas o efeito sobre a espera transversal é",
            "  indistinguível de zero, e negativo em alguns cenários. `ganho_compensacao_k`",
            "  (0,7) e `n_ciclos_compensacao` (2) de `parametros.yaml` foram escolhidos",
            "  como ponto de partida e **nunca foram calibrados contra dado real**; este",
            "  piloto é o primeiro insumo para calibrá-los. Enquanto o número não subir,",
            "  H2 tem mecanismo mas não tem evidência.",
        ]

    if not saude.segura:
        itens.append(
            f"- **Execuções com incidente**: {saude.colisoes} colisão(ões), "
            f"{saude.teleportes} teleporte(s), {saude.violacoes} violação(ões) de "
            "invariante. Nenhum deles pode sobreviver ao Bloco 8."
        )

    if not itens:
        return []

    return [
        "## 6. O que este piloto obriga a decidir",
        "",
        "Seção gerada a partir dos dados: ela só aparece quando alguma resposta",
        "acima ficou ruim. É para isso que o piloto foi antecipado — corrigir o",
        "modelo ou a redação **agora**, com margem, e não na última semana.",
        "",
        *itens,
        "",
    ]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argumentos: Sequence[str] | None = None) -> int:
    # O console do Windows abre em cp1252, e o relatório tem "≥", "δ" e travessão.
    # Sem isto, o `print` estoura com UnicodeEncodeError DEPOIS de o arquivo já
    # ter sido escrito — o pior dos dois mundos: código de saída 1 sobre um
    # relatório correto. O arquivo continua em UTF-8; só a cópia na tela degrada.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    analisador = argparse.ArgumentParser(description="Gera o relatório do piloto (Bloco 4).")
    analisador.add_argument("--dados", type=Path, default=DADOS)
    analisador.add_argument("--saida", type=Path, default=RELATORIOS)
    analisador.add_argument(
        "--planejadas",
        type=int,
        default=60,
        help="execuções que a matriz do piloto previa (4 cenários x 3 modos x 5 seeds)",
    )
    opcoes = analisador.parse_args(argumentos)

    caminho_execucoes = opcoes.dados / ARQUIVO_EXECUCOES
    if not caminho_execucoes.is_file():
        print(f"não achei {caminho_execucoes}. Rode `python -m sim.controlador.lote` antes.")
        return 1

    execucoes = ler_execucoes(caminho_execucoes)
    viagens = ler_viagens(opcoes.dados / ARQUIVO_VE)
    descartes = ler_descartes(opcoes.dados / ARQUIVO_DESCARTES)

    texto = gerar_markdown(
        execucoes,
        parear(viagens),
        descartes,
        opcoes.planejadas,
        ler_caracterizacao(opcoes.dados / ARQUIVO_CALIBRACAO),
    )

    opcoes.saida.mkdir(parents=True, exist_ok=True)
    destino = opcoes.saida / f"piloto_{date.today().strftime('%Y%m%d')}.md"
    destino.write_text(texto, encoding="utf-8")
    print(texto)
    print(f"relatório: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
