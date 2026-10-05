"""Difusão para o WebSocket `/api/v1/stream`, com throttle de 5 Hz (`context/01` §7).

Sem o throttle, uma simulação a 10 passos/s satura o navegador. Duas espécies de
mensagem, tratadas de forma diferente:

* **Estado** (`estado_semaforo`, `posicao_ve`, `metrica`, `trafego`): só o mais recente
  importa. Cada uma tem uma chave (o semáforo, o VE), e uma mensagem nova
  substitui a anterior da mesma chave que ainda não saiu.
* **Evento** (`evento`): todos saem, em ordem. Um evento perdido no meio de
  duas descargas seria um "PREEMP_INI" que o dashboard nunca mostrou.

**O throttle é pela borda de subida.** Se a última descarga foi há mais de um
intervalo, a mensagem sai na hora; senão, sai no fim do intervalo, junto com o
que chegar até lá. Uma descarga periódica fixa somaria até 200 ms a toda
mudança, e o RF04 dá 500 ms do estado ao cliente (`context/06` §2), com a
leitura da ponte no meio.

Tudo roda no laço de eventos do processo. Quem publica de outra thread usa
`loop.call_soon_threadsafe`.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from typing import Any, Final, Literal

import structlog

log = structlog.get_logger(__name__)

TipoEstado = Literal["estado_semaforo", "posicao_ve", "metrica", "trafego"]

#: Até que idade o último estado é reenviado a quem conecta (Bloco 7). A mesma
#: validade do "ao vivo" da simulação (`app/services/ao_vivo.py`): sem ela, quem
#: abre o dashboard depois de uma simulação acabar a veria "ao vivo", parada no
#: último instante, e uma bancada desligada pareceria ligada.
VALIDADE_REENVIO_S: Final = 5.0

#: Mensagens à espera por cliente. Um cliente que fica tão para trás está
#: travado, e é desligado: segurar a fila dele seria vazar memória (RNF02).
LIMITE_FILA_CLIENTE: Final = 1000


def mensagem(tipo: str, dados: Mapping[str, Any]) -> str:
    """O envelope do WebSocket: `{"tipo": ..., "dados": {...}}`."""
    return json.dumps({"tipo": tipo, "dados": dict(dados)}, ensure_ascii=False, default=str)


class Difusor:
    """Junta o que os produtores publicam e entrega aos clientes conectados."""

    def __init__(
        self, intervalo_s: float = 0.2, relogio: Callable[[], float] = time.monotonic
    ) -> None:
        self.intervalo_s = intervalo_s
        self._relogio = relogio
        self._clientes: set[asyncio.Queue[str | None]] = set()
        self._estado_pendente: dict[tuple[str, str], str] = {}
        self._eventos_pendentes: list[str] = []
        # O último estado de cada chave, com o instante, para quem conecta
        # depois não começar com a tela vazia até o próximo ciclo da bancada.
        self._ultimo_estado: dict[tuple[str, str], tuple[str, float]] = {}
        self._ultima_descarga = float("-inf")
        self._agendada: asyncio.TimerHandle | None = None
        self.descargas = 0

    @property
    def clientes(self) -> int:
        return len(self._clientes)

    def publicar_estado(self, tipo: TipoEstado, chave: str, dados: Mapping[str, Any]) -> None:
        """Estado mais recente de `chave`; substitui o que ainda não saiu."""
        texto = mensagem(tipo, dados)
        self._estado_pendente[(tipo, chave)] = texto
        self._ultimo_estado[(tipo, chave)] = (texto, self._relogio())
        self._agendar()

    def publicar_evento(self, dados: Mapping[str, Any]) -> None:
        """Um evento: nunca é descartado nem fundido com outro."""
        self._eventos_pendentes.append(mensagem("evento", dados))
        self._agendar()

    @asynccontextmanager
    async def assinar(self) -> AsyncIterator[asyncio.Queue[str | None]]:
        """Fila de mensagens de um cliente, já com o último estado recente.

        Só o estado publicado há menos de `VALIDADE_REENVIO_S` é reenviado.
        `None` na fila quer dizer "cliente desligado por lentidão".
        """
        fila: asyncio.Queue[str | None] = asyncio.Queue()
        agora = self._relogio()
        for texto, instante in self._ultimo_estado.values():
            if agora - instante < VALIDADE_REENVIO_S:
                fila.put_nowait(texto)
        self._clientes.add(fila)
        try:
            yield fila
        finally:
            self._clientes.discard(fila)

    def _agendar(self) -> None:
        if self._agendada is not None:
            return
        laco = asyncio.get_running_loop()
        espera = self._ultima_descarga + self.intervalo_s - self._relogio()
        if espera <= 0:
            self._agendada = laco.call_soon(self._descarregar)
        else:
            self._agendada = laco.call_later(espera, self._descarregar)

    def _descarregar(self) -> None:
        self._agendada = None
        self._ultima_descarga = self._relogio()
        lote = [*self._estado_pendente.values(), *self._eventos_pendentes]
        self._estado_pendente.clear()
        self._eventos_pendentes.clear()
        if not lote:
            return
        self.descargas += 1
        for fila in list(self._clientes):
            if fila.qsize() + len(lote) > LIMITE_FILA_CLIENTE:
                log.warning("cliente do websocket desligado por lentidao", pendentes=fila.qsize())
                self._clientes.discard(fila)
                fila.put_nowait(None)
                continue
            for texto in lote:
                fila.put_nowait(texto)
