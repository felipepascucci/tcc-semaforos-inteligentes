"""Gravação do fluxo de tempo real: detecção → priorização → latência.

Estas três tabelas têm volume baixo (uma linha por evento de priorização, não
por passo de simulação) e **precisam da chave gerada**: `metrica_latencia.fk_log`
aponta para o `log_prioridade` recém-criado. Por isso a gravação aqui é síncrona
e devolve o objeto — ao contrário de `fila_lote.py`, que é para o caminho quente
e não devolve id.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Deteccao, LogPrioridade, MetricaLatencia, StatusExecucao


def registrar_deteccao(
    sessao: Session,
    *,
    id_correlacao: uuid.UUID,
    origem: str,
    reconhecido: bool,
    uid_bruto: str | None = None,
    fk_dispositivo: int | None = None,
    fk_veiculo: int | None = None,
    rssi: int | None = None,
    sequencia: int | None = None,
) -> Deteccao:
    """Grava uma leitura, reconhecida ou não.

    Gravar as **não** reconhecidas é requisito, não zelo: é o registro da
    tentativa com UID desconhecido exigido por `context/02` §6, e é o
    denominador da taxa de reconhecimento do RNF05.
    """
    deteccao = Deteccao(
        id_correlacao=id_correlacao,
        origem=origem,
        fk_dispositivo=fk_dispositivo,
        fk_veiculo=fk_veiculo,
        uid_bruto=uid_bruto,
        reconhecido=reconhecido,
        rssi=rssi,
        sequencia=sequencia,
    )
    sessao.add(deteccao)
    sessao.flush()
    return deteccao


def registrar_log_prioridade(
    sessao: Session,
    *,
    id_correlacao: uuid.UUID,
    fk_semaforo: int,
    timestamp_inicio: datetime,
    status_execucao: StatusExecucao,
    motivo: str,
    fk_veiculo: int | None = None,
    fk_execucao: int | None = None,
    fk_metrica: int | None = None,
    timestamp_fim: datetime | None = None,
    ganho_tempo_segundos: int | None = None,
    fase_anterior: int | None = None,
    fase_aplicada: int | None = None,
) -> LogPrioridade:
    """Registra uma tentativa de priorização.

    `motivo` não é opcional na assinatura de propósito. Um log de decisão sem
    justificativa não sustenta uma defesa (`context/01` §9): é o campo que
    explica na banca *por que* o sistema agiu, e o que distingue
    `CONFLITO_ADIADO` legítimo de bug.
    """
    log = LogPrioridade(
        id_correlacao=id_correlacao,
        fk_veiculo=fk_veiculo,
        fk_semaforo=fk_semaforo,
        fk_metrica=fk_metrica,
        fk_execucao=fk_execucao,
        timestamp_inicio=timestamp_inicio,
        timestamp_fim=timestamp_fim,
        ganho_tempo_segundos=ganho_tempo_segundos,
        status_execucao=status_execucao,
        motivo=motivo,
        fase_anterior=fase_anterior,
        fase_aplicada=fase_aplicada,
    )
    sessao.add(log)
    sessao.flush()
    return log


def registrar_latencia(
    sessao: Session,
    *,
    id_correlacao: uuid.UUID,
    t_deteccao: datetime,
    t_decisao: datetime,
    ambiente: str,
    fk_log: int | None = None,
    t_atuacao: datetime | None = None,
) -> MetricaLatencia:
    """Grava os carimbos de uma priorização (decisão P2).

    `latencia_decisao_ms` **não** é passada: é coluna gerada pelo Postgres a
    partir de `t_decisao - t_deteccao`, para que não exista a possibilidade de o
    valor gravado divergir dos carimbos que o originaram.

    `latencia_total_ms` é calculada aqui porque `t_atuacao` pode não existir
    (preempção abortada) e porque é carimbada **na chegada do ACK**, não no envio
    do comando — medir o envio mediria só a velocidade do próprio código
    (`contrato-hardware-software.md` §10).
    """
    latencia = MetricaLatencia(
        id_correlacao=id_correlacao,
        fk_log=fk_log,
        t_deteccao=t_deteccao,
        t_decisao=t_decisao,
        t_atuacao=t_atuacao,
        latencia_total_ms=(
            round((t_atuacao - t_deteccao).total_seconds() * 1000) if t_atuacao else None
        ),
        ambiente=ambiente,
    )
    sessao.add(latencia)
    sessao.flush()
    return latencia
