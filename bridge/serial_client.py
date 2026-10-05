"""A porta USB de verdade — `Transporte` sobre pyserial (`context/05` §6).

O pyserial é bloqueante. Cada leitura e escrita roda numa thread
(`asyncio.to_thread`) com timeout curto, para que o laço da ponte nunca fique
preso esperando o UNO, e o PING de 1 s continue saindo mesmo com a placa calada.

Aceita qualquer URL do pyserial: `COM3` e `/dev/ttyUSB0` na bancada, e
`loop://` nos testes, que devolve o que se escreve — é como o cliente é testado
sem Arduino.
"""

from __future__ import annotations

import asyncio

import serial  # type: ignore[import-untyped]  # pyserial não traz tipos

from bridge.protocolo import BAUD, TERMINADOR
from bridge.transporte import ConexaoPerdidaError

#: Quanto uma leitura espera antes de devolver o controle ao laço. Curto o
#: bastante para que fechar a porta não demore, longo o bastante para não girar
#: em falso.
TIMEOUT_LEITURA_S = 0.1

#: Linha maior que isto é ruído (o contrato não tem nenhuma acima de ~30 bytes).
#: Sem o teto, lixo sem `\n` cresceria o buffer indefinidamente.
TAMANHO_MAXIMO_LINHA = 256


class TransporteSerial:
    """Ligação com o UNO por uma porta serial.

    Args:
        url: Porta ou URL do pyserial (`COM3`, `/dev/ttyUSB0`, `loop://`).
        baud: Velocidade; o protocolo fixa 115200.
    """

    def __init__(self, url: str, baud: int = BAUD) -> None:
        self.url = url
        self._baud = baud
        self._porta: serial.SerialBase | None = None
        self._buffer = bytearray()

    @property
    def conectado(self) -> bool:
        return self._porta is not None and self._porta.is_open

    async def abrir(self) -> None:
        await self.fechar()
        try:
            self._porta = await asyncio.to_thread(
                serial.serial_for_url,
                self.url,
                baudrate=self._baud,
                timeout=TIMEOUT_LEITURA_S,
                write_timeout=1.0,
            )
        except (serial.SerialException, OSError, ValueError) as erro:
            raise ConexaoPerdidaError(f"não abriu {self.url}: {erro}") from erro
        self._buffer.clear()

    async def fechar(self) -> None:
        porta, self._porta = self._porta, None
        if porta is not None:
            await asyncio.to_thread(porta.close)

    async def escrever(self, linha: bytes) -> None:
        porta = self._exigir_porta()
        try:
            await asyncio.to_thread(porta.write, linha)
        except (serial.SerialException, OSError) as erro:
            raise ConexaoPerdidaError(f"escrita em {self.url} falhou: {erro}") from erro

    async def ler_linha(self) -> bytes:
        while True:
            fim = self._buffer.find(TERMINADOR)
            if fim >= 0:
                linha = bytes(self._buffer[: fim + 1])
                del self._buffer[: fim + 1]
                return linha
            if len(self._buffer) > TAMANHO_MAXIMO_LINHA:
                self._buffer.clear()
            porta = self._exigir_porta()
            try:
                # `read_until` devolve o que tiver ao estourar o timeout; a linha
                # incompleta fica no buffer até o resto chegar.
                pedaco = await asyncio.to_thread(porta.read_until, TERMINADOR)
            except (serial.SerialException, OSError, TypeError, AttributeError) as erro:
                # TypeError/AttributeError: a porta foi fechada por outra tarefa
                # no meio da leitura, e o pyserial não traduz isso.
                raise ConexaoPerdidaError(f"leitura de {self.url} falhou: {erro}") from erro
            self._buffer += pedaco

    def _exigir_porta(self) -> serial.SerialBase:
        if self._porta is None or not self._porta.is_open:
            raise ConexaoPerdidaError(f"{self.url} não está aberta")
        return self._porta
