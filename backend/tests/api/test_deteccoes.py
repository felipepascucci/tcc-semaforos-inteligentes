"""`POST /deteccoes` — P20 na API e anti-replay de 2 s (`context/01` §7, `context/02` §6)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Deteccao, DispositivoIot, LogPrioridade, StatusOperacao, VeiculoEmergencia
from app.schemas.deteccoes import RespostaDeteccao
from app.services.deteccoes import Deduplicador, Resultado
from tests.api.conftest import CODIGO_LEITOR, TOKEN_LEITOR, UID_AMBULANCIA

pytestmark = pytest.mark.banco

CABECALHO = {"X-Device-Token": TOKEN_LEITOR}


def _deteccao(uid: str = "A3 4F 21 9C", sequencia: int | None = 1) -> dict[str, object]:
    return {
        "origem": "V2I_RFID",
        "uid_tag": uid,
        "id_leitor": CODIGO_LEITOR,
        "rssi": -47,
        "timestamp_dispositivo": 1234567,
        "sequencia": sequencia,
    }


def _deteccoes(sessao: Session) -> list[Deteccao]:
    sessao.rollback()
    return list(sessao.scalars(select(Deteccao).order_by(Deteccao.id_deteccao)))


def test_tag_reconhecida_sem_ocorrencia_e_200_sem_prioridade(
    cliente: TestClient, semeado: Session, leitor: DispositivoIot, ambulancia: VeiculoEmergencia
) -> None:
    """P20: a credencial vale, falta o serviço. 200, não 403."""
    resposta = cliente.post("/api/v1/deteccoes", json=_deteccao(), headers=CABECALHO)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo == {
        "reconhecido": True,
        "autorizado": False,
        "id_veiculo": ambulancia.id_veiculo,
        "tipo": "AMBULANCIA",
        "criticidade": None,
        "acao": "SEM_OCORRENCIA",
        "id_log": None,
        "mensagem_lcd": "SEM OCORRENCIA\nSEM PRIORIDADE",
        "duplicada": False,
    }
    (deteccao,) = _deteccoes(semeado)
    assert (deteccao.reconhecido, deteccao.autorizado, deteccao.fk_ocorrencia) == (
        True,
        False,
        None,
    )
    assert deteccao.uid_bruto == "A3 4F 21 9C"
    assert deteccao.fk_dispositivo == leitor.id_dispositivo


def test_com_ocorrencia_a_deteccao_autoriza_e_correlaciona_ate_o_log(
    cliente: TestClient, semeado: Session, leitor: DispositivoIot, ambulancia: VeiculoEmergencia
) -> None:
    ocorrencia = cliente.post(
        "/api/v1/ocorrencias", json={"id_veiculo": ambulancia.id_veiculo, "criticidade": 1}
    ).json()

    corpo = cliente.post("/api/v1/deteccoes", json=_deteccao(), headers=CABECALHO).json()

    assert (corpo["autorizado"], corpo["acao"], corpo["criticidade"]) == (
        True,
        "PREEMPCAO_SOLICITADA",
        1,
    )
    assert corpo["mensagem_lcd"] == "AMBULANCIA\nPRIORIDADE ATIVA"
    (deteccao,) = _deteccoes(semeado)
    assert deteccao.autorizado
    assert deteccao.fk_ocorrencia == ocorrencia["id_ocorrencia"]
    log = semeado.get(LogPrioridade, corpo["id_log"])
    assert log is not None
    # id_correlacao gerado na detecção e propagado (context/02 §7).
    assert log.id_correlacao == deteccao.id_correlacao
    assert log.fk_semaforo == leitor.fk_semaforo
    assert log.fk_veiculo == ambulancia.id_veiculo
    assert "não comanda atuador" in (log.motivo or "")


def test_tag_desconhecida_e_403_e_a_tentativa_fica_gravada(
    cliente: TestClient, semeado: Session, leitor: DispositivoIot
) -> None:
    resposta = cliente.post("/api/v1/deteccoes", json=_deteccao("DE AD BE EF"), headers=CABECALHO)

    assert resposta.status_code == 403
    assert resposta.json()["acao"] == "ACESSO_NEGADO"
    (deteccao,) = _deteccoes(semeado)
    assert (deteccao.reconhecido, deteccao.autorizado, deteccao.fk_veiculo) == (False, False, None)


def test_tag_inativa_e_tratada_como_desconhecida(
    cliente: TestClient, semeado: Session, leitor: DispositivoIot
) -> None:
    """As tags dos seeds são placeholders inativos: nenhuma autoriza (context/03 §5)."""
    resposta = cliente.post("/api/v1/deteccoes", json=_deteccao("PLACEHOLDER01"), headers=CABECALHO)
    assert resposta.status_code == 403


def test_veiculo_inativo_e_200_sem_prioridade(
    cliente: TestClient, semeado: Session, leitor: DispositivoIot, ambulancia: VeiculoEmergencia
) -> None:
    ambulancia.status_operacional = StatusOperacao.MANUTENCAO
    semeado.commit()

    corpo = cliente.post("/api/v1/deteccoes", json=_deteccao(), headers=CABECALHO).json()

    assert (corpo["reconhecido"], corpo["autorizado"], corpo["acao"]) == (
        True,
        False,
        "VEICULO_INATIVO",
    )


def test_mesma_tag_dentro_de_2_s_devolve_a_mesma_resposta_sem_gravar(
    cliente: TestClient, semeado: Session, leitor: DispositivoIot, ambulancia: VeiculoEmergencia
) -> None:
    """O RC522 lê a mesma tag várias vezes por segundo: uma passagem, uma linha."""
    primeira = cliente.post("/api/v1/deteccoes", json=_deteccao(sequencia=1), headers=CABECALHO)
    segunda = cliente.post("/api/v1/deteccoes", json=_deteccao(sequencia=2), headers=CABECALHO)

    assert segunda.status_code == primeira.status_code
    assert segunda.json() == {**primeira.json(), "duplicada": True}
    assert len(_deteccoes(semeado)) == 1


def test_uid_normalizado_conta_como_a_mesma_tag(
    cliente: TestClient, semeado: Session, leitor: DispositivoIot, ambulancia: VeiculoEmergencia
) -> None:
    cliente.post("/api/v1/deteccoes", json=_deteccao("a3:4f:21:9c"), headers=CABECALHO)
    repetida = cliente.post("/api/v1/deteccoes", json=_deteccao(UID_AMBULANCIA), headers=CABECALHO)

    assert repetida.json()["duplicada"] is True
    assert len(_deteccoes(semeado)) == 1


def _resultado() -> Resultado:
    resposta = RespostaDeteccao(
        reconhecido=True,
        autorizado=False,
        id_veiculo=1,
        tipo=None,
        criticidade=None,
        acao="SEM_OCORRENCIA",
        id_log=None,
        mensagem_lcd="",
    )
    return Resultado(resposta, 200)


def test_janela_anti_replay_vence_em_2_s() -> None:
    agora = [100.0]
    dedup = Deduplicador(janela_s=2.0, relogio=lambda: agora[0])
    dedup.lembrar("A34F219C", "L1", 7, _resultado())

    agora[0] = 101.9
    assert dedup.repetida("A34F219C", "L1", 8) is not None
    agora[0] = 102.0
    assert dedup.repetida("A34F219C", "L1", 8) is None


def test_sequencia_repetida_do_mesmo_leitor_e_o_mesmo_pacote() -> None:
    """Um reenvio do mesmo pacote, ainda que com outra tag no corpo, não grava de novo."""
    dedup = Deduplicador(janela_s=2.0, relogio=lambda: 0.0)
    original = _resultado()
    dedup.lembrar("A34F219C", "L1", 7, original)

    assert dedup.repetida("FFFFFFFF", "L1", 7) is original
    assert dedup.repetida("FFFFFFFF", "L2", 7) is None
    assert dedup.repetida("FFFFFFFF", "L1", 8) is None
