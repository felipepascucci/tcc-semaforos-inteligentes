"""O que a ponte espera de uma "porta serial" — real ou simulada.

A ponte não fala com o pyserial diretamente: fala com um `Transporte`. Há duas
implementações, e é essa troca que permite desenvolver sem a bancada:

* `bridge/serial_client.py` — a porta USB de verdade, com pyserial;
* `adapters/hardware/simulado.py` — o dublê do UNO, em memória.

Mesmo princípio do motor (`context/01` §1), um degrau abaixo: quem usa a porta
não sabe se do outro lado há um Arduino.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LinhaRecebida:
    """Uma linha e o instante em que o **primeiro byte** dela chegou.

    O carimbo é do primeiro byte, e não da linha completa, porque a 9600 baud
    cada caractere leva ~1 ms: carimbar o fim somaria a duração da linha à
    latência de H3, e as linhas das duas pontas têm comprimentos diferentes
    (`context/05` §4.3).

    Attributes:
        dados: A linha, com o terminador.
        t_chegada: `time.perf_counter()` na chegada do primeiro byte. A ponte o
            converte para o relógio de parede (`Relogio.em`).
        bytes_em_espera: Quantos bytes já esperavam na porta quando o primeiro
            foi lido. Diagnóstico do carimbo: zero quer dizer que a ponte estava
            esperando o byte chegar; um número alto quer dizer que ele chegou
            antes de ser lido, e o carimbo está atrasado de pelo menos ~1 ms por
            byte. Zero onde não se aplica (dublê, testes).
    """

    dados: bytes
    t_chegada: float
    bytes_em_espera: int = 0


class ConexaoPerdidaError(ConnectionError):
    """A porta sumiu: cabo puxado, dispositivo desconectado, porta fechada.

    É condição de operação, não bug. A ponte reage reabrindo a porta; o UNO,
    do outro lado, não depende dela para nada (`context/05` §2).
    """


class Transporte(Protocol):
    """Uma ligação por linhas com uma placa: o UNO, ou o emissor na medição de H3."""

    async def abrir(self) -> None:
        """Abre a ligação.

        Abrir a porta de um UNO **reinicia a placa** (o DTR do USB serial puxa o
        reset), então quem abre deve esperar o estado voltar ao ciclo fixo.

        Raises:
            ConexaoPerdidaError: o dispositivo não está disponível.
        """
        ...

    async def fechar(self) -> None:
        """Fecha a ligação. Fechar o que já está fechado não é erro."""
        ...

    async def escrever(self, linha: bytes) -> None:
        """Envia uma linha já codificada, com terminador.

        Retorna assim que a linha sai; **não** espera a resposta.

        Raises:
            ConexaoPerdidaError: a ligação caiu.
        """
        ...

    async def ler_linha(self) -> LinhaRecebida:
        """Espera a próxima linha completa, carimbada no primeiro byte.

        Raises:
            ConexaoPerdidaError: a ligação caiu.
        """
        ...
