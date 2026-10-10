"""O esquema elétrico acompanha o firmware e o `context/05` §1.

As ligações que `docs/diagramas/esquema_eletrico.py` desenha são conferidas
contra o código que as usa (`semaforo.ino` e os `#define` dos emissores) e
contra as tabelas do `context/05` §1. Um pino trocado no firmware, ou na
tabela, quebra o teste até o esquema ser revisto e regerado (`context/08` §5:
"um diagrama que diverge do sistema é passivo").

O módulo é carregado sem o schemdraw: só o desenho precisa dele.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

RAIZ = Path(__file__).resolve().parents[2]
DIAGRAMAS = RAIZ / "docs" / "diagramas"
FIRMWARE = RAIZ / "firmware"
CONTEXTO_05 = RAIZ / "context" / "05-integracao-hardware.md"
EMISSORES = ("veiculo_ambulancia", "veiculo_bombeiro", "veiculo_policia")


def _esquema() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "esquema_eletrico", DIAGRAMAS / "esquema_eletrico.py"
    )
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


ESQUEMA = _esquema()


def _sketch_do_uno() -> str:
    return (FIRMWARE / "uno" / "semaforo" / "semaforo.ino").read_text(encoding="utf-8")


def _sketch(nome: str) -> str:
    return (FIRMWARE / "nodemcu" / nome / f"{nome}.ino").read_text(encoding="utf-8")


def _tabela_do_uno(nome: str) -> list[int]:
    achado = re.search(rf"{nome}\[bancada::N_SEMAFOROS\] = \{{([\d, ]+)\}}", _sketch_do_uno())
    assert achado, f"{nome} mudou de forma em semaforo.ino"
    return [int(v) for v in achado.group(1).split(",")]


def test_pinos_dos_semaforos_sao_os_do_firmware() -> None:
    do_esquema = [(r, y, g) for *_, r, y, g in ESQUEMA.SEMAFOROS]
    do_firmware = list(
        zip(
            _tabela_do_uno("VERM_DE"),
            _tabela_do_uno("AMAR_DE"),
            _tabela_do_uno("VERDE_DE"),
            strict=True,
        )
    )
    assert do_esquema == do_firmware


def test_semaforos_sao_os_da_tabela_do_contexto() -> None:
    texto = CONTEXTO_05.read_text(encoding="utf-8")
    linhas = re.findall(
        r"^\| (S[1-4]) \| .+? \| `(RUA[1-4])` \| \w+ \| (\d+) \| (\d+) \| (\d+) \|$",
        texto,
        re.MULTILINE,
    )
    do_contexto = [(s, rua, int(r), int(y), int(g)) for s, rua, r, y, g in linhas]
    do_esquema = [(s, rua, r, y, g) for s, _, rua, r, y, g in ESQUEMA.SEMAFOROS]
    assert do_contexto == do_esquema


def test_receptor_no_a0_pela_serial_do_sketch() -> None:
    """O UNO lê o receptor no A0, e o receptor escreve no TX da UART0 (GPIO 1)."""
    assert ESQUEMA.RECEPTOR["TX"] == "A0"
    assert re.search(r"PINO_RECEPTOR = A0;", _sketch_do_uno())
    receptor = _sketch("nodeMCU_semaforo")
    # `Serial` sem `swap()` sai no TX (GPIO 1); com `swap()` sairia no D8.
    assert "Serial.begin(9600)" in receptor
    assert "swap" not in receptor
    assert ESQUEMA.GPIO_NODEMCU["TX"] == 1


def test_lcd_e_receptor_sao_os_da_tabela_do_contexto() -> None:
    texto = CONTEXTO_05.read_text(encoding="utf-8")
    lcd = ESQUEMA.LCD
    assert f"SDA → {lcd['SDA']} · SCL → {lcd['SCL']}" in texto
    assert re.search(r"\| TX do NodeMCU receptor \| \*\*A0\*\*", texto)
    assert re.search(r"\| Alimentação do NodeMCU receptor \| \*\*5V do ICSP \(pino 2\)\*\*", texto)
    assert ESQUEMA.RECEPTOR["VIN"] == "ICSP-2"


def test_lcd_no_i2c_do_uno() -> None:
    """No UNO, o I2C é A4 (SDA) e A5 (SCL): o `Wire` não deixa escolher."""
    assert "#include <Wire.h>" in _sketch_do_uno()
    assert (ESQUEMA.LCD["SDA"], ESQUEMA.LCD["SCL"]) == ("A4", "A5")
    assert "LiquidCrystal_I2C lcd(0x27, 16, 2)" in _sketch_do_uno()


@pytest.mark.parametrize("nome", EMISSORES)
def test_rst_e_ss_do_rc522_sao_os_do_codigo_de_cada_emissor(nome: str) -> None:
    codigo = _sketch(nome)
    assert re.search(rf"#define RST_PIN {ESQUEMA.RC522['RST']}\b", codigo)
    assert re.search(rf"#define SS_PIN  {ESQUEMA.RC522['SDA/SS']}\b", codigo)


def test_rc522_e_o_da_tabela_do_contexto() -> None:
    """MISO, MOSI e SCK são do SPI do ESP8266 (D6, D7, D5): só a tabela os diz."""
    texto = CONTEXTO_05.read_text(encoding="utf-8")
    linhas = re.findall(
        r"^\| (3\.3V|RST|GND|MISO|MOSI|SCK|SDA/SS) \| (\w+)(?: \(GPIO (\d+)\))? \|",
        texto,
        re.MULTILINE,
    )
    do_contexto = {pino: nodemcu for pino, nodemcu, _ in linhas}
    assert do_contexto == ESQUEMA.RC522
    gpio = {nodemcu: int(n) for _, nodemcu, n in linhas if n}
    assert gpio == {p: g for p, g in ESQUEMA.GPIO_NODEMCU.items() if p != "TX"}


def test_ordem_dos_pinos_do_rc522_cobre_a_tabela() -> None:
    assert set(ESQUEMA.PINOS_DO_RC522) == set(ESQUEMA.RC522) | {"IRQ"}


def test_rst_da_policia_e_o_do_cabecalho_do_sketch() -> None:
    cabecalho = _sketch("veiculo_policia").split("*/", 1)[0]
    assert f"o RST do RC522 vai ao {ESQUEMA.RST_DA_POLICIA}" in cabecalho


def test_veiculo_na_power_bank_como_no_contexto() -> None:
    """A alimentação dos carrinhos foi corrigida em 2026-10-10 (`context/09`)."""
    texto = CONTEXTO_05.read_text(encoding="utf-8")
    assert "power bank no micro-USB" in texto
    assert "Bateria de 9 V em VIN/GND" not in texto


@pytest.mark.parametrize("nome", ["esquema_cruzamento", "esquema_veiculo"])
@pytest.mark.parametrize("formato", ["pdf", "png"])
def test_desenho_gerado_esta_versionado(nome: str, formato: str) -> None:
    assert nome in ESQUEMA.DESENHOS
    assert (DIAGRAMAS / f"{nome}.{formato}").stat().st_size > 0


def test_o_desenho_roda() -> None:
    """Desenha os dois esquemas sem gravar arquivo: pega erro de layout no código."""
    pytest.importorskip("schemdraw")
    import matplotlib

    matplotlib.use("Agg")
    for desenhar in (ESQUEMA.desenhar_cruzamento, ESQUEMA.desenhar_veiculo):
        assert desenhar().draw(show=False).fig is not None
