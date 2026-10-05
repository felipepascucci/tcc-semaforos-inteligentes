"""A bancada vista pelo backend: tradução dos eventos do UNO e leitura da ponte.

**O backend lê a ponte, e não o contrário** (decisão de 2026-10-05, Bloco 6). A
cada 200 ms ele pede `GET /estado`, que traz as últimas telemetrias, eventos e
amostras de H3, já carimbados no relógio do notebook. A ponte continua sem saber
que o backend existe, e o código que carimba H3 não muda.

**O UNO já decidiu.** Os eventos chegam aqui depois que a preempção começou, então
nada passa por `core/autorizacao`: rodar P20 sobre uma decisão já executada
geraria um log que contradiz a bancada. O que este módulo faz é **registrar**:

=================  ============================  =======================================
Evento do UNO      `log_prioridade`              `timestamp_fim`
=================  ============================  =======================================
``PREEMP_INI``     linha nova, `SUCESSO`         no `PREEMP_FIM` do mesmo VE, ou no
                                                 `FILA` dele (interrompido)
``RENOVADO``       linha nova, `SUCESSO`         junto com o `PREEMP_INI` do episódio
``FILA``           linha nova, `CONFLITO_ADIADO` quando sai da fila: atendido, deslocado
                                                 ou descartado pelo teto
``DESCARTADO``     linha nova, `FALHA`           o próprio instante
``TIMEOUT``        —                             o episódio em curso termina `TIMEOUT`
``BOOT``           —                             tudo o que estava aberto termina
                                                 `FALHA` (o UNO reiniciou)
``RECUSADO``       —                             (só o evento no WebSocket)
=================  ============================  =======================================

A aproximação vai em `motivo`, e `fase_aplicada` fica nula (decisão de
2026-10-05): a emergência abre o verde de **uma** aproximação, que não é fase do
ciclo, e `fase_aplicada` continua significando índice de `fase_semaforo`.

`id_correlacao` nasce em cada evento de decisão, que é a "detecção" da bancada
(uma por linha recebida pelo UNO, `context/05` §4.2), e segue até a amostra de
H3 em `metrica_latencia`, ligada à linha do `PREEMP_INI` pelo carimbo.

**A identidade do VE na bancada é (rua, tipo).** Dois veículos do mesmo tipo na
mesma rua são indistinguíveis, limitação já declarada em `context/05` §3.3.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

import httpx
import structlog
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.configuracao import CODIGO_BANCADA
from app.models import LogPrioridade, MetricaLatencia, StatusExecucao
from app.repositories import operacao
from app.repositories.cadastro import buscar_semaforo_por_codigo
from app.services.difusao import Difusor

log = structlog.get_logger(__name__)

#: Quanto `motivo` comporta (`log_prioridade.motivo VARCHAR(200)`).
TAMANHO_MOTIVO: Final = 200

#: Quantos `PREEMP_INI` lembrar para ligar a amostra de H3 que chega depois.
INIS_LEMBRADOS: Final = 200

Ve = tuple[int, str]


# ---------------------------------------------------------------------------
# O que vem da ponte (o JSON de `GET /estado`, já interpretado)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EventoBancada:
    recebido_em: datetime
    t_dispositivo_ms: int
    tipo: str
    rua: int | None = None
    veiculo: str | None = None

    @classmethod
    def do_json(cls, dados: dict[str, Any]) -> EventoBancada:
        return cls(
            recebido_em=datetime.fromisoformat(dados["recebido_em"]),
            t_dispositivo_ms=int(dados["t_dispositivo_ms"]),
            tipo=str(dados["tipo"]),
            rua=dados.get("rua"),
            veiculo=dados.get("veiculo"),
        )


@dataclass(frozen=True)
class AmostraBancada:
    t_deteccao: datetime
    t_atuacao: datetime
    latencia_total_ms: float
    rua: int
    veiculo: str

    @classmethod
    def do_json(cls, dados: dict[str, Any]) -> AmostraBancada:
        return cls(
            t_deteccao=datetime.fromisoformat(dados["t_deteccao"]),
            t_atuacao=datetime.fromisoformat(dados["t_atuacao"]),
            latencia_total_ms=float(dados["latencia_total_ms"]),
            rua=int(dados["rua"]),
            veiculo=str(dados["veiculo"]),
        )


# ---------------------------------------------------------------------------
# O que o tradutor manda gravar
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InserirLog:
    """Linha nova em `log_prioridade`; `chave` é local ao tradutor."""

    chave: int
    id_correlacao: uuid.UUID
    timestamp_inicio: datetime
    status: StatusExecucao
    motivo: str
    timestamp_fim: datetime | None = None


@dataclass(frozen=True)
class EncerrarLog:
    """Fecha a linha `chave`; `status` e `motivo`, se vierem, substituem os dela."""

    chave: int
    timestamp_fim: datetime
    status: StatusExecucao | None = None
    motivo: str | None = None


@dataclass(frozen=True)
class InserirLatencia:
    """Uma amostra de H3 em `metrica_latencia`, com `t_decisao` nulo."""

    id_correlacao: uuid.UUID
    chave_log: int | None
    t_deteccao: datetime
    t_atuacao: datetime


Operacao = InserirLog | EncerrarLog | InserirLatencia


def _aproximacao(rua: int) -> str:
    return f"S{rua} (RUA{rua})"


def _juntar(motivo: str, sufixo: str) -> str:
    return f"{motivo}; {sufixo}"[:TAMANHO_MOTIVO]


@dataclass
class TradutorBancada:
    """Eventos do UNO → operações de gravação. Puro: não toca banco nem rede.

    `novo_id` existe para os testes fixarem os `id_correlacao`.
    """

    novo_id: Callable[[], uuid.UUID] = uuid.uuid4
    _proxima: int = 0
    _motivos: dict[int, str] = field(default_factory=dict)
    _correlacao: dict[int, uuid.UUID] = field(default_factory=dict)
    # Linhas abertas do VE atendido (o PREEMP_INI e os RENOVADO). Pode haver
    # dois por um instante: o novo PREEMP_INI sai antes do FILA do interrompido.
    _episodios: dict[Ve, list[int]] = field(default_factory=dict)
    _fila: tuple[Ve, int] | None = None
    _deslocado: tuple[Ve, int] | None = None
    _teto: bool = False
    _acabou_de_encerrar: bool = False
    _inis: deque[tuple[datetime, int]] = field(default_factory=lambda: deque(maxlen=INIS_LEMBRADOS))

    def traduzir(self, evento: EventoBancada) -> list[Operacao]:
        """As gravações que um evento do UNO implica."""
        acabou_de_encerrar, self._acabou_de_encerrar = self._acabou_de_encerrar, False
        t = evento.recebido_em
        if evento.tipo == "BOOT":
            return self._reinicio(t)
        if evento.tipo == "TIMEOUT":
            self._teto = True
            return self._tirar_da_fila("fila descartada pelo teto de 30 s (TIMEOUT)", t)
        if evento.rua is None or evento.veiculo is None:
            return []  # RECUSADO: não há VE a registrar
        ve: Ve = (evento.rua, evento.veiculo)
        if evento.tipo == "PREEMP_INI":
            return self._inicio(ve, t, vindo_da_fila=acabou_de_encerrar)
        if evento.tipo == "RENOVADO":
            return self._renovado(ve, t)
        if evento.tipo == "FILA":
            return self._fila_nova(ve, t)
        if evento.tipo == "DESCARTADO":
            return self._descartado(ve, t)
        if evento.tipo == "PREEMP_FIM":
            self._acabou_de_encerrar = True
            return self._fim(ve, t)
        return []

    def amostra(self, amostra: AmostraBancada) -> InserirLatencia:
        """A latência de H3, ligada à linha do `PREEMP_INI` do mesmo carimbo."""
        chave = next((c for quando, c in self._inis if quando == amostra.t_atuacao), None)
        return InserirLatencia(
            id_correlacao=self._correlacao[chave] if chave is not None else self.novo_id(),
            chave_log=chave,
            t_deteccao=amostra.t_deteccao,
            t_atuacao=amostra.t_atuacao,
        )

    # -- regras ---------------------------------------------------------------

    def _inserir(
        self, t: datetime, status: StatusExecucao, motivo: str, *, fim: datetime | None = None
    ) -> InserirLog:
        chave, self._proxima = self._proxima, self._proxima + 1
        id_correlacao = self.novo_id()
        self._motivos[chave] = motivo[:TAMANHO_MOTIVO]
        self._correlacao[chave] = id_correlacao
        return InserirLog(chave, id_correlacao, t, status, motivo[:TAMANHO_MOTIVO], fim)

    def _encerrar(
        self,
        chave: int,
        t: datetime,
        sufixo: str | None = None,
        status: StatusExecucao | None = None,
    ) -> EncerrarLog:
        motivo = None if sufixo is None else _juntar(self._motivos[chave], sufixo)
        return EncerrarLog(chave, t, status, motivo)

    def _inicio(self, ve: Ve, t: datetime, *, vindo_da_fila: bool) -> list[Operacao]:
        operacoes: list[Operacao] = []
        if vindo_da_fila and self._fila is not None and self._fila[0] == ve:
            operacoes.append(self._encerrar(self._fila[1], t, "atendido ao sair da fila"))
            self._fila = None
        for chave in self._episodios.pop(ve, []):  # não deveria haver; fecha por segurança
            operacoes.append(self._encerrar(chave, t))
        rua, veiculo = ve
        nova = self._inserir(
            t,
            StatusExecucao.SUCESSO,
            f"Bancada: PREEMP_INI — verde exclusivo {_aproximacao(rua)} para {veiculo}, "
            "decidido pelo UNO",
        )
        self._episodios[ve] = [nova.chave]
        self._inis.append((t, nova.chave))
        return [*operacoes, nova]

    def _renovado(self, ve: Ve, t: datetime) -> list[Operacao]:
        rua, veiculo = ve
        nova = self._inserir(
            t,
            StatusExecucao.SUCESSO,
            f"Bancada: RENOVADO — {veiculo} releu RUA{rua}; o verde de S{rua} recomeça",
        )
        self._episodios.setdefault(ve, []).append(nova.chave)
        return [nova]

    def _fila_nova(self, ve: Ve, t: datetime) -> list[Operacao]:
        rua, veiculo = ve
        operacoes: list[Operacao] = [
            self._encerrar(chave, t, "interrompido por VE de prioridade maior")
            for chave in self._episodios.pop(ve, [])
        ]
        if self._fila is not None:
            self._deslocado = self._fila
        nova = self._inserir(
            t,
            StatusExecucao.CONFLITO_ADIADO,
            f"Bancada: FILA — {veiculo} na RUA{rua} aguarda VE de prioridade maior",
        )
        self._fila = (ve, nova.chave)
        return [*operacoes, nova]

    def _descartado(self, ve: Ve, t: datetime) -> list[Operacao]:
        rua, veiculo = ve
        operacoes: list[Operacao] = []
        if self._deslocado is not None and self._deslocado[0] == ve:
            operacoes.append(self._encerrar(self._deslocado[1], t, "deslocado da fila"))
            self._deslocado = None
            motivo = f"Bancada: DESCARTADO — {veiculo} na RUA{rua} perdeu o lugar na fila"
        else:
            motivo = f"Bancada: DESCARTADO — {veiculo} na RUA{rua} sem lugar na fila"
        return [*operacoes, self._inserir(t, StatusExecucao.FALHA, motivo, fim=t)]

    def _fim(self, ve: Ve, t: datetime) -> list[Operacao]:
        teto, self._teto = self._teto, False
        return [
            self._encerrar(chave, t, "encerrado pelo teto de 30 s", StatusExecucao.TIMEOUT)
            if teto
            else self._encerrar(chave, t)
            for chave in self._episodios.pop(ve, [])
        ]

    def _tirar_da_fila(self, sufixo: str, t: datetime) -> list[Operacao]:
        if self._fila is None:
            return []
        chave = self._fila[1]
        self._fila = None
        return [self._encerrar(chave, t, sufixo)]

    def _reinicio(self, t: datetime) -> list[Operacao]:
        abertas = [chave for chaves in self._episodios.values() for chave in chaves]
        abertas += [par[1] for par in (self._fila, self._deslocado) if par is not None]
        self._episodios.clear()
        self._fila = self._deslocado = None
        self._teto = False
        return [
            self._encerrar(chave, t, "interrompido pelo reinício do UNO", StatusExecucao.FALHA)
            for chave in abertas
        ]


# ---------------------------------------------------------------------------
# Gravação
# ---------------------------------------------------------------------------


@dataclass
class GravadorBancada:
    """Aplica as operações do tradutor no banco. Síncrono: roda numa thread."""

    fabrica: sessionmaker[Session]
    _ids: dict[int, int] = field(default_factory=dict)
    _id_semaforo: int | None = None

    def marcas(self) -> tuple[datetime | None, datetime | None]:
        """O último evento e a última amostra já gravados, para não regravar.

        Ao subir, o backend relê o histórico da ponte (até 100 eventos). Sem as
        marcas, cada reinício do backend duplicaria as linhas daquele histórico.
        """
        with self.fabrica() as sessao:
            id_semaforo = self._semaforo(sessao)
            ultimo_log = sessao.scalar(
                select(func.max(LogPrioridade.timestamp_inicio)).where(
                    LogPrioridade.fk_semaforo == id_semaforo, LogPrioridade.fk_execucao.is_(None)
                )
            )
            ultima_amostra = sessao.scalar(
                select(func.max(MetricaLatencia.t_atuacao)).where(
                    MetricaLatencia.ambiente == "HARDWARE"
                )
            )
        return ultimo_log, ultima_amostra

    def gravar(self, operacoes: Sequence[Operacao]) -> None:
        if not operacoes:
            return
        with self.fabrica() as sessao, sessao.begin():
            id_semaforo = self._semaforo(sessao)
            for op in operacoes:
                self._aplicar(sessao, op, id_semaforo)

    def _semaforo(self, sessao: Session) -> int:
        if self._id_semaforo is None:
            semaforo = buscar_semaforo_por_codigo(sessao, CODIGO_BANCADA)
            if semaforo is None:
                raise LookupError(f"{CODIGO_BANCADA} não está cadastrado; rode os seeds")
            self._id_semaforo = semaforo.id_semaforo
        return self._id_semaforo

    def _aplicar(self, sessao: Session, op: Operacao, id_semaforo: int) -> None:
        if isinstance(op, InserirLog):
            linha = operacao.registrar_log_prioridade(
                sessao,
                id_correlacao=op.id_correlacao,
                fk_semaforo=id_semaforo,
                timestamp_inicio=op.timestamp_inicio,
                timestamp_fim=op.timestamp_fim,
                status_execucao=op.status,
                motivo=op.motivo,
            )
            self._ids[op.chave] = linha.id_log
        elif isinstance(op, EncerrarLog):
            id_log = self._ids.get(op.chave)
            if id_log is None:
                return  # aberta antes de o backend subir; o fim fica sem dono
            valores: dict[str, Any] = {"timestamp_fim": op.timestamp_fim}
            if op.status is not None:
                valores["status_execucao"] = op.status
            if op.motivo is not None:
                valores["motivo"] = op.motivo
            sessao.execute(
                update(LogPrioridade).where(LogPrioridade.id_log == id_log).values(**valores)
            )
        else:
            operacao.registrar_latencia(
                sessao,
                id_correlacao=op.id_correlacao,
                fk_log=None if op.chave_log is None else self._ids.get(op.chave_log),
                t_deteccao=op.t_deteccao,
                t_decisao=None,
                t_atuacao=op.t_atuacao,
                ambiente="HARDWARE",
            )


# ---------------------------------------------------------------------------
# Leitura da ponte
# ---------------------------------------------------------------------------


def texto_do_evento(evento: EventoBancada) -> str:
    """A linha que o dashboard mostra para um evento do UNO."""
    if evento.rua is None or evento.veiculo is None:
        return {
            "BOOT": "UNO reiniciado; volta pelo all-red",
            "TIMEOUT": "Teto de 30 s de emergência; a fila é descartada",
            "RECUSADO": "Linha inválida recusada pelo UNO",
        }.get(evento.tipo, evento.tipo)
    return f"{evento.tipo} — {evento.veiculo} na Rua {evento.rua} ({CODIGO_BANCADA})"


def estado_do_semaforo(telemetria: dict[str, Any]) -> dict[str, Any]:
    """`estado_semaforo` do WebSocket para a bancada.

    O contrato tem uma fase e um estado por cruzamento, e a bancada tem quatro
    aproximações. `aproximacoes` leva as quatro cores (S1 S2 S3 S4); `fase` é o
    eixo do ciclo que está aberto (1 principal, 2 transversal), nula em
    emergência e no all-red; `estado` é a cor mais "aberta" do cruzamento.
    """
    cores: str = telemetria["cores"]
    abertas = [i for i, cor in enumerate(cores) if cor != "R"]
    emergencia = telemetria["regime"] == "E"
    fase: int | None = None
    if abertas and not emergencia:
        fase = 1 if abertas[0] < 2 else 2  # S1/S2 no eixo principal, S3/S4 no transversal
    estado = "VERMELHO"
    if "G" in cores:
        estado = "VERDE"
    elif "Y" in cores:
        estado = "AMARELO"
    return {
        "id": CODIGO_BANCADA,
        "fase": fase,
        "estado": estado,
        "em_preempcao": emergencia,
        "aproximacoes": cores,
        "regime": telemetria["regime"],
        "rua_ativa": telemetria["rua_ativa"],
        "rua_fila": telemetria["rua_fila"],
        "recebido_em": telemetria["recebida_em"],
    }


class PonteIndisponivelError(RuntimeError):
    """A ponte não respondeu ou não está configurada."""


@dataclass
class LeitorPonte:
    """Lê `GET /estado` a 5 Hz, grava o que é novo e alimenta o WebSocket.

    Args:
        cliente: Cliente HTTP já apontado para a ponte (`base_url`).
        difusor: Destino do WebSocket.
        gravador: `None` quando não há banco: o WebSocket continua funcionando.
        intervalo_s: Período da leitura.
        tradutor: Injetável nos testes.
    """

    cliente: httpx.AsyncClient
    difusor: Difusor
    gravador: GravadorBancada | None = None
    intervalo_s: float = 0.2
    tradutor: TradutorBancada = field(default_factory=TradutorBancada)
    disponivel: bool = False
    ultimo_estado: dict[str, Any] | None = None
    ultima_leitura: datetime | None = None
    falhas_de_gravacao: int = 0
    _marca_evento: datetime | None = None
    _marca_amostra: datetime | None = None
    _marcas_lidas: bool = False
    _ultima_publicada: str | None = None
    _parar: asyncio.Event = field(default_factory=asyncio.Event)

    async def rodar(self) -> None:
        """Até `parar()`. Ponte fora do ar não derruba o backend: espera e tenta de novo."""
        while not self._parar.is_set():
            espera = self.intervalo_s
            try:
                await self.ler_uma_vez()
            except httpx.HTTPError as erro:
                if self.disponivel:
                    log.warning("ponte_indisponivel", erro=type(erro).__name__)
                self.disponivel = False
                espera = max(self.intervalo_s, 1.0)
            except Exception:
                log.exception("leitura_da_ponte_falhou")
                espera = max(self.intervalo_s, 1.0)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._parar.wait(), espera)

    def parar(self) -> None:
        self._parar.set()

    async def ler_uma_vez(self) -> None:
        resposta = await self.cliente.get("/estado", timeout=2.0)
        resposta.raise_for_status()
        corpo: dict[str, Any] = resposta.json()
        if not self.disponivel:
            log.info("ponte_disponivel")
        self.disponivel = True
        self.ultimo_estado = corpo
        self.ultima_leitura = datetime.now(UTC)
        await self._marcas()

        eventos = [EventoBancada.do_json(ev) for ev in corpo.get("eventos", [])]
        novos = [
            ev
            for ev in eventos
            if self._marca_evento is None or ev.recebido_em > self._marca_evento
        ]
        amostras = [AmostraBancada.do_json(a) for a in corpo.get("amostras_h3", [])]
        novas = [
            a for a in amostras if self._marca_amostra is None or a.t_atuacao > self._marca_amostra
        ]

        operacoes: list[Operacao] = []
        for evento in novos:
            operacoes += self.tradutor.traduzir(evento)
            self.difusor.publicar_evento(
                {
                    "nivel": "WARNING" if evento.tipo in {"TIMEOUT", "RECUSADO"} else "INFO",
                    "texto": texto_do_evento(evento),
                    "origem": "BANCADA",
                    "tipo": evento.tipo,
                    "rua": evento.rua,
                    "veiculo": evento.veiculo,
                    "recebido_em": evento.recebido_em.isoformat(),
                }
            )
        operacoes += [self.tradutor.amostra(amostra) for amostra in novas]
        if novos:
            self._marca_evento = novos[-1].recebido_em
        if novas:
            self._marca_amostra = novas[-1].t_atuacao
        await self._gravar(operacoes)

        telemetria = corpo.get("telemetria")
        if telemetria is not None and telemetria["recebida_em"] != self._ultima_publicada:
            # Só a telemetria nova: republicar a mesma a 5 Hz não informa nada, e
            # o dashboard a veria como "atualizada agora" sem ser.
            self._ultima_publicada = telemetria["recebida_em"]
            estado = estado_do_semaforo(telemetria)
            self.difusor.publicar_estado("estado_semaforo", CODIGO_BANCADA, estado)
            self.difusor.publicar_estado(
                "metrica",
                CODIGO_BANCADA,
                {
                    "origem": "BANCADA",
                    "latencia_ms": amostras[-1].latencia_total_ms if amostras else None,
                    "priorizacoes_ativas": 1 if estado["em_preempcao"] else 0,
                },
            )

    async def injetar(self, rua: int, veiculo: str) -> httpx.Response:
        """`POST /injecao` da ponte: a preempção manual da bancada."""
        return await self.cliente.post(
            "/injecao", json={"rua": rua, "veiculo": veiculo}, timeout=5.0
        )

    async def _marcas(self) -> None:
        if self._marcas_lidas:
            return
        if self.gravador is None:
            # Sem banco não há o que duplicar; o histórico da ponte é só o que
            # aconteceu antes de o backend subir, e não vira evento novo.
            agora = datetime.now(UTC)
            self._marca_evento = self._marca_amostra = agora
        else:
            # Se o banco falhar aqui, a exceção sobe e a leitura inteira é
            # refeita no próximo ciclo: processar sem as marcas regravaria o
            # histórico da ponte.
            self._marca_evento, self._marca_amostra = await asyncio.to_thread(self.gravador.marcas)
        self._marcas_lidas = True

    async def _gravar(self, operacoes: Iterable[Operacao]) -> None:
        lista = list(operacoes)
        if self.gravador is None or not lista:
            return
        try:
            await asyncio.to_thread(self.gravador.gravar, lista)
        except Exception:
            self.falhas_de_gravacao += 1
            log.exception("gravacao_da_bancada_falhou", operacoes=len(lista))
