"""Ocorrências contra um banco de verdade — decisão P20.

O que se prova aqui é o que só o banco garante: no máximo uma ocorrência aberta
por veículo, criticidade dentro da escala, e a detecção que registra se a tag
reconhecida estava ou não em serviço. A regra de autorização em si é pura e está
em `backend/tests/core/test_autorizacao.py`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Deteccao, Ocorrencia, TipoVeiculo, VeiculoEmergencia
from app.repositories import operacao
from app.repositories.ocorrencia import (
    OcorrenciaJaEncerradaError,
    abrir_ocorrencia,
    encerrar_ocorrencia,
    listar_ocorrencias_ativas,
    ocorrencia_ativa_do_veiculo,
)
from core.autorizacao import MotivoAutorizacao, autorizar
from core.modelos import Criticidade

pytestmark = pytest.mark.banco


@pytest.fixture
def id_veiculo(sessao: Session) -> int:
    """Uma ambulância de teste, obviamente artificial (context/08 §4.2)."""
    veiculo = VeiculoEmergencia(placa="TST0O01", tipo=TipoVeiculo.AMBULANCIA)
    sessao.add(veiculo)
    sessao.flush()
    return veiculo.id_veiculo


def test_veiculo_sem_ocorrencia_nao_esta_em_servico(sessao: Session, id_veiculo: int) -> None:
    """Estado inicial dos seeds: ninguém em serviço, a demo começa negando."""
    assert ocorrencia_ativa_do_veiculo(sessao, id_veiculo) is None
    assert autorizar(True, None).motivo is MotivoAutorizacao.SEM_OCORRENCIA


def test_ocorrencia_aberta_autoriza_com_a_criticidade_dela(
    sessao: Session, id_veiculo: int
) -> None:
    aberta = abrir_ocorrencia(
        sessao, fk_veiculo=id_veiculo, criticidade=Criticidade.RISCO_VIDA, descricao="PCR"
    )

    ativa = ocorrencia_ativa_do_veiculo(sessao, id_veiculo)

    assert ativa is not None
    assert ativa.id_ocorrencia == aberta.id_ocorrencia
    assert ativa.criticidade is Criticidade.RISCO_VIDA
    assert autorizar(True, ativa).autorizado


def test_segunda_ocorrencia_aberta_para_o_mesmo_veiculo_e_recusada_pelo_banco(
    sessao: Session, id_veiculo: int
) -> None:
    """Duas criticidades concorrentes para o mesmo VE seriam ambíguas para o motor."""
    abrir_ocorrencia(sessao, fk_veiculo=id_veiculo, criticidade=Criticidade.URGENCIA)

    with (
        pytest.raises(IntegrityError, match="uq_ocorrencia_aberta_por_veiculo"),
        sessao.begin_nested(),
    ):
        abrir_ocorrencia(sessao, fk_veiculo=id_veiculo, criticidade=Criticidade.RISCO_VIDA)


def test_depois_de_encerrar_pode_abrir_outra(sessao: Session, id_veiculo: int) -> None:
    """Encerrada, a ocorrência vira histórico e o veículo volta a poder ser despachado."""
    primeira = abrir_ocorrencia(sessao, fk_veiculo=id_veiculo, criticidade=Criticidade.URGENCIA)
    encerrar_ocorrencia(sessao, primeira.id_ocorrencia)
    assert ocorrencia_ativa_do_veiculo(sessao, id_veiculo) is None

    segunda = abrir_ocorrencia(sessao, fk_veiculo=id_veiculo, criticidade=Criticidade.RISCO_VIDA)

    ativa = ocorrencia_ativa_do_veiculo(sessao, id_veiculo)
    assert ativa is not None
    assert ativa.id_ocorrencia == segunda.id_ocorrencia
    assert sessao.get(Ocorrencia, primeira.id_ocorrencia).encerrada_em is not None  # type: ignore[union-attr]


def test_encerrar_duas_vezes_e_recusado(sessao: Session, id_veiculo: int) -> None:
    """Reencerrar apagaria o instante verdadeiro do fim do atendimento."""
    ocorrencia = abrir_ocorrencia(sessao, fk_veiculo=id_veiculo, criticidade=Criticidade.URGENCIA)
    encerrar_ocorrencia(sessao, ocorrencia.id_ocorrencia)

    with pytest.raises(OcorrenciaJaEncerradaError):
        encerrar_ocorrencia(sessao, ocorrencia.id_ocorrencia)


def test_criticidade_fora_da_escala_e_recusada_pelo_banco(sessao: Session, id_veiculo: int) -> None:
    """O `CHECK` é a última linha: um nível 7 não chega ao motor nem por SQL direto."""
    with (
        pytest.raises(IntegrityError, match="ck_ocorrencia_criticidade_na_escala"),
        sessao.begin_nested(),
    ):
        sessao.execute(
            text("INSERT INTO ocorrencia (fk_veiculo, criticidade) VALUES (:v, 7)"),
            {"v": id_veiculo},
        )


def test_painel_lista_os_em_servico_do_mais_critico_para_o_menos(sessao: Session) -> None:
    veiculos = [
        VeiculoEmergencia(placa=f"TST0O1{indice}", tipo=TipoVeiculo.BOMBEIRO) for indice in range(3)
    ]
    sessao.add_all(veiculos)
    sessao.flush()
    for veiculo, nivel in zip(
        veiculos,
        (Criticidade.URGENCIA, Criticidade.RISCO_VIDA, Criticidade.RISCO_COLETIVO),
        strict=True,
    ):
        abrir_ocorrencia(sessao, fk_veiculo=veiculo.id_veiculo, criticidade=nivel)

    assert [o.criticidade for o in listar_ocorrencias_ativas(sessao)] == [1, 2, 3]


def test_deteccao_de_tag_reconhecida_sem_ocorrencia_fica_registrada_como_nao_autorizada(
    sessao: Session, id_veiculo: int
) -> None:
    """É a ambulância que tentou abrir o corredor sem estar em serviço."""
    deteccao = operacao.registrar_deteccao(
        sessao,
        id_correlacao=uuid.uuid4(),
        origem="V2I_RFID",
        reconhecido=True,
        fk_veiculo=id_veiculo,
        uid_bruto="A34F219C",
    )

    lida = sessao.get(Deteccao, deteccao.id_deteccao)
    assert lida is not None
    assert lida.reconhecido
    assert not lida.autorizado
    assert lida.fk_ocorrencia is None


def test_deteccao_autorizada_aponta_a_ocorrencia_que_a_autorizou(
    sessao: Session, id_veiculo: int
) -> None:
    ocorrencia = abrir_ocorrencia(
        sessao, fk_veiculo=id_veiculo, criticidade=Criticidade.RISCO_COLETIVO
    )

    deteccao = operacao.registrar_deteccao(
        sessao,
        id_correlacao=uuid.uuid4(),
        origem="V2I_RFID",
        reconhecido=True,
        fk_veiculo=id_veiculo,
        autorizado=True,
        fk_ocorrencia=ocorrencia.id_ocorrencia,
    )

    assert deteccao.ocorrencia is not None
    assert deteccao.ocorrencia.criticidade == 2


def test_autorizacao_sem_ocorrencia_e_recusada_antes_de_gravar(
    sessao: Session, id_veiculo: int
) -> None:
    """Autorização precisa ser afirmada com a ocorrência, nunca presumida."""
    with pytest.raises(ValueError, match="P20"):
        operacao.registrar_deteccao(
            sessao,
            id_correlacao=uuid.uuid4(),
            origem="V2I_RFID",
            reconhecido=True,
            fk_veiculo=id_veiculo,
            autorizado=True,
        )


def test_encerramento_logo_apos_a_abertura_usa_o_relogio_do_banco(
    sessao: Session, id_veiculo: int
) -> None:
    """Regressão: abrir e encerrar a milissegundos de distância.

    `aberta_em` vem do `now()` do Postgres. O encerramento era carimbado com o
    relógio da aplicação, e com o banco em contêiner poucos milissegundos
    adiantado ele caía *antes* da abertura — o `CHECK` recusava um encerramento
    legítimo. Os dois carimbos agora vêm do mesmo relógio.
    """
    for _ in range(20):
        ocorrencia = abrir_ocorrencia(
            sessao, fk_veiculo=id_veiculo, criticidade=Criticidade.URGENCIA
        )
        encerrada = encerrar_ocorrencia(sessao, ocorrencia.id_ocorrencia)

        assert encerrada.encerrada_em is not None
        assert encerrada.encerrada_em >= encerrada.aberta_em


def test_encerramento_usa_o_instante_informado(sessao: Session, id_veiculo: int) -> None:
    ocorrencia = abrir_ocorrencia(sessao, fk_veiculo=id_veiculo, criticidade=Criticidade.URGENCIA)
    quando = datetime(2099, 1, 1, tzinfo=UTC)

    encerrada = encerrar_ocorrencia(sessao, ocorrencia.id_ocorrencia, quando=quando)

    assert encerrada.encerrada_em == quando
