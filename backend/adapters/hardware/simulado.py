"""Dublê do Arduino UNO — entrega 5.2, `context/05` §8.

Responde ao protocolo serial em memória, com latência artificial, para que o
trio desenvolva a ponte e o backend sem a bancada na mesa.

Duas camadas:

* `UnoSimulado` — o firmware, **puro e determinístico**: recebe linhas e o
  instante atual, devolve as linhas que o UNO enviaria. Sem relógio próprio,
  sem asyncio; é o que os testes exercitam.
* `TransporteSimulado` — a mesma interface de `bridge/transporte.py` que a porta
  serial real implementa, com relógio de verdade e latência artificial.

**O semáforo não é reimplementado aqui.** A sinalização vem da máquina de
estados de `core/priorizacao/fases.py`, que foi escrita como modelo executável
do que o firmware precisa fazer e é o alvo dos testes de I1 a I4. Este módulo só
acrescenta o que é do firmware e não do controlador: ACK/NAK, eventos,
telemetria a 2 Hz, watchdog (I6), modo de teste e parada segura.

Onde o firmware precisa se afastar daquela máquina, o afastamento está aqui e
declarado, porque vira requisito do firmware real (5.3):

1. **`PRE` é aceito também durante amarelo e all-red.** A máquina do core
   recusa `IR_PARA_FASE` em transição e conta com o motor reemitindo a cada
   passo de 0,1 s; na bancada o pedido chega uma vez. Recusar levaria o pior
   caso a 9 s (amarelo + all-red + verde mínimo da fase seguinte + amarelo +
   all-red), contra os **6 s** que o contrato §7 promete. A transição em curso
   não muda: só o destino dela.
2. **`PRE,<fase>,<dur_s>` termina sozinho.** O verde da fase alvo vale até
   `dur_s` contados do recebimento (com o verde mínimo como piso) e, quando ele
   acaba, a preempção acaba junto, com `EV,PREEMP_FIM`. No SUMO o motor manda
   `LIBERAR` quando vê o VE cruzar; na bancada não há como ver isso.
3. **O UNO liga em all-red** e só então abre a fase 1. A máquina do core parte
   da fase 1 em verde, o que na placa seria acender um verde no reset.

**Nenhum número produzido com este dublê é dado experimental.** A latência é
arbitrária e o tempo é o do relógio do notebook; H3 se mede na bancada
(`context/00` §5). Usar `TransporteSimulado` numa medição de latência mediria a
constante que alguém digitou.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Sequence
from dataclasses import replace
from enum import StrEnum
from typing import Final

from bridge.protocolo import (
    N_SEMAFOROS,
    Ack,
    ComandoSerial,
    Cor,
    Evento,
    LinhaInvalidaError,
    MotivoNak,
    Nak,
    NomeComando,
    Telemetria,
    TipoEvento,
    interpretar_comando,
)
from bridge.transporte import ConexaoPerdidaError
from core.comandos import Comando, TipoComando, fallback_seguro
from core.malha import Cruzamento, Fase
from core.modelos import Sinal
from core.parametros import Parametros
from core.priorizacao.fases import EstadoControlador, avancar, estado_inicial

#: Contrato §7, requisito 6: telemetria a 2 Hz.
PERIODO_TELEMETRIA_S: Final = 0.5

#: O cruzamento único da bancada, como em `db/seeds/dados.yaml`.
ID_CRUZAMENTO: Final = "PROTO_CRUZ_01"

#: Latência padrão entre receber um comando e responder. **Arbitrária**: existe
#: para que a ponte não seja testada só contra respostas instantâneas.
LATENCIA_PADRAO_S: Final = 0.005

#: A máquina do core marca preempção quando há um VE associado. A linha serial
#: não diz qual VE é — só o backend sabe —, então o dublê usa este marcador.
_VE_SERIAL: Final = "VE_SERIAL"

_COR_DO_SINAL: Final = {
    Sinal.VERDE: Cor.VERDE,
    Sinal.AMARELO: Cor.AMARELO,
    Sinal.VERMELHO: Cor.VERMELHO,
}

_TODOS_VERMELHOS: Final = (Cor.VERMELHO,) * N_SEMAFOROS


class Regime(StrEnum):
    """Em que regime o UNO está. Os três nunca coexistem."""

    NORMAL = "NORMAL"  # ciclo fixo, com ou sem preempção
    TESTE = "TESTE"  # TESTMODE,1: ciclo suspenso, cores pelo comando TEST
    PARADA = "PARADA"  # SAFE: todos em vermelho, até CLR ou watchdog


def cruzamento_da_bancada(verde_s: float, parametros: Parametros) -> Cruzamento:
    """As quatro fases de *split phasing* do protótipo (P13).

    A matriz de conflito fica no padrão do `Cruzamento`, que é total — toda fase
    conflita com todas —, e é exatamente o regime da bancada.
    """
    return Cruzamento(
        id=ID_CRUZAMENTO,
        fases=tuple(
            Fase(
                indice=indice,
                descricao=f"S{indice}",
                movimentos=frozenset({(f"S{indice}_ENTRADA", f"S{indice}_SAIDA")}),
                duracao_base_s=verde_s,
                verde_min_s=parametros.verde_min_s,
                verde_max_s=parametros.verde_max_s,
            )
            for indice in range(1, N_SEMAFOROS + 1)
        ),
    )


class UnoSimulado:
    """O firmware do UNO, em Python, dirigido por tempo injetado.

    Args:
        parametros: Perfil `hardware` (`parametros.hardware.yaml`).
        verde_s: Duração do verde de cada fase no ciclo fixo. Não faz parte de
            `Parametros` porque no perfil de simulação a duração vem da rede.
        t_s: Instante do boot, em segundos, no relógio de quem dirige.
    """

    def __init__(self, parametros: Parametros, verde_s: float, t_s: float = 0.0) -> None:
        self._parametros = parametros
        self._cruzamento = cruzamento_da_bancada(verde_s, parametros)
        self._t0_s = t_s
        self._t_s = t_s
        ultima = self._cruzamento.indices_de_fase[-1]
        # Liga em all-red "depois" da última fase, para que a primeira a abrir
        # seja a fase 1 — e nenhum verde acenda no reset.
        self._estado: EstadoControlador = replace(
            estado_inicial(ID_CRUZAMENTO, self._cruzamento, t_s),
            fase_corrente=ultima,
            sinal=Sinal.VERMELHO,
            t_ultimo_verde={},
        )
        self._regime = Regime.NORMAL
        self._cores_teste: tuple[Cor, Cor, Cor, Cor] = _TODOS_VERMELHOS
        self._t_ultimo_comando_s = t_s
        self._proxima_telemetria_s = t_s
        self._fase_preemptada: int | None = None
        self._preempcao_ate_s: float | None = None

    # -- leitura do estado -----------------------------------------------------

    @property
    def regime(self) -> Regime:
        return self._regime

    @property
    def em_preempcao(self) -> bool:
        """Há preempção em curso, em transição ou já com o verde aceso."""
        return self._fase_preemptada is not None

    @property
    def t_dispositivo_ms(self) -> int:
        """O `millis()` da placa: tempo desde o boot."""
        return int((self._t_s - self._t0_s) * 1000)

    def cores(self) -> tuple[Cor, Cor, Cor, Cor]:
        """O que cada módulo exibe agora, na ordem S1 S2 S3 S4."""
        if self._regime is Regime.TESTE:
            return self._cores_teste
        s1, s2, s3, s4 = (
            _COR_DO_SINAL[self._estado.sinal]
            if indice == self._estado.fase_corrente
            else Cor.VERMELHO
            for indice in self._cruzamento.indices_de_fase
        )
        return (s1, s2, s3, s4)

    def telemetria(self) -> Telemetria:
        """A linha `ST` deste instante."""
        verde_preemptado = (
            self._fase_preemptada is not None
            and self._estado.sinal is Sinal.VERDE
            and self._estado.fase_corrente == self._fase_preemptada
        )
        return Telemetria(
            t_dispositivo_ms=self.t_dispositivo_ms,
            fase=self._estado.fase_corrente,
            cores=self.cores(),
            em_preempcao=verde_preemptado,
            em_teste=self._regime is Regime.TESTE,
        )

    # -- entrada ---------------------------------------------------------------

    def avancar(self, t_s: float) -> list[bytes]:
        """Faz o tempo passar até `t_s`; devolve o que o UNO enviou nesse meio.

        Raises:
            ValueError: se `t_s` for anterior ao instante atual.
        """
        if t_s < self._t_s:
            raise ValueError(f"o tempo não volta: {t_s} < {self._t_s}")
        self._t_s = t_s
        saida: list[bytes] = []

        if self._sob_watchdog() and t_s - self._t_ultimo_comando_s >= self._parametros.watchdog_s:
            saida.append(self._evento(TipoEvento.WATCHDOG))
            saida += self._voltar_ao_ciclo_fixo(t_s)
            self._t_ultimo_comando_s = t_s

        if self._regime is Regime.NORMAL:
            saida += self._passo(t_s)
        elif self._regime is Regime.PARADA and self._estado.sinal is not Sinal.VERMELHO:
            # Termina o verde (respeitando o mínimo) e o amarelo; no all-red, para.
            saida += self._passo(t_s)

        if t_s >= self._proxima_telemetria_s:
            saida.append(self.telemetria().codificar())
            while self._proxima_telemetria_s <= t_s:
                self._proxima_telemetria_s += PERIODO_TELEMETRIA_S
        return saida

    def receber(self, linha: bytes, t_s: float) -> list[bytes]:
        """Processa uma linha do host chegada em `t_s`.

        Linha malformada com nome de comando reconhecível recebe
        `NAK,<comando>,FORMATO`; lixo sem nome reconhecível é ignorado, como
        ruído. Nenhuma das duas alimenta o watchdog: só comando válido prova que
        o host está vivo.
        """
        saida = self.avancar(t_s)
        try:
            comando = interpretar_comando(linha)
        except LinhaInvalidaError:
            nome = _nome_do_comando(linha)
            if nome is not None:
                saida.append(Nak(nome, MotivoNak.FORMATO).codificar())
            return saida
        self._t_ultimo_comando_s = t_s
        return saida + self._executar(comando, t_s)

    # -- comandos --------------------------------------------------------------

    def _executar(self, comando: ComandoSerial, t_s: float) -> list[bytes]:
        argumentos = comando.argumentos
        match comando.nome:
            case NomeComando.PING:
                return [Ack(NomeComando.PING).codificar()]
            case NomeComando.CONSULTA:
                return [self.telemetria().codificar()]
            case NomeComando.PRE:
                return self._pre(int(argumentos[0]), int(argumentos[1]), t_s)
            case NomeComando.CLR:
                return self._clr(t_s)
            case NomeComando.CFG:
                verde, amarelo, all_red = (float(a) for a in argumentos)
                return self._cfg(verde, amarelo, all_red)
            case NomeComando.SAFE:
                return self._safe(t_s)
            case NomeComando.TESTMODE:
                return self._testmode(argumentos[0] == "1", t_s)
            case NomeComando.TEST:
                return self._test(argumentos[0])

    def _pre(self, fase: int, duracao_s: int, t_s: float) -> list[bytes]:
        if self._regime is not Regime.NORMAL:
            return [Nak(NomeComando.PRE, MotivoNak.MODO).codificar()]
        if fase not in self._cruzamento.indices_de_fase:
            return [Nak(NomeComando.PRE, MotivoNak.FASE_INVALIDA).codificar()]

        nova = self._fase_preemptada is None
        self._fase_preemptada = fase
        self._preempcao_ate_s = t_s + duracao_s
        saida = [Ack(NomeComando.PRE).codificar()]
        if nova:
            saida.append(self._evento(TipoEvento.PREEMP_INI))

        estado = self._estado
        if estado.sinal is Sinal.VERDE and estado.fase_corrente == fase:
            saida += self._passo(t_s, (self._estender(duracao_s),))
        elif estado.sinal is Sinal.VERDE:
            ir = Comando(
                TipoComando.IR_PARA_FASE,
                ID_CRUZAMENTO,
                fase_alvo=fase,
                duracao_s=duracao_s,
                id_veiculo=_VE_SERIAL,
                motivo=f"PRE,{fase},{duracao_s} pela serial",
            )
            saida += self._passo(t_s, (ir,))
        else:
            # Amarelo ou all-red: só o destino da transição em curso muda
            # (afastamento 1 da docstring do módulo).
            self._estado = replace(
                estado,
                fase_alvo=fase,
                em_preempcao=True,
                t_inicio_preempcao=estado.t_inicio_preempcao if estado.em_preempcao else t_s,
                id_veiculo=_VE_SERIAL,
            )
        return saida

    def _clr(self, t_s: float) -> list[bytes]:
        if self._regime is Regime.PARADA:
            self._regime = Regime.NORMAL
            return [Ack(NomeComando.CLR).codificar()]
        if self._regime is Regime.NORMAL and self._fase_preemptada is not None:
            return [Ack(NomeComando.CLR).codificar(), *self._encerrar_preempcao(t_s)]
        return [Nak(NomeComando.CLR, MotivoNak.MODO).codificar()]

    def _cfg(self, verde_s: float, amarelo_s: float, all_red_s: float) -> list[bytes]:
        if self._regime is not Regime.NORMAL or self._fase_preemptada is not None:
            return [Nak(NomeComando.CFG, MotivoNak.MODO).codificar()]
        if verde_s < self._parametros.verde_min_s:
            # Um verde de ciclo abaixo do mínimo seria I4 violado por construção.
            return [Nak(NomeComando.CFG, MotivoNak.VERDE_MIN).codificar()]
        self._parametros = replace(self._parametros, amarelo_s=amarelo_s, all_red_s=all_red_s)
        self._cruzamento = cruzamento_da_bancada(verde_s, self._parametros)
        return [Ack(NomeComando.CFG).codificar()]

    def _safe(self, t_s: float) -> list[bytes]:
        saida = [Ack(NomeComando.SAFE).codificar()]
        if self._regime is Regime.TESTE:
            saida += self._sair_do_teste(t_s)
        elif self._regime is Regime.NORMAL and self._fase_preemptada is not None:
            saida += self._encerrar_preempcao(t_s)
        if self._estado.sinal is Sinal.VERDE:
            # Pede a troca para que o verde saia pelo amarelo, depois do mínimo.
            proxima = self._cruzamento.proxima_fase(self._estado.fase_corrente)
            self._estado = replace(self._estado, fase_alvo=proxima)
        self._regime = Regime.PARADA
        return saida

    def _testmode(self, ativo: bool, t_s: float) -> list[bytes]:
        if not ativo:
            if self._regime is not Regime.TESTE:
                return [Ack(NomeComando.TESTMODE).codificar()]
            return [Ack(NomeComando.TESTMODE).codificar(), *self._sair_do_teste(t_s)]
        if self._regime is Regime.TESTE:
            return [Ack(NomeComando.TESTMODE).codificar()]
        if self._regime is Regime.PARADA or self._fase_preemptada is not None:
            return [Nak(NomeComando.TESTMODE, MotivoNak.MODO).codificar()]
        self._regime = Regime.TESTE
        self._cores_teste = _TODOS_VERMELHOS
        return [Ack(NomeComando.TESTMODE).codificar(), self._evento(TipoEvento.TESTE_INI)]

    def _test(self, cores: str) -> list[bytes]:
        if self._regime is not Regime.TESTE:
            return [Nak(NomeComando.TEST, MotivoNak.MODO).codificar()]
        if cores.count(Cor.VERDE.value) > 1:
            # A guarda de I1 vale inclusive em modo de teste (contrato §6, regra 3).
            return [
                Nak(NomeComando.TEST, MotivoNak.CONFLITO).codificar(),
                self._evento(TipoEvento.CONFLITO_RECUSADO),
            ]
        s1, s2, s3, s4 = (Cor(c) for c in cores)
        self._cores_teste = (s1, s2, s3, s4)
        return [Ack(NomeComando.TEST).codificar()]

    # -- mecânica --------------------------------------------------------------

    def _passo(self, t_s: float, comandos: tuple[Comando, ...] = ()) -> list[bytes]:
        """Um passo da máquina do core, mais o que a preempção serial exige."""
        avanco = avancar(self._estado, t_s, self._cruzamento, self._parametros, comandos)
        self._estado = avanco.estado
        if self._fase_preemptada is None:
            return []

        if not self._estado.em_preempcao:
            # O core encerrou sozinho: timeout de E6 (PREEMP_MAX, contrato §7 req. 5).
            self._limpar_preempcao()
            return [self._evento(TipoEvento.TIMEOUT), self._evento(TipoEvento.PREEMP_FIM)]

        for transicao in avanco.transicoes:
            if transicao.fase != self._fase_preemptada:
                continue
            if transicao.sinal is Sinal.VERDE and self._preempcao_ate_s is not None:
                restante = self._preempcao_ate_s - t_s
                if restante > 0:
                    self._estado = avancar(
                        self._estado,
                        t_s,
                        self._cruzamento,
                        self._parametros,
                        (self._estender(restante),),
                    ).estado
            elif transicao.sinal is Sinal.AMARELO:
                # O verde da preempção acabou (afastamento 2 da docstring).
                self._limpar_preempcao()
                liberar = Comando(
                    TipoComando.LIBERAR, ID_CRUZAMENTO, motivo="dur_s do PRE esgotado"
                )
                self._estado = avancar(
                    self._estado, t_s, self._cruzamento, self._parametros, (liberar,)
                ).estado
                return [self._evento(TipoEvento.PREEMP_FIM)]
        return []

    def _estender(self, duracao_s: float) -> Comando:
        return Comando(
            TipoComando.ESTENDER_VERDE,
            ID_CRUZAMENTO,
            fase_alvo=self._fase_preemptada,
            duracao_s=duracao_s,
            id_veiculo=_VE_SERIAL,
            motivo="PRE pela serial",
        )

    def _encerrar_preempcao(self, t_s: float) -> list[bytes]:
        self._limpar_preempcao()
        self._passo(t_s, (fallback_seguro(ID_CRUZAMENTO, "fim da preempção serial"),))
        return [self._evento(TipoEvento.PREEMP_FIM)]

    def _limpar_preempcao(self) -> None:
        self._fase_preemptada = None
        self._preempcao_ate_s = None

    def _sair_do_teste(self, t_s: float) -> list[bytes]:
        # Recomeça pelo all-red: as cores do teste são arbitrárias, e o ciclo só
        # volta depois de o cruzamento estar limpo (I3).
        self._regime = Regime.NORMAL
        self._estado = replace(
            self._estado, sinal=Sinal.VERMELHO, t_mudanca=t_s, fase_alvo=None, verde_ate=None
        )
        return [self._evento(TipoEvento.TESTE_FIM)]

    def _voltar_ao_ciclo_fixo(self, t_s: float) -> list[bytes]:
        if self._regime is Regime.TESTE:
            return self._sair_do_teste(t_s)
        if self._regime is Regime.PARADA:
            self._regime = Regime.NORMAL
            return []
        return self._encerrar_preempcao(t_s)

    def _sob_watchdog(self) -> bool:
        """I6 vale em preempção, em teste e em parada — nunca no ciclo fixo."""
        return self._regime is not Regime.NORMAL or self._fase_preemptada is not None

    def _evento(self, tipo: TipoEvento) -> bytes:
        return Evento(self.t_dispositivo_ms, tipo).codificar()


def _nome_do_comando(linha: bytes) -> NomeComando | None:
    primeiro = linha.split(b",", 1)[0].strip()
    try:
        return NomeComando(primeiro.decode("ascii"))
    except (UnicodeDecodeError, ValueError):
        return None


def uno_da_bancada(t_s: float = 0.0) -> UnoSimulado:
    """Um `UnoSimulado` com o perfil `hardware` lido de `backend/config/`."""
    from adapters.configuracao import carregar_dicionario

    dados = carregar_dicionario("hardware")
    return UnoSimulado(Parametros.de_dicionario(dados), float(dados["verde_s"]), t_s)


class TransporteSimulado:
    """`Transporte` em memória, com o `UnoSimulado` do outro lado do "cabo".

    O UNO da bancada tem **fonte externa** neste modelo: `puxar_cabo()` corta a
    comunicação, mas a placa continua rodando — e o watchdog dispara, que é o
    passo 6 da demonstração (`context/05` §7). Abrir de novo **reinicia** a
    placa, como o DTR faz no UNO real.

    Args:
        fabrica: Cria o UNO no boot, a partir do instante do relógio.
        latencia_s: Atraso entre o comando sair e a resposta ser produzida.
            Arbitrária — ver a docstring do módulo.
        passo_s: De quanto em quanto tempo o relógio do UNO avança.
    """

    def __init__(
        self,
        fabrica: Callable[[float], UnoSimulado] = uno_da_bancada,
        *,
        latencia_s: float = LATENCIA_PADRAO_S,
        passo_s: float = 0.05,
    ) -> None:
        self._fabrica = fabrica
        self._latencia_s = latencia_s
        self._passo_s = passo_s
        self.uno: UnoSimulado | None = None
        self._fila: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._conectado = False
        self._relogio: asyncio.Task[None] | None = None

    @property
    def conectado(self) -> bool:
        return self._conectado

    async def abrir(self) -> None:
        await self._parar_relogio()
        self.uno = self._fabrica(self._agora())
        self._fila = asyncio.Queue()
        self._conectado = True
        self._relogio = asyncio.create_task(self._rodar_relogio())

    async def fechar(self) -> None:
        self._desconectar()
        await self._parar_relogio()

    async def escrever(self, linha: bytes) -> None:
        if not self._conectado:
            raise ConexaoPerdidaError("porta simulada fechada")
        asyncio.get_running_loop().call_later(self._latencia_s, self._entregar, linha)

    async def ler_linha(self) -> bytes:
        if not self._conectado:
            raise ConexaoPerdidaError("porta simulada fechada")
        linha = await self._fila.get()
        if linha is None:
            raise ConexaoPerdidaError("cabo puxado")
        return linha

    def puxar_cabo(self) -> None:
        """Corta a comunicação; o UNO segue rodando sozinho."""
        self._desconectar()

    # -- interno ---------------------------------------------------------------

    def _agora(self) -> float:
        return asyncio.get_running_loop().time()

    def _desconectar(self) -> None:
        if self._conectado:
            self._conectado = False
            self._fila.put_nowait(None)  # acorda quem está esperando em ler_linha

    def _entregar(self, linha: bytes) -> None:
        if self._conectado and self.uno is not None:
            self._publicar(self.uno.receber(linha, self._agora()))

    def _publicar(self, linhas: Sequence[bytes]) -> None:
        if self._conectado:
            for linha in linhas:
                self._fila.put_nowait(linha)

    async def _rodar_relogio(self) -> None:
        while self.uno is not None:
            self._publicar(self.uno.avancar(self._agora()))
            await asyncio.sleep(self._passo_s)

    async def _parar_relogio(self) -> None:
        if self._relogio is not None:
            self._relogio.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._relogio
            self._relogio = None
