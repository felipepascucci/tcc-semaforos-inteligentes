"""O que a ponte espera de uma "porta serial" — real ou simulada.

A ponte não fala com o pyserial diretamente: fala com um `Transporte`. Há duas
implementações, e é essa troca que permite desenvolver sem a bancada:

* `bridge/serial_client.py` — a porta USB de verdade, com pyserial;
* `adapters/hardware/simulado.py` — o dublê do UNO, em memória.

Mesmo princípio do motor (`context/01` §1), um degrau abaixo: quem usa a porta
não sabe se do outro lado há um Arduino.
"""

from __future__ import annotations

from typing import Protocol


class ConexaoPerdidaError(ConnectionError):
    """A porta sumiu: cabo puxado, dispositivo desconectado, porta fechada.

    É condição de operação, não bug. A ponte reage reabrindo a porta; o UNO,
    do outro lado, reage sozinho pelo watchdog (I6).
    """


class Transporte(Protocol):
    """Uma ligação por linhas com o UNO."""

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

    async def ler_linha(self) -> bytes:
        """Espera a próxima linha completa vinda do UNO.

        Raises:
            ConexaoPerdidaError: a ligação caiu.
        """
        ...
