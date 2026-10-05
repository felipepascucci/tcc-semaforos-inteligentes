"""Dublê do Arduino UNO da bancada — entrega 5.2, `context/05` §3, §4 e §8.

**É o modelo de referência do firmware (5.3).** O firmware se comporta como este
módulo, e o roteiro de aceitação (`bridge/verificar.py`) passa igual contra os
dois. Por isso a regra está escrita aqui por extenso, e não emprestada do motor:
desde 2026-10-05 o UNO decide sozinho, com a regra que a equipe de hardware já
tinha (prioridade por tipo, fila de um lugar, verde exclusivo), e essa regra não
é a de `core/priorizacao/`.

Duas camadas:

* `UnoSimulado` — o firmware, **puro e determinístico**: recebe linhas e o
  instante atual, devolve as linhas que o UNO escreveria. Sem relógio próprio,
  sem asyncio; é o que os testes exercitam.
* `TransporteSimulado` — a mesma interface de `bridge/transporte.py` que a porta
  serial real implementa, com relógio de verdade e latência artificial.

**Como as luzes andam.** Em vez de enumerar estados, o UNO persegue um
*destino*: o conjunto de aproximações que deve ficar verde (um eixo no ciclo, a
aproximação do VE na emergência). Quatro regras, aplicadas a cada instante até
nada mais mudar, levam qualquer estado ao destino sem violar I1 a I4:

1. verde fora do destino cumpre o verde mínimo e vai a amarelo (I4, I2);
2. amarelo cumpre o tempo dele e vai a vermelho (I2);
3. o destino só abre com **todas** as aproximações em vermelho há o all-red
   inteiro (I3) e passando pela guarda de I1;
4. nunca amarelo -> verde: um destino que muda no meio da troca espera o all-red.

A exceção é o destino já verde: a aproximação do VE que já está em verde fica
acesa, e só as outras saem (`context/05` §3.4, item 4).

**O tempo é exato.** `avancar()` processa cada mudança no instante em que ela
vence, não no passo de quem dirige, e o `<ms>` de cada linha é esse instante. A
sequência de `ST` (que sai a cada mudança de estado) é, portanto, a sequência
completa de transições, com tempos verificáveis.

**Nenhum número produzido com este dublê é dado experimental.** A latência é
arbitrária e o tempo é o do relógio do notebook; H3 se mede na bancada
(`context/05` §4.3).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from bridge.protocolo import (
    EIXO_DE,
    N_SEMAFOROS,
    Cor,
    Deteccao,
    Evento,
    LinhaInvalidaError,
    Regime,
    Telemetria,
    TipoEvento,
    interpretar_deteccao,
    parece_deteccao,
)
from bridge.transporte import ConexaoPerdidaError
from core.excecoes import ConfiguracaoInvalidaError
from core.modelos import TipoVeiculo

#: `context/05` §4.2: telemetria a 2 Hz, além da que sai a cada mudança.
PERIODO_TELEMETRIA_S: Final = 0.5

#: Latência padrão entre a linha sair da ponte e o UNO processá-la. **Arbitrária**:
#: existe para que a ponte não seja testada só contra respostas instantâneas.
LATENCIA_PADRAO_S: Final = 0.005

#: Folga de ponto flutuante nas comparações de tempo.
_EPS: Final = 1e-9

#: As aproximações de cada fase do ciclo: eixo principal e eixo transversal.
FASES_DO_CICLO: Final = (
    frozenset(i for i in range(N_SEMAFOROS) if EIXO_DE[i] == 0),
    frozenset(i for i in range(N_SEMAFOROS) if EIXO_DE[i] == 1),
)


class ViolacaoDeSegurancaError(AssertionError):
    """A guarda de I1 barrou um verde. No dublê, é defeito do modelo."""


@dataclass(frozen=True)
class ConfigBancada:
    """Os números da bancada, de `parametros.hardware.yaml` (`context/05` §3).

    Attributes:
        verde_s: Verde de cada fase no ciclo.
        verde_min_s: Piso de I4.
        amarelo_s: Duração do amarelo (I2).
        all_red_s: Duração do all-red (I3).
        teto_s: Teto da emergência contínua (I6, redefinido em 2026-10-05).
        prioridade: Tipos do mais ao menos prioritário.
        verde_por_tipo_s: Verde do VE, por tipo.
    """

    verde_s: float
    verde_min_s: float
    amarelo_s: float
    all_red_s: float
    teto_s: float
    prioridade: tuple[TipoVeiculo, ...]
    verde_por_tipo_s: Mapping[TipoVeiculo, float]

    @classmethod
    def de_dicionario(cls, dados: Mapping[str, Any]) -> ConfigBancada:
        """Monta a partir do perfil `hardware` já mesclado.

        Raises:
            ConfiguracaoInvalidaError: chave ausente ou valor incoerente.
        """
        try:
            config = cls(
                verde_s=float(dados["verde_s"]),
                verde_min_s=float(dados["verde_min_s"]),
                amarelo_s=float(dados["amarelo_s"]),
                all_red_s=float(dados["all_red_s"]),
                teto_s=float(dados["preempcao_timeout_s"]),
                prioridade=tuple(TipoVeiculo(t) for t in dados["prioridade_tipo"]),
                verde_por_tipo_s={
                    TipoVeiculo(t): float(s) for t, s in dados["verde_por_tipo_s"].items()
                },
            )
        except KeyError as erro:
            raise ConfiguracaoInvalidaError(f"perfil da bancada sem {erro}") from erro
        except ValueError as erro:
            raise ConfiguracaoInvalidaError(f"perfil da bancada inválido: {erro}") from erro
        config.validar()
        return config

    def validar(self) -> None:
        """Falha cedo com configuração que tornaria um invariante violável.

        Raises:
            ConfiguracaoInvalidaError: se algum tempo for incoerente.
        """
        if min(self.amarelo_s, self.all_red_s, self.verde_min_s) <= 0:
            raise ConfiguracaoInvalidaError("amarelo, all-red e verde mínimo precisam ser > 0")
        if self.verde_s < self.verde_min_s:
            raise ConfiguracaoInvalidaError("verde_s abaixo do verde mínimo violaria I4")
        if set(self.verde_por_tipo_s) != set(self.prioridade):
            raise ConfiguracaoInvalidaError("verde_por_tipo_s precisa cobrir todos os tipos")
        if min(self.verde_por_tipo_s.values()) < self.verde_min_s:
            raise ConfiguracaoInvalidaError("verde de VE abaixo do verde mínimo violaria I4")
        transicao = self.verde_min_s + self.amarelo_s + self.all_red_s
        if self.teto_s <= transicao + max(self.verde_por_tipo_s.values()):
            raise ConfiguracaoInvalidaError("o teto cortaria o verde de um VE recém-atendido")

    def nivel(self, tipo: TipoVeiculo) -> int:
        """Prioridade do tipo: 1 é a maior."""
        return self.prioridade.index(tipo) + 1


def config_da_bancada() -> ConfigBancada:
    """O `ConfigBancada` lido de `backend/config/`."""
    from adapters.configuracao import carregar_dicionario

    return ConfigBancada.de_dicionario(carregar_dicionario("hardware"))


@dataclass(frozen=True)
class _Ve:
    rua: int
    tipo: TipoVeiculo


class UnoSimulado:
    """O firmware do UNO, em Python, dirigido por tempo injetado.

    Args:
        config: Os números da bancada.
        t_s: Instante do boot, em segundos, no relógio de quem dirige.
    """

    def __init__(self, config: ConfigBancada, t_s: float = 0.0) -> None:
        self._c = config
        self._t0_s = t_s
        self._t_s = t_s

        # Luzes: cor e instante da última mudança de cada aproximação.
        self._cores: list[Cor] = [Cor.VERMELHO] * N_SEMAFOROS
        self._desde: list[float] = [t_s] * N_SEMAFOROS
        # Boot em all-red: conta como se todos tivessem acabado de ir a vermelho,
        # e a fase 1 só abre depois do all-red inteiro.
        self._t_ultimo_vermelho = t_s

        self._destino: frozenset[int] = FASES_DO_CICLO[0]
        self._fechar: frozenset[int] = frozenset()
        self._estabelecido = False
        self._fim_verde_s: float | None = None

        self._regime = Regime.CICLO
        self._fase_ciclo = 0
        self._atendido: _Ve | None = None
        self._fila: _Ve | None = None
        self._t_inicio_emergencia: float | None = None

        self._ultima_publicada: tuple[object, ...] | None = None
        self._proxima_telemetria_s = t_s
        self._saida: list[bytes] = [Evento(0, TipoEvento.BOOT).codificar()]

    # -- leitura do estado -----------------------------------------------------

    @property
    def t_dispositivo_ms(self) -> int:
        """O `millis()` da placa: tempo desde o boot."""
        return round((self._t_s - self._t0_s) * 1000)

    @property
    def regime(self) -> Regime:
        return self._regime

    def cores(self) -> tuple[Cor, Cor, Cor, Cor]:
        """O que cada módulo exibe agora, na ordem S1 S2 S3 S4."""
        s1, s2, s3, s4 = self._cores
        return (s1, s2, s3, s4)

    def telemetria(self) -> Telemetria:
        """A linha `ST` deste instante."""
        return Telemetria(
            self.t_dispositivo_ms,
            self.cores(),
            self._regime,
            None if self._atendido is None else self._atendido.rua,
            None if self._fila is None else self._fila.rua,
        )

    # -- entrada ---------------------------------------------------------------

    def avancar(self, t_s: float) -> list[bytes]:
        """Faz o tempo passar até `t_s`; devolve o que o UNO escreveu nesse meio.

        Raises:
            ValueError: se `t_s` for anterior ao instante atual.
        """
        if t_s < self._t_s - _EPS:
            raise ValueError(f"o tempo não volta: {t_s} < {self._t_s}")
        while True:
            self._assentar()
            proximo = self._proximo_instante()
            if proximo > t_s + _EPS:
                break
            self._t_s = proximo
        self._t_s = max(self._t_s, t_s)
        self._assentar()
        return self._esvaziar()

    def receber(self, linha: bytes, t_s: float) -> list[bytes]:
        """Processa uma linha chegada ao RX em `t_s` (`context/05` §3.2).

        Linha sem vírgula é ignorada (lixo de boot do ESP8266); com vírgula e
        conteúdo inválido, recebe `EV,RECUSADO`.
        """
        saida = self.avancar(t_s)
        if not parece_deteccao(linha):
            return saida
        try:
            deteccao = interpretar_deteccao(linha)
        except LinhaInvalidaError:
            self._emitir(Evento(self.t_dispositivo_ms, TipoEvento.RECUSADO))
            return saida + self._esvaziar()
        self._decidir(_Ve(deteccao.rua, deteccao.veiculo))
        self._assentar()
        return saida + self._esvaziar()

    # -- decisão (context/05 §3.3) --------------------------------------------

    def _decidir(self, novo: _Ve) -> None:
        """A regra do sketch, com uma linha de decisão por detecção, antes de tudo."""
        atendido = self._atendido
        if atendido is None:
            self._atender(novo)
        elif novo == atendido:
            if self._estabelecido:
                self._fim_verde_s = self._t_s + self._c.verde_por_tipo_s[novo.tipo]
            self._evento(TipoEvento.RENOVADO, novo)
        elif self._c.nivel(novo.tipo) < self._c.nivel(atendido.tipo):
            self._atender(novo)
            self._enfileirar(atendido)
        elif self._fila is None or self._c.nivel(novo.tipo) < self._c.nivel(self._fila.tipo):
            self._enfileirar(novo)
        else:
            self._evento(TipoEvento.DESCARTADO, novo)

    def _enfileirar(self, ve: _Ve) -> None:
        """Fila de um lugar: quem estava nela sai, e sai com `DESCARTADO`."""
        deslocado, self._fila = self._fila, ve
        self._evento(TipoEvento.FILA, ve)
        if deslocado is not None:
            self._evento(TipoEvento.DESCARTADO, deslocado)

    def _atender(self, ve: _Ve) -> None:
        if self._regime is Regime.CICLO:
            self._regime = Regime.EMERGENCIA
            self._t_inicio_emergencia = self._t_s
        self._atendido = ve
        self._evento(TipoEvento.PREEMP_INI, ve)
        self._mirar(frozenset({ve.rua - 1}))

    def _encerrar_atendimento(self) -> None:
        """O verde do VE acabou: atende a fila ou volta ao ciclo pelo eixo oposto."""
        atendido = self._atendido
        assert atendido is not None
        self._evento(TipoEvento.PREEMP_FIM, atendido)
        self._atendido = None
        if self._fila is not None:
            proximo, self._fila = self._fila, None
            self._atender(proximo)
        else:
            self._voltar_ao_ciclo(atendido)

    def _estourar_teto(self) -> None:
        atendido = self._atendido
        assert atendido is not None
        self._emitir(Evento(self.t_dispositivo_ms, TipoEvento.TIMEOUT))
        self._evento(TipoEvento.PREEMP_FIM, atendido)
        self._atendido = None
        self._fila = None
        self._voltar_ao_ciclo(atendido)

    def _voltar_ao_ciclo(self, ultimo: _Ve) -> None:
        # Recomeça pelo eixo que ficou esperando (context/05 §3.4, item 6).
        self._regime = Regime.CICLO
        self._t_inicio_emergencia = None
        self._fase_ciclo = 1 - EIXO_DE[ultimo.rua - 1]
        self._mirar(FASES_DO_CICLO[self._fase_ciclo])

    def _mirar(self, destino: frozenset[int]) -> None:
        """Troca o destino. Fica aceso só o que já está verde e cabe nele inteiro."""
        verdes = frozenset(i for i, cor in enumerate(self._cores) if cor is Cor.VERDE)
        manter = destino if destino <= verdes and destino else frozenset()
        self._destino = destino
        # Os verdes acesos agora que não podem ficar. Os que o destino abrir
        # depois não entram aqui: esses ficam até o destino mudar de novo.
        self._fechar = verdes - manter
        self._estabelecido = False
        self._fim_verde_s = None

    def _deve_fechar(self, i: int) -> bool:
        return self._cores[i] is Cor.VERDE and (i not in self._destino or i in self._fechar)

    # -- luzes ----------------------------------------------------------------

    def _assentar(self) -> None:
        """Aplica as regras no instante atual até nada mais mudar."""
        while self._um_passo():
            pass
        publicou = self._publicar_se_mudou()
        if self._t_s >= self._proxima_telemetria_s - _EPS:
            if not publicou:  # uma `ST` por instante basta
                self._emitir(self.telemetria())
            while self._proxima_telemetria_s <= self._t_s + _EPS:
                self._proxima_telemetria_s += PERIODO_TELEMETRIA_S

    def _um_passo(self) -> bool:
        t = self._t_s
        c = self._c

        if (
            self._t_inicio_emergencia is not None
            and t - self._t_inicio_emergencia >= c.teto_s - _EPS
        ):
            self._estourar_teto()
            return True
        if self._estabelecido and self._fim_verde_s is not None and t >= self._fim_verde_s - _EPS:
            if self._regime is Regime.EMERGENCIA:
                self._encerrar_atendimento()
            else:
                self._fase_ciclo = 1 - self._fase_ciclo
                self._mirar(FASES_DO_CICLO[self._fase_ciclo])
            return True

        mudou = False
        for i, cor in enumerate(self._cores):
            if self._deve_fechar(i):
                if t - self._desde[i] >= c.verde_min_s - _EPS:
                    self._acender(i, Cor.AMARELO)
                    mudou = True
            elif cor is Cor.AMARELO and t - self._desde[i] >= c.amarelo_s - _EPS:
                self._acender(i, Cor.VERMELHO)
                self._t_ultimo_vermelho = t
                mudou = True
        if mudou:
            return True

        a_abrir = [i for i in self._destino if self._cores[i] is not Cor.VERDE]
        todos_vermelhos = all(cor is Cor.VERMELHO for cor in self._cores)
        if a_abrir and todos_vermelhos and t - self._t_ultimo_vermelho >= c.all_red_s - _EPS:
            self._guarda_i1(self._destino)
            for i in a_abrir:
                self._acender(i, Cor.VERDE)
            return True

        if not self._estabelecido and self._destino_estabelecido():
            self._estabelecido = True
            if self._regime is Regime.EMERGENCIA:
                assert self._atendido is not None
                self._fim_verde_s = t + c.verde_por_tipo_s[self._atendido.tipo]
            else:
                self._fim_verde_s = t + c.verde_s
            return True
        return False

    def _destino_estabelecido(self) -> bool:
        return all(
            (cor is Cor.VERDE) == (i in self._destino) and cor is not Cor.AMARELO
            for i, cor in enumerate(self._cores)
        )

    def _guarda_i1(self, novos: frozenset[int]) -> None:
        """Independente da máquina: nada verde fora do eixo dos novos verdes."""
        verdes = {i for i, cor in enumerate(self._cores) if cor is Cor.VERDE} | novos
        if len({EIXO_DE[i] for i in verdes}) > 1:
            raise ViolacaoDeSegurancaError(f"I1: verde nos dois eixos, {sorted(verdes)}")
        if self._regime is Regime.EMERGENCIA and len(novos) > 1:
            raise ViolacaoDeSegurancaError(f"emergência abrindo mais de um verde: {sorted(novos)}")

    def _acender(self, i: int, cor: Cor) -> None:
        self._cores[i] = cor
        self._desde[i] = self._t_s

    def _proximo_instante(self) -> float:
        """O próximo instante em que alguma coisa vence."""
        c = self._c
        candidatos = [self._proxima_telemetria_s]
        if self._t_inicio_emergencia is not None:
            candidatos.append(self._t_inicio_emergencia + c.teto_s)
        if self._estabelecido and self._fim_verde_s is not None:
            candidatos.append(self._fim_verde_s)
        for i, cor in enumerate(self._cores):
            if self._deve_fechar(i):
                candidatos.append(self._desde[i] + c.verde_min_s)
            elif cor is Cor.AMARELO:
                candidatos.append(self._desde[i] + c.amarelo_s)
        if all(cor is Cor.VERMELHO for cor in self._cores):
            candidatos.append(self._t_ultimo_vermelho + c.all_red_s)
        futuros = [t for t in candidatos if t > self._t_s + _EPS]
        return min(futuros)

    # -- saída ----------------------------------------------------------------

    def _evento(self, tipo: TipoEvento, ve: _Ve) -> None:
        self._emitir(Evento(self.t_dispositivo_ms, tipo, ve.rua, ve.tipo))

    def _emitir(self, mensagem: Telemetria | Evento) -> None:
        if isinstance(mensagem, Telemetria):
            self._ultima_publicada = _assinatura(mensagem)
        self._saida.append(mensagem.codificar())

    def _publicar_se_mudou(self) -> bool:
        """`ST` a cada mudança de estado (luz, regime, rua ativa ou fila)."""
        atual = self.telemetria()
        if _assinatura(atual) == self._ultima_publicada:
            return False
        self._emitir(atual)
        return True

    def _esvaziar(self) -> list[bytes]:
        saida, self._saida = self._saida, []
        return saida


def _assinatura(telemetria: Telemetria) -> tuple[object, ...]:
    return (telemetria.cores, telemetria.regime, telemetria.rua_ativa, telemetria.rua_fila)


def uno_da_bancada(t_s: float = 0.0) -> UnoSimulado:
    """Um `UnoSimulado` com o perfil `hardware` lido de `backend/config/`."""
    return UnoSimulado(config_da_bancada(), t_s)


class TransporteSimulado:
    """`Transporte` em memória, com o `UnoSimulado` do outro lado do cabo USB.

    Modela a fiação da bancada (`context/05` §1):

    * o cabo USB é a **alimentação** do UNO: `puxar_cabo()` corta a ligação e
      desliga a placa;
    * abrir a porta **reinicia** a placa, como o DTR faz no UNO real;
    * com o fio do NodeMCU no RX (`fio_do_nodemcu_no_rx=True`), o que a ponte
      escreve **se perde**: o TX do NodeMCU prevalece sobre o do conversor USB.
      O padrão é o fio solto, que é como se testa.

    Args:
        fabrica: Cria o UNO no boot, a partir do instante do relógio.
        latencia_s: Atraso entre a linha sair e o UNO processá-la. Arbitrária —
            ver a docstring do módulo.
        passo_s: De quanto em quanto tempo o relógio do UNO avança. Não afeta os
            instantes das transições, só quando elas são publicadas.
        fio_do_nodemcu_no_rx: Se o fio do receptor está ligado ao RX do UNO.
    """

    def __init__(
        self,
        fabrica: Callable[[float], UnoSimulado] = uno_da_bancada,
        *,
        latencia_s: float = LATENCIA_PADRAO_S,
        passo_s: float = 0.05,
        fio_do_nodemcu_no_rx: bool = False,
    ) -> None:
        self._fabrica = fabrica
        self._latencia_s = latencia_s
        self._passo_s = passo_s
        self.fio_do_nodemcu_no_rx = fio_do_nodemcu_no_rx
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
        if self.fio_do_nodemcu_no_rx:
            return  # o NodeMCU domina o RX; a linha não chega ao UNO
        asyncio.get_running_loop().call_later(self._latencia_s, self._entregar, linha)

    async def ler_linha(self) -> bytes:
        if not self._conectado:
            raise ConexaoPerdidaError("porta simulada fechada")
        linha = await self._fila.get()
        if linha is None:
            raise ConexaoPerdidaError("cabo puxado")
        return linha

    def puxar_cabo(self) -> None:
        """Corta a ligação — e a alimentação: a placa para."""
        self._desconectar()
        if self._relogio is not None:
            self._relogio.cancel()
            self._relogio = None

    def simular_receptor(self, deteccao: Deteccao) -> None:
        """O NodeMCU receptor entregando uma detecção ao RX, como na operação."""
        asyncio.get_running_loop().call_later(
            self._latencia_s, self._entregar, deteccao.codificar()
        )

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
