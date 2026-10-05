"""Firmware do UNO contra o dublê, linha por linha — entrega 5.3, `context/05` §8.

O dublê (`adapters/hardware/simulado.py`) é o modelo de referência do firmware.
Aqui o **mesmo** `controlador.cpp` que vai para a placa é compilado para o PC
(`firmware/uno/teste_host/`, com o compilador C++ do pacote `ziglang`) e
recebe as mesmas entradas, nos mesmos instantes, que o dublê. As linhas que os
dois escrevem na serial têm de ser **idênticas**, com o `millis()` de cada uma.

O laço de teste anda de 1 em 1 ms, como um `loop()` rápido; o dublê processa
cada mudança no instante exato em que vence. Com todas as durações em ms
inteiros, os dois veem os mesmos instantes, e a igualdade é exata.

O que a comparação não cobre — pinos de verdade, a serial a 9600, o LCD físico
— fica com a aceitação na placa (`bridge.verificar`, 16 de 16).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from adapters.hardware.simulado import UnoSimulado, config_da_bancada
from bridge.protocolo import Deteccao
from bridge.verificar import violacoes
from core.modelos import TipoVeiculo

RAIZ = Path(__file__).resolve().parents[2]
FIRMWARE = RAIZ / "firmware" / "uno"
SKETCH = FIRMWARE / "semaforo"
FONTES = (SKETCH / "semaforo.ino", SKETCH / "controlador.h", SKETCH / "controlador.cpp")

AMB, BOMB, POL = TipoVeiculo.AMBULANCIA, TipoVeiculo.BOMBEIRO, TipoVeiculo.POLICIA
CONFIG = config_da_bancada()

#: Depois da última entrada, tempo bastante para o teto (30 s) e a volta ao ciclo.
SOBRA_MS = 45_000

Entrada = tuple[int, bytes]  # (instante em ms, linha que chega ao RX)


@pytest.fixture(scope="session")
def executavel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """O núcleo do firmware compilado para o PC."""
    pytest.importorskip("ziglang", reason="compilador do pacote ziglang não instalado")
    saida = tmp_path_factory.mktemp("firmware") / "semaforo_host.exe"
    comando = [
        sys.executable,
        "-m",
        "ziglang",
        "c++",
        "-std=c++11",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-Wno-nullability-completeness",  # cabeçalhos do libc++ do zig, não nossos
        "-o",
        str(saida),
        str(FIRMWARE / "teste_host" / "main.cpp"),
        str(SKETCH / "controlador.cpp"),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True, check=False)
    assert resultado.returncode == 0, resultado.stderr
    return saida


def _roteiro(entradas: Sequence[Entrada], fim_ms: int) -> str:
    linhas = ["B 0"]
    linhas += [f"R {ms} {linha.hex()}" for ms, linha in entradas]
    linhas.append(f"A {fim_ms}")
    return "\n".join(linhas) + "\n"


def _firmware(executavel: Path, roteiro: str) -> list[str]:
    resultado = subprocess.run(
        [str(executavel)], input=roteiro, capture_output=True, text=True, check=True
    )
    return resultado.stdout.splitlines()


def _serial(saida: list[str]) -> list[str]:
    return [linha for linha in saida if not linha.startswith("#")]


def _duble(entradas: Sequence[Entrada], fim_ms: int) -> list[str]:
    uno = UnoSimulado(CONFIG, 0.0)
    saida = uno.avancar(0.0)
    for ms, linha in entradas:
        saida += uno.receber(linha, ms / 1000)
    saida += uno.avancar(fim_ms / 1000)
    return [linha.decode("ascii").rstrip("\n") for linha in saida]


def _comparar(executavel: Path, entradas: Sequence[Entrada]) -> list[str]:
    fim_ms = (entradas[-1][0] if entradas else 0) + SOBRA_MS
    firmware = _firmware(executavel, _roteiro(entradas, fim_ms))
    assert "#VIOLACAO_I1" not in firmware
    serial = _serial(firmware)
    assert serial == _duble(entradas, fim_ms)
    return serial


def _ve(rua: int, tipo: TipoVeiculo) -> bytes:
    """A linha como o NodeMCU receptor a escreve (`println`)."""
    return Deteccao(rua, tipo).codificar().replace(b"\n", b"\r\n")


def _sequencia(serial: list[str]) -> list[tuple[int, str]]:
    return [(int(c[1]), c[2]) for c in (linha.split(",") for linha in serial) if c[0] == "ST"]


# ---------------------------------------------------------------------------
# Os cenários de context/05 §3 e §4, um a um
# ---------------------------------------------------------------------------


def test_ciclo_ocioso_igual_ao_duble(executavel: Path) -> None:
    serial = _comparar(executavel, [])
    assert serial[:2] == ["EV,0,BOOT", "ST,0,RRRR,C,0,0"]
    assert violacoes(_sequencia(serial)) == []


def test_exemplo_de_context_05_secao_4_2(executavel: Path) -> None:
    """VE na Rua 3 com o eixo principal verde há 1 s."""
    serial = _comparar(executavel, [(2000, _ve(3, AMB))])
    assert "EV,2000,PREEMP_INI,3,AMBULANCIA" in serial
    assert "ST,7000,RRGR,E,3,0" in serial  # 3 + 2 + 1 s até o verde exclusivo
    assert "EV,16000,PREEMP_FIM,3,AMBULANCIA" in serial  # 9 s depois
    assert "ST,16000,RRYR,C,0,0" in serial  # volta pelo eixo principal


def test_prioridade_fila_e_descarte(executavel: Path) -> None:
    serial = _comparar(
        executavel,
        [(1500, _ve(1, BOMB)), (4000, _ve(3, AMB)), (4200, _ve(2, POL)), (4300, _ve(4, BOMB))],
    )
    assert "EV,4000,FILA,1,BOMBEIRO" in serial
    assert "EV,4200,FILA,2,POLICIA" not in serial
    assert "EV,4200,DESCARTADO,2,POLICIA" in serial


def test_renovacao_ate_o_teto(executavel: Path) -> None:
    entradas = [(ms, _ve(4, AMB)) for ms in range(2000, 32_000, 4000)]
    serial = _comparar(executavel, entradas)
    assert "EV,32000,TIMEOUT" in serial


@pytest.mark.parametrize(
    "linha",
    [
        b"RUA9,AMBULANCIA\r\n",
        b"RUA0,AMBULANCIA\r\n",
        b"0,BOMBEIRO\n",
        b"RUA,POLICIA\n",
        b"RUA3,HELICOPTERO\n",
        b"RUA3,AMBULANCIA,X\n",
        b",\n",
        b"3,BOMBEIRO\r\n",
        b" RUA3 , BOMBEIRO \r\n",
        b"RUA03,POLICIA\n",
        b"RUA 3,POLICIA\n",
        b"\x00\xfe ets Jan  8 2013 rst cause:2\n",
        b"RUA3,AMBUL\xc3\x82NCIA\n",
        b"\x1cRUA2\x0b,\tPOLICIA\x1f\r\n",
    ],
)
def test_entrada_aceita_e_recusa_igual_ao_duble(executavel: Path, linha: bytes) -> None:
    _comparar(executavel, [(2000, linha)])


# ---------------------------------------------------------------------------
# Sequências aleatórias: chegadas de VE, lixo e linhas quase válidas
# ---------------------------------------------------------------------------

_PEDACOS = [
    b"RUA",
    b"1",
    b"2",
    b"3",
    b"4",
    b"5",
    b"0",
    b" ",
    b",",
    b"\r",
    b"\t",
    b"AMBULANCIA",
    b"BOMBEIRO",
    b"POLICIA",
    b"HELI",
    b"\x00",
    b"\xff",
    b"\x1c",
]

_linha_qualquer = (
    st.lists(st.sampled_from(_PEDACOS), max_size=10)
    .map(b"".join)
    .filter(lambda linha: len(linha) <= 64)  # o maior POST /injecao/bruta
    .map(lambda linha: linha + b"\n")
)

_entradas = st.lists(
    st.tuples(
        st.integers(0, 8000),  # espera desde a entrada anterior, em ms
        st.one_of(
            st.builds(_ve, st.integers(1, 4), st.sampled_from(list(TipoVeiculo))),
            _linha_qualquer,
        ),
    ),
    max_size=20,
)


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(_entradas)
def test_qualquer_sequencia_de_entradas_da_as_mesmas_linhas_que_o_duble(
    executavel: Path, esperas: list[tuple[int, bytes]]
) -> None:
    entradas: list[Entrada] = []
    ms = 0
    for espera, linha in esperas:
        ms += espera
        entradas.append((ms, linha))
    serial = _comparar(executavel, entradas)
    assert violacoes(_sequencia(serial)) == []


# ---------------------------------------------------------------------------
# O que o dublê não modela: LCD, buffer de saída, guarda de I1 nos pinos
# ---------------------------------------------------------------------------


def _lcds(saida: list[str]) -> list[tuple[str, str]]:
    return [tuple(linha.split("|")[1:3]) for linha in saida if linha.startswith("#LCD|")]  # type: ignore[misc]


def test_lcd_mostra_as_mensagens_do_sketch(executavel: Path) -> None:
    """`context/05` §3.6, completadas com espaços até as 16 colunas."""
    roteiro = "\n".join(
        [
            "B 0",
            "L",
            f"R 1500 {_ve(1, BOMB).hex()}",
            "L",
            f"R 4000 {_ve(3, AMB).hex()}",
            "L",
            "L",  # nada mudou: não reescreve
            "A 40000",
            "L",
        ]
    )
    saida = _firmware(executavel, roteiro + "\n")
    assert _lcds(saida) == [
        ("Semaforo: Normal", "Aguardando Sinal"),
        ("BOMBEIRO na R1  ", " " * 16),
        ("AMBULANCIA na R3", "Fila:BOMB na R1 "),
        ("Semaforo: Normal", "Aguardando Sinal"),
    ]
    assert "#LCD=" in saida


def test_st_periodica_e_pulada_com_o_buffer_cheio_mas_eventos_nao(executavel: Path) -> None:
    """`context/05` §3.5, item 7: a 9600 baud o `Serial.print` bloquearia."""
    roteiro = "\n".join(["B 0", "S 10", "A 2000", f"R 2000 {_ve(3, AMB).hex()}", "A 8000"])
    serial = _serial(_firmware(executavel, roteiro + "\n"))
    periodicas = {"ST,500,RRRR,C,0,0", "ST,1500,GGRR,C,0,0", "ST,2500,GGRR,E,3,0"}
    assert periodicas.isdisjoint(serial)
    # As de mudança de estado e o evento saem mesmo assim.
    assert "ST,1000,GGRR,C,0,0" in serial
    assert "EV,2000,PREEMP_INI,3,AMBULANCIA" in serial
    assert "ST,7000,RRGR,E,3,0" in serial


def test_guarda_de_i1_le_os_pinos_e_nao_a_maquina_de_estados(executavel: Path) -> None:
    """Um verde aceso por fora da máquina (pino travado) impede abrir o outro eixo."""
    saida = _firmware(executavel, "B 0\nG 2\nA 5000\n")  # S3 verde no pino
    assert "#VIOLACAO_I1" not in saida
    assert not any(linha.startswith(("#LUZ S1 G", "#LUZ S2 G")) for linha in saida)
    # Fica em all-red, que é o estado seguro.
    assert _serial(saida)[-1] == "ST,5000,RRRR,C,0,0"


def test_guarda_de_i1_deixa_abrir_o_mesmo_eixo(executavel: Path) -> None:
    """Controle da anterior: um verde do eixo principal não barra o eixo principal."""
    saida = _firmware(executavel, "B 0\nG 1\nA 1000\n")  # S2 verde no pino
    assert "#LUZ S1 G" in saida


# ---------------------------------------------------------------------------
# Fonte e compilação para a placa
# ---------------------------------------------------------------------------


def _codigo(caminho: Path) -> str:
    """O fonte sem comentários: o que se procura é uso, não menção."""
    texto = caminho.read_text(encoding="utf-8")
    texto = re.sub(r"/\*.*?\*/", "", texto, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", texto)


@pytest.mark.parametrize("fonte", FONTES, ids=lambda f: f.name)
def test_sem_string_nem_delay(fonte: Path) -> None:
    """`context/05` §3.5: `String` fragmenta os 2 KB de RAM; `delay()` cega a serial."""
    codigo = _codigo(fonte)
    assert not re.search(r"\bString\b", codigo)
    assert not re.search(r"\bdelay(Microseconds)?\s*\(", codigo)
    assert not re.search(r"\b(malloc|new)\b", codigo)


def test_lcd_e_o_da_biblioteca_de_frank_de_brabander_em_0x27() -> None:
    codigo = _codigo(SKETCH / "semaforo.ino")
    assert "#include <LiquidCrystal_I2C.h>" in codigo
    assert "LiquidCrystal_I2C lcd(0x27, 16, 2)" in codigo
    assert "lcd.init();" in codigo
    assert "Serial.begin(BAUD)" in codigo
    assert "BAUD = 9600" in codigo


def _arduino_cli() -> str | None:
    candidatos = [
        os.getenv("ARDUINO_CLI"),
        shutil.which("arduino-cli"),
        r"C:\Program Files\Arduino CLI\arduino-cli.exe",
    ]
    return next((c for c in candidatos if c and Path(c).is_file()), None)


def test_compila_para_o_uno_com_folga_de_ram(tmp_path: Path) -> None:
    cli = _arduino_cli()
    if cli is None:
        pytest.skip("arduino-cli não encontrado (defina ARDUINO_CLI)")
    resultado = subprocess.run(
        [cli, "compile", "--fqbn", "arduino:avr:uno", "--build-path", str(tmp_path), str(SKETCH)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    ram = re.search(r"Global variables use (\d+) bytes", resultado.stdout)
    assert ram is not None, resultado.stdout
    # O que sobra é a pilha. Metade dos 2 KB é margem confortável no ATmega328P.
    assert int(ram[1]) <= 1024
