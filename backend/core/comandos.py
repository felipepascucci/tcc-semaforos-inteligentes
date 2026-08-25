r"""Comandos abstratos — `context/01` §9.

O motor devolve **intenções**, não ações. Quem traduz `IR_PARA_FASE` em
`traci.trafficlight.setPhase()` ou em `PRE,3,20\n` é um adaptador. É essa
indireção que sustenta a afirmação central do trabalho: o modelo validado em
simulação é literalmente o mesmo que roda no protótipo.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TipoComando(StrEnum):
    """As cinco intenções que o motor sabe expressar."""

    ESTENDER_VERDE = "ESTENDER_VERDE"
    IR_PARA_FASE = "IR_PARA_FASE"
    LIBERAR = "LIBERAR"
    COMPENSAR = "COMPENSAR"
    FALLBACK_SEGURO = "FALLBACK_SEGURO"


@dataclass(frozen=True)
class Comando:
    """Uma intenção dirigida a um cruzamento.

    Attributes:
        tipo: O que fazer.
        id_semaforo: Cruzamento destinatário.
        fase_alvo: Fase de destino, para `IR_PARA_FASE`.
        duracao_s: Duração pretendida, em segundos.
        id_veiculo: VE que motivou o comando, quando houver.
        motivo: Justificativa legível da decisão.

    `motivo` tem valor padrão por compatibilidade com a definição de
    `context/01` §9, mas na prática é obrigatório: é o que aparece no dashboard e
    no relatório de validação, e é o que permite explicar na banca *por que* o
    sistema tomou cada decisão. Um log de decisão sem justificativa não sustenta
    uma defesa. Há teste garantindo que o motor nunca emite comando sem motivo.
    """

    tipo: TipoComando
    id_semaforo: str
    fase_alvo: int | None = None
    duracao_s: float | None = None
    id_veiculo: str | None = None
    motivo: str = ""


def fallback_seguro(id_semaforo: str, motivo: str) -> Comando:
    """Constrói o comando de fail-safe: abortar preempção e voltar ao ciclo fixo."""
    return Comando(tipo=TipoComando.FALLBACK_SEGURO, id_semaforo=id_semaforo, motivo=motivo)
