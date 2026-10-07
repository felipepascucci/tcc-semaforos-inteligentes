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
from bridge.protocolo import Autorizacoes
from bridge.transporte import ConexaoPerdidaError, LinhaRecebida

CONFIG_BANCADA = config_da_bancada()

#: Uma ocorrência de cada tipo, na ordem antiga dos tipos (ambulância 1,
#: bombeiro 2, polícia 3): com ela, a regra de antes de 2026-10-06 vale.
TODOS: Autorizacoes = (1, 2, 3)


class UnoJaAutorizado(UnoSimulado):
    """Atalho de teste: o UNO como fica depois de a ponte mandar a lista.

    O UNO de verdade liga negando todos; quem testa a autorização em si usa
    `autorizacoes=NENHUMA_AUTORIZACAO` e manda as linhas `AUT`.
    """

    def __init__(self, autorizacoes: Autorizacoes, t_s: float) -> None:
        super().__init__(CONFIG_BANCADA, t_s)
        self._autorizacoes = list(autorizacoes)


def fabrica_de_uno(autorizacoes: Autorizacoes = TODOS) -> Callable[[float], UnoSimulado]:
    return lambda t_s: UnoJaAutorizado(autorizacoes, t_s)


def transporte_rapido(
    *, latencia_s: float = LATENCIA_PADRAO_S, autorizacoes: Autorizacoes = TODOS
) -> TransporteSimulado:
    return TransporteSimulado(fabrica_de_uno(autorizacoes), passo_s=0.01, latencia_s=latencia_s)


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
