r"""Protocolo serial entre a ponte e o Arduino UNO — contrato §6, `context/05` §4.

Texto ASCII, uma mensagem por linha terminada em `\n`, 115200 baud. Este módulo
é **puro**: não abre porta, não lê relógio, não sabe que o pyserial existe. Entra
`Comando`, sai `bytes`; entram `bytes`, sai resposta. É o que permite desenvolver
e testar o protocolo com o Arduino fora da mesa (`context/05` §6).

Os dois sentidos estão aqui, e os dois papéis também. A ponte codifica comandos
e interpreta respostas; o dublê de `adapters/hardware/simulado.py` faz o
contrário. Escrever os dois lados no mesmo módulo é o que garante que o dublê
fala o mesmo protocolo que a ponte, e o teste de ida e volta prova isso.

**Este módulo garante formato; a semântica é do firmware.** `PRE,5,20` sai daqui
sem objeção e o UNO responde `NAK,PRE,FASE_INVALIDA`; `TEST,GG--` também, e o UNO
responde `NAK,TEST,CONFLITO`. Recusar aqui esconderia justamente a guarda que
precisa ser demonstrada: a matriz de conflito é aplicada no motor e, de forma
independente, no firmware (P13), e a ponte não é uma terceira cópia dela.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, TypeAlias, TypeVar, assert_never

from core.comandos import Comando, TipoComando

BAUD: Final = 115200
TERMINADOR: Final = b"\n"
SEPARADOR: Final = ","

#: S1..S4, na ordem da telemetria. É estrutura do protocolo, não parâmetro: a
#: string de estado tem um caractere por módulo semáforo da bancada.
N_SEMAFOROS: Final = 4

_DIGITOS = re.compile(r"[0-9]+")


class ProtocoloError(ValueError):
    """Raiz dos erros do protocolo serial."""


class ComandoInvalidoError(ProtocoloError):
    """O pedido não pode ser expresso como linha válida do protocolo."""


class LinhaInvalidaError(ProtocoloError):
    """A linha recebida não segue o protocolo.

    Ruído na serial é esperado — o UNO imprime lixo ao resetar, e o reset
    acontece toda vez que a porta é aberta. Quem lê a porta registra e segue;
    não derruba a ponte.
    """


# ---------------------------------------------------------------------------
# Vocabulário
# ---------------------------------------------------------------------------


class NomeComando(StrEnum):
    """Os comandos que o host envia ao UNO."""

    PING = "PING"
    PRE = "PRE"
    CLR = "CLR"
    CFG = "CFG"
    CONSULTA = "ST?"
    SAFE = "SAFE"
    TESTMODE = "TESTMODE"
    TEST = "TEST"


class Cor(StrEnum):
    """O que um módulo semáforo exibe.

    `APAGADO` só existe em modo de teste, onde `TEST` pode apagar um módulo; no
    ciclo fixo e na preempção todo módulo tem exatamente uma luz acesa.
    """

    VERMELHO = "R"
    AMARELO = "Y"
    VERDE = "G"
    APAGADO = "-"


class MotivoNak(StrEnum):
    """Por que o UNO recusou um comando."""

    FASE_INVALIDA = "FASE_INVALIDA"
    CONFLITO = "CONFLITO"
    MODO = "MODO"
    VERDE_MIN = "VERDE_MIN"
    FORMATO = "FORMATO"


class TipoEvento(StrEnum):
    """Eventos que o UNO publica por conta própria."""

    WATCHDOG = "WATCHDOG"
    TIMEOUT = "TIMEOUT"
    PREEMP_INI = "PREEMP_INI"
    PREEMP_FIM = "PREEMP_FIM"
    TESTE_INI = "TESTE_INI"
    TESTE_FIM = "TESTE_FIM"
    CONFLITO_RECUSADO = "CONFLITO_RECUSADO"


def _linha(*campos: str) -> bytes:
    return SEPARADOR.join(campos).encode("ascii") + TERMINADOR


# ---------------------------------------------------------------------------
# Host -> UNO
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComandoSerial:
    """Uma linha do host para o UNO, já validada quanto ao formato.

    Construa pelas funções deste módulo (`preempcao`, `configurar`...), não
    diretamente: são elas que validam os argumentos.

    Attributes:
        nome: Qual comando. É também o que volta no `ACK`/`NAK` correspondente,
            e é por ele que a ponte casa a resposta com o pedido.
        argumentos: Campos depois do nome, já como texto.
    """

    nome: NomeComando
    argumentos: tuple[str, ...] = ()

    def codificar(self) -> bytes:
        """A linha pronta para escrever na porta, com o terminador."""
        return _linha(self.nome.value, *self.argumentos)


def _inteiro_positivo(valor: int, campo: str) -> str:
    # `bool` é subclasse de `int`; `PRE,True,20` é bug de quem chamou.
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 1:
        raise ComandoInvalidoError(f"{campo} precisa ser inteiro positivo, veio {valor!r}")
    return str(valor)


def _segundos_para_cima(duracao_s: float, campo: str) -> str:
    if not math.isfinite(duracao_s) or duracao_s <= 0:
        raise ComandoInvalidoError(f"{campo} precisa ser positivo e finito, veio {duracao_s!r}")
    # O `round` absorve o ruído de ponto flutuante: 20.000000000004 é 20, não 21.
    return str(math.ceil(round(duracao_s, 6)))


def _segundos_exatos(valor_s: float, campo: str) -> str:
    if not math.isfinite(valor_s) or valor_s <= 0 or not float(valor_s).is_integer():
        raise ComandoInvalidoError(
            f"{campo} precisa ser um número inteiro e positivo de segundos, veio {valor_s!r}"
        )
    return str(int(valor_s))


def ping() -> ComandoSerial:
    """`PING` — prova de vida; alimenta o watchdog do UNO (I6)."""
    return ComandoSerial(NomeComando.PING)


def preempcao(fase: int, duracao_s: float) -> ComandoSerial:
    """`PRE,<fase>,<dur_s>` — preempta para a fase, ou estende se ela já está verde.

    A duração é arredondada **para cima** ao segundo inteiro. O UNO interpreta
    `dur_s` como inteiro (parse barato no AVR, contrato §6), e arredondar para
    baixo poderia fechar o verde segundos antes de o VE passar. O erro para
    cima custa no máximo 1 s à transversal.

    Args:
        fase: Fase de destino, `1..4` na bancada (quem valida a faixa é o UNO).
        duracao_s: Quanto manter o verde, em segundos, contados a partir do
            comando — a mesma semântica de `ESTENDER_VERDE` no motor.

    Raises:
        ComandoInvalidoError: fase não positiva, ou duração não positiva ou
            não finita.
    """
    return ComandoSerial(
        NomeComando.PRE,
        (_inteiro_positivo(fase, "fase"), _segundos_para_cima(duracao_s, "duracao_s")),
    )


def liberar() -> ComandoSerial:
    """`CLR` — encerra a preempção e retoma o ciclo fixo."""
    return ComandoSerial(NomeComando.CLR)


def configurar(verde_s: float, amarelo_s: float, all_red_s: float) -> ComandoSerial:
    """`CFG,<verde_s>,<amarelo_s>,<allred_s>` — ajusta os tempos do ciclo fixo.

    Diferente de `preempcao`, aqui **nada é arredondado**: os três são tempos de
    segurança (I2, I3, I4), e arredondar `amarelo_s = 2.5` para 2 encurtaria o
    amarelo em silêncio. Valor fracionário é recusado.

    Raises:
        ComandoInvalidoError: algum tempo fracionário, não positivo ou não finito.
    """
    return ComandoSerial(
        NomeComando.CFG,
        (
            _segundos_exatos(verde_s, "verde_s"),
            _segundos_exatos(amarelo_s, "amarelo_s"),
            _segundos_exatos(all_red_s, "all_red_s"),
        ),
    )


def consultar() -> ComandoSerial:
    """`ST?` — pede uma telemetria imediata."""
    return ComandoSerial(NomeComando.CONSULTA)


def parada_segura() -> ComandoSerial:
    """`SAFE` — todos os acessos em vermelho."""
    return ComandoSerial(NomeComando.SAFE)


def modo_teste(ativo: bool) -> ComandoSerial:
    """`TESTMODE,<0|1>` — entra ou sai do modo de bancada."""
    return ComandoSerial(NomeComando.TESTMODE, ("1" if ativo else "0",))


def acionamento_direto(cores: str) -> ComandoSerial:
    """`TEST,<c1><c2><c3><c4>` — acende cores escolhidas, só em modo de teste.

    `GG--` é aceito aqui de propósito: é o comando que demonstra que o UNO
    recusa dois verdes com `NAK,TEST,CONFLITO` (contrato §6, regra 3).

    Args:
        cores: Quatro caracteres de `R`, `Y`, `G`, `-`, na ordem S1 S2 S3 S4.

    Raises:
        ComandoInvalidoError: tamanho diferente de quatro ou cor desconhecida.
    """
    validas = {cor.value for cor in Cor}
    if len(cores) != N_SEMAFOROS or any(c not in validas for c in cores):
        raise ComandoInvalidoError(
            f"cores precisa ter {N_SEMAFOROS} caracteres de 'RYG-', veio {cores!r}"
        )
    return ComandoSerial(NomeComando.TEST, (cores,))


def traduzir(comando: Comando) -> ComandoSerial | None:
    """Traduz o comando abstrato do motor na linha do protocolo.

    ===========================  ======================  ===========================
    Comando do motor             Linha                   Por quê
    ===========================  ======================  ===========================
    `IR_PARA_FASE`               `PRE,<fase>,<dur_s>`    Preempção (E5)
    `ESTENDER_VERDE` de um VE    `PRE,<fase>,<dur_s>`    Fase já verde: o UNO estende
    `ESTENDER_VERDE` sem VE      nenhuma                 Compensação (E7); ver abaixo
    `LIBERAR`                    `CLR`                   Fim da preempção
    `COMPENSAR`                  `CLR`                   Fim da preempção, com E7
    `FALLBACK_SEGURO`            `CLR`                   Volta ao ciclo fixo (§6)
    ===========================  ======================  ===========================

    `COMPENSAR` precisa virar `CLR`: o motor o emite **no lugar** de `LIBERAR`
    quando há compensação, e sem o `CLR` o UNO ficaria preso na preempção até o
    timeout de 30 s.

    `FALLBACK_SEGURO` é `CLR`, não `SAFE`. O fail-safe do projeto é voltar ao
    ciclo fixo; `SAFE` (todos em vermelho) é parada de operador.

    A extensão de compensação do E7 sai do motor **sem** `id_veiculo`, e o
    protocolo não tem linha para "estender o verde do ciclo fixo sem
    preempção" — `PRE` marcaria o UNO como em preempção, que é exatamente a
    confusão que o motor evita ao omitir o VE. Na bancada não há sensor de
    fila, então o plano de E7 é a própria duração base e a extensão coincide
    com o ciclo fixo; por isso nada se perde hoje. Se o protocolo ganhar esse
    comando (contrato §15, item 4), é aqui que ele entra.

    `id_semaforo` não vai na linha: a bancada é um cruzamento só, e quem escolhe
    a porta serial pelo cruzamento é o adaptador.

    Args:
        comando: O que o motor decidiu.

    Returns:
        A linha a enviar, ou `None` quando o comando não tem expressão no
        protocolo (só a extensão de compensação).

    Raises:
        ComandoInvalidoError: preempção sem fase ou sem duração.
    """
    match comando.tipo:
        case TipoComando.LIBERAR | TipoComando.COMPENSAR | TipoComando.FALLBACK_SEGURO:
            return liberar()
        case TipoComando.ESTENDER_VERDE if comando.id_veiculo is None:
            return None
        case TipoComando.IR_PARA_FASE | TipoComando.ESTENDER_VERDE:
            if comando.fase_alvo is None or comando.duracao_s is None:
                raise ComandoInvalidoError(
                    f"{comando.tipo} sem fase_alvo ou duracao_s não vira PRE: {comando!r}"
                )
            return preempcao(comando.fase_alvo, comando.duracao_s)
        case _:
            assert_never(comando.tipo)


# ---------------------------------------------------------------------------
# UNO -> host
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ack:
    """`ACK,<comando>` — comando aceito.

    Para `PRE`, a chegada desta linha é o instante `t_atuacao` (P14): o UNO
    responde ao **iniciar** a transição, e o amarelo já é a alteração do
    semáforo.
    """

    comando: NomeComando

    def codificar(self) -> bytes:
        """A linha como o UNO a envia."""
        return _linha("ACK", self.comando.value)


@dataclass(frozen=True)
class Nak:
    """`NAK,<comando>,<motivo>` — comando recusado."""

    comando: NomeComando
    motivo: MotivoNak

    def codificar(self) -> bytes:
        """A linha como o UNO a envia."""
        return _linha("NAK", self.comando.value, self.motivo.value)


@dataclass(frozen=True)
class Telemetria:
    """`ST,<ms>,<fase>,<s1><s2><s3><s4>,<preemp>[,<teste>]` — estado completo.

    Uma telemetria com dois verdes é **interpretada, não rejeitada**. Ela é a
    evidência de uma violação de I1, e o relatório de validação precisa
    contá-la (contrato §6); descartá-la como linha malformada apagaria
    justamente o que se quer detectar. Ver `viola_i1`.

    Attributes:
        t_dispositivo_ms: `millis()` do UNO. Sem relação com o relógio do
            notebook: serve para ordenar e medir intervalos dentro do
            dispositivo, nunca para latência (contrato §10).
        fase: Fase corrente do ciclo, `1..4`.
        cores: O que cada módulo exibe, na ordem S1 S2 S3 S4.
        em_preempcao: Preempção ativa.
        em_teste: Modo de teste ativo. O campo entrou em P13; firmware anterior
            não o envia, e não tem modo de teste, então a ausência é `False`.
    """

    t_dispositivo_ms: int
    fase: int
    cores: tuple[Cor, Cor, Cor, Cor]
    em_preempcao: bool
    em_teste: bool = False

    @property
    def verdes(self) -> int:
        """Quantos módulos estão em verde."""
        return sum(cor is Cor.VERDE for cor in self.cores)

    @property
    def viola_i1(self) -> bool:
        """Dois verdes ao mesmo tempo — sob *split phasing*, sempre conflito."""
        return self.verdes > 1

    def codificar(self) -> bytes:
        """A linha como o firmware atual a envia, com o campo `<teste>`."""
        return _linha(
            "ST",
            str(self.t_dispositivo_ms),
            str(self.fase),
            "".join(cor.value for cor in self.cores),
            "1" if self.em_preempcao else "0",
            "1" if self.em_teste else "0",
        )


@dataclass(frozen=True)
class Evento:
    """`EV,<ms>,<tipo>` — algo que o UNO fez por conta própria."""

    t_dispositivo_ms: int
    tipo: TipoEvento

    def codificar(self) -> bytes:
        """A linha como o UNO a envia."""
        return _linha("EV", str(self.t_dispositivo_ms), self.tipo.value)


Resposta: TypeAlias = Ack | Nak | Telemetria | Evento

_E = TypeVar("_E", bound=StrEnum)


def _campos(linha: bytes) -> list[str]:
    try:
        texto = linha.decode("ascii")
    except UnicodeDecodeError as erro:
        raise LinhaInvalidaError(f"linha não é ASCII: {linha!r}") from erro
    # `Serial.println` do Arduino termina em "\r\n"; o contrato diz "\n". Aceitar
    # os dois custa uma linha e evita depender de qual o firmware usou.
    texto = texto.removesuffix("\n").removesuffix("\r")
    if not texto:
        raise LinhaInvalidaError("linha vazia")
    return texto.split(SEPARADOR)


def _exigir_campos(campos: list[str], *quantidades: int) -> None:
    if len(campos) not in quantidades:
        esperado = " ou ".join(str(q) for q in quantidades)
        raise LinhaInvalidaError(
            f"{campos[0]} espera {esperado} campos, veio {len(campos)}: {SEPARADOR.join(campos)!r}"
        )


def _membro(enum: type[_E], texto: str, campo: str) -> _E:
    try:
        return enum(texto)
    except ValueError as erro:
        raise LinhaInvalidaError(f"{campo} desconhecido: {texto!r}") from erro


def _natural(texto: str, campo: str) -> int:
    # `int()` aceitaria " 12", "+12" e "1_2". O firmware nunca produz isso, e
    # aceitar seria esconder ruído na linha.
    if not _DIGITOS.fullmatch(texto):
        raise LinhaInvalidaError(f"{campo} precisa ser inteiro sem sinal, veio {texto!r}")
    return int(texto)


def _bandeira(texto: str, campo: str) -> bool:
    if texto not in ("0", "1"):
        raise LinhaInvalidaError(f"{campo} precisa ser 0 ou 1, veio {texto!r}")
    return texto == "1"


def _cores(texto: str) -> tuple[Cor, Cor, Cor, Cor]:
    if len(texto) != N_SEMAFOROS:
        raise LinhaInvalidaError(f"estado precisa ter {N_SEMAFOROS} cores, veio {texto!r}")
    s1, s2, s3, s4 = (_membro(Cor, c, "cor") for c in texto)
    return (s1, s2, s3, s4)


def interpretar(linha: bytes) -> Resposta:
    r"""Interpreta uma linha do UNO.

    Args:
        linha: Uma linha, com ou sem terminador (`\n` ou `\r\n`).

    Returns:
        A resposta correspondente.

    Raises:
        LinhaInvalidaError: a linha não segue o protocolo.
    """
    campos = _campos(linha)
    match campos[0]:
        case "ACK":
            _exigir_campos(campos, 2)
            return Ack(_membro(NomeComando, campos[1], "comando"))
        case "NAK":
            _exigir_campos(campos, 3)
            return Nak(
                _membro(NomeComando, campos[1], "comando"),
                _membro(MotivoNak, campos[2], "motivo"),
            )
        case "ST":
            _exigir_campos(campos, 5, 6)
            fase = _natural(campos[2], "fase")
            if fase < 1:
                raise LinhaInvalidaError(f"fase precisa ser positiva, veio {fase}")
            return Telemetria(
                t_dispositivo_ms=_natural(campos[1], "ms"),
                fase=fase,
                cores=_cores(campos[3]),
                em_preempcao=_bandeira(campos[4], "preemp"),
                em_teste=_bandeira(campos[5], "teste") if len(campos) == 6 else False,
            )
        case "EV":
            _exigir_campos(campos, 3)
            return Evento(_natural(campos[1], "ms"), _membro(TipoEvento, campos[2], "evento"))
        case outro:
            raise LinhaInvalidaError(f"tipo de linha desconhecido: {outro!r}")


#: Quantos argumentos cada comando leva depois do nome.
_ARIDADE: Final = {
    NomeComando.PING: 0,
    NomeComando.PRE: 2,
    NomeComando.CLR: 0,
    NomeComando.CFG: 3,
    NomeComando.CONSULTA: 0,
    NomeComando.SAFE: 0,
    NomeComando.TESTMODE: 1,
    NomeComando.TEST: 1,
}


def interpretar_comando(linha: bytes) -> ComandoSerial:
    """Interpreta uma linha do host — o lado do UNO, usado pelo dublê.

    Args:
        linha: Uma linha, com ou sem terminador.

    Returns:
        O comando, validado pelas mesmas funções que a ponte usa para criá-lo.

    Raises:
        LinhaInvalidaError: a linha não é um comando válido. O UNO responderia
            `NAK,<comando>,FORMATO`.
    """
    campos = _campos(linha)
    nome = _membro(NomeComando, campos[0], "comando")
    argumentos = campos[1:]
    if len(argumentos) != _ARIDADE[nome]:
        raise LinhaInvalidaError(
            f"{nome} espera {_ARIDADE[nome]} argumento(s), veio {len(argumentos)}"
        )
    try:
        match nome:
            case NomeComando.PRE:
                return preempcao(_natural(argumentos[0], "fase"), _natural(argumentos[1], "dur_s"))
            case NomeComando.CFG:
                verde, amarelo, all_red = (_natural(a, "tempo") for a in argumentos)
                return configurar(verde, amarelo, all_red)
            case NomeComando.TESTMODE:
                return modo_teste(_bandeira(argumentos[0], "modo"))
            case NomeComando.TEST:
                return acionamento_direto(argumentos[0])
            case _:
                return ComandoSerial(nome)
    except ComandoInvalidoError as erro:
        raise LinhaInvalidaError(str(erro)) from erro
