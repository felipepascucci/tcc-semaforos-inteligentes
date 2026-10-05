"""Apoio aos testes da ponte: um UNO simulado rápido e portas que falham de propósito."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from adapters.hardware.simulado import (
    LATENCIA_PADRAO_S,
    TransporteSimulado,
    UnoSimulado,
    config_da_bancada,
)
from bridge.transporte import ConexaoPerdidaError

CONFIG_BANCADA = config_da_bancada()


def fabrica_de_uno() -> Callable[[float], UnoSimulado]:
    return lambda t_s: UnoSimulado(CONFIG_BANCADA, t_s)


def transporte_rapido(
    *, latencia_s: float = LATENCIA_PADRAO_S, fio_do_nodemcu_no_rx: bool = False
) -> TransporteSimulado:
    return TransporteSimulado(
        fabrica_de_uno(),
        passo_s=0.01,
        latencia_s=latencia_s,
        fio_do_nodemcu_no_rx=fio_do_nodemcu_no_rx,
    )


async def ate(condicao: Callable[[], bool], limite_s: float = 2.0) -> None:
    """Espera a condição ficar verdadeira, ou falha o teste."""
    fim = asyncio.get_running_loop().time() + limite_s
    while not condicao():
        assert asyncio.get_running_loop().time() < fim, "condição não atingida no prazo"
        await asyncio.sleep(0.01)


class PortaRoteirizada:
    """`Transporte` que entrega linhas fixas e nunca responde a nada."""

    def __init__(self, linhas: list[bytes] | None = None) -> None:
        self._linhas: asyncio.Queue[bytes] = asyncio.Queue()
        for linha in linhas or []:
            self._linhas.put_nowait(linha)
        self.escritas: list[bytes] = []

    async def abrir(self) -> None:
        pass

    async def fechar(self) -> None:
        pass

    async def escrever(self, linha: bytes) -> None:
        self.escritas.append(linha)

    async def ler_linha(self) -> bytes:
        return await self._linhas.get()


class PortaAusente:
    """`Transporte` de um UNO que não está plugado."""

    tentativas = 0

    async def abrir(self) -> None:
        self.tentativas += 1
        raise ConexaoPerdidaError("COM3 não existe")

    async def fechar(self) -> None:
        pass

    async def escrever(self, linha: bytes) -> None:
        raise ConexaoPerdidaError("fechada")

    async def ler_linha(self) -> bytes:
        raise ConexaoPerdidaError("fechada")
