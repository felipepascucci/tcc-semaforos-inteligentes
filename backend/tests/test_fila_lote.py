"""A política da fila de gravação em lote (`context/03` §4.1).

Estes testes **não** usam banco. A política é lógica pura, e testá-la contra um
Postgres real só tornaria lento o que precisa ser rápido — além de não conseguir
verificar o mais importante: que `enfileirar()` não faz I/O nenhum.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.models import EstadoSemaforoAmostra, MetricaViaTransversal
from app.repositories.fila_lote import FilaEmLote, PoliticaDeFlush


class SessaoFalsa:
    """Registra o que teria sido executado, sem tocar em banco."""

    def __init__(self, registro: list[tuple[Any, int]]) -> None:
        self.registro = registro
        self.commits = 0

    def __enter__(self) -> SessaoFalsa:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, declaracao: Any, registros: list[dict[str, Any]]) -> None:
        self.registro.append((declaracao.table.name, len(registros)))

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        return None


class FabricaFalsa:
    def __init__(self) -> None:
        self.execucoes: list[tuple[Any, int]] = []
        self.sessoes: list[SessaoFalsa] = []

    def __call__(self) -> SessaoFalsa:
        sessao = SessaoFalsa(self.execucoes)
        self.sessoes.append(sessao)
        return sessao


class RelogioFalso:
    """Relógio controlado pelo teste — a alternativa seria dormir 5 s de verdade."""

    def __init__(self) -> None:
        self.agora = 0.0

    def __call__(self) -> float:
        return self.agora

    def avancar(self, segundos: float) -> None:
        self.agora += segundos


@pytest.fixture
def fabrica() -> FabricaFalsa:
    return FabricaFalsa()


@pytest.fixture
def relogio() -> RelogioFalso:
    return RelogioFalso()


def _amostra(t: float) -> dict[str, Any]:
    return {"fk_execucao": 1, "fk_semaforo": 1, "t_simulacao": t, "fase": 1, "estado": "VERDE"}


def test_enfileirar_nao_toca_o_banco(fabrica: FabricaFalsa, relogio: RelogioFalso) -> None:
    """A garantia central: acumular é O(1) e sem I/O."""
    fila = FilaEmLote(fabrica, PoliticaDeFlush(max_registros=500), relogio)

    for i in range(499):
        fila.enfileirar(EstadoSemaforoAmostra, _amostra(i * 0.1))

    assert fabrica.execucoes == []
    assert fabrica.sessoes == []
    assert fila.pendentes == 499


def test_descarrega_ao_atingir_o_limite_de_registros(
    fabrica: FabricaFalsa, relogio: RelogioFalso
) -> None:
    fila = FilaEmLote(fabrica, PoliticaDeFlush(max_registros=500), relogio)

    for i in range(499):
        fila.enfileirar(EstadoSemaforoAmostra, _amostra(i * 0.1))
        assert fila.descarregar_se_necessario() == 0

    fila.enfileirar(EstadoSemaforoAmostra, _amostra(49.9))
    assert fila.descarregar_se_necessario() == 500
    assert fabrica.execucoes == [("estado_semaforo_amostra", 500)]
    assert fila.pendentes == 0


def test_descarrega_ao_atingir_o_limite_de_tempo(
    fabrica: FabricaFalsa, relogio: RelogioFalso
) -> None:
    """Execução lenta não pode deixar dado preso: o dashboard lê do banco."""
    fila = FilaEmLote(fabrica, PoliticaDeFlush(max_registros=500, max_intervalo_s=5.0), relogio)
    fila.enfileirar(EstadoSemaforoAmostra, _amostra(0.0))

    relogio.avancar(4.9)
    assert fila.descarregar_se_necessario() == 0

    relogio.avancar(0.1)
    assert fila.descarregar_se_necessario() == 1


def test_fila_vazia_nunca_descarrega(fabrica: FabricaFalsa, relogio: RelogioFalso) -> None:
    """Sem isso, o limite de tempo abriria uma transação vazia a cada 5 s."""
    fila = FilaEmLote(fabrica, PoliticaDeFlush(), relogio)
    relogio.avancar(3600)

    assert fila.deve_descarregar() is False
    assert fila.descarregar() == 0
    assert fabrica.sessoes == []


def test_grava_tabelas_em_ordem_de_dependencia(
    fabrica: FabricaFalsa, relogio: RelogioFalso
) -> None:
    """`metrica_via_transversal` e `estado_semaforo_amostra` dependem de execução.

    A ordem de gravação segue a ordenação topológica de `Base.metadata`, não a
    ordem em que o chamador enfileirou — senão uma linha poderia chegar antes
    daquela para a qual sua chave estrangeira aponta.
    """
    fila = FilaEmLote(fabrica, PoliticaDeFlush(), relogio)
    fila.enfileirar(
        MetricaViaTransversal,
        {
            "fk_execucao": 1,
            "fk_semaforo": 1,
            "tempo_espera_medio": 1,
            "fila_maxima": 1,
            "veiculos_processados": 1,
            "janela": "DURANTE",
        },
    )
    fila.enfileirar(EstadoSemaforoAmostra, _amostra(0.0))
    fila.descarregar()

    tabelas = [nome for nome, _ in fabrica.execucoes]
    assert set(tabelas) == {"estado_semaforo_amostra", "metrica_via_transversal"}
    assert len(fabrica.sessoes) == 1  # uma transação, não uma por tabela


def test_saida_do_contexto_descarrega_o_resto(fabrica: FabricaFalsa, relogio: RelogioFalso) -> None:
    """Sem isso, os últimos até 499 registros da execução se perderiam calados."""
    with FilaEmLote(fabrica, PoliticaDeFlush(max_registros=500), relogio) as fila:
        for i in range(7):
            fila.enfileirar(EstadoSemaforoAmostra, _amostra(i * 0.1))
        assert fabrica.execucoes == []

    assert fabrica.execucoes == [("estado_semaforo_amostra", 7)]


def test_falha_de_gravacao_propaga(relogio: RelogioFalso) -> None:
    """Dado experimental perdido em silêncio é pior que execução interrompida."""

    class SessaoQueFalha(SessaoFalsa):
        def execute(self, declaracao: Any, registros: list[dict[str, Any]]) -> None:
            raise RuntimeError("conexão caiu no meio do lote")

    class FabricaQueFalha(FabricaFalsa):
        def __call__(self) -> SessaoFalsa:
            sessao = SessaoQueFalha(self.execucoes)
            self.sessoes.append(sessao)
            return sessao

    fila = FilaEmLote(FabricaQueFalha(), PoliticaDeFlush(), relogio)
    fila.enfileirar(EstadoSemaforoAmostra, _amostra(0.0))

    with pytest.raises(RuntimeError, match="conexão caiu"):
        fila.descarregar()


def test_estatisticas_alimentam_o_relatorio_de_validacao(
    fabrica: FabricaFalsa, relogio: RelogioFalso
) -> None:
    fila = FilaEmLote(fabrica, PoliticaDeFlush(max_registros=10), relogio)
    for i in range(25):
        fila.enfileirar(EstadoSemaforoAmostra, _amostra(i * 0.1))
        fila.descarregar_se_necessario()

    assert fila.estatisticas.enfileirados == 25
    assert fila.estatisticas.gravados == 20
    assert fila.estatisticas.pendentes == 5
    assert fila.estatisticas.descargas == 2
    assert fila.estatisticas.maior_lote == 10
