"""Figura 1 do Guia do Usuário v2.0: arquitetura nas cinco camadas.

    python docs/qualificacao/guia_usuario/figuras/arquitetura_camadas.py

Desenhada com matplotlib, e não com PlantUML, para controlar a posição de cada
caixa: as camadas são faixas horizontais na ordem pedida pelo orientador
(Borda embaixo, Interface com o Usuário em cima), e as setas seguem caminhos
que não se cruzam. Gera `arquitetura_camadas.png` (300 dpi) e `.pdf` nesta pasta.

Fontes dos rótulos: `context/01`, `context/02` §3, `context/05` §1, §2 e §6,
`docker-compose.yml`, `db/schema.sql` e `frontend/src/App.tsx`.
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

PASTA = Path(__file__).resolve().parent
NOME = "arquitetura_camadas"

# Unidades do desenho. X0 é onde começa o conteúdo, à direita da coluna de rótulos.
X0 = 2.9
X_FIM = X0 + 20.3
LARGURA_ROTULO = 2.7

# Faixas (y inferior, y superior), de baixo para cima.
FAIXAS = {
    1: (0.0, 2.2, "1\nBORDA"),
    2: (2.95, 3.95, "2\nCONECTIVIDADE"),
    3: (4.75, 6.55, "3\nPERSISTÊNCIA"),
    4: (7.5, 9.2, "4\nINTELIGÊNCIA"),
    5: (9.7, 10.75, "5\nINTERFACE COM\nO USUÁRIO"),
}

FONTE_TITULO = 7.6
FONTE_CORPO = 6.6
FONTE_SETA = 6.3

COR_FAIXA = "#eef1f4"
COR_ROTULO = "#2f3e4e"
COR_CAIXA = "white"
COR_ARMAZEM = "#fbf6e9"
COR_GRUPO = "#dfe5eb"


def _cy(faixa: int) -> float:
    baixo, alto, _ = FAIXAS[faixa]
    return (baixo + alto) / 2


class Caixa:
    """Uma caixa com título em negrito e corpo, e os pontos de ancoragem."""

    def __init__(self, cx: float, cy: float, w: float, h: float) -> None:
        """Centro (cx, cy), largura w e altura h, em unidades do desenho."""
        self.cx, self.cy, self.w, self.h = cx, cy, w, h

    @property
    def topo(self) -> float:
        """Y da borda superior."""
        return self.cy + self.h / 2

    @property
    def base(self) -> float:
        """Y da borda inferior."""
        return self.cy - self.h / 2

    @property
    def esq(self) -> float:
        """X da borda esquerda."""
        return self.cx - self.w / 2

    @property
    def dir(self) -> float:
        """X da borda direita."""
        return self.cx + self.w / 2


def caixa(
    ax: Axes,
    cx: float,
    cy: float,
    w: float,
    h: float,
    titulo: str,
    corpo: str = "",
    cor: str = COR_CAIXA,
) -> Caixa:
    """Desenha a caixa e devolve as ancoragens."""
    ax.add_patch(
        FancyBboxPatch(
            (cx - w / 2, cy - h / 2),
            w,
            h,
            boxstyle="round,pad=0,rounding_size=0.12",
            facecolor=cor,
            edgecolor="#333333",
            linewidth=0.9,
            zorder=3,
        )
    )
    linhas_corpo = corpo.count("\n") + 1 if corpo else 0
    # Altura de linha em unidades do desenho (fonte de ~7 pt com entrelinha 1,25).
    passo = 0.27
    altura_texto = passo * (titulo.count("\n") + 1 + linhas_corpo)
    topo_texto = cy + altura_texto / 2
    ax.text(
        cx,
        topo_texto,
        titulo,
        ha="center",
        va="top",
        fontsize=FONTE_TITULO,
        fontweight="bold",
        zorder=4,
        linespacing=1.15,
    )
    if corpo:
        ax.text(
            cx,
            topo_texto - passo * (titulo.count("\n") + 1),
            corpo,
            ha="center",
            va="top",
            fontsize=FONTE_CORPO,
            zorder=4,
            linespacing=1.25,
        )
    return Caixa(cx, cy, w, h)


def seta(
    ax: Axes,
    pontos: list[tuple[float, float]],
    dupla: bool = False,
    tracejada: bool = False,
) -> None:
    """Seta por uma sequência de pontos (segmentos retos); a ponta fica no último."""
    estilo = "-" if not tracejada else (0, (4, 2))
    for a, b in pairwise(pontos[:-1]):
        ax.plot([a[0], b[0]], [a[1], b[1]], color="#222222", lw=0.9, ls=estilo, zorder=2)
    if dupla and len(pontos) > 2:
        ax.add_patch(
            FancyArrowPatch(
                pontos[1],
                pontos[0],
                arrowstyle="-|>",
                mutation_scale=9,
                color="#222222",
                lw=0.9,
                zorder=2,
                shrinkA=0,
                shrinkB=0,
            )
        )
    ax.add_patch(
        FancyArrowPatch(
            pontos[-2],
            pontos[-1],
            arrowstyle="<|-|>" if dupla and len(pontos) == 2 else "-|>",
            mutation_scale=9,
            color="#222222",
            lw=0.9,
            ls=estilo,
            zorder=2,
            shrinkA=0,
            shrinkB=0,
        )
    )


def rotulo(ax: Axes, x: float, y: float, texto: str, ha: str = "center", **extra: object) -> None:
    """Rótulo de seta, com fundo para não ser cortado por linhas."""
    ax.text(
        x,
        y,
        texto,
        ha=ha,
        va="center",
        fontsize=FONTE_SETA,
        zorder=5,
        linespacing=1.15,
        bbox={"boxstyle": "round,pad=0.15", "facecolor": "white", "edgecolor": "none"},
        **extra,
    )


def desenhar() -> plt.Figure:
    """Monta a figura inteira."""
    fig, ax = plt.subplots(figsize=(10.0, 4.68))
    ax.set_xlim(0, X_FIM + 0.1)
    ax.set_ylim(-0.05, 10.8)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.subplots_adjust(left=0.005, right=0.995, top=0.995, bottom=0.005)

    # Faixas das camadas e a coluna de rótulos.
    for baixo, alto, nome in FAIXAS.values():
        ax.add_patch(
            Rectangle(
                (LARGURA_ROTULO + 0.1, baixo),
                X_FIM - LARGURA_ROTULO - 0.1,
                alto - baixo,
                facecolor=COR_FAIXA,
                edgecolor="none",
                zorder=0,
            )
        )
        ax.add_patch(
            Rectangle(
                (0, baixo),
                LARGURA_ROTULO,
                alto - baixo,
                facecolor=COR_ROTULO,
                edgecolor="none",
                zorder=1,
            )
        )
        ax.text(
            LARGURA_ROTULO / 2,
            (baixo + alto) / 2,
            nome,
            ha="center",
            va="center",
            color="white",
            fontsize=7.6,
            fontweight="bold",
            linespacing=1.2,
            zorder=2,
        )

    # 5 — Interface com o Usuário
    y5 = _cy(5)
    operador = caixa(ax, X0 + 8.0, y5, 2.3, 0.75, "Operador", "navegador web")
    dash = caixa(
        ax,
        X0 + 14.4,
        y5,
        5.9,
        0.9,
        "Dashboard React 18 (nginx 1.27)",
        "https://localhost:8443\nabas Ao vivo, Central, Logs, Métricas, Simulações",
    )

    # 4 — Inteligência
    y4 = _cy(4)
    motor = caixa(
        ax,
        X0 + 2.65,
        y4,
        4.3,
        1.4,
        "Motor de decisão (Python)",
        "core/priorizacao: ETA, preempção,\n"
        "compensação, invariantes I1 a I6\n"
        "(executor e atendente, no host)",
    )
    politica = caixa(
        ax,
        X0 + 8.6,
        y4,
        4.0,
        1.4,
        "Política aprendida",
        "regressão logística par a par\n4 pesos · modo PREEMPCAO_ML\npolitica_desempate.yaml",
    )
    caixa(
        ax,
        X0 + 18.15,
        y4,
        4.2,
        1.4,
        "Regra local da bancada",
        "firmware do Arduino UNO: Central,\n"
        "criticidade, fila de 1, transição\n"
        "segura (executa na Borda)",
    )

    # 3 — Persistência
    y3 = _cy(3)
    csv_sim = caixa(
        ax,
        X0 + 6.2,
        y3,
        2.9,
        1.15,
        "CSV da simulação",
        "analysis/data/\nsim/saida/",
        cor=COR_ARMAZEM,
    )
    db = caixa(
        ax,
        X0 + 10.05,
        y3,
        3.5,
        1.6,
        "PostgreSQL 16 (:5432)",
        "pedido_simulacao\nexecucao_simulacao\nocorrencia, log_prioridade\nmetrica_latencia",
        cor=COR_ARMAZEM,
    )
    backend = caixa(
        ax,
        X0 + 14.75,
        y3,
        3.8,
        1.4,
        "Back-end FastAPI (:8000)",
        "ingestão (ponte e simulação),\nAPI REST e WebSocket,\nCentral de ocorrências",
    )
    csv_banc = caixa(
        ax,
        X0 + 18.95,
        y3,
        2.5,
        1.15,
        "CSV da bancada",
        "analysis/data/\n*_bancada.csv",
        cor=COR_ARMAZEM,
    )

    # 2 — Conectividade
    y2 = _cy(2)
    traci = caixa(ax, X0 + 1.95, y2, 3.0, 0.75, "TraCI", "socket TCP local")
    ponte = caixa(
        ax, X0 + 16.4, y2, 4.6, 0.75, "Ponte serial (bridge/)", "HTTP 127.0.0.1:8001 · USB COM3"
    )

    # 1 — Borda: os dois grupos e as caixas.
    b1, a1, _ = FAIXAS[1]
    for x_esq, x_dir, titulo in (
        (X0 + 0.15, X0 + 3.75, "Borda simulada"),
        (X0 + 4.45, X0 + 20.2, "Borda física (bancada)"),
    ):
        ax.add_patch(
            FancyBboxPatch(
                (x_esq, b1 + 0.12),
                x_dir - x_esq,
                a1 - b1 - 0.24,
                boxstyle="round,pad=0,rounding_size=0.1",
                facecolor=COR_GRUPO,
                edgecolor="#555555",
                linewidth=0.7,
                linestyle=(0, (3, 2)),
                zorder=1,
            )
        )
        ax.text(
            x_esq + 0.15,
            b1 + 0.3,
            titulo,
            ha="left",
            va="center",
            fontsize=7.2,
            fontstyle="italic",
            zorder=2,
        )
    y1 = b1 + 1.12
    sumo = caixa(
        ax, X0 + 1.95, y1, 3.1, 1.1, "SUMO 1.27.1", "gêmeo digital da malha\nCRUZ_01 a CRUZ_08"
    )
    tags = caixa(ax, X0 + 5.75, y1, 1.9, 1.1, "4 tags RFID", "uma por rua")
    carros = caixa(ax, X0 + 9.55, y1, 2.75, 1.1, "3 carrinhos", "NodeMCU ESP8266\n+ leitor RC522")
    receptor = caixa(ax, X0 + 13.4, y1, 2.3, 1.1, "NodeMCU", "ESP8266\nreceptor")
    uno = caixa(
        ax, X0 + 17.95, y1, 4.1, 1.1, "Arduino UNO R3", "4 semáforos de LED\nLCD 16x2 I2C · decide"
    )

    # --- Setas -----------------------------------------------------------------
    # Interface
    seta(ax, [(operador.dir, y5), (dash.esq, y5)])
    rotulo(ax, (operador.dir + dash.esq) / 2, y5 + 0.2, "HTTPS")
    x_dash = X0 + 13.6
    seta(ax, [(x_dash, dash.base), (x_dash, backend.topo)], dupla=True)
    rotulo(ax, x_dash - 0.15, y4, "HTTPS e WSS\n(REST e WebSocket\npelo nginx)", ha="right")

    # Inteligência
    seta(ax, [(motor.dir, y4), (politica.esq, y4)])
    rotulo(ax, (motor.dir + politica.esq) / 2, y4 + 0.25, "desempate")

    # Barramento do motor para a persistência, abaixo da faixa 4.
    y_bus = FAIXAS[3][1] + 0.42
    x_saida = X0 + 3.4
    ax.plot([x_saida, x_saida], [motor.base, y_bus], color="#222222", lw=0.9, zorder=2)
    x_bk = X0 + 13.0
    ax.plot([x_saida, x_bk], [y_bus, y_bus], color="#222222", lw=0.9, zorder=2)
    seta(ax, [(csv_sim.cx, y_bus), (csv_sim.cx, csv_sim.topo)])
    seta(ax, [(db.cx - 0.6, y_bus), (db.cx - 0.6, db.topo)], dupla=True)
    seta(ax, [(x_bk, y_bus), (x_bk, backend.topo)])
    y_rot = y_bus + 0.22
    rotulo(ax, (x_saida + csv_sim.cx) / 2 + 0.15, y_rot, "CSV do lote")
    rotulo(ax, (csv_sim.cx + db.cx - 0.6) / 2, y_rot, "SQL: pedidos, execuções")
    rotulo(ax, (db.cx - 0.6 + x_bk) / 2, y_rot, "HTTP: estado ao vivo, 5 Hz")

    # Persistência
    seta(ax, [(backend.esq, y3), (db.dir, y3)])
    rotulo(ax, (backend.esq + db.dir) / 2, y3 + 0.25, "SQL")

    # Conectividade
    x_tr = traci.cx
    seta(ax, [(x_tr, traci.topo), (x_tr, motor.base)], dupla=True)
    rotulo(ax, x_tr + 0.2, y3, "estado dos VEs ↑\ncomandos de fase ↓", ha="left")
    seta(ax, [(x_tr, sumo.topo), (x_tr, traci.base)], dupla=True)

    x_pt = X0 + 15.5
    seta(ax, [(x_pt, backend.base), (x_pt, ponte.topo)], dupla=True)
    rotulo(
        ax,
        x_pt - 0.15,
        (backend.base + ponte.topo) / 2,
        "HTTP: GET /estado (5 Hz),\nPUT /autorizacoes",
        ha="right",
    )
    x_cb = X0 + 18.3
    seta(ax, [(x_cb, ponte.topo), (x_cb, csv_banc.base)])
    rotulo(
        ax,
        x_cb + 0.15,
        (ponte.topo + csv_banc.base) / 2,
        "latência,\ndetecções,\ntelemetria",
        ha="left",
    )

    # Borda física
    seta(ax, [(tags.dir, y1), (carros.esq, y1)])
    rotulo(ax, (tags.dir + carros.esq) / 2, y1 + 0.32, "RFID\n13,56 MHz")
    seta(ax, [(carros.dir, y1), (receptor.esq, y1)])
    rotulo(ax, (carros.dir + receptor.esq) / 2, y1 + 0.32, "ESP-NOW\n2,4 GHz")
    seta(ax, [(receptor.dir, y1), (uno.esq, y1)])
    rotulo(ax, (receptor.dir + uno.esq) / 2, y1 + 0.32, "UART 9600\nTX → A0")

    x_up, x_dn = X0 + 16.8, X0 + 17.9
    seta(ax, [(x_up, uno.topo), (x_up, ponte.base)])
    seta(ax, [(x_dn, ponte.base), (x_dn, uno.topo)])
    y_mid = (FAIXAS[1][1] + FAIXAS[2][0]) / 2
    rotulo(ax, x_up - 0.15, y_mid, "USB serial 9600:\nST, EV", ha="right")
    rotulo(ax, x_dn + 0.15, y_mid, "AUT (lista\nda Central)", ha="left")
    return fig


def main() -> int:
    """Gera PNG e PDF."""
    fig = desenhar()
    for formato in ("png", "pdf"):
        fig.savefig(PASTA / f"{NOME}.{formato}", dpi=300)
    plt.close(fig)
    print("gerados:", ", ".join(f"{NOME}.{f}" for f in ("png", "pdf")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
