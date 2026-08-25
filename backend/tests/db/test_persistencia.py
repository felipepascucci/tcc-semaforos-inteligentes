"""Teste de integração do critério de pronto do Bloco 1.

"grava e lê um `log_prioridade` completo" — completo significa com todas as
chaves estrangeiras preenchidas e o `id_correlacao` atravessando a cadeia
inteira: detecção → log → métrica de latência. É esse encadeamento que torna
possível o relatório de validação de `context/06` §5.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Deteccao,
    LogPrioridade,
    MetricaLatencia,
    ModoControle,
    Semaforo,
    StatusExecucao,
    TipoVeiculo,
    VeiculoEmergencia,
)
from app.repositories import cadastro, experimento, operacao

pytestmark = pytest.mark.banco


@pytest.fixture
def cenario(sessao: Session) -> dict[str, int]:
    """Cadastros mínimos, obviamente artificiais (context/08 §4.2)."""
    semaforo = Semaforo(
        codigo_externo="SEMAFORO_TESTE",
        descricao="Cruzamento de teste",
        latitude=Decimal("-23.55000000"),
        longitude=Decimal("-46.63000000"),
        tempo_ciclo=60,
    )
    veiculo = VeiculoEmergencia(
        placa="TST0A00", tipo=TipoVeiculo.AMBULANCIA, identificacao="Ambulância de teste"
    )
    sessao.add_all([semaforo, veiculo])
    sessao.flush()

    execucao = experimento.abrir_execucao(
        sessao,
        nome_cenario="cenario_teste",
        modo=ModoControle.PREEMPCAO,
        seed=1,
        duracao_s=60,
        arquivo_rede="malha_teste.net.xml",
        parametros={"raio_deteccao_m": 500, "verde_min_s": 7.0},
        versao_codigo="abc1234",
        exemplar=True,
    )
    return {
        "id_semaforo": semaforo.id_semaforo,
        "id_veiculo": veiculo.id_veiculo,
        "id_execucao": execucao.id_execucao,
    }


def test_grava_e_le_log_prioridade_completo(sessao: Session, cenario: dict[str, int]) -> None:
    """O critério de pronto do Bloco 1, ponta a ponta."""
    id_correlacao = uuid.uuid4()
    t_deteccao = datetime.now(UTC)
    t_decisao = t_deteccao + timedelta(milliseconds=68)
    t_atuacao = t_deteccao + timedelta(milliseconds=142)

    deteccao = operacao.registrar_deteccao(
        sessao,
        id_correlacao=id_correlacao,
        origem="V2I_RFID",
        reconhecido=True,
        uid_bruto="A34F219C",
        fk_veiculo=cenario["id_veiculo"],
        rssi=-47,
        sequencia=42,
    )

    metrica = experimento.registrar_metrica_simulacao(
        sessao,
        id_execucao=cenario["id_execucao"],
        tempo_medio_resposta=Decimal("120.50"),
        tempo_espera=Decimal("15.25"),
        percentual_reducao=Decimal("27.30"),
        latencia_ia=Decimal("68.00"),
        cenario_simulado="cenario_teste",
    )

    log = operacao.registrar_log_prioridade(
        sessao,
        id_correlacao=id_correlacao,
        fk_veiculo=cenario["id_veiculo"],
        fk_semaforo=cenario["id_semaforo"],
        fk_metrica=metrica.id_metrica,
        fk_execucao=cenario["id_execucao"],
        timestamp_inicio=t_deteccao,
        timestamp_fim=t_atuacao,
        ganho_tempo_segundos=12,
        status_execucao=StatusExecucao.SUCESSO,
        motivo="VE a 480 m na rota; ETA 22 s dentro da janela de ativação",
        fase_anterior=1,
        fase_aplicada=3,
    )

    operacao.registrar_latencia(
        sessao,
        id_correlacao=id_correlacao,
        fk_log=log.id_log,
        t_deteccao=t_deteccao,
        t_decisao=t_decisao,
        t_atuacao=t_atuacao,
        ambiente="SIMULACAO",
    )
    sessao.commit()

    # --- releitura, em sessão limpa de identity map -------------------------
    sessao.expunge_all()
    lido = sessao.scalars(
        select(LogPrioridade).where(LogPrioridade.id_correlacao == id_correlacao)
    ).one()

    assert lido.fk_veiculo == cenario["id_veiculo"]
    assert lido.fk_semaforo == cenario["id_semaforo"]
    assert lido.fk_metrica == metrica.id_metrica
    assert lido.fk_execucao == cenario["id_execucao"]
    assert lido.status_execucao is StatusExecucao.SUCESSO
    assert lido.motivo
    assert (lido.fase_anterior, lido.fase_aplicada) == (1, 3)

    # As relações resolvem — o encadeamento existe de verdade, não só as chaves.
    assert lido.veiculo is not None
    assert lido.veiculo.tipo is TipoVeiculo.AMBULANCIA
    assert lido.semaforo.codigo_externo == "SEMAFORO_TESTE"
    assert lido.execucao is not None
    assert lido.execucao.parametros["raio_deteccao_m"] == 500

    # O id_correlacao atravessa detecção, log e latência (context/02 §7).
    assert deteccao.id_correlacao == id_correlacao
    latencia = sessao.scalars(
        select(MetricaLatencia).where(MetricaLatencia.id_correlacao == id_correlacao)
    ).one()
    assert latencia.fk_log == lido.id_log


def test_latencia_de_decisao_e_calculada_pelo_banco(
    sessao: Session, cenario: dict[str, int]
) -> None:
    """`latencia_decisao_ms` é coluna gerada — não pode divergir dos carimbos."""
    t_deteccao = datetime.now(UTC)
    latencia = operacao.registrar_latencia(
        sessao,
        id_correlacao=uuid.uuid4(),
        t_deteccao=t_deteccao,
        t_decisao=t_deteccao + timedelta(milliseconds=68),
        t_atuacao=t_deteccao + timedelta(milliseconds=142),
        ambiente="SIMULACAO",
    )
    sessao.commit()
    sessao.refresh(latencia)

    assert latencia.latencia_decisao_ms == 68  # RNF01 — só o motor
    assert latencia.latencia_total_ms == 142  # H3 — fim a fim


def test_latencia_total_fica_nula_sem_atuacao(sessao: Session) -> None:
    """Preempção abortada não tem `t_atuacao`, e a latência fim-a-fim não existe."""
    t_deteccao = datetime.now(UTC)
    latencia = operacao.registrar_latencia(
        sessao,
        id_correlacao=uuid.uuid4(),
        t_deteccao=t_deteccao,
        t_decisao=t_deteccao + timedelta(milliseconds=50),
        ambiente="HARDWARE",
    )
    sessao.commit()
    sessao.refresh(latencia)

    assert latencia.latencia_decisao_ms == 50
    assert latencia.latencia_total_ms is None


def test_deteccao_nao_reconhecida_tambem_e_gravada(sessao: Session) -> None:
    """UID desconhecido gera registro da tentativa (context/02 §6)."""
    operacao.registrar_deteccao(
        sessao,
        id_correlacao=uuid.uuid4(),
        origem="V2I_RFID",
        reconhecido=False,
        uid_bruto="DEADBEEF",
    )
    sessao.commit()

    tentativa = sessao.scalars(select(Deteccao).where(Deteccao.uid_bruto == "DEADBEEF")).one()
    assert tentativa.reconhecido is False
    assert tentativa.fk_veiculo is None


def test_execucao_recusa_ponto_experimental_duplicado(
    sessao: Session, cenario: dict[str, int]
) -> None:
    """(cenário, modo, seed) é único — reexecução exige descarte documentado."""
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        experimento.abrir_execucao(
            sessao,
            nome_cenario="cenario_teste",
            modo=ModoControle.PREEMPCAO,
            seed=1,
            duracao_s=60,
            arquivo_rede="malha_teste.net.xml",
            parametros={},
        )
    sessao.rollback()


def test_uid_normaliza_e_tag_inativa_nao_resolve(sessao: Session) -> None:
    """Tag inativa é tratada como desconhecida — é como se revoga um cartão."""
    from app.models import TagRfid

    veiculo = VeiculoEmergencia(placa="TST0A01", tipo=TipoVeiculo.BOMBEIRO)
    sessao.add(veiculo)
    sessao.flush()
    sessao.add_all(
        [
            TagRfid(uid="A34F219C", fk_veiculo=veiculo.id_veiculo, ativo=True),
            TagRfid(uid="BADCAFE0", fk_veiculo=veiculo.id_veiculo, ativo=False),
        ]
    )
    sessao.commit()

    # O leitor entrega com espaços; o banco guarda normalizado.
    assert cadastro.buscar_veiculo_por_uid(sessao, "a3 4f 21 9c") is not None
    assert cadastro.buscar_veiculo_por_uid(sessao, "A3:4F:21:9C") is not None
    assert cadastro.buscar_veiculo_por_uid(sessao, "BADCAFE0") is None
    assert cadastro.buscar_veiculo_por_uid(sessao, "00000000") is None
