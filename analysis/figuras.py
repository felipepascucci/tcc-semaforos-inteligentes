"""Figuras do capítulo 5 — `context/07` §5.

Padrão (`context/07` §5): PDF vetorial, fonte serifada, legível quando reduzida
à largura da página, **distinguível em escala de cinza** (o TCC pode ser
impresso em preto e branco) e eixos com unidade. Por isso nenhuma figura
depende só de cor: os braços se distinguem por tom de cinza **e** por hachura,
marcador ou tipo de linha.

Cada função recebe dado já organizado e um caminho, e não calcula estatística:
o que a figura mostra é o mesmo dado que as tabelas testam.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # sem janela: o pipeline roda em lote

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, MaxNLocator, ScalarFormatter

#: Largura útil da página A4 com as margens da ABNT (3 cm + 2 cm), em polegadas.
LARGURA_PAGINA_POL = 16.0 / 2.54

#: Aparência de cada braço: tom de cinza, hachura (caixas e barras), marcador e
#: tipo de linha. Os quatro recursos juntos é o que garante a leitura sem cor.
ESTILO_MODO: Mapping[str, Mapping[str, object]] = {
    "FIXO": {"cinza": "0.95", "hachura": "", "marcador": "o", "linha": "-", "rotulo": "Fixo"},
    "PREEMPCAO": {
        "cinza": "0.70",
        "hachura": "///",
        "marcador": "s",
        "linha": "--",
        "rotulo": "Preempção",
    },
    "PREEMPCAO_COMPENSADA": {
        "cinza": "0.45",
        "hachura": "...",
        "marcador": "^",
        "linha": "-.",
        "rotulo": "Preempção + compensação",
    },
    "PREEMPCAO_ML": {
        "cinza": "0.20",
        "hachura": "xx",
        "marcador": "D",
        "linha": ":",
        "rotulo": "Preempção + política aprendida",
    },
}

ROTULO_CENARIO = {
    "leve": "leve",
    "moderado": "moderado",
    "intenso": "intenso",
    "multiplas_emergencias": "múltiplas\nemergências",
}


def aplicar_estilo() -> None:
    """Fonte serifada, tamanhos legíveis a 16 cm e fonte embutida no PDF."""
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
            "font.size": 9,
            "axes.labelsize": 9,
            "axes.titlesize": 9,
            "legend.fontsize": 8,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "axes.grid": True,
            "grid.color": "0.85",
            "grid.linewidth": 0.5,
            "axes.axisbelow": True,
            "pdf.fonttype": 42,
            "savefig.bbox": "tight",
        }
    )


def _rotulo(modo: str) -> str:
    return str(ESTILO_MODO.get(modo, {}).get("rotulo", modo))


def _virgula_decimal(figura: plt.Figure) -> None:
    """Vírgula decimal nos eixos lineares, como no texto do TCC."""
    formatador = FuncFormatter(lambda valor, _: f"{valor:g}".replace(".", ","))
    for eixo in figura.axes:
        for direcao in (eixo.xaxis, eixo.yaxis):
            # Só o eixo numérico: rótulos postos à mão (as fases da F6) usam um
            # FixedFormatter, e trocá-lo os apagaria.
            if direcao.get_scale() == "linear" and isinstance(
                direcao.get_major_formatter(), ScalarFormatter
            ):
                direcao.set_major_formatter(formatador)


def _salvar(figura: plt.Figure, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    _virgula_decimal(figura)
    # Metadado fixo: sem ele o PDF carrega a data de criação, e duas gerações
    # do mesmo dado dariam arquivos diferentes.
    figura.savefig(destino, format="pdf", metadata={"CreationDate": None})
    plt.close(figura)
    return destino


# ---------------------------------------------------------------------------
# F1 — boxplot da travessia do VE
# ---------------------------------------------------------------------------


def f1_travessia(por_cenario: Mapping[str, pd.DataFrame], destino: Path) -> Path:
    """Tempo de travessia do VE por braço, agrupado por cenário.

    Args:
        por_cenario: Para cada cenário, uma linha por seed e uma coluna por
            braço, com a travessia média sobre os VEs pareados, em segundos.
        destino: Arquivo PDF.
    """
    aplicar_estilo()
    figura, eixo = plt.subplots(figsize=(LARGURA_PAGINA_POL, 3.0))
    modos = [m for m in ESTILO_MODO if any(m in t.columns for t in por_cenario.values())]
    largura = 0.8 / max(len(modos), 1)
    for i, tabela in enumerate(por_cenario.values()):
        for j, modo in enumerate(modos):
            if modo not in tabela.columns:
                continue
            estilo = ESTILO_MODO[modo]
            posicao = i + (j - (len(modos) - 1) / 2) * largura
            caixa = eixo.boxplot(
                tabela[modo].dropna().to_numpy(),
                positions=[posicao],
                widths=largura * 0.85,
                patch_artist=True,
                showfliers=True,
                flierprops={"marker": ".", "markersize": 3, "markerfacecolor": "0.3"},
                medianprops={"color": "black", "linewidth": 1.0},
            )
            for corpo in caixa["boxes"]:
                corpo.set_facecolor(str(estilo["cinza"]))
                corpo.set_hatch(str(estilo["hachura"]))
                corpo.set_edgecolor("black")
                corpo.set_linewidth(0.6)
    eixo.set_xticks(range(len(por_cenario)))
    eixo.set_xticklabels([ROTULO_CENARIO.get(c, c) for c in por_cenario])
    eixo.set_ylabel("Tempo de travessia do VE (s)")
    eixo.legend(
        handles=[
            Patch(
                facecolor=str(ESTILO_MODO[m]["cinza"]),
                hatch=str(ESTILO_MODO[m]["hachura"]),
                edgecolor="black",
                label=_rotulo(m),
            )
            for m in modos
        ],
        # Fora do eixo, acima: dentro dele a legenda cobria o bigode do FIXO
        # no `intenso`, o ponto mais alto do gráfico.
        loc="lower center",
        bbox_to_anchor=(0.5, 1.0),
        ncols=2,
        frameon=False,
    )
    figura.tight_layout()
    return _salvar(figura, destino)


# ---------------------------------------------------------------------------
# F2 — latência de decisão
# ---------------------------------------------------------------------------


def f2_latencia(latencias: pd.DataFrame, destino: Path) -> Path:
    """Histograma e CDF da latência de decisão, com os orçamentos de 100 e 200 ms.

    A latência medida fica três ordens de grandeza abaixo dos orçamentos; o eixo
    é logarítmico para que as duas coisas caibam na mesma figura sem esconder
    nenhuma.

    Args:
        latencias: Colunas `modo` e `latencia_ms` (as execuções exemplares).
        destino: Arquivo PDF.
    """
    aplicar_estilo()
    figura, (eixo_h, eixo_c) = plt.subplots(1, 2, figsize=(LARGURA_PAGINA_POL, 2.8))
    valores = latencias["latencia_ms"].to_numpy(dtype=float)
    valores = valores[valores > 0]
    minimo = 10 ** np.floor(np.log10(valores.min())) if valores.size else 1e-3
    limites = (minimo, 400.0)
    bins = np.logspace(np.log10(limites[0]), np.log10(limites[1]), 80)

    eixo_h.hist(valores, bins=bins, color="0.6", edgecolor="0.3", linewidth=0.3)
    eixo_h.set_xscale("log")
    eixo_h.set_yscale("log")
    eixo_h.set_xlabel("Latência de decisão (ms)")
    eixo_h.set_ylabel("Decisões")
    eixo_h.set_title("(a) Histograma")

    for modo, grupo in latencias.groupby("modo"):
        ordenados = np.sort(grupo["latencia_ms"].to_numpy(dtype=float))
        if ordenados.size == 0:
            continue
        estilo = ESTILO_MODO.get(str(modo), {"linha": "-"})
        eixo_c.plot(
            ordenados,
            np.arange(1, ordenados.size + 1) / ordenados.size,
            linestyle=str(estilo["linha"]),
            color="black",
            linewidth=1.0,
            label=_rotulo(str(modo)),
        )
    eixo_c.set_xscale("log")
    eixo_c.set_xlabel("Latência de decisão (ms)")
    eixo_c.set_ylabel("Fração acumulada")
    eixo_c.set_title("(b) CDF")

    for eixo in (eixo_h, eixo_c):
        eixo.set_xlim(*limites)
        eixo.axvline(100, color="black", linestyle="--", linewidth=0.8)
        eixo.axvline(200, color="black", linestyle=":", linewidth=0.8)
    eixo_c.text(100, 0.05, " 100 ms (RNF01)", rotation=90, va="bottom", ha="right", fontsize=7)
    eixo_c.text(200, 0.05, " 200 ms (H3)", rotation=90, va="bottom", ha="left", fontsize=7)
    # Abaixo dos dois painéis: dentro da CDF a legenda cobria as curvas.
    figura.legend(*eixo_c.get_legend_handles_labels(), loc="lower center", ncols=3, frameon=False)
    figura.tight_layout(rect=(0, 0.1, 1, 1))
    return _salvar(figura, destino)


# ---------------------------------------------------------------------------
# F3 — perfil espaço-temporal do VE
# ---------------------------------------------------------------------------


def posicoes_dos_cruzamentos(traco_ve: pd.DataFrame) -> list[float]:
    """Distâncias ao longo da rota em que o VE entra num cruzamento.

    O SUMO dá às faixas internas de um cruzamento ids que começam por `:`; o
    primeiro ponto do traço em cada uma delas marca o cruzamento. Sai do dado,
    e não de uma lista escrita à mão, para valer para qualquer rota.
    """
    internas = traco_ve[traco_ve["via"].astype(str).str.startswith(":")]
    if internas.empty:
        return []
    juncao = internas["via"].astype(str).str.extract(r"^:(.+)_\d+$")[0]
    primeiros = internas.assign(juncao=juncao).groupby("juncao")["distancia_m"].min()
    return sorted(float(d) for d in primeiros)


def f3_espaco_tempo(traco_ve: pd.DataFrame, id_veiculo: str, destino: Path) -> Path:
    """Posição x tempo de um VE em cada braço, com os cruzamentos marcados.

    O tempo é contado da partida do VE em cada braço, para as curvas começarem
    juntas: o VE parte no mesmo instante em toda seed e braço (`context/04` §7).

    Args:
        traco_ve: `traco_ve.csv`.
        id_veiculo: O VE a desenhar.
        destino: Arquivo PDF.
    """
    aplicar_estilo()
    figura, eixo = plt.subplots(figsize=(LARGURA_PAGINA_POL, 3.4))
    do_ve = traco_ve[traco_ve["id_veiculo"] == id_veiculo]
    for modo in ESTILO_MODO:
        serie = do_ve[do_ve["modo"] == modo].sort_values("t_s")
        if serie.empty:
            continue
        estilo = ESTILO_MODO[modo]
        eixo.plot(
            serie["t_s"] - serie["t_s"].iloc[0],
            serie["distancia_m"],
            linestyle=str(estilo["linha"]),
            color="black" if modo == "FIXO" else str(estilo["cinza"]),
            linewidth=1.2,
            label=_rotulo(modo),
        )
    referencia = do_ve[do_ve["modo"] == "FIXO"]
    for distancia in posicoes_dos_cruzamentos(referencia if not referencia.empty else do_ve):
        eixo.axhline(distancia, color="0.75", linewidth=0.5, zorder=0)
    eixo.set_xlabel("Tempo desde a partida do VE (s)")
    eixo.set_ylabel("Distância percorrida na rota (m)")
    eixo.legend(loc="lower right", frameon=False)
    return _salvar(figura, destino)


# ---------------------------------------------------------------------------
# F4 e F6 — fila na transversal e fases de um cruzamento
# ---------------------------------------------------------------------------


def intervalos_de_preempcao(
    traco_sinal: pd.DataFrame, modo: str, id_semaforo: str
) -> list[tuple[float, float]]:
    """Trechos em que o cruzamento esteve sob preempção, num braço.

    Cada transição carrega `em_preempcao`; um trecho começa na primeira
    transição sob preempção e termina na primeira seguinte que não está.
    """
    linhas = traco_sinal[
        (traco_sinal["modo"] == modo) & (traco_sinal["id_semaforo"] == id_semaforo)
    ].sort_values("t_s")
    trechos: list[tuple[float, float]] = []
    inicio: float | None = None
    for t, preempcao in zip(linhas["t_s"], linhas["em_preempcao"], strict=True):
        if preempcao and inicio is None:
            inicio = float(t)
        elif not preempcao and inicio is not None:
            trechos.append((inicio, float(t)))
            inicio = None
    if inicio is not None:
        trechos.append((inicio, float(linhas["t_s"].max())))
    return trechos


def f4_fila_transversal(
    traco_fila: pd.DataFrame,
    traco_sinal: pd.DataFrame,
    id_semaforo: str,
    janela: tuple[float, float],
    destino: Path,
) -> Path:
    """Fila total nas aproximações transversais de um cruzamento, nos três braços.

    Args:
        traco_fila: `traco_fila.csv.gz`.
        traco_sinal: `traco_sinal.csv`, para marcar a preempção.
        id_semaforo: Cruzamento.
        janela: Intervalo de tempo de simulação mostrado, em segundos.
        destino: Arquivo PDF.
    """
    aplicar_estilo()
    figura, eixo = plt.subplots(figsize=(LARGURA_PAGINA_POL, 2.8))
    do_cruzamento = traco_fila[
        (traco_fila["id_semaforo"] == id_semaforo) & traco_fila["t_s"].between(janela[0], janela[1])
    ]
    for modo in ESTILO_MODO:
        serie = (
            do_cruzamento[do_cruzamento["modo"] == modo].groupby("t_s")["fila"].sum().sort_index()
        )
        if serie.empty:
            continue
        estilo = ESTILO_MODO[modo]
        eixo.step(
            serie.index,
            serie.to_numpy(),
            where="post",
            linestyle=str(estilo["linha"]),
            color="black" if modo == "FIXO" else str(estilo["cinza"]),
            linewidth=1.0,
            label=_rotulo(modo),
        )
    for inicio, fim in intervalos_de_preempcao(traco_sinal, "PREEMPCAO", id_semaforo):
        if fim >= janela[0] and inicio <= janela[1]:
            eixo.axvspan(inicio, fim, color="0.88", zorder=0, linewidth=0)
    eixo.set_xlim(*janela)
    eixo.set_xlabel("Tempo de simulação (s)")
    eixo.set_ylabel(f"Veículos parados nas transversais de {id_semaforo}")
    eixo.yaxis.set_major_locator(MaxNLocator(integer=True))
    eixo.legend(
        handles=[
            *eixo.get_legend_handles_labels()[0],
            Patch(color="0.88", label="Sob preempção (braço Preempção)"),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.2),
        ncols=2,
        frameon=False,
    )
    return _salvar(figura, destino)


#: Tons do Gantt: verde escuro, amarelo claro com hachura. Vermelho é fundo.
_GANTT = {"VERDE": ("0.25", ""), "AMARELO": ("0.80", "////")}


def f6_fases(
    traco_sinal: pd.DataFrame,
    modo: str,
    id_semaforo: str,
    janela: tuple[float, float],
    destino: Path,
) -> Path:
    """Diagrama de Gantt das fases de um cruzamento durante uma preempção.

    Uma faixa por fase e uma para o all-red. Verde e amarelo aparecem na faixa
    da fase corrente; `VERMELHO` na fase corrente é o all-red (`core/priorizacao/
    fases.py`) e vai para a faixa própria. Em toda troca de fase, amarelo e
    all-red precisam aparecer — é a prova visual de I2 e I3.

    Args:
        traco_sinal: `traco_sinal.csv`.
        modo: Braço.
        id_semaforo: Cruzamento.
        janela: Intervalo mostrado, em segundos.
        destino: Arquivo PDF.
    """
    aplicar_estilo()
    linhas = traco_sinal[
        (traco_sinal["modo"] == modo) & (traco_sinal["id_semaforo"] == id_semaforo)
    ].sort_values("t_s")
    fases = sorted(int(f) for f in linhas["fase"].unique())
    faixas = {fase: i for i, fase in enumerate(fases)}
    faixa_all_red = len(fases)
    figura, eixo = plt.subplots(figsize=(LARGURA_PAGINA_POL, 0.6 + 0.45 * (len(fases) + 1)))

    instantes = linhas["t_s"].to_numpy(dtype=float)
    fins = np.append(instantes[1:], janela[1])
    for (_, linha), fim in zip(linhas.iterrows(), fins, strict=True):
        inicio = float(linha["t_s"])
        if fim < janela[0] or inicio > janela[1]:
            continue
        inicio, fim = max(inicio, janela[0]), min(fim, janela[1])
        if linha["sinal"] == "VERMELHO":
            eixo.broken_barh([(inicio, fim - inicio)], (faixa_all_red - 0.35, 0.7), color="black")
            continue
        cinza, hachura = _GANTT[str(linha["sinal"])]
        eixo.broken_barh(
            [(inicio, fim - inicio)],
            (faixas[int(linha["fase"])] - 0.35, 0.7),
            facecolors=cinza,
            hatch=hachura,
            edgecolor="black",
            linewidth=0.4,
        )
    for inicio, fim in intervalos_de_preempcao(traco_sinal, modo, id_semaforo):
        if fim >= janela[0] and inicio <= janela[1]:
            eixo.axvspan(inicio, fim, color="0.92", zorder=0, linewidth=0)
    eixo.set_yticks([*faixas.values(), faixa_all_red])
    eixo.set_yticklabels([*(f"Fase {f}" for f in fases), "All-red"])
    eixo.set_ylim(-0.6, faixa_all_red + 0.6)
    eixo.invert_yaxis()
    eixo.set_xlim(*janela)
    eixo.set_xlabel("Tempo de simulação (s)")
    eixo.grid(axis="y", visible=False)
    eixo.legend(
        handles=[
            Patch(facecolor="0.25", edgecolor="black", label="Verde"),
            Patch(facecolor="0.80", hatch="////", edgecolor="black", label="Amarelo"),
            Patch(facecolor="black", label="All-red"),
            Patch(facecolor="0.92", label="Sob preempção"),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.35),
        ncols=4,
        frameon=False,
    )
    return _salvar(figura, destino)


# ---------------------------------------------------------------------------
# F5 — redução x saturação
# ---------------------------------------------------------------------------


def f5_reducao_saturacao(
    reducoes: Mapping[str, Sequence[float]],
    vc: Mapping[str, float],
    meta: float,
    destino: Path,
    *,
    cenarios_da_tendencia: Sequence[str] = ("leve", "moderado", "intenso"),
) -> Path:
    """Redução da travessia por seed contra o v/c medido do cenário.

    A tendência é uma reta de mínimos quadrados sobre os pontos dos cenários de
    um VE só; o `multiplas_emergencias` aparece com marcador próprio e fica fora
    da reta, porque o que o distingue é a segunda emergência, não a saturação.

    Args:
        reducoes: Para cada cenário, a redução de cada seed (fração).
        vc: v/c medido de cada cenário (`calibracao_cenarios.csv`).
        meta: Meta de H1, desenhada como referência.
        destino: Arquivo PDF.
        cenarios_da_tendencia: Os que entram na reta.
    """
    aplicar_estilo()
    figura, eixo = plt.subplots(figsize=(LARGURA_PAGINA_POL * 0.7, 3.0))
    gerador = np.random.default_rng(0)  # só o espalhamento horizontal dos pontos
    xs: list[float] = []
    ys: list[float] = []
    for cenario, valores in reducoes.items():
        if cenario not in vc:
            continue
        y = np.asarray(valores, dtype=float) * 100
        x = np.full(y.size, vc[cenario]) + gerador.uniform(-0.008, 0.008, y.size)
        unico = cenario in cenarios_da_tendencia
        eixo.scatter(
            x,
            y,
            s=10,
            marker="o" if unico else "^",
            facecolors="0.5" if unico else "none",
            edgecolors="black",
            linewidths=0.4,
            label=(
                # Os círculos também vão para a legenda, uma vez só.
                (None if xs else "um VE (" + ", ".join(cenarios_da_tendencia) + ")")
                if unico
                else ROTULO_CENARIO.get(cenario, cenario).replace("\n", " ")
            ),
        )
        if unico:
            xs.extend([vc[cenario]] * y.size)
            ys.extend(y)
    if len(set(xs)) >= 2:
        inclinacao, intercepto = np.polyfit(xs, ys, 1)
        grade = np.linspace(min(xs) - 0.03, max(xs) + 0.03, 10)
        eixo.plot(
            grade,
            inclinacao * grade + intercepto,
            color="black",
            linewidth=1.0,
            label="Tendência (MQO)",
        )
    eixo.axhline(
        meta * 100,
        color="black",
        linestyle="--",
        linewidth=0.8,
        label=f"Meta de H1 ({meta * 100:.0f}%)".replace(".", ","),
    )
    eixo.set_xlabel("Grau de saturação medido (v/c)")
    eixo.set_ylabel("Redução da travessia do VE (%)")
    # Abaixo do eixo: dentro dele, qualquer canto cobre pontos ou a linha da meta.
    eixo.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncols=2, frameon=False)
    figura.tight_layout()
    return _salvar(figura, destino)
