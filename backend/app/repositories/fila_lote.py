"""Fila de gravação em lote — a regra crítica de `context/03` §4.1.

**Nunca escrever no banco dentro do loop de simulação.** O
`traci.simulationStep()` roda a 10 Hz; um `INSERT` síncrono por passo não só
derruba o desempenho como **contamina a medição de latência** — que é o dado que
sustenta RNF01 e H3. Uma latência de decisão medida junto com um round-trip de
banco não mede o motor, mede a rede.

O contrato desta fila é, portanto: `enfileirar()` **nunca** toca o banco. Ela só
acumula em memória. A escrita acontece em `descarregar()`, chamado quando a
política manda — 500 registros ou 5 s, o que vier primeiro — ou no fim da
execução.
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import insert
from sqlalchemy.orm import Session, sessionmaker

from app.models.base import Base


@dataclass(frozen=True)
class PoliticaDeFlush:
    """Quando o lote acumulado deve ir para o banco.

    Os dois limites existem por motivos diferentes. `max_registros` protege a
    memória numa execução intensa; `max_intervalo_s` garante que uma execução
    lenta ou quase vazia não deixe dados presos indefinidamente — o dashboard
    lê do banco, e um lote que nunca fecha é um dashboard que nunca atualiza.
    """

    max_registros: int = 500
    max_intervalo_s: float = 5.0


@dataclass
class EstatisticasFila:
    """Contabilidade da fila, para o relatório de validação."""

    enfileirados: int = 0
    gravados: int = 0
    descargas: int = 0
    maior_lote: int = 0

    @property
    def pendentes(self) -> int:
        return self.enfileirados - self.gravados


@dataclass
class FilaEmLote:
    """Acumula registros em memória e os grava em lote.

    Uso típico no controlador da simulação::

        with FilaEmLote(fabrica) as fila:
            for passo in simulacao:
                fila.enfileirar(EstadoSemaforoAmostra, {...})
                fila.descarregar_se_necessario()

    O `with` garante a descarga final: sair do bloco sem gravar o resto do lote
    perderia os últimos até 499 registros da execução, silenciosamente.
    """

    fabrica_sessao: sessionmaker[Session]
    politica: PoliticaDeFlush = field(default_factory=PoliticaDeFlush)
    relogio: Callable[[], float] = time.monotonic

    _pendentes: dict[type[Base], list[dict[str, Any]]] = field(
        default_factory=lambda: defaultdict(list), init=False, repr=False
    )
    _total_pendente: int = field(default=0, init=False)
    _ultima_descarga: float = field(default=0.0, init=False)
    estatisticas: EstatisticasFila = field(default_factory=EstatisticasFila, init=False)

    def __post_init__(self) -> None:
        self._ultima_descarga = self.relogio()

    # -- acumulação (sem I/O) ------------------------------------------------

    def enfileirar(self, modelo: type[Base], registro: Mapping[str, Any]) -> None:
        """Acumula um registro em memória, sem tocar o banco.

        Args:
            modelo: A classe do model — ex.: `EstadoSemaforoAmostra`.
            registro: Colunas e valores, como dicionário.
        """
        self._pendentes[modelo].append(dict(registro))
        self._total_pendente += 1
        self.estatisticas.enfileirados += 1

    def enfileirar_varios(self, modelo: type[Base], registros: list[Mapping[str, Any]]) -> None:
        """Acumula vários registros do mesmo model."""
        for registro in registros:
            self.enfileirar(modelo, registro)

    # -- política ------------------------------------------------------------

    @property
    def pendentes(self) -> int:
        """Quantos registros aguardam gravação."""
        return self._total_pendente

    def deve_descarregar(self) -> bool:
        """Diz se a política já foi atingida, sem gravar nada."""
        if self._total_pendente == 0:
            return False
        if self._total_pendente >= self.politica.max_registros:
            return True
        return (self.relogio() - self._ultima_descarga) >= self.politica.max_intervalo_s

    def descarregar_se_necessario(self) -> int:
        """Grava só se a política mandar. É o que se chama a cada passo do loop."""
        return self.descarregar() if self.deve_descarregar() else 0

    # -- gravação ------------------------------------------------------------

    def descarregar(self) -> int:
        """Grava tudo o que está pendente, em lote.

        Usa `insert()` com lista de dicionários, que o SQLAlchemy traduz para um
        `executemany` — uma ida ao banco por tabela, não uma por registro.

        As tabelas são gravadas na ordem topológica de `Base.metadata`, para que
        uma linha nunca chegue antes daquela que sua chave estrangeira aponta.

        Returns:
            Quantidade de registros gravados.

        Raises:
            Exception: qualquer falha do banco é propagada após o rollback. A
                fila **não** engole erro de gravação: dado experimental perdido
                em silêncio é pior que execução interrompida.
        """
        if self._total_pendente == 0:
            return 0

        ordem = {tabela: posicao for posicao, tabela in enumerate(Base.metadata.sorted_tables)}
        modelos = sorted(self._pendentes, key=lambda m: ordem[m.__table__])

        gravados = 0
        with self.fabrica_sessao() as sessao:
            try:
                for modelo in modelos:
                    registros = self._pendentes[modelo]
                    if not registros:
                        continue
                    sessao.execute(insert(modelo), registros)
                    gravados += len(registros)
                sessao.commit()
            except Exception:
                sessao.rollback()
                raise

        self._pendentes.clear()
        self._total_pendente = 0
        self._ultima_descarga = self.relogio()
        self.estatisticas.gravados += gravados
        self.estatisticas.descargas += 1
        self.estatisticas.maior_lote = max(self.estatisticas.maior_lote, gravados)
        return gravados

    # -- ciclo de vida -------------------------------------------------------

    def __enter__(self) -> FilaEmLote:
        return self

    def __exit__(self, *_: object) -> None:
        self.descarregar()


@contextmanager
def fila_de_gravacao(
    fabrica_sessao: sessionmaker[Session], politica: PoliticaDeFlush | None = None
) -> Iterator[FilaEmLote]:
    """Abre uma fila e garante a descarga final."""
    fila = FilaEmLote(fabrica_sessao, politica or PoliticaDeFlush())
    try:
        yield fila
    finally:
        fila.descarregar()
