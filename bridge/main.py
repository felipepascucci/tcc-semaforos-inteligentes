"""Ponto de entrada da ponte serial — `python -m bridge.main`.

Roda no host, fora do compose, porque precisa da porta USB (`context/02` §3)::

    python -m bridge.main                 # COM3 do .env (SERIAL_PORT)
    python -m bridge.main --porta COM5
    python -m bridge.main --simulado      # sem bancada: dublê do UNO em memória

    # Medição de H3 (context/05 §4.3): o emissor no USB do notebook.
    python -m bridge.main --porta COM3 --porta-veiculo COM4
    python -m bridge.main --porta-veiculo  # COM do .env (SERIAL_PORT_VEICULO)

A ponte escuta o UNO e escreve nele só a lista da Central e a injeção de teste
(`context/05` §6). A API fica em `http://127.0.0.1:8001` (`/health`, `/estado`,
`/autorizacoes`, `/injecao`, documentação em `/docs`). Abrir a porta reinicia o
UNO, que volta **negando todos** até receber a lista: com o backend no ar, ele a
reenvia sozinho em até ~1 s.

Com `--porta-veiculo`, cada detecção que o UNO atende vira uma linha de
`analysis/data/latencia_bancada.csv` (H3), e cada leitura do emissor, atendida
ou não, uma de `analysis/data/deteccoes_bancada.csv` (RNF05). O resumo das duas
sai de `python -m analysis.resumo_bancada`. **Não há como medir H3 com o dublê**: a
combinação `--simulado --porta-veiculo` é recusada, para que nenhum número
simulado chegue ao CSV.

Com `--telemetria`, cada linha do USB do UNO, nos dois sentidos, vira uma linha
de `analysis/data/telemetria_bancada.csv`: é o dado do checklist da bancada
(`context/06` §6), lido por `python -m analysis.checklist_bancada`. Também é
recusada com `--simulado`::

    python -m bridge.main --porta COM3 --telemetria
    python -m bridge.main --porta COM3 --porta-veiculo COM5 --telemetria
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from bridge.api import criar_app
from bridge.latencia import CSV_DESFECHOS_PADRAO, CSV_PADRAO, GravadorCsv, GravadorDesfechos
from bridge.ponte import Ponte
from bridge.protocolo import BAUD
from bridge.registro import CSV_TELEMETRIA_PADRAO, GravadorTelemetria
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
    parser.add_argument(
        "--porta-veiculo",
        nargs="?",
        const=os.getenv("SERIAL_PORT_VEICULO", "COM4"),
        default=None,
        help="mede H3: porta do NodeMCU emissor (sem valor: SERIAL_PORT_VEICULO do .env)",
    )
    parser.add_argument(
        "--csv-h3",
        type=Path,
        default=CSV_PADRAO,
        help="onde gravar as amostras de H3 (padrão: analysis/data/latencia_bancada.csv)",
    )
    parser.add_argument(
        "--csv-deteccoes",
        type=Path,
        default=CSV_DESFECHOS_PADRAO,
        help="onde gravar cada desfecho de detecção, o dado do RNF05 "
        "(padrão: analysis/data/deteccoes_bancada.csv)",
    )
    parser.add_argument(
        "--telemetria",
        nargs="?",
        type=Path,
        const=CSV_TELEMETRIA_PADRAO,
        default=None,
        help="grava cada linha do USB do UNO, o dado do checklist "
        "(sem valor: analysis/data/telemetria_bancada.csv)",
    )
    parser.add_argument("--host", default=os.getenv("BRIDGE_HOST", "127.0.0.1"))
    parser.add_argument("--porta-http", type=int, default=int(os.getenv("BRIDGE_PORT", "8001")))
    args = parser.parse_args(argv)
    if args.simulado and args.porta_veiculo is not None:
        parser.error("H3 se mede na bancada: --porta-veiculo não combina com --simulado")
    if args.simulado and args.telemetria is not None:
        parser.error("o checklist é da bancada: --telemetria não combina com --simulado")
    return args


def main(argv: Sequence[str] | None = None) -> None:
    load_dotenv()
    args = _argumentos(argv)

    transporte: Transporte
    if args.simulado:
        # Importado só aqui: na bancada a ponte não precisa carregar o dublê.
        from adapters.hardware.simulado import TransporteSimulado

        transporte, nome = TransporteSimulado(), "simulada"
    else:
        if args.baud != BAUD:
            # O UNO divide a UART com o NodeMCU receptor, que fala a 9600: outra
            # velocidade só produz lixo na porta (context/05 §4).
            print(f"AVISO: baud {args.baud}, mas a bancada fala a {BAUD}. SERIAL_BAUDRATE do .env?")
        transporte, nome = TransporteSerial(args.porta, args.baud), args.porta

    # Uma sessão por execução da ponte, a mesma em todos os CSV que ela gravar.
    sessao = datetime.now(UTC)
    veiculo: Transporte | None = None
    gravador: GravadorCsv | None = None
    gravador_desfechos: GravadorDesfechos | None = None
    if args.porta_veiculo is not None:
        # O emissor imprime a 9600 (veiculo_ambulancia.ino), qualquer que seja o
        # baud do UNO.
        veiculo = TransporteSerial(args.porta_veiculo, BAUD)
        gravador = GravadorCsv(args.csv_h3, sessao=sessao)
        gravador_desfechos = GravadorDesfechos(
            args.csv_deteccoes, sessao=sessao, versao_codigo=gravador.versao_codigo
        )
        print(f"Medindo H3 e RNF05: emissor em {args.porta_veiculo}, sessão {sessao.isoformat()}")
        print(f"  amostras de H3 em {args.csv_h3}")
        print(f"  desfechos de cada leitura em {args.csv_deteccoes}")

    registro: GravadorTelemetria | None = None
    if args.telemetria is not None:
        registro = GravadorTelemetria(args.telemetria, sessao=sessao)
        print(f"Gravando a telemetria do UNO: sessão {sessao.isoformat()}")
        print(f"  cada linha do USB em {args.telemetria}")

    ponte = Ponte(
        transporte,
        transporte_veiculo=veiculo,
        gravador=gravador,
        gravador_desfechos=gravador_desfechos,
        registro=registro,
    )
    uvicorn.run(criar_app(ponte, nome), host=args.host, port=args.porta_http)


if __name__ == "__main__":
    main()
