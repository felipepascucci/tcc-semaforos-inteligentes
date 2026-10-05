r"""Protocolo serial do Arduino UNO da bancada — `context/05` §4.

Texto ASCII, uma mensagem por linha, **9600 baud** — a velocidade do NodeMCU
receptor, que divide a única UART do UNO com o USB. Este módulo é **puro**: não
abre porta, não lê relógio, não sabe que o pyserial existe. Entram `bytes`, sai
mensagem; entra mensagem, saem `bytes`. É o que permite desenvolver e testar sem
a bancada (`context/05` §8).

Três vozes passam por aqui, desde a arquitetura de 2026-10-05:

* **NodeMCU receptor → UNO**: `RUA3,AMBULANCIA` (`Deteccao`). É a única
  entrada do UNO. A ponte escreve a mesma linha para testar, com o fio do
  NodeMCU solto do RX (`context/05` §6).
* **UNO → notebook**: telemetria `ST` e eventos `EV` (`Telemetria`, `Evento`).
* **NodeMCU emissor → notebook**: `Tag <UID> lida -> Enviando RUAn`
  (`LeituraVeiculo`), só na medição de H3 (`context/05` §4.3).

Os dois lados de cada voz estão no mesmo módulo, como antes: o dublê de
`adapters/hardware/simulado.py` escreve o que a ponte lê, e o teste de ida e
volta prova que falam a mesma língua.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, TypeAlias, TypeVar

from core.modelos import TipoVeiculo

BAUD: Final = 9600
TERMINADOR: Final = b"\n"
SEPARADOR: Final = ","

#: S1..S4, na ordem da telemetria. É estrutura do protocolo, não parâmetro: a
#: string de estado tem um caractere por módulo semáforo da bancada.
N_SEMAFOROS: Final = 4

#: O eixo de cada aproximação, na ordem S1..S4: 0 principal, 1 transversal.
#: Aproximações de eixos diferentes conflitam (I1 na bancada, `context/01` §6).
EIXO_DE: Final = (0, 0, 1, 1)

_DIGITOS = re.compile(r"[0-9]+")
_LEITURA_VEICULO = re.compile(r"Tag ([0-9A-F]+) lida -> Enviando RUA([1-4])")


class ProtocoloError(ValueError):
    """Raiz dos erros do protocolo serial."""


class LinhaInvalidaError(ProtocoloError):
    """A linha recebida não segue o protocolo.

    Ruído na serial é esperado — o UNO e o ESP8266 imprimem lixo ao resetar, e
    o UNO reseta toda vez que a porta é aberta. Quem lê a porta registra e
    segue; não derruba a ponte.
    """


# ---------------------------------------------------------------------------
# Vocabulário
# ---------------------------------------------------------------------------


class Cor(StrEnum):
    """O que um módulo semáforo exibe. Sempre exatamente uma luz acesa."""

    VERMELHO = "R"
    AMARELO = "Y"
    VERDE = "G"


class Regime(StrEnum):
    """Em que regime o UNO está (`context/05` §3.1)."""

    CICLO = "C"
    EMERGENCIA = "E"


class TipoEvento(StrEnum):
    """Eventos que o UNO publica (`context/05` §4.2)."""

    BOOT = "BOOT"
    PREEMP_INI = "PREEMP_INI"
    RENOVADO = "RENOVADO"
    FILA = "FILA"
    DESCARTADO = "DESCARTADO"
    PREEMP_FIM = "PREEMP_FIM"
    TIMEOUT = "TIMEOUT"
    RECUSADO = "RECUSADO"


#: Os eventos que dizem respeito a um VE e trazem `<rua>,<veiculo>`.
EVENTOS_DE_VEICULO: Final = frozenset(
    {
        TipoEvento.PREEMP_INI,
        TipoEvento.RENOVADO,
        TipoEvento.FILA,
        TipoEvento.DESCARTADO,
        TipoEvento.PREEMP_FIM,
    }
)

#: As quatro respostas possíveis a uma detecção válida — exatamente uma por
#: linha recebida, escrita antes de qualquer outra (`context/05` §4.2).
EVENTOS_DE_DECISAO: Final = frozenset(
    {TipoEvento.PREEMP_INI, TipoEvento.RENOVADO, TipoEvento.FILA, TipoEvento.DESCARTADO}
)

_E = TypeVar("_E", bound=StrEnum)


def _linha(*campos: str) -> bytes:
    return SEPARADOR.join(campos).encode("ascii") + TERMINADOR


def _texto(linha: bytes) -> str:
    try:
        texto = linha.decode("ascii")
    except UnicodeDecodeError as erro:
        raise LinhaInvalidaError(f"linha não é ASCII: {linha!r}") from erro
    # `Serial.println` termina em "\r\n". Aceitar os dois custa uma linha e não
    # depende de qual o firmware usou.
    texto = texto.removesuffix("\n").removesuffix("\r")
    if not texto:
        raise LinhaInvalidaError("linha vazia")
    return texto


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


def _rua_ou_zero(texto: str, campo: str) -> int | None:
    numero = _natural(texto, campo)
    if numero > N_SEMAFOROS:
        raise LinhaInvalidaError(f"{campo} fora de 0..{N_SEMAFOROS}: {numero}")
    return numero or None


def _rua(texto: str, campo: str) -> int:
    rua = _rua_ou_zero(texto, campo)
    if rua is None:
        raise LinhaInvalidaError(f"{campo} precisa estar em 1..{N_SEMAFOROS}, veio 0")
    return rua


def _validar_rua(rua: int) -> None:
    if isinstance(rua, bool) or not 1 <= rua <= N_SEMAFOROS:
        raise ProtocoloError(f"rua precisa estar em 1..{N_SEMAFOROS}, veio {rua!r}")


# ---------------------------------------------------------------------------
# NodeMCU receptor -> UNO
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Deteccao:
    """`RUA<n>,<VEICULO>` — um VE chegando pela rua `n` (`context/05` §3.2).

    É a linha que o NodeMCU receptor repassa ao UNO, e a mesma que a ponte
    injeta nos testes.

    Raises:
        ProtocoloError: rua fora de 1..4.
    """

    rua: int
    veiculo: TipoVeiculo

    def __post_init__(self) -> None:
        _validar_rua(self.rua)

    def codificar(self) -> bytes:
        """A linha como o receptor a envia."""
        return _linha(f"RUA{self.rua}", self.veiculo.value)


def parece_deteccao(linha: bytes) -> bool:
    """A linha tem a forma de uma detecção, válida ou não.

    O UNO responde `EV,RECUSADO` a linha com vírgula e conteúdo inválido, e
    ignora em silêncio a que não tem vírgula — é o lixo que o ESP8266 imprime no
    próprio boot, a 74880 baud (`context/05` §3.2).
    """
    return SEPARADOR.encode("ascii") in linha


def interpretar_deteccao(linha: bytes) -> Deteccao:
    """Interpreta a linha do receptor — o lado do UNO, usado pelo dublê.

    Aceita `RUA3` e `3`, como o sketch da equipe de hardware.

    Raises:
        LinhaInvalidaError: rua ou tipo desconhecido, ou campos a mais.
    """
    campos = _texto(linha).split(SEPARADOR)
    if len(campos) != 2:
        raise LinhaInvalidaError(f"detecção espera 2 campos, veio {len(campos)}")
    rua_texto, veiculo_texto = (campo.strip() for campo in campos)
    rua = _rua(rua_texto.removeprefix("RUA"), "rua")
    return Deteccao(rua, _membro(TipoVeiculo, veiculo_texto, "veículo"))


# ---------------------------------------------------------------------------
# UNO -> notebook
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Telemetria:
    """`ST,<ms>,<s1s2s3s4>,<C|E>,<rua_ativa>,<rua_fila>` (`context/05` §4.2).

    Sai a 2 Hz e a cada mudança de estado. Uma telemetria com verde nos dois
    eixos é **interpretada, não rejeitada**: é a evidência de uma violação de
    I1, e o relatório de validação precisa contá-la. Ver `viola_i1`.

    Attributes:
        t_dispositivo_ms: `millis()` do UNO. Ordena e mede intervalos dentro da
            placa; a latência oficial usa o relógio do notebook.
        cores: O que cada módulo exibe, na ordem S1 S2 S3 S4.
        regime: Ciclo ou emergência.
        rua_ativa: A rua do VE atendido, ou `None`.
        rua_fila: A rua do VE na fila, ou `None`.
    """

    t_dispositivo_ms: int
    cores: tuple[Cor, Cor, Cor, Cor]
    regime: Regime
    rua_ativa: int | None = None
    rua_fila: int | None = None

    @property
    def viola_i1(self) -> bool:
        """Verde nos dois eixos ao mesmo tempo."""
        eixos = {EIXO_DE[i] for i, cor in enumerate(self.cores) if cor is Cor.VERDE}
        return len(eixos) > 1

    @property
    def estado(self) -> str:
        """As quatro cores como na linha, `S1S2S3S4`."""
        return "".join(cor.value for cor in self.cores)

    def codificar(self) -> bytes:
        """A linha como o UNO a envia."""
        return _linha(
            "ST",
            str(self.t_dispositivo_ms),
            self.estado,
            self.regime.value,
            str(self.rua_ativa or 0),
            str(self.rua_fila or 0),
        )


@dataclass(frozen=True)
class Evento:
    """`EV,<ms>,<tipo>[,<rua>,<veiculo>]` — algo que o UNO decidiu ou fez.

    Raises:
        ProtocoloError: evento de VE sem rua ou veículo, ou evento sem VE que
            os traz.
    """

    t_dispositivo_ms: int
    tipo: TipoEvento
    rua: int | None = None
    veiculo: TipoVeiculo | None = None

    def __post_init__(self) -> None:
        de_veiculo = self.tipo in EVENTOS_DE_VEICULO
        if de_veiculo != (self.rua is not None and self.veiculo is not None):
            raise ProtocoloError(f"{self.tipo} {'exige' if de_veiculo else 'não leva'} rua e VE")
        if self.rua is not None:
            _validar_rua(self.rua)

    def codificar(self) -> bytes:
        """A linha como o UNO a envia."""
        if self.rua is None or self.veiculo is None:
            return _linha("EV", str(self.t_dispositivo_ms), self.tipo.value)
        return _linha(
            "EV", str(self.t_dispositivo_ms), self.tipo.value, str(self.rua), self.veiculo.value
        )


Resposta: TypeAlias = Telemetria | Evento


def _cores(texto: str) -> tuple[Cor, Cor, Cor, Cor]:
    if len(texto) != N_SEMAFOROS:
        raise LinhaInvalidaError(f"estado precisa ter {N_SEMAFOROS} cores, veio {texto!r}")
    s1, s2, s3, s4 = (_membro(Cor, c, "cor") for c in texto)
    return (s1, s2, s3, s4)


def interpretar(linha: bytes) -> Resposta:
    r"""Interpreta uma linha do UNO.

    Args:
        linha: Uma linha, com ou sem terminador (`\n` ou `\r\n`).

    Raises:
        LinhaInvalidaError: a linha não segue o protocolo.
    """
    campos = _texto(linha).split(SEPARADOR)
    match campos[0]:
        case "ST":
            if len(campos) != 6:
                raise LinhaInvalidaError(f"ST espera 6 campos, veio {len(campos)}")
            return Telemetria(
                t_dispositivo_ms=_natural(campos[1], "ms"),
                cores=_cores(campos[2]),
                regime=_membro(Regime, campos[3], "regime"),
                rua_ativa=_rua_ou_zero(campos[4], "rua_ativa"),
                rua_fila=_rua_ou_zero(campos[5], "rua_fila"),
            )
        case "EV":
            if len(campos) not in (3, 5):
                raise LinhaInvalidaError(f"EV espera 3 ou 5 campos, veio {len(campos)}")
            ms = _natural(campos[1], "ms")
            tipo = _membro(TipoEvento, campos[2], "evento")
            try:
                if len(campos) == 3:
                    return Evento(ms, tipo)
                return Evento(
                    ms, tipo, _rua(campos[3], "rua"), _membro(TipoVeiculo, campos[4], "veículo")
                )
            except LinhaInvalidaError:
                raise
            except ProtocoloError as erro:
                raise LinhaInvalidaError(str(erro)) from erro
        case outro:
            raise LinhaInvalidaError(f"tipo de linha desconhecido: {outro!r}")


# ---------------------------------------------------------------------------
# NodeMCU emissor -> notebook (só na medição de H3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LeituraVeiculo:
    """`Tag <UID> lida -> Enviando RUA<n>` — o emissor leu a tag e enviou.

    O sketch imprime esta linha logo depois do `esp_now_send`; a chegada dela ao
    notebook é o `t_deteccao` de H3 (`context/05` §4.3).
    """

    uid: str
    rua: int

    def __post_init__(self) -> None:
        _validar_rua(self.rua)

    def codificar(self) -> bytes:
        """A linha como o emissor a imprime."""
        return f"Tag {self.uid} lida -> Enviando RUA{self.rua}".encode("ascii") + TERMINADOR


def interpretar_leitura_veiculo(linha: bytes) -> LeituraVeiculo:
    """Interpreta a linha do emissor.

    Raises:
        LinhaInvalidaError: não é a linha de envio do emissor (ele imprime outras
            coisas no boot).
    """
    casamento = _LEITURA_VEICULO.fullmatch(_texto(linha))
    if casamento is None:
        raise LinhaInvalidaError(f"não é linha de envio do emissor: {linha!r}")
    return LeituraVeiculo(casamento[1], int(casamento[2]))
