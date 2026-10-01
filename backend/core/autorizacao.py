"""Confirmação da emergência — P20 (`context/09`).

**Emergência é estado declarado, não propriedade do veículo.** A tag RFID prova
*quem* é o veículo; só a ocorrência aberta pela central de despacho prova que ele
*está em serviço*. É a exigência do CTB, art. 29, VII, que concede prioridade ao
VE apenas "quando em serviço de urgência". Uma ambulância voltando para a base é
reconhecida e não recebe o corredor verde.

A regra é **determinística de propósito**. Confirmar a emergência é autenticação:
precisa ser auditável e não pode ter falso negativo estatístico — a detecção
acústica da sirene foi recusada exatamente por isso. O aprendizado de máquina do
trabalho fica em E8 (P19), onde há lacuna genuína.

Este módulo não lê banco: o serviço de `/deteccoes` busca o cadastro e a
ocorrência e chama `autorizar()`. Assim a regra é a mesma nos dois modos, fica
testável sem banco e não fura a regra de `context/01` §1. Na simulação o
equivalente é o parâmetro `criticidade` da rota, lido pelo adaptador SUMO.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from core.modelos import Criticidade


class MotivoAutorizacao(StrEnum):
    """Desfecho da confirmação, na ordem em que as condições são checadas."""

    TAG_DESCONHECIDA = "TAG_DESCONHECIDA"
    VEICULO_INATIVO = "VEICULO_INATIVO"
    SEM_OCORRENCIA = "SEM_OCORRENCIA"
    AUTORIZADO = "AUTORIZADO"


@dataclass(frozen=True)
class OcorrenciaAtiva:
    """A ocorrência aberta de um veículo, como o serviço a entrega.

    Attributes:
        id_ocorrencia: Chave em `ocorrencia`, para gravar em `deteccao`.
        criticidade: Nível atribuído pela central ao despachar.
    """

    id_ocorrencia: int
    criticidade: Criticidade


@dataclass(frozen=True)
class Autorizacao:
    """Resultado da confirmação.

    Attributes:
        motivo: Por que foi ou não autorizado — vai para o log e para a resposta.
        ocorrencia: A ocorrência que autorizou; `None` quando negado.
    """

    motivo: MotivoAutorizacao
    ocorrencia: OcorrenciaAtiva | None = None

    @property
    def autorizado(self) -> bool:
        """Se o VE pode entrar no `EstadoMalha` e disputar preempção."""
        return self.motivo is MotivoAutorizacao.AUTORIZADO

    @property
    def criticidade(self) -> Criticidade | None:
        """Criticidade com que o VE entra em E8; `None` quando negado."""
        return self.ocorrencia.criticidade if self.ocorrencia is not None else None


def autorizar(veiculo_ativo: bool | None, ocorrencia: OcorrenciaAtiva | None) -> Autorizacao:
    """Decide se o veículo identificado está em serviço de emergência.

    Dois fatores, os dois obrigatórios: **identidade** (tag reconhecida, de
    veículo ativo) e **estado** (ocorrência aberta).

    Args:
        veiculo_ativo: `None` se a tag não resolve para veículo nenhum — UID
            ausente de `tag_rfid` ou tag inativa; senão, se o veículo está com
            `status_operacional = 'ATIVO'`.
        ocorrencia: A ocorrência aberta do veículo, ou `None` se não houver.

    Returns:
        A autorização, com o motivo. Tag desconhecida vira HTTP 403 no serviço;
        os demais desfechos negados respondem 200, porque a credencial é válida.
    """
    if veiculo_ativo is None:
        return Autorizacao(MotivoAutorizacao.TAG_DESCONHECIDA)
    if not veiculo_ativo:
        return Autorizacao(MotivoAutorizacao.VEICULO_INATIVO)
    if ocorrencia is None:
        return Autorizacao(MotivoAutorizacao.SEM_OCORRENCIA)
    return Autorizacao(MotivoAutorizacao.AUTORIZADO, ocorrencia)
