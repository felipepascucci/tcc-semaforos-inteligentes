"""`GET /metricas/resumo` — agregados para o dashboard, calculados no banco.

Tudo aqui é contagem ou percentil sobre linhas gravadas por execução real. Nada
é número do capítulo 5: o capítulo 5 sai de `analysis/`, a partir dos CSV.

A latência segue as regras de cada ambiente:

* **SIMULACAO** (RNF01) — p95 e p99 de `latencia_decisao_ms`, nunca a média
  (decisão P2). `percentile_disc` devolve um valor medido, sem interpolação,
  como o posto mais próximo de `sim/controlador/coletor.py`.
* **HARDWARE** (H3) — mínimo, mediana e máximo de `latencia_total_ms`, com o
  `n`. Desde 2026-10-06 H3 se mede em 100 passagens (`context/09`), e o p95
  oficial sai de `analysis/`, sobre o `latencia_bancada.csv`.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Deteccao,
    ExecucaoSimulacao,
    LogPrioridade,
    MetricaLatencia,
    Ocorrencia,
    PedidoSimulacao,
)


def _contagem_por(sessao: Session, coluna: Any) -> dict[str, int]:
    linhas = sessao.execute(select(coluna, func.count()).group_by(coluna)).all()
    return {str(getattr(chave, "value", chave)): int(n) for chave, n in linhas}


def _latencia_simulacao(sessao: Session) -> dict[str, Any]:
    coluna = MetricaLatencia.latencia_decisao_ms
    n, p95, p99 = sessao.execute(
        select(
            func.count(coluna),
            func.percentile_disc(0.95).within_group(coluna),
            func.percentile_disc(0.99).within_group(coluna),
        ).where(MetricaLatencia.ambiente == "SIMULACAO")
    ).one()
    return {"n": int(n), "p95_decisao_ms": p95, "p99_decisao_ms": p99}


def _latencia_hardware(sessao: Session) -> dict[str, Any]:
    coluna = MetricaLatencia.latencia_total_ms
    n, minimo, mediana, maximo = sessao.execute(
        select(
            func.count(coluna),
            func.min(coluna),
            func.percentile_disc(0.5).within_group(coluna),
            func.max(coluna),
        ).where(MetricaLatencia.ambiente == "HARDWARE")
    ).one()
    return {
        "n": int(n),
        "min_total_ms": minimo,
        "mediana_total_ms": mediana,
        "max_total_ms": maximo,
    }


def resumo(sessao: Session) -> dict[str, Any]:
    deteccoes = sessao.execute(
        select(
            func.count(),
            func.count().filter(Deteccao.reconhecido),
            func.count().filter(Deteccao.autorizado),
        )
    ).one()
    return {
        "priorizacoes": {
            "total": sessao.scalar(select(func.count()).select_from(LogPrioridade)) or 0,
            "por_status": _contagem_por(sessao, LogPrioridade.status_execucao),
        },
        "deteccoes": {
            "total": int(deteccoes[0]),
            "reconhecidas": int(deteccoes[1]),
            "autorizadas": int(deteccoes[2]),
        },
        "ocorrencias_ativas": sessao.scalar(
            select(func.count()).where(Ocorrencia.encerrada_em.is_(None))
        )
        or 0,
        "latencia": {
            "simulacao": _latencia_simulacao(sessao),
            "hardware": _latencia_hardware(sessao),
        },
        "simulacoes": {
            "execucoes": sessao.scalar(select(func.count()).select_from(ExecucaoSimulacao)) or 0,
            "pedidos_por_status": _contagem_por(sessao, PedidoSimulacao.status),
        },
    }
