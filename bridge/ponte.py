"""O laço da ponte — entrega 5.7, refeita para a arquitetura de 2026-10-05.

O notebook não está no caminho da decisão (`context/05` §6): a ponte ouve a
telemetria e os eventos que o UNO escreve no USB, carimba cada linha no relógio
do notebook e os entrega ao backend e ao dashboard. Se a ponte cair, o
cruzamento continua funcionando, com a última lista da Central que recebeu.

Duas escritas, pelo USB, que desde 2026-10-06 é só da ponte (o receptor foi
para o A0):

* a **lista da Central** (`autorizar`): `AUT,<VEICULO>,<0..3>` por tipo. Quem
  decide o que mandar é o backend, que compara a lista dele com a que a `ST`
  traz e chama `PUT /autorizacoes` quando diferem. A ponte continua sem saber
  que o backend existe;
* a **injeção de teste**: a mesma linha que o receptor escreveria
  (`RUA3,AMBULANCIA`), esperando o evento de decisão do UNO para ela.

O relógio é o do notebook, lido com a resolução do `perf_counter` (100 ns) e
ancorado no relógio de parede uma vez: no Windows o relógio de parede declara
resolução de 15,6 ms, grosseira demais para um intervalo que se quer abaixo de
200 ms (H3). Cada linha é carimbada na chegada do **primeiro byte**, pelo
transporte (`LinhaRecebida`).

**Medição de H3** (`context/05` §4.3). Com `transporte_veiculo`, a ponte ouve
também a serial do NodeMCU emissor, casa cada `Tag … lida -> Enviando RUAn` com
a decisão do UNO para ela (`bridge/latencia.py`) e entrega as amostras ao
gravador do CSV. Todo desfecho, amostra ou não, vai para o gravador de
desfechos: é o dado do RNF05.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

import structlog

from bridge.latencia import (
    AmostraH3,
    CasadorH3,
    DecisaoCarimbada,
    Desfecho,
    GravadorCsv,
    GravadorDesfechos,
    LeituraCarimbada,
)
from bridge.protocolo import (
    EVENTOS_DE_DECISAO,
    TERMINADOR,
    Autorizacao,
    Deteccao,
    Evento,
    LinhaInvalidaError,
    Resposta,
    Telemetria,
    interpretar,
    interpretar_leitura_veiculo,
)
from bridge.transporte import ConexaoPerdidaError, LinhaRecebida, Transporte

log = structlog.get_logger(__name__)

#: Quanto esperar o evento de decisão de uma injeção. O UNO decide na mesma
#: iteração em que lê a linha; um segundo inteiro sem resposta é UNO calado (ou
#: um firmware de antes de 2026-10-06, com o receptor ainda no RX), não UNO lento.
TIMEOUT_DECISAO_S: Final = 1.0

#: Intervalo entre tentativas de reabrir a porta.
ESPERA_RECONEXAO_S: Final = 1.0

#: Sem telemetria por este tempo (4 períodos de 2 Hz), o UNO não está respondendo.
SILENCIO_MAXIMO_S: Final = 2.0

#: Quantas telemetrias e eventos a ponte guarda para quem a consulta.
TELEMETRIAS_GUARDADAS: Final = 200
EVENTOS_GUARDADOS: Final = 100


class Relogio:
    """Relógio de parede em UTC com a resolução do `perf_counter`."""

    def __init__(self) -> None:
        self._parede = datetime.now(UTC)
        self._perf = time.perf_counter()

    def agora(self) -> datetime:
        return self.em(time.perf_counter())

    def em(self, perf: float) -> datetime:
        """O instante de parede de uma leitura de `time.perf_counter()`."""
        return self._parede + timedelta(seconds=perf - self._perf)


@dataclass(frozen=True)
class ResultadoInjecao:
    """O que o UNO fez com uma detecção injetada.

    Attributes:
        deteccao: O que foi injetado.
        t_envio: Quando a linha foi entregue à porta.
        decisao: O evento de decisão do UNO (`PREEMP_INI`, `RENOVADO`, `FILA`
            ou `DESCARTADO`); `None` se nada chegou no prazo.
        t_decisao: Quando o evento chegou.
    """

    deteccao: Deteccao
    t_envio: datetime
    decisao: Evento | None
    t_decisao: datetime | None

    @property
    def linha(self) -> str:
        return self.deteccao.codificar().decode("ascii").rstrip("\n")

    @property
    def latencia_ms(self) -> float | None:
        """Do envio ao evento. Conferência da ponte, não H3 (`context/05` §4.3)."""
        if self.t_decisao is None:
            return None
        return (self.t_decisao - self.t_envio).total_seconds() * 1000


class Ponte:
    """Mantém a escuta do UNO e guarda o que ele disse.

    Args:
        transporte: A porta — `TransporteSerial` na bancada, `TransporteSimulado`
            sem ela.
        relogio: Fonte dos carimbos; injetável nos testes.
        transporte_veiculo: A serial do NodeMCU emissor, só na medição de H3.
        gravador: Onde as amostras de H3 vão parar; só com `transporte_veiculo`.
        gravador_desfechos: Onde todo desfecho de detecção vai parar (RNF05);
            só com `transporte_veiculo`.
    """

    def __init__(
        self,
        transporte: Transporte,
        *,
        relogio: Relogio | None = None,
        timeout_decisao_s: float = TIMEOUT_DECISAO_S,
        espera_reconexao_s: float = ESPERA_RECONEXAO_S,
        transporte_veiculo: Transporte | None = None,
        gravador: GravadorCsv | None = None,
        gravador_desfechos: GravadorDesfechos | None = None,
    ) -> None:
        if (gravador is not None or gravador_desfechos is not None) and transporte_veiculo is None:
            raise ValueError("os gravadores da medição exigem a porta do emissor")
        self.transporte = transporte
        self.transporte_veiculo = transporte_veiculo
        self.gravador = gravador
        self.gravador_desfechos = gravador_desfechos
        self.relogio = relogio or Relogio()
        self._timeout_decisao_s = timeout_decisao_s
        self._espera_reconexao_s = espera_reconexao_s

        self.conectada = False
        self.reconexoes = 0
        self.linhas_invalidas = 0
        self.telemetrias_violando_i1 = 0
        self.telemetrias: deque[tuple[datetime, Telemetria]] = deque(maxlen=TELEMETRIAS_GUARDADAS)
        self.eventos: deque[tuple[datetime, Evento]] = deque(maxlen=EVENTOS_GUARDADOS)

        # Medição de H3: só existe com a porta do emissor.
        self.emissor_conectado = False
        self.amostras_h3: list[AmostraH3] = []
        self.deteccoes_sem_amostra: dict[str, int] = {}
        self._casador = None if transporte_veiculo is None else CasadorH3()

        self._pendentes: deque[tuple[Deteccao, asyncio.Future[tuple[Evento, datetime]]]] = deque()
        self._trava_escrita = asyncio.Lock()
        self._parar = asyncio.Event()

    # -- estado ----------------------------------------------------------------

    @property
    def ultima_telemetria(self) -> Telemetria | None:
        return self.telemetrias[-1][1] if self.telemetrias else None

    @property
    def t_ultima_telemetria(self) -> datetime | None:
        return self.telemetrias[-1][0] if self.telemetrias else None

    def uno_respondendo(self) -> bool:
        ultima = self.t_ultima_telemetria
        if not self.conectada or ultima is None:
            return False
        return (self.relogio.agora() - ultima).total_seconds() <= SILENCIO_MAXIMO_S

    # -- ciclo de vida ---------------------------------------------------------

    async def rodar(self) -> None:
        """Abre a porta e a mantém aberta até `parar()`, reabrindo quando cai.

        Abrir a porta reinicia o UNO (DTR), que volta pelo all-red; fechar não.
        A porta do emissor, se houver, é mantida à parte: cair uma não derruba
        a outra.
        """
        self._parar.clear()
        emissor = (
            None
            if self.transporte_veiculo is None
            else asyncio.create_task(self._escutar_emissor(self.transporte_veiculo), name="emissor")
        )
        try:
            await self._manter_uno()
        finally:
            if self._casador is not None and self._casador.pendentes:
                # Ficam fora dos dois CSV: a decisão delas ainda podia chegar.
                log.warning("deteccoes_pendentes_no_encerramento", n=self._casador.pendentes)
            if emissor is not None:
                emissor.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await emissor

    async def _manter_uno(self) -> None:
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
        """Lê até a porta cair ou alguém pedir para parar."""
        tarefas = {
            asyncio.create_task(self._ler(), name="ler"),
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
            chegada = self.relogio.em(linha.t_chegada)
            try:
                resposta = interpretar(linha.dados)
            except LinhaInvalidaError as erro:
                # Ruído é esperado: o UNO imprime lixo a cada reset.
                self.linhas_invalidas += 1
                log.debug("linha_invalida", linha=linha.dados, erro=str(erro))
                continue
            self._despachar(resposta, chegada)
            if self._casador is not None:
                if isinstance(resposta, Evento):
                    decisao = DecisaoCarimbada(chegada, resposta, linha.bytes_em_espera)
                    self._concluir(self._casador.evento(decisao))
                # As linhas do UNO chegam em ordem, e a `ST` sai a 2 Hz: cada uma
                # é a deixa para fechar o que passou da janela.
                self._concluir(self._casador.expirar(chegada))

    def _despachar(self, resposta: Resposta, chegada: datetime) -> None:
        if isinstance(resposta, Telemetria):
            self.telemetrias.append((chegada, resposta))
            if resposta.viola_i1:
                # Nunca deve acontecer: o firmware tem guarda própria. Contar é o
                # que permite ao relatório de validação afirmar que deu zero.
                self.telemetrias_violando_i1 += 1
                log.error("telemetria_viola_i1", telemetria=resposta)
            return
        self.eventos.append((chegada, resposta))
        log.info(
            "evento_uno",
            tipo=resposta.tipo,
            rua=resposta.rua,
            veiculo=resposta.veiculo,
            t_dispositivo_ms=resposta.t_dispositivo_ms,
        )
        if resposta.tipo in EVENTOS_DE_DECISAO:
            self._resolver(resposta, chegada)

    def _resolver(self, evento: Evento, chegada: datetime) -> None:
        for indice, (deteccao, futuro) in enumerate(self._pendentes):
            if (deteccao.rua, deteccao.veiculo) == (evento.rua, evento.veiculo):
                del self._pendentes[indice]
                if not futuro.done():
                    futuro.set_result((evento, chegada))
                return

    # -- medição de H3 ---------------------------------------------------------

    async def _escutar_emissor(self, transporte: Transporte) -> None:
        """Ouve o NodeMCU emissor e reabre a porta dele quando cai."""
        while not self._parar.is_set():
            try:
                await transporte.abrir()
            except ConexaoPerdidaError as erro:
                log.warning("porta_emissor_indisponivel", erro=str(erro))
                await self._dormir(self._espera_reconexao_s)
                continue
            self.emissor_conectado = True
            log.info("porta_emissor_aberta")
            try:
                while True:
                    self._ouvir_emissor(await transporte.ler_linha())
            except ConexaoPerdidaError as erro:
                log.warning("porta_emissor_perdida", erro=str(erro))
            finally:
                self.emissor_conectado = False
                await transporte.fechar()
            await self._dormir(self._espera_reconexao_s)

    def _ouvir_emissor(self, linha: LinhaRecebida) -> None:
        assert self._casador is not None
        try:
            leitura = interpretar_leitura_veiculo(linha.dados)
        except LinhaInvalidaError:
            # O emissor imprime outras coisas, e lixo a 74880 baud no boot.
            log.debug("linha_do_emissor_ignorada", linha=linha.dados)
            return
        t_deteccao = self.relogio.em(linha.t_chegada)
        deteccao = LeituraCarimbada(t_deteccao, leitura, linha.bytes_em_espera)
        log.info("deteccao_do_emissor", uid=leitura.uid, rua=leitura.rua)
        self._concluir(self._casador.deteccao(deteccao))

    def _concluir(self, desfechos: list[Desfecho]) -> None:
        for desfecho in desfechos:
            if self.gravador_desfechos is not None:
                try:
                    self.gravador_desfechos.gravar(desfecho)
                except OSError as erro:
                    log.error("csv_desfechos_nao_gravado", erro=str(erro))
            amostra = desfecho.amostra
            if amostra is None:
                # FILA, RENOVADO e DESCARTADO não têm atuação para medir;
                # SEM_DECISAO é detecção que não chegou ao UNO.
                tipo = desfecho.tipo
                self.deteccoes_sem_amostra[tipo] = self.deteccoes_sem_amostra.get(tipo, 0) + 1
                log.warning("deteccao_sem_amostra_h3", decisao=tipo, rua=desfecho.deteccao.rua)
                continue
            self.amostras_h3.append(amostra)
            log.info(
                "amostra_h3",
                latencia_total_ms=round(amostra.latencia_total_ms, 3),
                rua=amostra.deteccao.rua,
                n=len(self.amostras_h3),
            )
            if self.gravador is not None:
                try:
                    self.gravador.gravar(amostra)
                except OSError as erro:
                    # A amostra continua em memória; perder o arquivo não pode
                    # derrubar a escuta.
                    log.error("csv_h3_nao_gravado", erro=str(erro))

    def _falhar_pendentes(self) -> None:
        while self._pendentes:
            _, futuro = self._pendentes.popleft()
            if not futuro.done():
                futuro.set_exception(ConexaoPerdidaError("a porta caiu antes da decisão"))

    # -- injeção de teste ------------------------------------------------------

    async def _escrever(self, linha: bytes) -> datetime:
        if not self.conectada:
            raise ConexaoPerdidaError("porta serial não está aberta")
        async with self._trava_escrita:
            t_envio = self.relogio.agora()
            await self.transporte.escrever(linha)
        return t_envio

    async def autorizar(self, autorizacoes: Sequence[Autorizacao]) -> datetime:
        """Escreve a lista da Central no UNO, uma linha `AUT` por tipo.

        Não espera resposta: a confirmação é a `ST` seguinte, que traz a lista
        que o UNO tem (`Telemetria.autorizacoes`).

        Raises:
            ConexaoPerdidaError: a porta não está aberta.
        """
        if not autorizacoes:
            raise ValueError("nenhuma autorização para enviar")
        envios = [await self._escrever(autorizacao.codificar()) for autorizacao in autorizacoes]
        t_envio = envios[0]
        log.info(
            "autorizacoes_enviadas",
            autorizacoes={a.veiculo.value: a.criticidade for a in autorizacoes},
        )
        return t_envio

    async def injetar(self, deteccao: Deteccao) -> ResultadoInjecao:
        """Escreve a detecção no RX do UNO, pelo USB, e espera a decisão dele.

        Raises:
            ConexaoPerdidaError: a porta não está aberta, ou caiu antes da decisão.
        """
        if not self.conectada:
            raise ConexaoPerdidaError("porta serial não está aberta")
        futuro: asyncio.Future[tuple[Evento, datetime]] = asyncio.get_running_loop().create_future()
        # Registrado ANTES de escrever: a decisão pode chegar antes de haver
        # quem a espere.
        pendente = (deteccao, futuro)
        self._pendentes.append(pendente)
        try:
            t_envio = await self._escrever(deteccao.codificar())
            evento, t_decisao = await asyncio.wait_for(futuro, self._timeout_decisao_s)
        except TimeoutError:
            log.warning("sem_decisao", deteccao=deteccao)
            return ResultadoInjecao(deteccao, t_envio, None, None)
        finally:
            with contextlib.suppress(ValueError):
                self._pendentes.remove(pendente)
        return ResultadoInjecao(deteccao, t_envio, evento, t_decisao)

    async def injetar_bruta(self, texto: str) -> datetime:
        """Escreve uma linha qualquer no RX — para conferir o `EV,RECUSADO`.

        Raises:
            ConexaoPerdidaError: a porta não está aberta.
            UnicodeEncodeError: o texto não é ASCII.
        """
        return await self._escrever(texto.encode("ascii") + TERMINADOR)
