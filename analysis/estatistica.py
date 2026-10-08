"""Estatística do capítulo 5 — `context/07` §3.

Funções puras sobre vetores pareados por seed. Nenhuma lê arquivo nem conhece
cenário: quem monta os vetores é `analysis/carregar.py`, e quem decide o que é
comparado com o quê é `analysis/gerar_resultados_tcc.py`.

AS ESCOLHAS, DECLARADAS ANTES DE HAVER DADO

- **Unidade de análise: a execução** (`context/07` §3.1). Cada posição dos
  vetores é uma seed; base e alvo vêm da mesma seed, com o mesmo tráfego.
- **Teste principal: Wilcoxon signed-rank, bilateral**, sobre as diferenças
  `alvo - base`, com `zero_method="wilcox"` (diferença zero sai do posto). O
  **t pareado** vai ao lado, como secundário, e o Shapiro-Wilk das diferenças é
  reportado para o leitor julgar a normalidade — não para escolher o teste
  depois de ver o p (`context/07` §3.2). Bilateral mesmo nas hipóteses
  direcionais: é o mais conservador, e o sentido do efeito se lê no δ e no IC.
- **Tamanho de efeito: Cliff's δ** entre as duas amostras, com o sinal
  `δ = P(alvo > base) - P(alvo < base)`. δ negativo significa que o alvo é
  **menor** (no tempo do VE, que reduziu). Magnitude pelos cortes de Romano et
  al. (2006): |δ| < 0,147 desprezível, < 0,33 pequeno, < 0,474 médio, senão
  grande.
- **IC 95% por bootstrap percentil**, 10.000 reamostragens **das seeds** (o par
  inteiro sai junto, que é o que preserva o pareamento), com semente fixa. A
  semente do bootstrap é do método, não do experimento: ela só torna o IC
  reprodutível byte a byte.
- **Holm-Bonferroni** sobre a família inteira de p-valores do capítulo, com p
  bruto e ajustado lado a lado (`context/07` §3.4).
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy import stats

#: Reamostragens do bootstrap. Com 10.000 o erro de Monte Carlo dos limites de um
#: IC de 95% fica bem abaixo da casa decimal que o texto reporta.
REAMOSTRAGENS = 10_000

#: Semente do bootstrap. É do método, não do experimento (ver o docstring).
SEMENTE_BOOTSTRAP = 20261007

#: Nível de significância (`context/07` §3.3).
ALFA = 0.05

#: Cortes de magnitude do Cliff's δ (Romano et al., 2006).
CORTES_CLIFF = ((0.147, "desprezível"), (0.33, "pequeno"), (0.474, "médio"))

Vetor = NDArray[np.float64]


def _vetor(valores: Sequence[float] | Vetor) -> Vetor:
    return np.asarray(valores, dtype=np.float64)


# ---------------------------------------------------------------------------
# Descritiva
# ---------------------------------------------------------------------------


def mediana_iqr(valores: Sequence[float] | Vetor) -> tuple[float, float]:
    """Mediana e amplitude interquartil (Q3 - Q1), com interpolação linear.

    Returns:
        `(mediana, iqr)`; `(nan, nan)` se não houver valor.
    """
    x = _vetor(valores)
    if x.size == 0:
        return math.nan, math.nan
    q1, mediana, q3 = np.percentile(x, [25, 50, 75])
    return float(mediana), float(q3 - q1)


# ---------------------------------------------------------------------------
# Tamanho de efeito
# ---------------------------------------------------------------------------


def cliff_delta(alvo: Sequence[float] | Vetor, base: Sequence[float] | Vetor) -> float:
    """Cliff's δ = P(alvo > base) - P(alvo < base), entre todos os pares.

    Args:
        alvo: Amostra do braço tratado.
        base: Amostra do braço de controle.

    Returns:
        δ em [-1, 1]; `nan` se alguma amostra for vazia.
    """
    x, y = _vetor(alvo), _vetor(base)
    if x.size == 0 or y.size == 0:
        return math.nan
    sinais = np.sign(x[:, None] - y[None, :])
    return float(sinais.mean())


def magnitude_cliff(delta: float) -> str:
    """Rótulo da magnitude de δ pelos cortes de Romano et al. (2006)."""
    if math.isnan(delta):
        return "—"
    for corte, rotulo in CORTES_CLIFF:
        if abs(delta) < corte:
            return rotulo
    return "grande"


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def ic_bootstrap(
    n: int,
    estatistica: Callable[[NDArray[np.intp]], float],
    *,
    reamostragens: int = REAMOSTRAGENS,
    semente: int = SEMENTE_BOOTSTRAP,
    nivel: float = 0.95,
) -> tuple[float, float]:
    """IC por bootstrap percentil, reamostrando **índices de seed**.

    A estatística recebe os índices sorteados e calcula o valor sobre eles. É o
    que permite reamostrar juntos vetores que pertencem à mesma seed — os três
    braços de H2, por exemplo —, sem quebrar o pareamento.

    Args:
        n: Quantas seeds há.
        estatistica: Função dos índices sorteados para o valor da estatística.
        reamostragens: Quantas reamostras.
        semente: Semente do gerador.
        nivel: Nível de confiança.

    Returns:
        `(inferior, superior)`; `(nan, nan)` com menos de duas seeds ou se a
        estatística não for finita em nenhuma reamostra.
    """
    if n < 2:
        return math.nan, math.nan
    gerador = np.random.default_rng(semente)
    sorteios = gerador.integers(0, n, size=(reamostragens, n))
    valores = np.array([estatistica(indices) for indices in sorteios], dtype=np.float64)
    valores = valores[np.isfinite(valores)]
    if valores.size == 0:
        return math.nan, math.nan
    cauda = (1.0 - nivel) / 2.0 * 100.0
    inferior, superior = np.percentile(valores, [cauda, 100.0 - cauda])
    return float(inferior), float(superior)


# ---------------------------------------------------------------------------
# Testes pareados
# ---------------------------------------------------------------------------


def wilcoxon_pareado(alvo: Vetor, base: Vetor) -> tuple[float, float]:
    """Wilcoxon signed-rank bilateral sobre `alvo - base`.

    Returns:
        `(estatística W, p)`. Se todas as diferenças forem zero, não há posto
        a ordenar: devolve `(0, 1)`, que é o que o dado diz — nenhuma diferença.
        Com menos de uma diferença não nula, idem.
    """
    diferencas = alvo - base
    if not np.any(diferencas != 0):
        return 0.0, 1.0
    with warnings.catch_warnings():
        # Com empates e n pequeno o scipy troca o exato pela aproximação normal
        # e avisa. É o comportamento documentado, e o aviso não muda o número.
        warnings.simplefilter("ignore", category=UserWarning)
        resultado = stats.wilcoxon(diferencas, zero_method="wilcox", alternative="two-sided")
    return float(resultado.statistic), float(resultado.pvalue)


def t_pareado(alvo: Vetor, base: Vetor) -> tuple[float, float]:
    """Teste t de Student pareado, bilateral.

    Returns:
        `(t, p)`. Sem diferença nenhuma, `(0, 1)`; com todas as diferenças
        iguais e não nulas, `(±inf, 0)`.
    """
    diferencas = alvo - base
    if diferencas.size < 2 or np.allclose(diferencas, 0.0):
        return 0.0, 1.0
    if np.allclose(diferencas, diferencas[0]):
        # Desvio-padrão zero com média não nula: t infinito, p zero. O scipy
        # devolveria nan com aviso de divisão por zero.
        return math.copysign(math.inf, float(diferencas[0])), 0.0
    resultado = stats.ttest_rel(alvo, base)
    return float(resultado.statistic), float(resultado.pvalue)


def shapiro_diferencas(alvo: Vetor, base: Vetor) -> float | None:
    """Valor p do Shapiro-Wilk sobre as diferenças, ou `None` se não for calculável.

    O teste exige pelo menos três valores e alguma variação.
    """
    diferencas = alvo - base
    if diferencas.size < 3 or np.allclose(diferencas, diferencas[0]):
        return None
    return float(stats.shapiro(diferencas).pvalue)


@dataclass(frozen=True)
class ComparacaoPareada:
    """Os quatro itens de `context/07` §3.3 para uma comparação alvo x base.

    Attributes:
        n: Seeds pareadas.
        mediana_base: Mediana do braço de controle.
        iqr_base: IQR do braço de controle.
        mediana_alvo: Mediana do braço tratado.
        iqr_alvo: IQR do braço tratado.
        mediana_diferenca: Mediana de `alvo - base`, por seed.
        ic_mediana_diferenca: IC 95% da mediana das diferenças (bootstrap).
        w: Estatística de Wilcoxon.
        p_wilcoxon: p bilateral de Wilcoxon — o teste principal.
        t: Estatística t pareada.
        p_t: p bilateral do t pareado — o secundário.
        p_shapiro: p do Shapiro-Wilk sobre as diferenças, ou `None`.
        delta: Cliff's δ(alvo, base).
    """

    n: int
    mediana_base: float
    iqr_base: float
    mediana_alvo: float
    iqr_alvo: float
    mediana_diferenca: float
    ic_mediana_diferenca: tuple[float, float]
    w: float
    p_wilcoxon: float
    t: float
    p_t: float
    p_shapiro: float | None
    delta: float

    @property
    def magnitude(self) -> str:
        """Magnitude do δ."""
        return magnitude_cliff(self.delta)


def comparar_pareado(
    alvo: Sequence[float] | Vetor,
    base: Sequence[float] | Vetor,
    *,
    reamostragens: int = REAMOSTRAGENS,
    semente: int = SEMENTE_BOOTSTRAP,
) -> ComparacaoPareada:
    """Compara dois braços pareados por seed.

    Args:
        alvo: Valor do braço tratado, uma posição por seed.
        base: Valor do braço de controle, na mesma ordem de seeds.
        reamostragens: Reamostras do bootstrap.
        semente: Semente do bootstrap.

    Raises:
        ValueError: se os vetores tiverem tamanhos diferentes ou estiverem vazios.
    """
    x, y = _vetor(alvo), _vetor(base)
    if x.shape != y.shape:
        raise ValueError(f"vetores pareados de tamanhos diferentes: {x.size} e {y.size}")
    if x.size == 0:
        raise ValueError("comparação sem nenhuma seed pareada")

    diferencas = x - y
    mediana_base, iqr_base = mediana_iqr(y)
    mediana_alvo, iqr_alvo = mediana_iqr(x)
    w, p_w = wilcoxon_pareado(x, y)
    t, p_t = t_pareado(x, y)
    return ComparacaoPareada(
        n=int(x.size),
        mediana_base=mediana_base,
        iqr_base=iqr_base,
        mediana_alvo=mediana_alvo,
        iqr_alvo=iqr_alvo,
        mediana_diferenca=float(np.median(diferencas)),
        ic_mediana_diferenca=ic_bootstrap(
            x.size,
            lambda indices: float(np.median(diferencas[indices])),
            reamostragens=reamostragens,
            semente=semente,
        ),
        w=w,
        p_wilcoxon=p_w,
        t=t,
        p_t=p_t,
        p_shapiro=shapiro_diferencas(x, y),
        delta=cliff_delta(x, y),
    )


# ---------------------------------------------------------------------------
# Múltiplas comparações
# ---------------------------------------------------------------------------


def holm(p_valores: Sequence[float]) -> list[float]:
    """Ajuste de Holm-Bonferroni, na ordem de entrada.

    O menor p é multiplicado por m, o segundo por m - 1, e assim por diante; o
    ajustado é forçado a não decrescer na ordem crescente dos brutos e limitado
    a 1. `nan` entra como está e não conta em m.

    Args:
        p_valores: p brutos da família.

    Returns:
        p ajustados, na mesma ordem.
    """
    validos = [(p, i) for i, p in enumerate(p_valores) if not math.isnan(p)]
    m = len(validos)
    ajustados = [math.nan] * len(p_valores)
    acumulado = 0.0
    for posto, (p, indice) in enumerate(sorted(validos)):
        acumulado = max(acumulado, min(1.0, (m - posto) * p))
        ajustados[indice] = acumulado
    return ajustados
