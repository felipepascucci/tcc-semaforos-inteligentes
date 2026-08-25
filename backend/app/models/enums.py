"""Enums do domínio, espelhando os `CREATE TYPE` de `context/03` §3.1.

Os nomes dos tipos no Postgres (`estado_sinal`, `tipo_veiculo`, ...) e os valores
são exatamente os do documento — são parte do schema que já foi entregue no
texto do TCC e não podem ser renomeados sem sinalizar correção no capítulo 4
(`context/03` §1).
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum as EnumSQL


class EstadoSinal(StrEnum):
    """Cor exibida por um acesso semafórico."""

    VERDE = "VERDE"
    AMARELO = "AMARELO"
    VERMELHO = "VERMELHO"


class TipoVeiculo(StrEnum):
    """Tipo do veículo de emergência. A ordem de prioridade vive em `parametros.yaml`."""

    AMBULANCIA = "AMBULANCIA"
    BOMBEIRO = "BOMBEIRO"
    POLICIA = "POLICIA"


class StatusOperacao(StrEnum):
    """Situação operacional de um ativo (semáforo, veículo, dispositivo)."""

    ATIVO = "ATIVO"
    INATIVO = "INATIVO"
    MANUTENCAO = "MANUTENCAO"
    FALHA = "FALHA"


class StatusExecucao(StrEnum):
    """Desfecho de uma tentativa de priorização.

    `CONFLITO_ADIADO` é o desfecho de E8 quando dois VEs demandam fases
    conflitantes no mesmo TLS e um precisa esperar (`context/01` §5.2).
    `ABORTADO_SEGURANCA` registra o fail-safe por violação de invariante.
    """

    SUCESSO = "SUCESSO"
    FALHA = "FALHA"
    TIMEOUT = "TIMEOUT"
    CONFLITO_ADIADO = "CONFLITO_ADIADO"
    ABORTADO_SEGURANCA = "ABORTADO_SEGURANCA"


class ModoControle(StrEnum):
    """Os três braços do experimento (`context/04`).

    `FIXO` é o baseline; `PREEMPCAO` isola o efeito de H1; `PREEMPCAO_COMPENSADA`
    acrescenta E7 e é o braço que sustenta H2.
    """

    FIXO = "FIXO"
    PREEMPCAO = "PREEMPCAO"
    PREEMPCAO_COMPENSADA = "PREEMPCAO_COMPENSADA"


def _tipo_pg(enum: type[StrEnum], nome: str) -> EnumSQL:
    """Mapeia um StrEnum para um ENUM nativo do Postgres.

    `values_callable` grava o *valor* do membro, não o nome. Aqui os dois
    coincidem, mas depender dessa coincidência é frágil: basta alguém acrescentar
    um membro com nome diferente do valor para o banco divergir do domínio.
    """
    return EnumSQL(
        enum,
        name=nome,
        native_enum=True,
        create_constraint=False,
        values_callable=lambda e: [membro.value for membro in e],
    )


ESTADO_SINAL = _tipo_pg(EstadoSinal, "estado_sinal")
TIPO_VEICULO = _tipo_pg(TipoVeiculo, "tipo_veiculo")
STATUS_OPERACAO = _tipo_pg(StatusOperacao, "status_operacao")
STATUS_EXECUCAO = _tipo_pg(StatusExecucao, "status_execucao")
MODO_CONTROLE = _tipo_pg(ModoControle, "modo_controle")
