"""Grava o firmware no UNO pelo bootloader, em pedaços pequenos — `python -m bridge.gravar_uno`.

**Por que não o `arduino-cli upload`.** Neste notebook, a gravação pelo avrdude
(8.0 e também 6.3) sai corrompida, e sempre do mesmo jeito: em cada página de
128 bytes, os bytes 60 a 63 chegam errados (achado de 2026-10-06, `context/09`).
O comando de gravar uma página tem 4 bytes de cabeçalho e 128 de dados, e o
conversor USB da placa (16U2, de placa compatível) transporta em pacotes de 64
bytes: o byte 60 dos dados é o primeiro do segundo pacote. O avrdude manda a
página inteira de uma vez e não deixa mudar isso.

Este gravador fala o mesmo protocolo do bootloader (STK500 v1, o de
`avrdude -c arduino`), mas escreve cada comando em **pedaços de 16 bytes, com
uma pausa entre eles**, e no fim **relê a flash inteira e compara** com o
arquivo. Gravação que não confere é erro, não aviso.

Uso::

    python -m bridge.gravar_uno --porta COM3          # compila firmware/uno/semaforo e grava
    python -m bridge.gravar_uno --porta COM3 --hex x.hex

Abrir a porta reinicia o UNO no bootloader (DTR). Feche a ponte antes: duas
aberturas da mesma porta não convivem.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Final, Protocol

from adapters.terminal import saida_utf8

RAIZ: Final = Path(__file__).resolve().parents[1]
SKETCH: Final = RAIZ / "firmware" / "uno" / "semaforo"
FQBN: Final = "arduino:avr:uno"

BAUD_BOOTLOADER: Final = 115200
PAGINA: Final = 128  # bytes por página de flash do ATmega328P
PEDACO: Final = 16  # bem abaixo dos 64 bytes de um pacote USB
PAUSA_S: Final = 0.004

# STK500 v1
_INSYNC, _OK, _CRC_EOP = 0x14, 0x10, 0x20
_SINCRONIZAR, _ENDERECO, _GRAVAR, _LER, _SAIR = 0x30, ord("U"), ord("d"), ord("t"), ord("Q")
_FLASH = ord("F")


class GravacaoError(RuntimeError):
    """O bootloader não respondeu como esperado, ou a releitura não conferiu."""


class Porta(Protocol):
    """O pedaço de `serial.Serial` que o gravador usa — e que os testes imitam."""

    dtr: bool

    def write(self, dados: bytes) -> int | None: ...
    def flush(self) -> None: ...
    def read(self, n: int) -> bytes: ...
    def reset_input_buffer(self) -> None: ...


def ler_hex(texto: str) -> dict[int, int]:
    """Intel HEX → `{endereço: byte}`.

    Raises:
        GravacaoError: linha com checksum errado.
    """
    memoria: dict[int, int] = {}
    base = 0
    for numero, linha in enumerate(texto.splitlines(), start=1):
        linha = linha.strip()
        if not linha.startswith(":"):
            continue
        bruto = bytes.fromhex(linha[1:])
        if sum(bruto) & 0xFF:
            raise GravacaoError(f"checksum errado na linha {numero} do .hex")
        n, endereco, tipo = bruto[0], int.from_bytes(bruto[1:3], "big"), bruto[3]
        dados = bruto[4 : 4 + n]
        if tipo == 0:
            for i, byte in enumerate(dados):
                memoria[base + endereco + i] = byte
        elif tipo == 2:
            base = int.from_bytes(dados, "big") << 4
        elif tipo == 4:
            base = int.from_bytes(dados, "big") << 16
    return memoria


def paginas(memoria: dict[int, int]) -> list[tuple[int, bytes]]:
    """As páginas que o programa ocupa, completadas com 0xFF (flash apagada)."""
    if not memoria:
        return []
    inicios = sorted({endereco - endereco % PAGINA for endereco in memoria})
    return [(i, bytes(memoria.get(i + k, 0xFF) for k in range(PAGINA))) for i in inicios]


class Gravador:
    """Conversa com o bootloader do UNO em pedaços pequenos.

    Args:
        porta: A porta já aberta a 115200.
        pausa_s: Pausa entre dois pedaços; injetável nos testes.
    """

    def __init__(self, porta: Porta, *, pausa_s: float = PAUSA_S) -> None:
        self._porta = porta
        self._pausa_s = pausa_s

    def _enviar(self, dados: bytes) -> None:
        for i in range(0, len(dados), PEDACO):
            self._porta.write(dados[i : i + PEDACO])
            self._porta.flush()
            if self._pausa_s:
                time.sleep(self._pausa_s)

    def _resposta(self, n_dados: int = 0) -> bytes:
        resposta = self._porta.read(2 + n_dados)
        if len(resposta) != 2 + n_dados or resposta[0] != _INSYNC or resposta[-1] != _OK:
            raise GravacaoError(f"resposta inesperada do bootloader: {resposta!r}")
        return resposta[1:-1]

    def sincronizar(self, tentativas: int = 30) -> None:
        """Reinicia o UNO pelo DTR e espera o bootloader responder."""
        self._porta.dtr = False
        time.sleep(0.1)
        self._porta.dtr = True
        time.sleep(0.05)
        self._porta.reset_input_buffer()
        for _ in range(tentativas):
            self._porta.write(bytes([_SINCRONIZAR, _CRC_EOP]))
            if self._porta.read(2) == bytes([_INSYNC, _OK]):
                self._porta.reset_input_buffer()
                return
            time.sleep(0.05)
        raise GravacaoError("o bootloader não respondeu: a porta está certa e livre?")

    def _endereco(self, byte: int) -> None:
        palavra = byte // 2  # o bootloader endereça a flash em palavras de 16 bits
        self._enviar(bytes([_ENDERECO, palavra & 0xFF, palavra >> 8, _CRC_EOP]))
        self._resposta()

    def gravar_pagina(self, inicio: int, dados: bytes) -> None:
        self._endereco(inicio)
        cabecalho = bytes([_GRAVAR, len(dados) >> 8, len(dados) & 0xFF, _FLASH])
        self._enviar(cabecalho + dados + bytes([_CRC_EOP]))
        self._resposta()

    def ler_pagina(self, inicio: int, tamanho: int = PAGINA) -> bytes:
        self._endereco(inicio)
        self._enviar(bytes([_LER, tamanho >> 8, tamanho & 0xFF, _FLASH, _CRC_EOP]))
        return self._resposta(tamanho)

    def sair(self) -> None:
        """Deixa o bootloader, que entrega o controle ao programa."""
        self._enviar(bytes([_SAIR, _CRC_EOP]))
        self._resposta()

    def gravar(self, memoria: dict[int, int]) -> int:
        """Grava, relê tudo e confere. Devolve quantos bytes foram gravados.

        Raises:
            GravacaoError: algum byte relido difere do arquivo.
        """
        lista = paginas(memoria)
        for inicio, dados in lista:
            self.gravar_pagina(inicio, dados)
        diferentes = [
            inicio + k
            for inicio, dados in lista
            for k, (a, b) in enumerate(zip(dados, self.ler_pagina(inicio), strict=True))
            if a != b
        ]
        self.sair()
        if diferentes:
            raise GravacaoError(
                f"{len(diferentes)} bytes não conferem na releitura; o primeiro em "
                f"{diferentes[0]:#06x}"
            )
        return len(lista) * PAGINA


def compilar(sketch: Path, destino: Path) -> Path:
    """Compila com o `arduino-cli` e devolve o `.hex`."""
    cli = shutil.which("arduino-cli") or r"C:\Program Files\Arduino CLI\arduino-cli.exe"
    comando = [cli, "compile", "--fqbn", FQBN, "--output-dir", str(destino), str(sketch)]
    subprocess.run(comando, check=True)
    return destino / f"{sketch.name}.ino.hex"


def main(argv: Sequence[str] | None = None) -> int:
    saida_utf8()
    parser = argparse.ArgumentParser(prog="python -m bridge.gravar_uno", description=__doc__)
    parser.add_argument("--porta", default="COM3")
    parser.add_argument("--hex", type=Path, help="grava este .hex em vez de compilar o sketch")
    parser.add_argument("--sketch", type=Path, default=SKETCH)
    args = parser.parse_args(argv)

    import serial  # extra `hardware`; importado aqui para os testes não dependerem dele

    with tempfile.TemporaryDirectory() as pasta:
        arquivo = args.hex or compilar(args.sketch, Path(pasta))
        memoria = ler_hex(arquivo.read_text(encoding="ascii"))
        with serial.Serial(args.porta, BAUD_BOOTLOADER, timeout=1) as porta:
            gravador = Gravador(porta)
            gravador.sincronizar()
            try:
                total = gravador.gravar(memoria)
            except GravacaoError as erro:
                print(f"FALHOU: {erro}", file=sys.stderr)
                return 1
    print(f"Gravado e conferido: {total} bytes de {arquivo.name} em {args.porta}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
