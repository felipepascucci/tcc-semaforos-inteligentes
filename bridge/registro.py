"""Registro de tudo o que passa pelo USB do UNO — checklist da bancada, `context/06` §6.

A ponte guarda em memória só as últimas 200 telemetrias e 100 eventos (`GET
/estado`). Os itens do checklist que falam das luzes (o ciclo, I1 a I4, a entrada
e a saída da emergência, o teto e as 30 min contínuas) precisam da sequência
**inteira** de uma sessão, e todo número do TCC precisa sair de dado gravado.
Com `--telemetria`, cada linha que o UNO escreve e cada linha que a ponte escreve
nele viram uma linha de `analysis/data/telemetria_bancada.csv`, gravada na hora;
`python -m analysis.checklist_bancada` tira dela o que o checklist pede.

A linha vai **crua**, como chegou (lixo de boot inclusive), e quem interpreta é o
script: um defeito na interpretação se corrige sem refazer a medição.

Este módulo é **puro** no mesmo sentido de `bridge/latencia.py`: não lê relógio
nem porta. Quem carimba é o transporte; quem chama, a ponte.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Final

from bridge.latencia import RAIZ, _acrescentar, versao_do_codigo

#: Onde vive a telemetria das sessões de bancada.
CSV_TELEMETRIA_PADRAO: Final = RAIZ / "analysis" / "data" / "telemetria_bancada.csv"

#: `t` é o carimbo da linha no relógio do notebook: o primeiro byte, para o que
#: o UNO escreveu (o mesmo `recebido_em` que o backend grava); o instante da
#: entrega à porta, para o que a ponte escreveu. `bytes_em_espera` só existe do
#: lado do UNO.
COLUNAS_TELEMETRIA: Final = (
    "sessao",
    "t",
    "direcao",
    "linha",
    "bytes_em_espera",
    "versao_codigo",
)


class Direcao(StrEnum):
    """Quem escreveu a linha."""

    UNO = "UNO"
    PONTE = "PONTE"


def texto_da_linha(dados: bytes) -> str:
    r"""A linha sem o terminador, legível mesmo quando é lixo.

    Byte fora do ASCII imprimível vira `\xNN`: o lixo de boot tem `0xFF` e `0x00`,
    e um caractere nulo no CSV atrapalharia quem o lê.
    """
    return "".join(
        chr(byte) if 0x20 <= byte < 0x7F else f"\\x{byte:02x}" for byte in dados.rstrip(b"\r\n")
    )


@dataclass
class GravadorTelemetria:
    """Acrescenta cada linha do USB do UNO a um CSV.

    Mesmas regras dos gravadores de H3: sessões acumuladas no mesmo arquivo, e o
    arquivo fechado a cada linha, para que uma ponte encerrada no meio (item 14
    do checklist) não perca nada.

    Args:
        caminho: O CSV. Na bancada, `CSV_TELEMETRIA_PADRAO`.
        sessao: Identifica a execução da ponte; a mesma dos CSV de H3, se houver.
        versao_codigo: Versão do código que gravou.
    """

    caminho: Path
    sessao: datetime
    versao_codigo: str = field(default_factory=versao_do_codigo)

    def gravar(self, t: datetime, direcao: Direcao, dados: bytes, bytes_em_espera: int = 0) -> None:
        _acrescentar(
            self.caminho,
            COLUNAS_TELEMETRIA,
            (
                self.sessao.isoformat(),
                t.isoformat(),
                direcao.value,
                texto_da_linha(dados),
                bytes_em_espera,
                self.versao_codigo,
            ),
        )
