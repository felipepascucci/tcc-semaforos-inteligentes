"""Leitura, validação e pareamento dos CSV do lote — `context/07` §2.

Lê o que `sim/controlador/lote.py` consolida numa pasta (`context/04` §10) e
entrega os vetores **pareados por seed** que `analysis/estatistica.py` compara.
Nenhum número é calculado aqui além de médias por execução: o que sai daqui é
dado organizado, não resultado.

O PAREAMENTO DO VE É POR VEÍCULO, DENTRO DA SEED

O mesmo cuidado do relatório do piloto (`analysis/relatorio_piloto.py`): o
último VE parte perto do fim do horizonte e, no braço mais lento, pode não
chegar dentro dos 3.600 s. Comparar a média de cinco VEs com a de seis mediria
também a diferença entre os conjuntos. Por isso, em cada (cenário, seed), só
entram os VEs presentes em **todos** os braços do cenário, e o número que a
interseção descartou é devolvido para ser declarado.

O "VE MAIS PREJUDICADO" DE H4

H4 compara o tempo do VE mais prejudicado (`context/00` §5). No
`multiplas_emergencias` os VEs partem em pares — o do corredor e o da
transversal, com o mesmo índice no id (`VE_ROTA_VE_CORREDOR_03` e
`VE_ROTA_VE_TRANSVERSAL_03`). Para cada par, o mais prejudicado é o de maior
tempo, que é o `minimax` da rotulagem (`sim/controlador/rotulagem.py`). Por
execução, o valor é a **média dos minimax dos pares** completos nos dois braços
— a mesma unidade de análise de H1 (`context/07` §3.1), com a média sobre os
encontros no lugar da média sobre os VEs.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
DADOS_PADRAO = RAIZ / "analysis" / "data" / "bloco8"
CALIBRACAO_PADRAO = RAIZ / "analysis" / "data" / "calibracao_cenarios.csv"
BANCADA_PADRAO = RAIZ / "analysis" / "data" / "latencia_bancada.csv"

ARQUIVO_EXECUCOES = "execucoes.csv"
ARQUIVO_VE = "ve_por_execucao.csv"
ARQUIVO_TRANSVERSAL = "transversal_por_execucao.csv"
ARQUIVO_LATENCIAS = "latencias.csv"
ARQUIVO_CONFLITOS = "conflitos_por_execucao.csv"
ARQUIVO_DESCARTES = "descartes.csv"

BASELINE = "FIXO"
PREEMPCAO = "PREEMPCAO"
COMPENSADA = "PREEMPCAO_COMPENSADA"
ML = "PREEMPCAO_ML"
MODOS = (BASELINE, PREEMPCAO, COMPENSADA, ML)
CENARIOS = ("leve", "moderado", "intenso", "multiplas_emergencias")

#: Colunas sem as quais a análise não roda. As demais são opcionais: o piloto de
#: 2026-08-26 não tem as de conflito, e é lido assim mesmo.
COLUNAS_EXECUCOES = (
    "cenario",
    "modo",
    "seed",
    "versao_codigo",
    "duracao_s",
    "veiculos_completos",
    "tempo_espera_medio_transversal_s",
    "latencia_p95_ms",
    "latencia_p99_ms",
    "latencia_max_ms",
    "colisoes",
    "teleportes",
    "violacoes",
)
COLUNAS_VE = ("cenario", "modo", "seed", "id_veiculo", "tipo", "tempo_viagem_s", "paradas")

#: Os acessos transversais começam por `T` (`context/04` §3: `T{coluna}_{S|N}…`).
PREFIXO_ACESSO_TRANSVERSAL = "T"

#: O índice do par no id do VE, que casa o do corredor com o da transversal.
_INDICE_DO_PAR = re.compile(r"_(\d+)$")


class DadosInvalidosError(ValueError):
    """Os CSV não servem para a análise: falta coluna, há duplicata, etc."""


@dataclass(frozen=True)
class Dados:
    """O que o lote produziu numa pasta, já validado.

    Attributes:
        pasta: De onde os CSV foram lidos.
        execucoes: `execucoes.csv`.
        ves: `ve_por_execucao.csv`.
        transversal: `transversal_por_execucao.csv`, ou vazio.
        latencias: `latencias.csv` (só as execuções exemplares), ou vazio.
        conflitos: `conflitos_por_execucao.csv`, ou vazio.
        descartes: `descartes.csv`, ou vazio.
    """

    pasta: Path
    execucoes: pd.DataFrame
    ves: pd.DataFrame
    transversal: pd.DataFrame
    latencias: pd.DataFrame
    conflitos: pd.DataFrame
    descartes: pd.DataFrame

    @property
    def versoes(self) -> list[str]:
        """Versões de código que produziram as execuções."""
        return sorted(self.execucoes["versao_codigo"].astype(str).unique())

    def cenarios(self) -> list[str]:
        """Cenários presentes, na ordem de `CENARIOS` e depois os desconhecidos."""
        presentes = set(self.execucoes["cenario"])
        return [c for c in CENARIOS if c in presentes] + sorted(presentes - set(CENARIOS))

    def modos(self, cenario: str) -> list[str]:
        """Braços presentes no cenário, na ordem de `MODOS`."""
        presentes = set(self.execucoes.loc[self.execucoes["cenario"] == cenario, "modo"])
        return [m for m in MODOS if m in presentes] + sorted(presentes - set(MODOS))


def _ler(caminho: Path, obrigatorio: bool, colunas: Sequence[str] = ()) -> pd.DataFrame:
    if not caminho.is_file():
        if obrigatorio:
            raise DadosInvalidosError(f"não achei {caminho}")
        return pd.DataFrame()
    tabela = pd.read_csv(caminho, dtype={"versao_codigo": str})
    if faltam := [coluna for coluna in colunas if coluna not in tabela.columns]:
        raise DadosInvalidosError(f"{caminho.name}: faltam as colunas {faltam}")
    return tabela


def ler_pasta(pasta: Path) -> Dados:
    """Lê os CSV de uma pasta do lote e confere o que a análise exige.

    Raises:
        DadosInvalidosError: se faltar arquivo ou coluna obrigatória, ou se um
            ponto (cenário, modo, seed) aparecer duas vezes — uma linha duplicada
            entraria como uma seed com peso dobrado na média, sem erro visível
            (o mesmo risco que o lote guarda do lado da escrita).
    """
    execucoes = _ler(pasta / ARQUIVO_EXECUCOES, True, COLUNAS_EXECUCOES)
    ves = _ler(pasta / ARQUIVO_VE, True, COLUNAS_VE)

    duplicados = execucoes.duplicated(subset=["cenario", "modo", "seed"], keep=False)
    if duplicados.any():
        pontos = execucoes.loc[duplicados, ["cenario", "modo", "seed"]].drop_duplicates()
        raise DadosInvalidosError(
            f"{ARQUIVO_EXECUCOES}: pontos duplicados: {pontos.to_dict('records')}"
        )

    return Dados(
        pasta=pasta,
        execucoes=execucoes,
        ves=ves,
        transversal=_ler(pasta / ARQUIVO_TRANSVERSAL, False),
        latencias=_ler(pasta / ARQUIVO_LATENCIAS, False),
        conflitos=_ler(pasta / ARQUIVO_CONFLITOS, False),
        descartes=_ler(pasta / ARQUIVO_DESCARTES, False),
    )


# ---------------------------------------------------------------------------
# H1 — travessia do VE pareada por veículo
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TravessiaPareada:
    """Travessia média do VE por seed e braço, sobre os VEs comuns a todos.

    Attributes:
        cenario: Cenário.
        modos: Braços pareados.
        por_seed: Uma linha por seed, uma coluna por braço, em segundos.
        ves_comuns: VEs comparados, somados sobre as seeds.
        ves_descartados: VEs presentes em algum braço e não em todos.
        paradas_por_seed: Paradas médias por VE, mesma forma de `por_seed`.
    """

    cenario: str
    modos: tuple[str, ...]
    por_seed: pd.DataFrame
    ves_comuns: int
    ves_descartados: int
    paradas_por_seed: pd.DataFrame


def travessia_pareada(dados: Dados, cenario: str, modos: Sequence[str]) -> TravessiaPareada:
    """Pareia os VEs de um cenário entre os braços pedidos.

    Uma seed só entra se tiver os braços todos e pelo menos um VE em comum.
    """
    ves = dados.ves[(dados.ves["cenario"] == cenario) & dados.ves["modo"].isin(modos)]
    travessia: dict[int, dict[str, float]] = {}
    paradas: dict[int, dict[str, float]] = {}
    comuns_total = 0
    descartados_total = 0
    for seed, da_seed in ves.groupby("seed"):
        por_modo = {modo: grupo.set_index("id_veiculo") for modo, grupo in da_seed.groupby("modo")}
        if set(por_modo) != set(modos):
            continue
        conjuntos = [set(grupo.index) for grupo in por_modo.values()]
        comuns = sorted(set.intersection(*conjuntos))
        if not comuns:
            continue
        comuns_total += len(comuns)
        descartados_total += len(set.union(*conjuntos)) - len(comuns)
        travessia[int(seed)] = {
            modo: float(grupo.loc[comuns, "tempo_viagem_s"].mean())
            for modo, grupo in por_modo.items()
        }
        paradas[int(seed)] = {
            modo: float(grupo.loc[comuns, "paradas"].mean()) for modo, grupo in por_modo.items()
        }
    colunas = list(modos)
    return TravessiaPareada(
        cenario=cenario,
        modos=tuple(modos),
        por_seed=pd.DataFrame.from_dict(travessia, orient="index", columns=colunas).sort_index(),
        ves_comuns=comuns_total,
        ves_descartados=descartados_total,
        paradas_por_seed=pd.DataFrame.from_dict(
            paradas, orient="index", columns=colunas
        ).sort_index(),
    )


# ---------------------------------------------------------------------------
# H4 — o VE mais prejudicado de cada par
# ---------------------------------------------------------------------------


def indice_do_par(id_veiculo: str) -> str | None:
    """O índice do par no id do VE (`…_03` → `"03"`), ou `None` sem sufixo."""
    casamento = _INDICE_DO_PAR.search(id_veiculo)
    return casamento.group(1) if casamento else None


@dataclass(frozen=True)
class PiorVEPareado:
    """Média por seed do minimax de cada par de VEs, nos dois braços de H4.

    Attributes:
        por_seed: Uma linha por seed, uma coluna por braço, em segundos.
        pares_comuns: Pares completos nos dois braços, somados sobre as seeds.
        pares_descartados: Pares incompletos em algum braço (um VE não chegou).
    """

    por_seed: pd.DataFrame
    pares_comuns: int
    pares_descartados: int


def pior_ve_pareado(dados: Dados, cenario: str, modos: Sequence[str]) -> PiorVEPareado:
    """O "VE mais prejudicado" de H4, pareado por seed e por par de VEs.

    Um par só entra se os seus VEs (os de mesmo índice) chegaram nos dois
    braços **e** em número igual: o minimax de um par sem um dos VEs não diz
    quanto o mais prejudicado esperou.
    """
    ves = dados.ves[(dados.ves["cenario"] == cenario) & dados.ves["modo"].isin(modos)].copy()
    ves["par"] = ves["id_veiculo"].map(indice_do_par)
    ves = ves.dropna(subset=["par"])
    valores: dict[int, dict[str, float]] = {}
    comuns_total = 0
    descartados_total = 0
    for seed, da_seed in ves.groupby("seed"):
        por_modo = {modo: grupo for modo, grupo in da_seed.groupby("modo")}
        if set(por_modo) != set(modos):
            continue
        membros = {
            modo: grupo.groupby("par")["id_veiculo"].apply(frozenset).to_dict()
            for modo, grupo in por_modo.items()
        }
        todos_pares = set.union(*(set(m) for m in membros.values()))
        completos = sorted(
            par
            for par in todos_pares
            if all(par in m for m in membros.values())
            and len({m[par] for m in membros.values()}) == 1
            and len(next(iter(membros.values()))[par]) >= 2
        )
        descartados_total += len(todos_pares) - len(completos)
        if not completos:
            continue
        comuns_total += len(completos)
        valores[int(seed)] = {
            modo: float(
                grupo[grupo["par"].isin(completos)].groupby("par")["tempo_viagem_s"].max().mean()
            )
            for modo, grupo in por_modo.items()
        }
    return PiorVEPareado(
        por_seed=pd.DataFrame.from_dict(valores, orient="index", columns=list(modos)).sort_index(),
        pares_comuns=comuns_total,
        pares_descartados=descartados_total,
    )


# ---------------------------------------------------------------------------
# H2 e T3 — por execução
# ---------------------------------------------------------------------------


def por_seed(dados: Dados, cenario: str, coluna: str, modos: Sequence[str]) -> pd.DataFrame:
    """Uma coluna de `execucoes.csv`, uma linha por seed e uma coluna por braço.

    Só as seeds com todos os braços pedidos — o pareamento de `context/04` §7.
    """
    tabela = dados.execucoes[
        (dados.execucoes["cenario"] == cenario) & dados.execucoes["modo"].isin(modos)
    ].pivot(index="seed", columns="modo", values=coluna)
    return tabela.reindex(columns=list(modos)).dropna().sort_index()


def fila_maxima_transversal(dados: Dados) -> pd.DataFrame:
    """Maior fila entre os acessos transversais, por execução.

    Returns:
        Colunas `cenario`, `modo`, `seed`, `fila_maxima`; vazio sem o CSV.
    """
    if dados.transversal.empty:
        return pd.DataFrame(columns=["cenario", "modo", "seed", "fila_maxima"])
    transversais = dados.transversal[
        dados.transversal["acesso"].astype(str).str.startswith(PREFIXO_ACESSO_TRANSVERSAL)
    ]
    return (
        transversais.groupby(["cenario", "modo", "seed"], as_index=False)["fila_maxima"]
        .max()
        .reset_index(drop=True)
    )


def ler_caracterizacao(caminho: Path) -> dict[str, float]:
    """v/c medido de cada cenário, de `calibracao_cenarios.csv` (Bloco 3).

    Lido, não escrito à mão: uma recalibração muda o número aqui sem ninguém
    precisar lembrar de atualizar o pipeline.
    """
    if not caminho.is_file():
        return {}
    tabela = pd.read_csv(caminho)
    return {
        str(c): float(v) for c, v in zip(tabela["cenario"], tabela["grau_saturacao"], strict=True)
    }
