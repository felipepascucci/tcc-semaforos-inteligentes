"""Esquemas complementares do Guia do Usuário v2.0 (Figuras 8 e 9, seções 2.2 e 2.3).

    python docs/qualificacao/guia_usuario/figuras/esquema_detalhe.py

Mesmo padrão visual da Figura 1 (`arquitetura_camadas.py`, de onde vêm as
caixas, os rótulos, as setas e as cores): faixas horizontais com o nome na
coluna escura à esquerda e módulos em molduras tracejadas. Os símbolos
elétricos (resistor, LED, capacitor, diodo, terra) são desenhados aqui.

Os esquemas de ligação pino a pino continuam sendo os de `docs/diagramas/`
(`esquema_eletrico.py`, conferidos contra o firmware por teste). Estes dois
mostram o que aqueles não mostram e o roteiro do orientador pede:

- `esquema_componentes_internos`: os resistores embutidos no módulo de
  semáforo, os pull-ups do adaptador I2C do LCD e os resistores de boot da
  NodeMCU ligados aos pinos do RC522;
- `esquema_alimentacao`: de onde sai e por onde passa a alimentação, com o
  regulador, os capacitores de desacoplamento e as correntes da Tabela 8.

Nenhum componente discreto foi acrescentado à montagem (resposta da equipe,
2026-11-05): tudo o que aparece aqui está dentro de um módulo ou de uma placa.

Fontes dos valores:
- resistores do módulo de semáforo (330, 220 e 470 Ω) e pull-ups de 4,7 kΩ do
  adaptador PCF8574T: equipe, 2026-11-05;
- NodeMCU: projeto de referência NodeMCU DevKit v1.0 (esquemático oficial,
  github.com/nodemcu/nodemcu-devkit-v1.0): resistores de 12 kΩ nos pinos de
  boot, regulador NCP1117 de 3,3 V, diodo 1N5819, capacitores de 10 µF,
  100 nF e 100 µF;
- correntes: ESP8266EX Datasheet v7.1, Tabela 5-3; NXP MFRC522 Rev. 3.9,
  Tabela 1; limite dos LEDs calculado na seção 2.3 do guia;
- pinagem: `context/05` §1 e `firmware/`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PASTA = Path(__file__).resolve().parent
sys.path.insert(0, str(PASTA))

import matplotlib.pyplot as plt  # noqa: E402
from arquitetura_camadas import (  # noqa: E402
    COR_ARMAZEM,
    COR_FAIXA,
    COR_GRUPO,
    COR_ROTULO,
    LARGURA_ROTULO,
    X0,
    X_FIM,
    caixa,
    rotulo,
    seta,
)
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle  # noqa: E402

COR_FIO = "#222222"
LW = 0.9
FONTE_VALOR = 6.6


# --- Moldura da figura -------------------------------------------------------


def _figura(altura: float, largura_pol: float = 10.0) -> tuple[plt.Figure, Axes]:
    fig, ax = plt.subplots(figsize=(largura_pol, largura_pol * (altura + 0.15) / (X_FIM + 0.1)))
    ax.set_xlim(0, X_FIM + 0.1)
    ax.set_ylim(-0.05, altura + 0.1)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.subplots_adjust(left=0.005, right=0.995, top=0.995, bottom=0.005)
    return fig, ax


def _faixa(ax: Axes, baixo: float, alto: float, nome: str) -> None:
    """Faixa da camada e rótulo na coluna escura, como na Figura 1."""
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


def _grupo(
    ax: Axes, x0: float, y0: float, x1: float, y1: float, titulo: str, titulo_em_cima: bool = False
) -> None:
    """Moldura tracejada de um módulo, com título em itálico."""
    ax.add_patch(
        FancyBboxPatch(
            (x0, y0),
            x1 - x0,
            y1 - y0,
            boxstyle="round,pad=0,rounding_size=0.1",
            facecolor=COR_GRUPO,
            edgecolor="#555555",
            linewidth=0.7,
            linestyle=(0, (3, 2)),
            zorder=1,
        )
    )
    y = y1 - 0.25 if titulo_em_cima else y0 + 0.25
    ax.text(
        x0 + 0.15, y, titulo, ha="left", va="center", fontsize=6.9, fontstyle="italic", zorder=2
    )


# --- Símbolos elétricos ------------------------------------------------------


def _fio(ax: Axes, *pontos: tuple[float, float]) -> None:
    xs, ys = zip(*pontos, strict=True)
    ax.plot(xs, ys, color=COR_FIO, lw=LW, zorder=2, solid_capstyle="round")


def _ponto(ax: Axes, x: float, y: float) -> None:
    ax.plot([x], [y], "o", color=COR_FIO, markersize=3.2, zorder=4)


def _texto(
    ax: Axes,
    x: float,
    y: float,
    texto: str,
    ha: str = "center",
    va: str = "center",
    fonte: float = FONTE_VALOR,
) -> None:
    ax.text(x, y, texto, ha=ha, va=va, fontsize=fonte, zorder=5, linespacing=1.15)


def _zigue(a: float, b: float, n: int = 6) -> list[float]:
    passo = (b - a) / n
    return [a + passo * (i + 0.5) for i in range(n)]


def _resistor_h(ax: Axes, x0: float, x1: float, y: float, valor: str) -> None:
    """Resistor horizontal entre x0 e x1, com o valor em cima."""
    meio = (x0 + x1) / 2
    a, b = meio - 0.4, meio + 0.4
    pontos = [(x0, y), (a, y)]
    for i, x in enumerate(_zigue(a, b)):
        pontos.append((x, y + (0.14 if i % 2 == 0 else -0.14)))
    pontos += [(b, y), (x1, y)]
    _fio(ax, *pontos)
    _texto(ax, meio, y + 0.32, valor)


def _resistor_v(ax: Axes, x: float, y_alto: float, y_baixo: float, valor: str) -> None:
    """Resistor vertical de y_alto a y_baixo, com o valor à direita."""
    meio = (y_alto + y_baixo) / 2
    a, b = meio + 0.32, meio - 0.32
    pontos = [(x, y_alto), (x, a)]
    for i, y in enumerate(_zigue(a, b)):
        pontos.append((x + (0.14 if i % 2 == 0 else -0.14), y))
    pontos += [(x, b), (x, y_baixo)]
    _fio(ax, *pontos)
    _texto(ax, x + 0.25, meio, valor, ha="left")


def _led_h(ax: Axes, x: float, y: float, cor: str) -> None:
    """LED apontando para a direita, centrado em x, com a cor embaixo."""
    ax.add_patch(
        Polygon(
            [(x - 0.22, y + 0.2), (x - 0.22, y - 0.2), (x + 0.18, y)],
            closed=True,
            facecolor="white",
            edgecolor=COR_FIO,
            lw=LW,
            zorder=3,
        )
    )
    _fio(ax, (x + 0.18, y + 0.2), (x + 0.18, y - 0.2))
    for dx in (-0.05, 0.12):
        ax.annotate(
            "",
            xy=(x + dx + 0.2, y + 0.45),
            xytext=(x + dx, y + 0.25),
            arrowprops={"arrowstyle": "-|>", "color": COR_FIO, "lw": 0.6, "mutation_scale": 5},
            zorder=3,
        )
    _texto(ax, x - 0.4, y + 0.27, cor, ha="right")


def _diodo_h(ax: Axes, x: float, y: float, nome: str) -> None:
    ax.add_patch(
        Polygon(
            [(x - 0.2, y + 0.2), (x - 0.2, y - 0.2), (x + 0.18, y)],
            closed=True,
            facecolor="white",
            edgecolor=COR_FIO,
            lw=LW,
            zorder=3,
        )
    )
    _fio(ax, (x + 0.18, y + 0.2), (x + 0.18, y - 0.2))
    _texto(ax, x, y - 0.4, nome)


def _terra(ax: Axes, x: float, y: float) -> None:
    for i, meia in enumerate((0.2, 0.13, 0.06)):
        yy = y - i * 0.08
        _fio(ax, (x - meia, yy), (x + meia, yy))


def _capacitor(ax: Axes, x: float, y: float, valor: str) -> None:
    """Capacitor do trilho em y para o terra, com o valor à direita."""
    _ponto(ax, x, y)
    _fio(ax, (x, y), (x, y - 0.28))
    _fio(ax, (x - 0.2, y - 0.28), (x + 0.2, y - 0.28))
    _fio(ax, (x - 0.2, y - 0.4), (x + 0.2, y - 0.4))
    _fio(ax, (x, y - 0.4), (x, y - 0.62))
    _terra(ax, x, y - 0.62)
    _texto(ax, x + 0.26, y - 0.34, valor, ha="left")


def _fonte(ax: Axes, x: float, y: float, texto: str) -> None:
    """Símbolo de alimentação: barra curta com a tensão em cima."""
    _fio(ax, (x - 0.22, y), (x + 0.22, y))
    _texto(ax, x, y + 0.2, texto)


def _regulador(ax: Axes, x: float, y: float) -> float:
    """Regulador de 3,3 V de x a x + 1,9, com o terra embaixo; devolve o x da saída."""
    caixa(ax, x + 0.95, y, 1.9, 0.8, "Regulador", "3,3 V")
    _fio(ax, (x + 0.95, y - 0.4), (x + 0.95, y - 0.6))
    _terra(ax, x + 0.95, y - 0.6)
    return x + 1.9


def _trilho(ax: Axes, x_ent: float, y: float) -> float:
    """Entrada de 5 V, capacitor, regulador e capacitores do 3,3 V; devolve o x do fim."""
    _capacitor(ax, x_ent + 0.7, y, "10 µF")
    x_reg = x_ent + 1.6
    _fio(ax, (x_ent, y), (x_reg, y))
    x_saida = _regulador(ax, x_reg, y)
    x_fim = x_saida + 4.5
    _fio(ax, (x_saida, y), (x_fim, y))
    for i, valor in enumerate(("10 µF", "100 nF", "100 µF")):
        _capacitor(ax, x_saida + 0.6 + i * 1.3, y, valor)
    _texto(ax, x_saida + 0.15, y + 0.2, "3,3 V", ha="left")
    return x_fim


# --- Figura 8: componentes internos -----------------------------------------


def _placa(ax: Axes, cy: float, h: float, titulo: str) -> Any:
    """Caixa de placa na esquerda da faixa: título à esquerda, pinos à direita."""
    b = caixa(ax, X0 + 1.7, cy, 3.2, h, "", "")
    ax.text(
        b.esq + 0.15,
        cy,
        titulo,
        ha="left",
        va="center",
        fontsize=7.6,
        fontweight="bold",
        zorder=4,
        linespacing=1.15,
    )
    return b


def desenhar_internos() -> plt.Figure:
    """Módulo de semáforo, adaptador I2C e pinos de boot da NodeMCU do carrinho."""
    fig, ax = _figura(12.25)
    _faixa(ax, 8.7, 12.25, "A\nMÓDULO DE\nSEMÁFORO")
    _faixa(ax, 4.0, 7.95, "B\nADAPTADOR I2C\nDO LCD")
    _faixa(ax, 0.0, 3.45, "C\nNODEMCU E RC522\n(PINOS DE BOOT)")

    # A. Módulo de semáforo (S1)
    linhas = (
        (11.2, "D13", "R", "330 Ω", "vermelho"),
        (10.2, "D12", "Y", "220 Ω", "amarelo"),
        (9.2, "D11", "G", "470 Ω", "verde"),
    )
    uno = _placa(ax, 10.2, 2.9, "Arduino\nUNO R3")
    _grupo(
        ax,
        X0 + 4.0,
        8.85,
        X0 + 11.9,
        12.1,
        "Módulo LED 8 mm (genérico), catodo comum",
        titulo_em_cima=True,
    )
    x_cat = X0 + 9.9
    for y, pino, letra, valor, cor in linhas:
        _texto(ax, uno.dir - 0.12, y, pino, ha="right", fonte=7)
        _fio(ax, (uno.dir, y), (X0 + 4.6, y))
        _texto(ax, X0 + 4.15, y + 0.2, letra, ha="left", fonte=7)
        _resistor_h(ax, X0 + 4.6, X0 + 6.6, y, valor)
        _fio(ax, (X0 + 6.6, y), (X0 + 7.9, y))
        _led_h(ax, X0 + 8.1, y, cor)
        _fio(ax, (X0 + 8.28, y), (x_cat, y))
        _ponto(ax, x_cat, y)
    _fio(ax, (x_cat, 11.2), (x_cat, 9.2))
    _fio(ax, (x_cat, 10.2), (X0 + 13.0, 10.2))
    _texto(ax, X0 + 11.75, 10.4, "GND", ha="right", fonte=7)
    caixa(ax, X0 + 14.6, 10.2, 3.2, 1.2, "Barramento GND", "protoboard → GND do UNO")
    caixa(
        ax,
        X0 + 18.6,
        10.2,
        3.2,
        2.6,
        "S2 a S4: iguais",
        "S2: D10, D9, D8\nS3: D7, D6, D5\nS4: D4, D3, D2",
        cor=COR_ARMAZEM,
    )

    # B. Adaptador I2C do LCD
    y_sda, y_scl = 6.6, 4.9
    uno_b = _placa(ax, 5.75, 2.6, "Arduino\nUNO R3")
    _grupo(ax, X0 + 4.0, 4.15, X0 + 11.9, 7.8, "Adaptador I2C (PCF8574T, placa tipo FC-113), 0x27")
    for y, pino in ((y_sda, "A4 (SDA)"), (y_scl, "A5 (SCL)")):
        _texto(ax, uno_b.dir - 0.12, y, pino, ha="right", fonte=7)
        _fio(ax, (uno_b.dir, y), (X0 + 9.0, y))
    for x, y, alto in ((X0 + 6.0, y_sda, 7.4), (X0 + 7.6, y_scl, 6.0)):
        _fonte(ax, x, alto, "5 V")
        _resistor_v(ax, x, alto, y, "4,7 kΩ")
        _ponto(ax, x, y)
    pcf = caixa(ax, X0 + 10.25, 5.75, 2.5, 2.15, "PCF8574T", "expansor I2C\ndo LCD")
    lcd = caixa(ax, X0 + 14.6, 5.75, 3.2, 1.2, "LCD 16x2", "fundo azul, 5 V")
    seta(ax, [(pcf.dir, 5.75), (lcd.esq, 5.75)])
    caixa(
        ax,
        X0 + 18.6,
        5.75,
        3.2,
        2.6,
        "Pull-ups do I2C",
        "4,7 kΩ (SMD 472), já\nsoldados no adaptador;\no UNO não acrescenta\noutros",
        cor=COR_ARMAZEM,
    )

    # C. NodeMCU do carrinho: pinos de boot ligados ao RC522
    y0, y15 = 2.25, 1.15
    esp = _placa(ax, 1.7, 2.0, "ESP-12E")
    _grupo(
        ax, X0 + 0.0, 0.12, X0 + 11.9, 3.3, "NodeMCU emissor (projeto de referência DevKit v1.0)"
    )
    for y, pino in ((y0, "GPIO0 (D3)"), (y15, "GPIO15 (D8)")):
        _texto(ax, esp.dir - 0.12, y, pino, ha="right", fonte=7)
        _fio(ax, (esp.dir, y), (X0 + 13.3, y))
    _fonte(ax, X0 + 7.0, 2.95, "3V3")
    _resistor_v(ax, X0 + 7.0, 2.95, y0, "12 kΩ (pull-up)")
    _ponto(ax, X0 + 7.0, y0)
    _resistor_v(ax, X0 + 9.0, y15, 0.45, "12 kΩ (pull-down)")
    _ponto(ax, X0 + 9.0, y15)
    _terra(ax, X0 + 9.0, 0.45)
    rc = caixa(ax, X0 + 14.6, 1.7, 2.6, 2.5, "RC522", "")
    _texto(ax, rc.esq + 0.12, y0, "RST *", ha="left", fonte=7)
    _texto(ax, rc.esq + 0.12, y15, "SDA/SS", ha="left", fonte=7)
    caixa(
        ax,
        X0 + 18.6,
        1.7,
        3.2,
        2.9,
        "Boot do ESP8266",
        "exige GPIO0 alto e\nGPIO15 baixo; os\nresistores da placa\ngarantem isso.\n"
        "* Polícia: RST no 3V3",
        cor=COR_ARMAZEM,
    )
    return fig


# --- Figura 9: alimentação ---------------------------------------------------


def desenhar_alimentacao() -> plt.Figure:
    """Alimentação do cruzamento e do carrinho, com as correntes da Tabela 8."""
    fig, ax = _figura(9.6)
    _faixa(ax, 3.3, 9.6, "A\nCRUZAMENTO")
    _faixa(ax, 0.0, 2.55, "B\nCARRINHO")

    # A. Cruzamento
    pc = caixa(ax, X0 + 1.5, 8.35, 2.8, 1.2, "Computador", "porta USB 2.0\n5 V, até 500 mA")
    uno = caixa(ax, X0 + 5.7, 7.6, 2.8, 2.9, "Arduino UNO R3", "alimentado só\npelo USB")
    seta(ax, [(pc.dir, 8.35), (uno.esq, 8.35)])
    rotulo(ax, (pc.dir + uno.esq) / 2, 8.6, "VBUS")
    lcd = caixa(ax, X0 + 10.8, 8.55, 3.8, 1.0, "LCD + adaptador I2C", "corrente não especificada")
    sem = caixa(
        ax, X0 + 10.8, 7.1, 3.8, 1.0, "4 módulos de semáforo", "≤ 75,8 mA (limite superior)"
    )
    seta(ax, [(uno.dir, 8.55), (lcd.esq, 8.55)])
    rotulo(ax, (uno.dir + lcd.esq) / 2, 8.8, "5V")
    seta(ax, [(uno.dir, 7.1), (sem.esq, 7.1)])
    rotulo(ax, (uno.dir + sem.esq) / 2, 7.35, "D2 a D13")
    caixa(
        ax,
        X0 + 17.5,
        7.8,
        5.2,
        2.0,
        "Orçamento da porta USB",
        "picos conhecidos: 75,8 + 170 = 245,8 mA\nfolga para UNO e LCD: 254,2 mA\n"
        "suficiência comprovada em 30 min\ncontínuos sem reinício (item 12)",
        cor=COR_ARMAZEM,
    )

    # ICSP-2 do UNO até o VIN do receptor
    y_r = 4.65
    x_icsp = X0 + 6.4
    _texto(ax, x_icsp + 0.12, uno.base - 0.25, "ICSP-2 (5 V)", ha="left", fonte=7)
    _grupo(ax, X0 + 7.3, 3.45, X0 + 20.2, 5.75, "NodeMCU receptor", titulo_em_cima=True)
    _fio(ax, (x_icsp, uno.base), (x_icsp, y_r), (X0 + 7.3, y_r))
    _texto(ax, X0 + 7.45, y_r + 0.2, "VIN", ha="left", fonte=7)
    x_fim = _trilho(ax, X0 + 7.3, y_r)
    esp = caixa(
        ax, x_fim + 1.5, y_r, 3.0, 1.2, "ESP-12E", "recebendo: 50 a 56 mA\ntransmitindo: 170 mA"
    )
    _fio(ax, (x_fim, y_r), (esp.esq, y_r))

    # B. Carrinho
    y_c = 1.45
    pb = caixa(ax, X0 + 1.5, y_c, 2.8, 1.2, "Power bank", "BASIKE 10000 mAh\nsaída USB 5 V")
    _grupo(ax, X0 + 4.0, 0.15, X0 + 16.0, 2.4, "NodeMCU emissor", titulo_em_cima=True)
    seta(ax, [(pb.dir, y_c), (X0 + 4.0, y_c)])
    rotulo(ax, (pb.dir + X0 + 4.0) / 2, y_c + 0.25, "micro-USB")
    _fio(ax, (X0 + 4.0, y_c), (X0 + 5.0, y_c))
    _diodo_h(ax, X0 + 5.2, y_c, "1N5819")
    _fio(ax, (X0 + 5.38, y_c), (X0 + 5.6, y_c))
    x_fim = _trilho(ax, X0 + 5.6, y_c)
    _fio(ax, (x_fim, y_c), (X0 + 16.4, y_c))
    esp_c = caixa(ax, X0 + 14.75, 0.72, 2.0, 0.8, "ESP-12E", "pico: 170 mA")
    _ponto(ax, esp_c.cx, y_c)
    _fio(ax, (esp_c.cx, y_c), (esp_c.cx, esp_c.topo))
    caixa(ax, X0 + 18.4, y_c, 3.6, 1.2, "RC522 (3,3 V)", "típico < 100 mA\n(nota 7 da NXP)")
    return fig


def salvar(fig: plt.Figure, nome: str) -> list[Path]:
    """Grava PNG (300 dpi) e PDF sem data, para o arquivo ser reprodutível."""
    gerados = []
    for formato in ("png", "pdf"):
        caminho = PASTA / f"{nome}.{formato}"
        metadados = {"CreationDate": None} if formato == "pdf" else {"Software": None}
        fig.savefig(caminho, dpi=300, metadata=metadados)
        gerados.append(caminho)
    plt.close(fig)
    return gerados


def main() -> int:
    """Ponto de entrada."""
    gerados = salvar(desenhar_internos(), "esquema_componentes_internos")
    gerados += salvar(desenhar_alimentacao(), "esquema_alimentacao")
    print("gerados:", ", ".join(p.name for p in gerados))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
