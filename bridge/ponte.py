"""O laço da ponte — entrega 5.7, `context/05` §6.

A ponte é o nó de borda (`context/01` §4.1): mantém a porta serial aberta,
alimenta o watchdog do UNO, traduz o que o motor decide e devolve, para cada
comando, o instante em que o semáforo começou a mudar.

**`t_atuacao` é a chegada do `ACK`** (P14, contrato §10), carimbada pela tarefa
que lê a porta no momento em que a linha chega, antes de interpretá-la. Medir o
envio mediria só a velocidade do próprio código.

O relógio é o do notebook, que é o oficial para a latência. Ele é lido com a
resolução do `perf_counter` (100 ns) e ancorado no relógio de parede uma vez:
no Windows o relógio de parede declara resolução de 15,6 ms, grosseira demais
para um intervalo que se quer abaixo de 200 ms (H3).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

import structlog

from bridge.protocolo import (
    Ack,
    ComandoSerial,
    Evento,
    LinhaInvalidaError,
    Nak,
    NomeComando,
    Resposta,
    Telemetria,
    interpretar,
    ping,
    traduzir,
)
from bridge.transporte import ConexaoPerdidaError, Transporte
from core.comandos import Comando

log = structlog.get_logger(__name__)

#: Contrato §6: PING a cada 1 s, contra um watchdog de 3 s no UNO.
PERIODO_PING_S: Final = 1.0

#: Quanto esperar o ACK/NAK de um comando. O UNO responde ao ler a linha; um
#: segundo inteiro sem resposta é porta muda, não UNO lento.
TIMEOUT_RESPOSTA_S: Final = 1.0

#: Intervalo entre tentativas de reabrir a porta.
ESPERA_RECONEXAO_S: Final = 1.0

#: Sem telemetria por este tempo (4 períodos de 2 Hz), o UNO não está respondendo.
SILENCIO_MAXIMO_S: Final = 2.0

_EVENTOS_GUARDADOS: Final = 50


class Relogio:
    """Relógio de parede em UTC com a resolução do `perf_counter`."""

    def __init__(self) -> None:
        self._parede = datetime.now(UTC)
        self._perf = time.perf_counter()

    def agora(self) -> datetime:
        return self._parede + timedelta(seconds=time.perf_counter() - self._perf)


@dataclass(frozen=True)
class ResultadoEnvio:
    """O que aconteceu com um comando enviado ao UNO.

    Attributes:
        linha: A linha enviada, sem terminador; `None` quando o comando do motor
            não tem tradução no protocolo (ver `protocolo.traduzir`).
        resposta: `ACK`, `NAK`, ou a telemetria de um `ST?`; `None` se nada
            chegou no prazo.
        t_envio: Quando a linha foi entregue à porta.
        t_resposta: Quando a resposta chegou.
        id_correlacao: Propagado da detecção até a métrica (`context/03` §4).
    """

    linha: str | None
    resposta: Resposta | None
    t_envio: datetime | None
    t_resposta: datetime | None
    id_correlacao: str | None = None

    @property
    def aceito(self) -> bool:
        return isinstance(self.resposta, Ack)

    @property
    def t_atuacao(self) -> datetime | None:
        """A chegada do `ACK` — só existe se o UNO aceitou (P14)."""
        return self.t_resposta if self.aceito else None

    @property
    def latencia_serial_ms(self) -> float | None:
        """Do envio à resposta. É a parcela serial de H3, não H3 inteira."""
        if self.t_envio is None or self.t_resposta is None:
            return None
        return (self.t_resposta - self.t_envio).total_seconds() * 1000


class Ponte:
    """Mantém a ligação com o UNO e atende os comandos do backend.

    Args:
        transporte: A porta — `TransporteSerial` na bancada, `TransporteSimulado`
            sem ela.
        relogio: Fonte dos carimbos; injetável nos testes.
    """

    def __init__(
        self,
        transporte: Transporte,
        *,
        relogio: Relogio | None = None,
        periodo_ping_s: float = PERIODO_PING_S,
        timeout_resposta_s: float = TIMEOUT_RESPOSTA_S,
        espera_reconexao_s: float = ESPERA_RECONEXAO_S,
    ) -> None:
        self.transporte = transporte
        self.relogio = relogio or Relogio()
        self._periodo_ping_s = periodo_ping_s
        self._timeout_resposta_s = timeout_resposta_s
        self._espera_reconexao_s = espera_reconexao_s

        self.conectada = False
        self.reconexoes = 0
        self.linhas_invalidas = 0
        self.telemetrias_com_dois_verdes = 0
        self.ultima_telemetria: Telemetria | None = None
        self.t_ultima_telemetria: datetime | None = None
        self.eventos: deque[tuple[datetime, Evento]] = deque(maxlen=_EVENTOS_GUARDADOS)

        self._pendentes: defaultdict[
            NomeComando, deque[asyncio.Future[tuple[Resposta, datetime]]]
        ] = defaultdict(deque)
        self._trava_escrita = asyncio.Lock()
        self._parar = asyncio.Event()

    # -- estado ----------------------------------------------------------------

    def uno_respondendo(self) -> bool:
        if not self.conectada or self.t_ultima_telemetria is None:
            return False
        silencio_s = (self.relogio.agora() - self.t_ultima_telemetria).total_seconds()
        return silencio_s <= SILENCIO_MAXIMO_S

    # -- ciclo de vida ---------------------------------------------------------

    async def rodar(self) -> None:
        """Abre a porta e a mantém aberta até `parar()`, reabrindo quando cai."""
        self._parar.clear()
        while not self._parar.is_set():
            try:
                await self.transporte.abrir()
            except ConexaoPerdidaError as erro:
                log.warning("porta_indisponivel", erro=str(erro))
                await self._dormir(self._espera_reconexao_s)
                continue

            self.conectada = True
            log.info("porta_aberta")
            await self._sessao()
            self.conectada = False
            self._falhar_pendentes()
            await self.transporte.fechar()

            if not self._parar.is_set():
                self.reconexoes += 1
                log.warning("porta_perdida", reconexoes=self.reconexoes)
                await self._dormir(self._espera_reconexao_s)

    def parar(self) -> None:
        self._parar.set()

    async def _sessao(self) -> None:
        """Lê e pinga até a porta cair ou alguém pedir para parar."""
        tarefas = {
            asyncio.create_task(self._ler(), name="ler"),
            asyncio.create_task(self._pingar(), name="pingar"),
            asyncio.create_task(self._parar.wait(), name="parar"),
        }
        feitas, pendentes = await asyncio.wait(tarefas, return_when=asyncio.FIRST_COMPLETED)
        for tarefa in pendentes:
            tarefa.cancel()
        for tarefa in pendentes:
            with contextlib.suppress(asyncio.CancelledError, ConexaoPerdidaError):
                await tarefa
        for tarefa in feitas:
            erro = tarefa.exception()
            if erro is not None and not isinstance(erro, ConexaoPerdidaError):
                raise erro

    async def _dormir(self, duracao_s: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._parar.wait(), duracao_s)

    # -- leitura ---------------------------------------------------------------

    async def _ler(self) -> None:
        while True:
            linha = await self.transporte.ler_linha()
            chegada = self.relogio.agora()  # antes de interpretar: é o t_atuacao
            try:
                resposta = interpretar(linha)
            except LinhaInvalidaError as erro:
                # Ruído é esperado: o UNO imprime lixo a cada reset.
                self.linhas_invalidas += 1
                log.debug("linha_invalida", linha=linha, erro=str(erro))
                continue
            self._despachar(resposta, chegada)

    def _despachar(self, resposta: Resposta, chegada: datetime) -> None:
        if isinstance(resposta, Ack | Nak):
            self._resolver(resposta.comando, resposta, chegada)
            if isinstance(resposta, Nak):
                log.warning("nak", comando=resposta.comando, motivo=resposta.motivo)
        elif isinstance(resposta, Telemetria):
            self.ultima_telemetria = resposta
            self.t_ultima_telemetria = chegada
            if resposta.viola_i1:
                # Nunca deve acontecer: o firmware recusa dois verdes. Contar é o
                # que permite ao relatório de validação afirmar que deu zero.
                self.telemetrias_com_dois_verdes += 1
                log.error("telemetria_com_dois_verdes", telemetria=resposta)
            self._resolver(NomeComando.CONSULTA, resposta, chegada)
        else:
            self.eventos.append((chegada, resposta))
            log.info("evento_uno", tipo=resposta.tipo, t_dispositivo_ms=resposta.t_dispositivo_ms)

    def _resolver(self, nome: NomeComando, resposta: Resposta, chegada: datetime) -> None:
        fila = self._pendentes[nome]
        while fila:
            futuro = fila.popleft()
            if not futuro.done():
                futuro.set_result((resposta, chegada))
                return

    def _falhar_pendentes(self) -> None:
        for fila in self._pendentes.values():
            while fila:
                futuro = fila.popleft()
                if not futuro.done():
                    futuro.set_exception(ConexaoPerdidaError("a porta caiu antes da resposta"))

    # -- escrita ---------------------------------------------------------------

    async def _escrever(self, linha: bytes) -> None:
        async with self._trava_escrita:
            await self.transporte.escrever(linha)

    async def _pingar(self) -> None:
        # O ACK do PING não é esperado por ninguém: o PING existe para o UNO,
        # não para a ponte, que sabe que ele está vivo pela telemetria.
        while True:
            await self._escrever(ping().codificar())
            await asyncio.sleep(self._periodo_ping_s)

    async def enviar(self, comando: Comando, id_correlacao: str | None = None) -> ResultadoEnvio:
        """Traduz o comando do motor e o envia.

        Raises:
            ConexaoPerdidaError: a porta não está aberta, ou caiu antes da
                resposta.
            ComandoInvalidoError: o comando não forma linha válida.
        """
        serial = traduzir(comando)
        if serial is None:
            return ResultadoEnvio(None, None, None, None, id_correlacao)
        return await self.enviar_serial(serial, id_correlacao)

    async def enviar_serial(
        self, comando: ComandoSerial, id_correlacao: str | None = None
    ) -> ResultadoEnvio:
        """Envia uma linha do protocolo e espera a resposta correspondente.

        Raises:
            ConexaoPerdidaError: a porta não está aberta, ou caiu antes da
                resposta.
        """
        if not self.conectada:
            raise ConexaoPerdidaError("porta serial não está aberta")
        linha = comando.codificar()
        futuro: asyncio.Future[tuple[Resposta, datetime]] = (
            asyncio.get_running_loop().create_future()
        )
        # Registrado ANTES de escrever: um ACK rápido não pode chegar antes de
        # haver quem o espere.
        self._pendentes[comando.nome].append(futuro)
        t_envio = self.relogio.agora()
        try:
            await self._escrever(linha)
            resposta, t_resposta = await asyncio.wait_for(futuro, self._timeout_resposta_s)
        except TimeoutError:
            log.warning("sem_resposta", linha=linha)
            return ResultadoEnvio(_texto(linha), None, t_envio, None, id_correlacao)
        finally:
            with contextlib.suppress(ValueError):
                self._pendentes[comando.nome].remove(futuro)
        return ResultadoEnvio(_texto(linha), resposta, t_envio, t_resposta, id_correlacao)


def _texto(linha: bytes) -> str:
    return linha.decode("ascii").rstrip("\n")
