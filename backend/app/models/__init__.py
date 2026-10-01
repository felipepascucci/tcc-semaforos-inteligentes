"""Models SQLAlchemy — as 13 tabelas de `context/03`.

Importar tudo aqui não é conveniência: o Alembic e o mapeador do SQLAlchemy só
enxergam as tabelas que já foram importadas quando `Base.metadata` é consultado.
Um model fora desta lista simplesmente não aparece na migration — e a falha é
silenciosa.

As quatro tabelas do texto original do TCC (`context/03` §1) são `Semaforo`,
`VeiculoEmergencia`, `LogPrioridade` e `MetricaSimulacao`. As outras nove são
extensões operacionais, e o capítulo 4 precisa ser atualizado para incluí-las
(pendência P4). A nona é `Ocorrencia`, da P20.
"""

from app.models.base import Base, CriadoEmMixin
from app.models.dispositivo import Deteccao, DispositivoIot
from app.models.enums import (
    ESTADO_SINAL,
    MODO_CONTROLE,
    STATUS_EXECUCAO,
    STATUS_OPERACAO,
    TIPO_VEICULO,
    EstadoSinal,
    ModoControle,
    StatusExecucao,
    StatusOperacao,
    TipoVeiculo,
)
from app.models.log import LogPrioridade
from app.models.metrica import MetricaLatencia, MetricaSimulacao, MetricaViaTransversal
from app.models.ocorrencia import Ocorrencia
from app.models.semaforo import FaseSemaforo, Semaforo
from app.models.simulacao import EstadoSemaforoAmostra, ExecucaoSimulacao
from app.models.veiculo import TagRfid, VeiculoEmergencia

#: Os cinco tipos ENUM nativos do Postgres, na ordem em que a migration os cria.
TIPOS_ENUM = (ESTADO_SINAL, TIPO_VEICULO, STATUS_OPERACAO, STATUS_EXECUCAO, MODO_CONTROLE)

__all__ = [
    "ESTADO_SINAL",
    "MODO_CONTROLE",
    "STATUS_EXECUCAO",
    "STATUS_OPERACAO",
    "TIPOS_ENUM",
    "TIPO_VEICULO",
    "Base",
    "CriadoEmMixin",
    "Deteccao",
    "DispositivoIot",
    "EstadoSemaforoAmostra",
    "EstadoSinal",
    "ExecucaoSimulacao",
    "FaseSemaforo",
    "LogPrioridade",
    "MetricaLatencia",
    "MetricaSimulacao",
    "MetricaViaTransversal",
    "ModoControle",
    "Ocorrencia",
    "Semaforo",
    "StatusExecucao",
    "StatusOperacao",
    "TagRfid",
    "TipoVeiculo",
    "VeiculoEmergencia",
]
