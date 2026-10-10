"""Esquema elétrico da bancada — `context/05` §1 e `context/08` §5.

    python docs/diagramas/esquema_eletrico.py

Gera dois desenhos, em PDF (vetorial, para o texto do TCC) e PNG (para slides),
nesta pasta:

- `esquema_cruzamento`: Arduino UNO R3, os 4 módulos de semáforo, o LCD I2C e o
  NodeMCU receptor;
- `esquema_veiculo`: o NodeMCU emissor com o RC522, alimentado por power bank
  no micro-USB, igual nos três carrinhos, com a exceção do RST no da polícia.

As ligações estão nas constantes abaixo, e o desenho é feito a partir delas.
`tests/diagramas/test_esquema_eletrico.py` confere cada uma contra o firmware
(`semaforo.ino` e os `#define` dos emissores) e contra as tabelas do
`context/05` §1: um pino trocado no código quebra o teste até o esquema ser
revisto.

Usa o schemdraw (extra `analysis`), decisão de 2026-10-10 em `context/09`: o
Fritzing que o `context/08` previa é programa de interface, e o desenho por
código segue o mesmo caminho dos diagramas PlantUML desta pasta. O schemdraw só
é importado na hora de desenhar, e o teste lê os dados sem ele.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

PASTA = Path(__file__).resolve().parent

#: Os semáforos no UNO: (nome, aproximação, rua, pinos R, Y e G).
#: Fonte: `context/05` §1, e as tabelas VERM_DE, AMAR_DE e VERDE_DE de
#: `firmware/uno/semaforo/semaforo.ino`.
SEMAFOROS: tuple[tuple[str, str, str, int, int, int], ...] = (
    ("S1", "Principal, sentido A", "RUA1", 13, 12, 11),
    ("S2", "Principal, sentido B", "RUA2", 10, 9, 8),
    ("S3", "Transversal, sentido A", "RUA3", 7, 6, 5),
    ("S4", "Transversal, sentido B", "RUA4", 4, 3, 2),
)

#: LCD 16x2 com módulo I2C (endereço 0x27): pino do módulo -> pino do UNO.
LCD: dict[str, str] = {"SDA": "A4", "SCL": "A5", "VCC": "5V", "GND": "GND"}

#: NodeMCU receptor: pino do NodeMCU -> pino do UNO. O TX é o da UART0 (GPIO 1),
#: a do `Serial` do sketch; a alimentação sai do pino 2 do ICSP (`context/05` §1).
RECEPTOR: dict[str, str] = {"TX": "A0", "VIN": "ICSP-2", "GND": "GND"}

#: RC522 -> NodeMCU emissor, na ordem física dos pinos do módulo. O IRQ fica
#: sem fio. Fonte: `context/05` §1 e os `#define RST_PIN` e `SS_PIN` dos emissores.
RC522: dict[str, str] = {
    "SDA/SS": "D8",
    "SCK": "D5",
    "MOSI": "D7",
    "MISO": "D6",
    "GND": "GND",
    "RST": "D3",
    "3.3V": "3V3",
}

#: A ordem física dos 8 pinos do RC522, IRQ incluído.
PINOS_DO_RC522 = ("SDA/SS", "SCK", "MOSI", "MISO", "IRQ", "GND", "RST", "3.3V")

#: O GPIO de cada pino do NodeMCU que aparece no esquema.
GPIO_NODEMCU: dict[str, int] = {"D3": 0, "D5": 14, "D6": 12, "D7": 13, "D8": 15, "TX": 1}

#: Carrinho da polícia: o RST do RC522 vai ao 3V3, e o D3 fica sem fio
#: (2026-10-08, `context/05` §1 e `context/09`).
RST_DA_POLICIA = "3V3"

#: Os desenhos que `main()` gera, sem extensão.
DESENHOS = ("esquema_cruzamento", "esquema_veiculo")

FORMATOS = ("pdf", "png")

# Distância vertical entre dois pinos, em unidades do schemdraw.
_S = 0.6
_FONTE_PINO = 10
_FONTE_NOTA = 9


def _y(linha: float) -> float:
    """A altura da linha `linha` da grade; a linha 0 é a de cima."""
    return -linha * _S


def _caixa(
    d: Any,
    x0: float,
    x1: float,
    linhas: tuple[float, float],
    titulo: str,
    esquerda: dict[str, tuple[float, str]] | None = None,
    direita: dict[str, tuple[float, str]] | None = None,
) -> dict[str, tuple[float, float]]:
    """Desenha um módulo e devolve a coordenada de cada pino, na borda da caixa.

    `esquerda` e `direita` mapeiam a âncora do pino a (linha da grade, rótulo).
    `linhas` é a primeira e a última linha que a caixa cobre.
    """
    import schemdraw.elements as elm

    topo, base = _y(linhas[0] - 0.6), _y(linhas[1] + 0.6)
    # O Rect herda a posição e a direção do último elemento (uma antena aponta
    # para cima, e a caixa sairia girada); `at` e `theta` o prendem à origem.
    d.add(elm.Rect(corner1=(x0, base), corner2=(x1, topo)).at((0, 0)).theta(0))
    if titulo:
        _texto(d, ((x0 + x1) / 2, topo + 0.12), titulo, "center", "bottom", fonte=11)
    pinos: dict[str, tuple[float, float]] = {}
    for lado, x, ofst, alinhamento in (
        (esquerda, x0, 0.15, "left"),
        (direita, x1, -0.15, "right"),
    ):
        for ancora, (linha, rotulo) in (lado or {}).items():
            pinos[ancora] = (x, _y(linha))
            _texto(d, (x + ofst, _y(linha)), rotulo, alinhamento, fonte=_FONTE_PINO)
    return pinos


def _texto(
    d: Any,
    xy: tuple[float, float],
    texto: str,
    halign: str = "left",
    valign: str = "center",
    fonte: float = _FONTE_NOTA,
) -> None:
    import schemdraw.elements as elm

    # `theta(0)`: o rótulo também herda a direção do último elemento desenhado.
    d.add(elm.Label().theta(0).at(xy).label(texto, halign=halign, valign=valign, fontsize=fonte))


def _fio(d: Any, a: tuple[float, float], b: tuple[float, float]) -> None:
    import schemdraw.elements as elm

    d.add(elm.Line().at(a).to(b))


def _terra(d: Any, xy: tuple[float, float], com_ponto: bool = False) -> None:
    import schemdraw.elements as elm

    if com_ponto:
        d.add(elm.Dot().at(xy))
    d.add(elm.Ground().at(xy))


def desenhar_cruzamento() -> Any:
    """O UNO, os quatro semáforos, o LCD e o NodeMCU receptor."""
    import schemdraw
    import schemdraw.elements as elm

    # Cada semáforo ocupa 4 linhas da grade (R, Y, G e GND), com uma de folga.
    def linha_do(i: int, cor: int) -> int:
        return 5 * i + cor

    d = schemdraw.Drawing(show=False)
    d.config(unit=2)

    ultima = linha_do(len(SEMAFOROS), 0)  # a do GND que vai ao barramento
    direita = {
        f"{nome}{cor}": (linha_do(i, j), f"D{pino}")
        for i, (nome, _, _, *pinos) in enumerate(SEMAFOROS)
        for j, (cor, pino) in enumerate(zip("RYG", pinos, strict=True))
    }
    direita["GND_BARRAMENTO"] = (ultima, "GND")
    esquerda = {
        "SDA": (0, f"{LCD['SDA']}/SDA"),
        "SCL": (1, f"{LCD['SCL']}/SCL"),
        "VCC": (2, LCD["VCC"]),
        "GND": (3, LCD["GND"]),
        "TX": (7, RECEPTOR["TX"]),
        "VIN": (8, f"{RECEPTOR['VIN']} (5V)"),
        "USB": (13, "USB-B"),
    }
    uno = _caixa(d, 0, 5, (0, ultima), "Arduino UNO R3", esquerda, direita)
    _texto(d, (0.15, _y(18.5)), "A1: reservado, sem fio\nA2 e A3: livres")

    # Barramento negativo da protoboard: o GND do UNO e o dos quatro semáforos.
    xm0, xm1 = 8.0, 9.6
    xb = 6.6
    topo_barramento = (xb, _y(linha_do(0, 3)))
    base_barramento = (xb, _y(ultima))
    d.add(elm.Line(lw=4).at(topo_barramento).to(base_barramento))
    _fio(d, uno["GND_BARRAMENTO"], base_barramento)
    d.add(elm.Dot().at(base_barramento))
    _terra(d, base_barramento)
    _texto(d, (xb + 0.25, _y(ultima + 0.9)), "barramento negativo\nda protoboard", valign="top")

    # Semáforos: módulos com resistor integrado, alinhados aos pinos do UNO.
    for i, (nome, aproximacao, rua, *_) in enumerate(SEMAFOROS):
        modulo = _caixa(
            d,
            xm0,
            xm1,
            (linha_do(i, 0), linha_do(i, 3)),
            "",
            esquerda={cor: (linha_do(i, j), cor) for j, cor in enumerate(("R", "Y", "G", "GND"))},
        )
        for cor in "RYG":
            _fio(d, uno[f"{nome}{cor}"], modulo[cor])
        no_barramento = (xb, modulo["GND"][1])
        _fio(d, modulo["GND"], no_barramento)
        d.add(elm.Dot().at(no_barramento))
        _texto(d, (xm1 + 0.25, _y(linha_do(i, 1))), f"{nome}\n{aproximacao}\ntag {rua}")

    # LCD I2C, à esquerda, nos quatro primeiros pinos.
    xl0, xl1 = -6.2, -3.0
    lcd = _caixa(
        d,
        xl0,
        xl1,
        (0, 3),
        "LCD 16x2 I2C (0x27)",
        direita={p: (j, p) for j, p in enumerate(("SDA", "SCL", "VCC", "GND"))},
    )
    for pino in ("SDA", "SCL", "VCC", "GND"):
        _fio(d, lcd[pino], uno[pino])
    _terra(d, (-1.5, uno["GND"][1]), com_ponto=True)

    # NodeMCU receptor, à esquerda, no A0 e no ICSP.
    receptor = _caixa(
        d,
        xl0,
        xl1,
        (7, 9),
        "",
        direita={"TX": (7, "TX (GPIO 1)"), "VIN": (8, "VIN"), "GND": (9, "GND")},
    )
    _texto(d, ((xl0 + xl1) / 2, _y(10.0)), "NodeMCU receptor", halign="center", valign="top")
    _fio(d, receptor["TX"], uno["TX"])
    _fio(d, receptor["VIN"], uno["VIN"])
    _texto(d, (-1.5, uno["TX"][1] + 0.05), "9600 baud", halign="center", valign="bottom")
    gnd_x = xl1 + 1.0
    _fio(d, receptor["GND"], (gnd_x, receptor["GND"][1]))
    _terra(d, (gnd_x, receptor["GND"][1]))
    antena_x = xl0 + 0.4
    d.add(elm.Line().at((antena_x, _y(6.4))).up(0.2))
    d.add(elm.Antenna())
    _texto(d, (antena_x + 0.35, _y(5.4)), "ESP-NOW dos 3 carrinhos")

    # USB para o notebook.
    notebook = _caixa(d, xl0, xl1, (12.4, 13.6), "", direita={"USB": (13, "")})
    _texto(d, ((xl0 + xl1) / 2, _y(13)), "Notebook\n(ponte e\nbackend)", halign="center")
    _fio(d, notebook["USB"], uno["USB"])
    _texto(d, (-1.5, uno["USB"][1] + 0.05), "USB: dados\ne 5 V do UNO", "center", "bottom")

    _texto(
        d,
        (2.5, _y(ultima + 2.6)),
        "Módulos de semáforo com resistor integrado; o LED acende com HIGH.\n"
        "Os símbolos de terra são todos o mesmo nó: o GND do UNO.",
        halign="center",
        valign="top",
    )
    return d


def desenhar_veiculo() -> Any:
    """O NodeMCU emissor, o RC522 e a power bank: o mesmo nos três carrinhos."""
    import schemdraw
    import schemdraw.elements as elm

    d = schemdraw.Drawing(show=False)
    d.config(unit=2)

    def ancora(pino: str) -> str:
        return pino.replace("/", "_").replace(".", "_")

    def nome_nodemcu(pino: str) -> str:
        return f"{pino} (GPIO {GPIO_NODEMCU[pino]})" if pino in GPIO_NODEMCU else pino

    ultima = len(PINOS_DO_RC522) - 1
    nodemcu = _caixa(
        d,
        0,
        4.0,
        (0, ultima),
        "",
        esquerda={"USB": (3.5, "micro-USB")},
        direita={
            ancora(p): (j, nome_nodemcu(RC522[p]))
            for j, p in enumerate(PINOS_DO_RC522)
            if p in RC522
        },
    )
    _texto(d, (2.0, _y(ultima + 1.0)), "NodeMCU 1.0 (ESP-12E) emissor", "center", "top")
    rc522 = _caixa(
        d,
        7.5,
        9.5,
        (0, ultima),
        "RC522 (3,3 V)",
        esquerda={
            ancora(p): (j, f"{p} *" if p == "RST" else p) for j, p in enumerate(PINOS_DO_RC522)
        },
    )
    for pino in PINOS_DO_RC522:
        if pino in RC522:
            _fio(d, nodemcu[ancora(pino)], rc522[ancora(pino)])
    _texto(d, (7.4, rc522["IRQ"][1]), "IRQ sem fio", halign="right")

    # Alimentação: power bank no micro-USB do NodeMCU (2026-10-10).
    xp0, xp1 = -4.6, -2.4
    power_bank = _caixa(d, xp0, xp1, (3.0, 4.0), "", direita={"USB": (3.5, "")})
    _texto(d, ((xp0 + xp1) / 2, _y(3.5)), "Power bank\n(5 V)", halign="center")
    _fio(d, power_bank["USB"], nodemcu["USB"])
    _texto(d, ((xp1 + 0) / 2, nodemcu["USB"][1] + 0.05), "cabo USB", "center", "bottom")

    antena_x = 0.4
    d.add(elm.Line().at((antena_x, _y(-0.6))).up(0.3))
    d.add(elm.Antenna())
    _texto(d, (antena_x + 0.35, _y(-1.4)), "ESP-NOW para o receptor")

    _texto(
        d,
        (4.75, _y(ultima + 2.2)),
        f"* No carrinho da polícia, o RST do RC522 vai ao {RST_DA_POLICIA}, e o D3 fica "
        "sem fio:\no pino D3 daquela placa não leva o nível ao fio (2026-10-08).\n"
        "O mesmo esquema nos três carrinhos (ambulância, bombeiro e polícia). "
        "O RC522 nunca em 5 V.",
        halign="center",
        valign="top",
    )
    return d


def salvar(desenho: Any, nome: str) -> list[Path]:
    """Grava o desenho em PDF e PNG, sem data no PDF, para o arquivo ser reprodutível."""
    figura = desenho.draw(show=False).fig
    gerados = []
    for formato in FORMATOS:
        caminho = PASTA / f"{nome}.{formato}"
        metadados = {"CreationDate": None} if formato == "pdf" else {"Software": None}
        figura.savefig(caminho, dpi=200, bbox_inches="tight", metadata=metadados)
        gerados.append(caminho)
    return gerados


def main() -> int:
    """Ponto de entrada: `python docs/diagramas/esquema_eletrico.py`."""
    import matplotlib

    matplotlib.use("Agg")
    gerados = salvar(desenhar_cruzamento(), "esquema_cruzamento")
    gerados += salvar(desenhar_veiculo(), "esquema_veiculo")
    print("gerados:", ", ".join(p.name for p in gerados))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
