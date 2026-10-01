"""Confirmação da emergência — P20.

Os quatro desfechos de `autorizar()`. O que mais importa é o terceiro: a tag
**reconhecida** de um veículo **sem ocorrência** não autoriza — é a ambulância
voltando para a base, que antes da P20 abriria o corredor verde.
"""

from __future__ import annotations

from core.autorizacao import MotivoAutorizacao, OcorrenciaAtiva, autorizar
from core.modelos import Criticidade

OCORRENCIA = OcorrenciaAtiva(id_ocorrencia=1, criticidade=Criticidade.RISCO_VIDA)


def test_tag_desconhecida_nao_autoriza() -> None:
    resultado = autorizar(veiculo_ativo=None, ocorrencia=None)

    assert not resultado.autorizado
    assert resultado.motivo is MotivoAutorizacao.TAG_DESCONHECIDA
    assert resultado.criticidade is None


def test_veiculo_inativo_nao_autoriza_nem_com_ocorrencia() -> None:
    """Veículo em manutenção não volta à rua por ter uma ocorrência esquecida aberta."""
    resultado = autorizar(veiculo_ativo=False, ocorrencia=OCORRENCIA)

    assert not resultado.autorizado
    assert resultado.motivo is MotivoAutorizacao.VEICULO_INATIVO


def test_tag_reconhecida_sem_ocorrencia_nao_autoriza() -> None:
    """Identidade não é emergência: sem ocorrência aberta, sem prioridade."""
    resultado = autorizar(veiculo_ativo=True, ocorrencia=None)

    assert not resultado.autorizado
    assert resultado.motivo is MotivoAutorizacao.SEM_OCORRENCIA
    assert resultado.criticidade is None


def test_tag_reconhecida_com_ocorrencia_autoriza_com_a_criticidade_dela() -> None:
    ocorrencia = OcorrenciaAtiva(id_ocorrencia=7, criticidade=Criticidade.RISCO_COLETIVO)

    resultado = autorizar(veiculo_ativo=True, ocorrencia=ocorrencia)

    assert resultado.autorizado
    assert resultado.motivo is MotivoAutorizacao.AUTORIZADO
    assert resultado.criticidade is Criticidade.RISCO_COLETIVO
    assert resultado.ocorrencia == ocorrencia
