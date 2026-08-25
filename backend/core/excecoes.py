"""Exceções de domínio — `context/08` §3.

Todas descendem de `ErroDominio`, para que a fronteira (API, adaptadores) consiga
distinguir "o domínio recusou" de "algo quebrou". A distinção importa: recusa de
domínio vira resposta HTTP 4xx e log de decisão; falha inesperada vira 5xx e
incidente.
"""

from __future__ import annotations


class DominioError(Exception):
    """Raiz das exceções do núcleo de decisão."""


class PreempcaoInvalidaError(DominioError):
    """A preempção pedida não pode ser executada no estado atual."""


class FaseInexistenteError(DominioError):
    """A fase indicada não existe no cruzamento."""


class InvarianteVioladoError(DominioError):
    """Um invariante de segurança de `context/01` §6 foi violado.

    Nunca deve ser capturada e ignorada. O tratamento correto é o fail-safe:
    abortar a preempção, voltar ao ciclo fixo e registrar o incidente.
    """


class ConfiguracaoInvalidaError(DominioError):
    """Parâmetros ou topologia inconsistentes.

    Levantada na carga, não em tempo de decisão: um `verde_min_s` maior que
    `verde_max_s` precisa falhar antes de a simulação começar, não no meio das
    600 execuções.
    """
