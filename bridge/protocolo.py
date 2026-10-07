r"""Protocolo serial do Arduino UNO da bancada — `context/05` §4.

Texto ASCII, uma mensagem por linha, **9600 baud**. Este módulo é **puro**: não
abre porta, não lê relógio, não sabe que o pyserial existe. Entram `bytes`, sai
mensagem; entra mensagem, saem `bytes`. É o que permite desenvolver e testar sem
a bancada (`context/05` §8).

Quatro vozes passam por aqui, desde a decisão de 2026-10-06 (o receptor no A0):

* **NodeMCU receptor → UNO**, pela serial por software no A0:
  `RUA3,AMBULANCIA` (`Deteccao`).
* **Notebook → UNO**, pelo USB: `AUT,AMBULANCIA,1` (`Autorizacao`), a
  criticidade da ocorrência ativa de cada tipo, que a Central decide (P20). A
  ponte também escreve ali a mesma `Deteccao` do receptor, para testar.
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

#: A ordem dos tipos no campo de autorizações da `ST`: um dígito por tipo.
TIPOS_DA_BANCADA: Final = (TipoVeiculo.AMBULANCIA, TipoVeiculo.BOMBEIRO, TipoVeiculo.POLICIA)

#: Criticidade de um tipo na bancada: 0 é sem ocorrência ativa (não preempta);
#: 1 a 3 são os valores de `core.modelos.Criticidade`, 1 o mais crítico.
SEM_OCORRENCIA: Final = 0
CRITICIDADE_MAXIMA: Final = 3

Autorizacoes: TypeAlias = tuple[int, int, int]

#: O UNO liga negando todos (decisão de 2026-10-06): até a ponte mandar a
#: lista, nenhum VE preempta.
NENHUMA_AUTORIZACAO: Final[Autorizacoes] = (0, 0, 0)

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
    SEM_OCORRENCIA = "SEM_OCORRENCIA"


#: Os eventos que dizem respeito a um VE e trazem `<rua>,<veiculo>`.
EVENTOS_DE_VEICULO: Final = frozenset(
    {
        TipoEvento.PREEMP_INI,
        TipoEvento.RENOVADO,
        TipoEvento.FILA,
        TipoEvento.DESCARTADO,
        TipoEvento.PREEMP_FIM,
        TipoEvento.SEM_OCORRENCIA,
    }
)

#: As respostas possíveis a uma detecção válida — exatamente uma por linha
#: recebida, escrita antes de qualquer outra (`context/05` §4.2).
#: `SEM_OCORRENCIA` é o VE do tipo sem ocorrência ativa na Central (P20).
EVENTOS_DE_DECISAO: Final = frozenset(
    {
        TipoEvento.PREEMP_INI,
        TipoEvento.RENOVADO,
        TipoEvento.FILA,
        TipoEvento.DESCARTADO,
        TipoEvento.SEM_OCORRENCIA,
    }
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
# Notebook -> UNO (pelo USB, desde 2026-10-06)
# ---------------------------------------------------------------------------

#: O primeiro campo da linha de autorização.
PREFIXO_AUTORIZACAO: Final = "AUT"


def _validar_criticidade(criticidade: int) -> None:
    if isinstance(criticidade, bool) or not SEM_OCORRENCIA <= criticidade <= CRITICIDADE_MAXIMA:
        raise ProtocoloError(
            f"criticidade precisa estar em {SEM_OCORRENCIA}..{CRITICIDADE_MAXIMA}, "
            f"veio {criticidade!r}"
        )


@dataclass(frozen=True)
class Autorizacao:
    """`AUT,<VEICULO>,<criticidade>` — o que a Central diz sobre um tipo (P20).

    `criticidade` 0 é "sem ocorrência ativa": o VE desse tipo não preempta e
    recebe `EV,SEM_OCORRENCIA`. De 1 a 3, é a criticidade da ocorrência
    (`core.modelos.Criticidade`), e é ela, e não o tipo, que ordena quem
    interrompe quem no UNO (decisão de 2026-10-06).

    Só o USB aceita esta linha. Vinda do receptor (rádio), ela é uma detecção
    inválida e recebe `EV,RECUSADO`: um VE não se autoriza sozinho.

    Raises:
        ProtocoloError: criticidade fora de 0..3.
    """

    veiculo: TipoVeiculo
    criticidade: int

    def __post_init__(self) -> None:
        _validar_criticidade(self.criticidade)

    def codificar(self) -> bytes:
        """A linha como a ponte a escreve."""
        return _linha(PREFIXO_AUTORIZACAO, self.veiculo.value, str(self.criticidade))


def parece_autorizacao(linha: bytes) -> bool:
    """A linha começa como uma autorização, válida ou não."""
    return linha.startswith((PREFIXO_AUTORIZACAO + SEPARADOR).encode("ascii"))


def interpretar_autorizacao(linha: bytes) -> Autorizacao:
    """Interpreta a linha de autorização — o lado do UNO, usado pelo dublê.

    Exige a forma exata: sem espaços, criticidade de um dígito.

    Raises:
        LinhaInvalidaError: tipo desconhecido, criticidade fora de 0..3 ou campos
            a mais.
    """
    campos = _texto(linha).split(SEPARADOR)
    if len(campos) != 3 or campos[0] != PREFIXO_AUTORIZACAO:
        raise LinhaInvalidaError(f"autorização espera AUT,<VEICULO>,<0..3>, veio {linha!r}")
    veiculo = _membro(TipoVeiculo, campos[1], "veículo")
    if len(campos[2]) != 1:
        raise LinhaInvalidaError(f"criticidade de um dígito, veio {campos[2]!r}")
    try:
        return Autorizacao(veiculo, _natural(campos[2], "criticidade"))
    except LinhaInvalidaError:
        raise
    except ProtocoloError as erro:
        raise LinhaInvalidaError(str(erro)) from erro


# ---------------------------------------------------------------------------
# UNO -> notebook
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Telemetria:
    """`ST,<ms>,<s1s2s3s4>,<C|E>,<rua_ativa>,<rua_fila>,<aut>` (`context/05` §4.2).

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
        autorizacoes: A criticidade que o UNO tem para cada tipo, na ordem de
            `TIPOS_DA_BANCADA`; 0 é sem ocorrência. Na linha, três dígitos
            (`100`: só a ambulância, com risco à vida). É por aqui que o
            backend confere se o UNO tem a lista da Central.
    """

    t_dispositivo_ms: int
    cores: tuple[Cor, Cor, Cor, Cor]
    regime: Regime
    rua_ativa: int | None = None
    rua_fila: int | None = None
    autorizacoes: Autorizacoes = NENHUMA_AUTORIZACAO

    def __post_init__(self) -> None:
        if len(self.autorizacoes) != len(TIPOS_DA_BANCADA):
            raise ProtocoloError(f"autorizações de {len(TIPOS_DA_BANCADA)} tipos")
        for criticidade in self.autorizacoes:
            _validar_criticidade(criticidade)

    def criticidade(self, tipo: TipoVeiculo) -> int:
        """A criticidade que o UNO tem para o tipo; 0 é sem ocorrência."""
        return self.autorizacoes[TIPOS_DA_BANCADA.index(tipo)]

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
            "".join(str(c) for c in self.autorizacoes),
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


def _autorizacoes(texto: str) -> Autorizacoes:
    if len(texto) != len(TIPOS_DA_BANCADA):
        raise LinhaInvalidaError(f"autorizações precisam de 3 dígitos, veio {texto!r}")
    a, b, c = (_natural(digito, "criticidade") for digito in texto)
    if max(a, b, c) > CRITICIDADE_MAXIMA:
        raise LinhaInvalidaError(f"criticidade fora de 0..{CRITICIDADE_MAXIMA}: {texto!r}")
    return (a, b, c)


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
            if len(campos) != 7:
                raise LinhaInvalidaError(f"ST espera 7 campos, veio {len(campos)}")
            return Telemetria(
                t_dispositivo_ms=_natural(campos[1], "ms"),
                cores=_cores(campos[2]),
                regime=_membro(Regime, campos[3], "regime"),
                rua_ativa=_rua_ou_zero(campos[4], "rua_ativa"),
                rua_fila=_rua_ou_zero(campos[5], "rua_fila"),
                autorizacoes=_autorizacoes(campos[6]),
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
