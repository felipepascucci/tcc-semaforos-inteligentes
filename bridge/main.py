"""Ponto de entrada da ponte serial — `python -m bridge.main`.

Roda no host, fora do compose, porque precisa da porta USB (`context/02` §3)::

    python -m bridge.main                 # COM3 do .env (SERIAL_PORT)
    python -m bridge.main --porta COM5
    python -m bridge.main --simulado      # sem bancada: dublê do UNO em memória

A API da ponte fica em `http://127.0.0.1:8001` (`/health`, `/estado`,
`/comandos`, documentação em `/docs`).
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

import uvicorn
from dotenv import load_dotenv

from bridge.api import criar_app
from bridge.ponte import Ponte
from bridge.protocolo import BAUD
from bridge.serial_client import TransporteSerial
from bridge.transporte import Transporte


def _argumentos(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m bridge.main", description=__doc__)
    parser.add_argument(
        "--porta",
        default=os.getenv("SERIAL_PORT", "COM3"),
        help="porta serial do UNO (padrão: SERIAL_PORT do .env)",
    )
    parser.add_argument("--baud", type=int, default=int(os.getenv("SERIAL_BAUDRATE", str(BAUD))))
    parser.add_argument(
        "--simulado",
        action="store_true",
        help="usa o dublê de adapters/hardware/simulado.py no lugar da porta",
    )
    parser.add_argument("--host", default=os.getenv("BRIDGE_HOST", "127.0.0.1"))
    parser.add_argument("--porta-http", type=int, default=int(os.getenv("BRIDGE_PORT", "8001")))
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    load_dotenv()
    args = _argumentos(argv)

    transporte: Transporte
    if args.simulado:
        # Importado só aqui: na bancada a ponte não precisa carregar o dublê.
        from adapters.hardware.simulado import TransporteSimulado

        transporte, nome = TransporteSimulado(), "simulada"
    else:
        transporte, nome = TransporteSerial(args.porta, args.baud), args.porta

    uvicorn.run(criar_app(Ponte(transporte), nome), host=args.host, port=args.porta_http)


if __name__ == "__main__":
    main()
