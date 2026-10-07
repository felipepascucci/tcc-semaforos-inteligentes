"""Medição de H3 na bancada — entrega 5.7, `context/05` §4.3.

H3 vai do instante em que o veículo lê a tag ao instante em que o UNO decide
atendê-lo, os dois no relógio do notebook:

* `t_deteccao` — primeiro byte de `Tag <UID> lida -> Enviando RUAn`, que o
  emissor imprime logo depois do `esp_now_send`. Durante a medição o emissor
  fica no USB do notebook (`--porta-veiculo`).
* `t_atuacao` — primeiro byte do `EV,…,PREEMP_INI,<rua>,…` do UNO.

**Só a detecção que vira `PREEMP_INI` é amostra.** Cada linha válida que chega
ao UNO gera exatamente um evento de decisão, escrito antes de qualquer outra
linha (`context/05` §4.2). Por isso cada detecção casa com o **primeiro evento
de decisão da mesma rua** carimbado depois dela, seja ele qual for. Se for
`FILA`, `RENOVADO` ou `DESCARTADO`, não houve atuação para medir, e a detecção
é registrada no log da ponte, não no CSV. Casar com "o próximo `PREEMP_INI`"
estaria errado: a detecção que vira `FILA` seria casada com a saída da fila,
segundos depois, e a latência sairia inflada por um tempo que não é do sistema.

**Todo desfecho vai para um segundo CSV** (`deteccoes_bancada.csv`), desde
2026-10-07: cada leitura que o emissor imprimiu, com o evento de decisão que
ela teve ou `SEM_DECISAO`. É o dado do RNF05 (`context/06` §6, item 4), cujo
denominador são as leituras impressas e cujo numerador são as que viraram
evento de decisão com a rua certa — o casamento já é por rua, então todo
desfecho que não é `SEM_DECISAO` chegou com a rua certa.

**O casamento é pelos carimbos, não pela ordem de leitura.** As duas portas são
lidas em paralelo, e a linha do emissor (~36 caracteres) termina de chegar
depois do começo da decisão do UNO, se a latência for curta. Então qualquer um
dos dois lados pode ser processado primeiro, e o casador guarda os dois por uma
janela.

Este módulo é **puro**: não lê relógio nem porta. Quem carimba é o transporte;
quem chama, a ponte.
"""

from __future__ import annotations

import csv
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final

from bridge.protocolo import EVENTOS_DE_DECISAO, Evento, LeituraVeiculo, TipoEvento

RAIZ: Final = Path(__file__).resolve().parents[1]

#: Onde as amostras de H3 vivem (`context/05` §6).
CSV_PADRAO: Final = RAIZ / "analysis" / "data" / "latencia_bancada.csv"

#: Onde vive cada desfecho de detecção, amostra de H3 ou não — o dado do RNF05.
CSV_DESFECHOS_PADRAO: Final = RAIZ / "analysis" / "data" / "deteccoes_bancada.csv"

#: Por quanto tempo uma detecção espera a decisão do UNO, e uma decisão espera a
#: detecção que a causou. É o limite do RF02 (3 s): a janela só existe para não
#: guardar as pendências para sempre, e precisa ser **folgada**. Uma janela
#: justa descartaria justamente as amostras lentas — o viés jogaria a favor da
#: hipótese. Detecção que passa dela sem decisão vai para o log como
#: `SEM_DECISAO` (ESP-NOW perdido, ou o receptor fora do RX).
JANELA_S: Final = 3.0

COLUNAS: Final = (
    "sessao",
    "t_deteccao",
    "t_atuacao",
    "latencia_total_ms",
    "rua",
    "uid",
    "veiculo",
    "uno_ms",
    "bytes_em_espera_deteccao",
    "bytes_em_espera_atuacao",
    "versao_codigo",
)

#: Uma linha por leitura do emissor. `t_decisao`, `latencia_ms`, `veiculo` e
#: `uno_ms` ficam vazios quando o desfecho é `SEM_DECISAO`.
COLUNAS_DESFECHOS: Final = (
    "sessao",
    "t_deteccao",
    "rua",
    "uid",
    "desfecho",
    "t_decisao",
    "latencia_ms",
    "veiculo",
    "uno_ms",
    "versao_codigo",
)


@dataclass(frozen=True)
class LeituraCarimbada:
    """O emissor leu uma tag e enviou: `LeituraVeiculo` com o instante dela."""

    t: datetime
    leitura: LeituraVeiculo
    bytes_em_espera: int = 0

    @property
    def rua(self) -> int:
        return self.leitura.rua


@dataclass(frozen=True)
class DecisaoCarimbada:
    """Um evento de decisão do UNO com o instante dele."""

    t: datetime
    evento: Evento
    bytes_em_espera: int = 0

    @property
    def rua(self) -> int | None:
        return self.evento.rua


@dataclass(frozen=True)
class AmostraH3:
    """Uma detecção que o UNO atendeu: uma amostra de H3."""

    deteccao: LeituraCarimbada
    decisao: DecisaoCarimbada

    @property
    def latencia_total_ms(self) -> float:
        return (self.decisao.t - self.deteccao.t).total_seconds() * 1000


@dataclass(frozen=True)
class Desfecho:
    """O que aconteceu com uma detecção.

    Attributes:
        deteccao: A leitura da tag.
        decisao: O evento de decisão casado; `None` se nenhum veio na janela.
    """

    deteccao: LeituraCarimbada
    decisao: DecisaoCarimbada | None

    @property
    def tipo(self) -> str:
        return "SEM_DECISAO" if self.decisao is None else self.decisao.evento.tipo.value

    @property
    def amostra(self) -> AmostraH3 | None:
        """A amostra de H3, só quando a decisão foi `PREEMP_INI`."""
        if self.decisao is None or self.decisao.evento.tipo is not TipoEvento.PREEMP_INI:
            return None
        return AmostraH3(self.deteccao, self.decisao)


@dataclass
class CasadorH3:
    """Casa cada detecção com a decisão que ela causou.

    Args:
        janela_s: Quanto um lado espera o outro. Ver `JANELA_S`.
    """

    janela_s: float = JANELA_S
    _deteccoes: list[LeituraCarimbada] = field(default_factory=list)
    _decisoes: list[DecisaoCarimbada] = field(default_factory=list)

    @property
    def pendentes(self) -> int:
        """Detecções esperando a decisão."""
        return len(self._deteccoes)

    def deteccao(self, deteccao: LeituraCarimbada) -> list[Desfecho]:
        """Uma linha `Tag … lida` chegou do emissor."""
        candidatas = [d for d in self._decisoes if d.rua == deteccao.rua and d.t > deteccao.t]
        if not candidatas:
            self._deteccoes.append(deteccao)
            return []
        decisao = min(candidatas, key=lambda d: d.t)
        self._decisoes.remove(decisao)
        return [Desfecho(deteccao, decisao)]

    def evento(self, decisao: DecisaoCarimbada) -> list[Desfecho]:
        """Um evento chegou do UNO. Só os de decisão interessam."""
        if decisao.evento.tipo not in EVENTOS_DE_DECISAO:
            return []
        candidatas = [d for d in self._deteccoes if d.rua == decisao.rua and d.t < decisao.t]
        if not candidatas:
            # Decisão sem detecção, por ora: injeção pela ponte, ou a linha do
            # emissor ainda não terminou de chegar.
            self._decisoes.append(decisao)
            return []
        deteccao = min(candidatas, key=lambda d: d.t)
        self._deteccoes.remove(deteccao)
        return [Desfecho(deteccao, decisao)]

    def expirar(self, agora: datetime) -> list[Desfecho]:
        """Fecha o que passou da janela; devolve as detecções sem decisão.

        Args:
            agora: O carimbo da linha mais recente do UNO. As linhas do UNO
                chegam em ordem, então toda decisão anterior a `agora` já foi
                vista.
        """
        limite = agora - timedelta(seconds=self.janela_s)
        vencidas = [d for d in self._deteccoes if d.t < limite]
        self._deteccoes = [d for d in self._deteccoes if d.t >= limite]
        self._decisoes = [d for d in self._decisoes if d.t >= limite]
        return [Desfecho(d, None) for d in vencidas]


def versao_do_codigo() -> str:
    """`git rev-parse --short HEAD`, ou `"desconhecida"` fora de um repositório."""
    resultado = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        cwd=RAIZ,
        check=False,
    )
    return resultado.stdout.strip() or "desconhecida"


@dataclass
class GravadorCsv:
    """Acrescenta amostras de H3 a um CSV, uma linha por amostra.

    O arquivo acumula sessões: cada execução da ponte é uma `sessao` (o
    instante em que ela subiu). A linha é gravada e o arquivo fechado a cada
    amostra, para que uma ponte derrubada no meio da medição não perca nada.

    Args:
        caminho: O CSV. Na bancada, `CSV_PADRAO`.
        sessao: Identifica a execução da ponte.
        versao_codigo: Versão do código que mediu.
    """

    caminho: Path
    sessao: datetime
    versao_codigo: str = field(default_factory=versao_do_codigo)

    def gravar(self, amostra: AmostraH3) -> None:
        evento = amostra.decisao.evento
        assert evento.veiculo is not None
        _acrescentar(
            self.caminho,
            COLUNAS,
            (
                self.sessao.isoformat(),
                amostra.deteccao.t.isoformat(),
                amostra.decisao.t.isoformat(),
                f"{amostra.latencia_total_ms:.3f}",
                amostra.deteccao.rua,
                amostra.deteccao.leitura.uid,
                evento.veiculo.value,
                evento.t_dispositivo_ms,
                amostra.deteccao.bytes_em_espera,
                amostra.decisao.bytes_em_espera,
                self.versao_codigo,
            ),
        )


@dataclass
class GravadorDesfechos:
    """Acrescenta cada desfecho de detecção a um CSV — o dado do RNF05.

    Mesmas regras do `GravadorCsv`: sessões acumuladas no mesmo arquivo, e o
    arquivo fechado a cada linha.

    Args:
        caminho: O CSV. Na bancada, `CSV_DESFECHOS_PADRAO`.
        sessao: Identifica a execução da ponte; a mesma do `GravadorCsv`.
        versao_codigo: Versão do código que mediu.
    """

    caminho: Path
    sessao: datetime
    versao_codigo: str = field(default_factory=versao_do_codigo)

    def gravar(self, desfecho: Desfecho) -> None:
        deteccao, decisao = desfecho.deteccao, desfecho.decisao
        veiculo = decisao.evento.veiculo if decisao is not None else None
        _acrescentar(
            self.caminho,
            COLUNAS_DESFECHOS,
            (
                self.sessao.isoformat(),
                deteccao.t.isoformat(),
                deteccao.rua,
                deteccao.leitura.uid,
                desfecho.tipo,
                "" if decisao is None else decisao.t.isoformat(),
                "" if decisao is None else f"{(decisao.t - deteccao.t).total_seconds() * 1000:.3f}",
                "" if veiculo is None else veiculo.value,
                "" if decisao is None else decisao.evento.t_dispositivo_ms,
                self.versao_codigo,
            ),
        )


def _acrescentar(caminho: Path, colunas: tuple[str, ...], linha: tuple[object, ...]) -> None:
    """Acrescenta uma linha ao CSV, com o cabeçalho se o arquivo for novo."""
    novo = not caminho.exists() or caminho.stat().st_size == 0
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("a", newline="", encoding="utf-8") as arquivo:
        escritor = csv.writer(arquivo)
        if novo:
            escritor.writerow(colunas)
        escritor.writerow(linha)
