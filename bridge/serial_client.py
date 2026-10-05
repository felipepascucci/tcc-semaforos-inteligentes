"""A porta USB de verdade — `Transporte` sobre pyserial (`context/05` §6).

O pyserial é bloqueante. Cada leitura e escrita roda numa thread
(`asyncio.to_thread`) com timeout curto, para que o laço da ponte nunca fique
preso esperando a placa, e fechar a porta não demore.

**Carimbo no primeiro byte** (`context/05` §4.3). Entre uma linha e outra, a
leitura pede **um** byte só: `read(1)` volta assim que ele chega, e o
`perf_counter` é lido ali mesmo, na thread, antes de devolver o controle ao
laço. O resto da linha vem depois, com `read_until`. Carimbar a linha completa
somaria ~1 ms por caractere ao instante.

Aceita qualquer URL do pyserial: `COM3` e `/dev/ttyUSB0` na bancada, e
`loop://` nos testes, que devolve o que se escreve — é como o cliente é testado
sem Arduino.
"""

from __future__ import annotations

import asyncio
import time

import serial  # type: ignore[import-untyped]  # pyserial não traz tipos

from bridge.protocolo import BAUD, TERMINADOR
from bridge.transporte import ConexaoPerdidaError, LinhaRecebida

#: Quanto uma leitura espera antes de devolver o controle ao laço. Curto o
#: bastante para que fechar a porta não demore, longo o bastante para não girar
#: em falso.
TIMEOUT_LEITURA_S = 0.1

#: Linha maior que isto é ruído (o contrato não tem nenhuma acima de ~40 bytes).
#: Sem o teto, lixo sem `\n` cresceria o buffer indefinidamente.
TAMANHO_MAXIMO_LINHA = 256


def _primeiro_byte(porta: serial.SerialBase) -> tuple[bytes, float, int]:
    """Espera um byte; devolve-o com o instante e os bytes que já esperavam.

    Roda na thread do `to_thread`: o `perf_counter` é lido no retorno do
    `read`, sem passar pelo laço do asyncio.
    """
    byte = porta.read(1)
    t_chegada = time.perf_counter()
    return byte, t_chegada, porta.in_waiting if byte else 0


class TransporteSerial:
    """Ligação com uma placa por uma porta serial.

    Args:
        url: Porta ou URL do pyserial (`COM3`, `/dev/ttyUSB0`, `loop://`).
        baud: Velocidade; a bancada usa 9600, a do NodeMCU receptor e a do
            emissor.
    """

    def __init__(self, url: str, baud: int = BAUD) -> None:
        self.url = url
        self._baud = baud
        self._porta: serial.SerialBase | None = None
        self._buffer = bytearray()
        # Carimbo do primeiro byte da linha que está no buffer, se houver.
        self._t_chegada = 0.0
        self._em_espera = 0

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

    async def ler_linha(self) -> LinhaRecebida:
        while True:
            fim = self._buffer.find(TERMINADOR)
            if fim >= 0:
                # `read_until` lê byte a byte e para no terminador: o buffer
                # nunca guarda o começo da linha seguinte, e o próximo byte lido
                # é o primeiro dela.
                linha = bytes(self._buffer[: fim + 1])
                del self._buffer[: fim + 1]
                return LinhaRecebida(linha, self._t_chegada, self._em_espera)
            if len(self._buffer) > TAMANHO_MAXIMO_LINHA:
                self._buffer.clear()
            porta = self._exigir_porta()
            try:
                if self._buffer:
                    # `read_until` devolve o que tiver ao estourar o timeout; a
                    # linha incompleta fica no buffer até o resto chegar.
                    self._buffer += await asyncio.to_thread(porta.read_until, TERMINADOR)
                    continue
                byte, t_chegada, em_espera = await asyncio.to_thread(_primeiro_byte, porta)
            except (serial.SerialException, OSError, TypeError, AttributeError) as erro:
                # TypeError/AttributeError: a porta foi fechada por outra tarefa
                # no meio da leitura, e o pyserial não traduz isso.
                raise ConexaoPerdidaError(f"leitura de {self.url} falhou: {erro}") from erro
            if byte:
                self._buffer += byte
                self._t_chegada, self._em_espera = t_chegada, em_espera

    def _exigir_porta(self) -> serial.SerialBase:
        if self._porta is None or not self._porta.is_open:
            raise ConexaoPerdidaError(f"{self.url} não está aberta")
        return self._porta
