"""Apoio aos testes da ponte: um UNO simulado rápido e portas que falham de propósito."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace

from adapters.configuracao import carregar_dicionario
from adapters.hardware.simulado import TransporteSimulado, UnoSimulado
from bridge.transporte import ConexaoPerdidaError
from core.parametros import Parametros

_DADOS = carregar_dicionario("hardware")
PARAMETROS_BANCADA = Parametros.de_dicionario(_DADOS)
VERDE_S = float(_DADOS["verde_s"])

#: Watchdog encurtado para os testes não esperarem 3 s de relógio de verdade.
WATCHDOG_TESTE_S = 0.3


def fabrica_de_uno(watchdog_s: float = WATCHDOG_TESTE_S) -> Callable[[float], UnoSimulado]:
    parametros = replace(PARAMETROS_BANCADA, watchdog_s=watchdog_s)
    return lambda t_s: UnoSimulado(parametros, VERDE_S, t_s)


def transporte_rapido(**opcoes: float) -> TransporteSimulado:
    return TransporteSimulado(fabrica_de_uno(), passo_s=0.01, **opcoes)


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
