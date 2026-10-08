"""Escuta crua da porta do emissor, carimbada — `python -m bridge.escuta_emissor`.

Diagnóstico, fora da ponte (as duas disputam a porta: feche a ponte antes)::

    python -m bridge.escuta_emissor --porta COM5 --baud 74880 --segundos 600

Imprime cada pedaço que chega, com a hora do notebook e o tamanho. A 74880
baud a mensagem de boot do ESP8266 sai legível (`ets Jan 8 2013,rst cause:…`) e
diz por que ele reiniciou; o texto do sketch, a 9600, vira lixo, mas o tamanho
e a hora de cada pedaço ainda mostram quando ele imprimiu. Foi assim que se viu,
em 2026-10-07, que o emissor reinicia ao abrir a porta e não ao ler uma tag fora
do mapa (`context/09`).
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Sequence
from datetime import datetime

import serial

from adapters.terminal import saida_utf8


def main(argv: Sequence[str] | None = None) -> int:
    saida_utf8()
    parser = argparse.ArgumentParser(prog="python -m bridge.escuta_emissor", description=__doc__)
    parser.add_argument("--porta", default="COM5")
    parser.add_argument("--baud", type=int, default=74880)
    parser.add_argument("--segundos", type=float, default=600.0)
    args = parser.parse_args(argv)

    with serial.Serial(args.porta, args.baud, timeout=0.05) as porta:
        fim = time.monotonic() + args.segundos
        while time.monotonic() < fim:
            dados = porta.read(4096)
            if not dados:
                continue
            agora = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            texto = dados.decode("ascii", errors="replace")
            texto = texto.replace("\r", "\\r").replace("\n", "\\n")
            print(f"{agora} [{len(dados)} B] {texto[:300]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
