"""Apoio aos testes da ponte: um UNO simulado rápido e portas que falham de propósito."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from adapters.hardware.simulado import (
    LATENCIA_PADRAO_S,
    TransporteSimulado,
    UnoSimulado,
    config_da_bancada,
)
from bridge.transporte import ConexaoPerdidaError, LinhaRecebida

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
    """`Transporte` que entrega linhas fixas e nunca responde a nada.

    Linha dada como `bytes` é carimbada quando é lida; como `LinhaRecebida`,
    chega com o carimbo que trouxer — é como os testes de H3 fixam os instantes.
    """

    def __init__(self, linhas: list[bytes | LinhaRecebida] | None = None) -> None:
        self._linhas: asyncio.Queue[bytes | LinhaRecebida] = asyncio.Queue()
        for linha in linhas or []:
            self.entregar(linha)
        self.escritas: list[bytes] = []
        self.aberturas = 0

    def entregar(self, linha: bytes | LinhaRecebida) -> None:
        self._linhas.put_nowait(linha)

    async def abrir(self) -> None:
        self.aberturas += 1

    async def fechar(self) -> None:
        pass

    async def escrever(self, linha: bytes) -> None:
        self.escritas.append(linha)

    async def ler_linha(self) -> LinhaRecebida:
        linha = await self._linhas.get()
        if isinstance(linha, LinhaRecebida):
            return linha
        return LinhaRecebida(linha, time.perf_counter())


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

    async def ler_linha(self) -> LinhaRecebida:
        raise ConexaoPerdidaError("fechada")
