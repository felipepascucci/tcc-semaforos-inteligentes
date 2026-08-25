"""Gravação do experimento: execuções, transições de fase e métricas agregadas.

A divisão de responsabilidade aqui reflete a decisão P5 e a regra de
`context/03` §4.1:

* `abrir_execucao` / `fechar_execucao` — uma vez por execução, síncrono.
* `transicao_para_fila` — milhares por execução, **sempre** via `FilaEmLote`,
  e apenas quando a execução é exemplar.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    EstadoSemaforoAmostra,
    EstadoSinal,
    ExecucaoSimulacao,
    MetricaSimulacao,
    MetricaViaTransversal,
    ModoControle,
)
from app.repositories.fila_lote import FilaEmLote


def abrir_execucao(
    sessao: Session,
    *,
    nome_cenario: str,
    modo: ModoControle,
    seed: int,
    duracao_s: int,
    arquivo_rede: str,
    parametros: dict[str, Any],
    versao_codigo: str | None = None,
    exemplar: bool = False,
) -> ExecucaoSimulacao:
    """Abre o registro de uma execução.

    `versao_codigo` e `parametros` são obrigatórios pela regra de
    reprodutibilidade (`context/03` §4.3): sem o hash do código e o snapshot dos
    parâmetros, não há como afirmar que rodar de novo com a mesma seed dá o mesmo
    resultado — e essa afirmação é o que sustenta o capítulo de resultados.

    A restrição única em `(nome_cenario, modo, seed)` faz o banco recusar uma
    segunda execução do mesmo ponto experimental. Isso é intencional: reexecução
    após descarte exige apagar a anterior, o que força o descarte a ser
    **documentado** em vez de silencioso (`context/06` §4).
    """
    execucao = ExecucaoSimulacao(
        nome_cenario=nome_cenario,
        modo=modo,
        seed=seed,
        duracao_s=duracao_s,
        arquivo_rede=arquivo_rede,
        versao_codigo=versao_codigo,
        parametros=parametros,
        exemplar=exemplar,
    )
    sessao.add(execucao)
    sessao.flush()
    return execucao


def fechar_execucao(sessao: Session, execucao: ExecucaoSimulacao) -> ExecucaoSimulacao:
    """Marca a execução como finalizada."""
    execucao.finalizada_em = datetime.now(UTC)
    sessao.flush()
    return execucao


def buscar_execucao(
    sessao: Session, *, nome_cenario: str, modo: ModoControle, seed: int
) -> ExecucaoSimulacao | None:
    """Localiza uma execução pelo ponto experimental (cenário, modo, seed)."""
    consulta = select(ExecucaoSimulacao).where(
        ExecucaoSimulacao.nome_cenario == nome_cenario,
        ExecucaoSimulacao.modo == modo,
        ExecucaoSimulacao.seed == seed,
    )
    return sessao.scalars(consulta).one_or_none()


def transicao_para_fila(
    fila: FilaEmLote,
    *,
    fk_execucao: int,
    fk_semaforo: int,
    t_simulacao: float,
    fase: int,
    estado: EstadoSinal,
    fase_anterior: int | None = None,
    duracao_fase_anterior_s: float | None = None,
    em_preempcao: bool = False,
    fila_total: int = 0,
) -> None:
    """Enfileira uma **transição** de fase (decisão P5).

    Chamada só quando a fase muda, nunca a cada passo. O coletor mantém a fase
    corrente de cada TLS em memória e calcula `duracao_fase_anterior_s` na
    virada — que é o campo que permite verificar I4 (verde mínimo) com uma
    consulta SQL em vez de reconstruir série temporal.

    Não toca o banco: só acumula na fila.
    """
    fila.enfileirar(
        EstadoSemaforoAmostra,
        {
            "fk_execucao": fk_execucao,
            "fk_semaforo": fk_semaforo,
            "t_simulacao": Decimal(str(round(t_simulacao, 2))),
            "fase_anterior": fase_anterior,
            "fase": fase,
            "estado": estado,
            "em_preempcao": em_preempcao,
            "fila_total": fila_total,
            "duracao_fase_anterior_s": (
                Decimal(str(round(duracao_fase_anterior_s, 2)))
                if duracao_fase_anterior_s is not None
                else None
            ),
        },
    )


def registrar_metrica_simulacao(
    sessao: Session,
    *,
    id_execucao: int,
    tempo_medio_resposta: Decimal,
    tempo_espera: Decimal,
    percentual_reducao: Decimal,
    latencia_ia: Decimal,
    cenario_simulado: str,
) -> MetricaSimulacao:
    """Grava os agregados de uma execução."""
    metrica = MetricaSimulacao(
        id_execucao=id_execucao,
        tempo_medio_resposta=tempo_medio_resposta,
        tempo_espera=tempo_espera,
        percentual_reducao=percentual_reducao,
        latencia_ia=latencia_ia,
        cenario_simulado=cenario_simulado,
    )
    sessao.add(metrica)
    sessao.flush()
    return metrica


def registrar_metrica_transversal(
    sessao: Session,
    *,
    fk_execucao: int,
    fk_semaforo: int,
    tempo_espera_medio: Decimal,
    fila_maxima: int,
    veiculos_processados: int,
    janela: str,
) -> MetricaViaTransversal:
    """Grava o custo nas transversais de uma janela (evidência de H2)."""
    metrica = MetricaViaTransversal(
        fk_execucao=fk_execucao,
        fk_semaforo=fk_semaforo,
        tempo_espera_medio=tempo_espera_medio,
        fila_maxima=fila_maxima,
        veiculos_processados=veiculos_processados,
        janela=janela,
    )
    sessao.add(metrica)
    sessao.flush()
    return metrica


def contar_transicoes(sessao: Session, id_execucao: int) -> int:
    """Quantas transições de fase foram persistidas para uma execução."""
    consulta = (
        select(func.count())
        .select_from(EstadoSemaforoAmostra)
        .where(EstadoSemaforoAmostra.fk_execucao == id_execucao)
    )
    return sessao.scalar(consulta) or 0
