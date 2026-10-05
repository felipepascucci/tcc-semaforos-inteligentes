"""RNF04 na API — `X-Device-Token` e tag desconhecida (`context/06` §2).

Na bancada nenhum dispositivo chama a API, e a falta de criptografia no ESP-NOW é
limitação declarada (`context/02` §6). Isto vale para o contrato V2I com rede.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Deteccao, DispositivoIot, StatusOperacao, VeiculoEmergencia
from tests.api.conftest import CODIGO_LEITOR, TOKEN_LEITOR

pytestmark = pytest.mark.banco

CORPO = {"uid_tag": "A3 4F 21 9C", "id_leitor": CODIGO_LEITOR, "sequencia": 1}


def _gravadas(sessao: Session) -> int:
    sessao.rollback()
    return sessao.scalar(select(func.count()).select_from(Deteccao)) or 0


@pytest.mark.parametrize(
    "cabecalho",
    [{}, {"X-Device-Token": "token-errado"}, {"X-Device-Token": ""}],
    ids=["sem_token", "token_errado", "token_vazio"],
)
def test_sem_token_valido_e_401_e_nada_e_gravado(
    cliente: TestClient,
    semeado: Session,
    leitor: DispositivoIot,
    ambulancia: VeiculoEmergencia,
    cabecalho: dict[str, str],
) -> None:
    resposta = cliente.post("/api/v1/deteccoes", json=CORPO, headers=cabecalho)

    assert resposta.status_code == 401
    assert _gravadas(semeado) == 0


def test_token_de_outro_dispositivo_nao_serve(
    cliente: TestClient, semeado: Session, leitor: DispositivoIot
) -> None:
    """O token do CTRL_PROTO_01 dos seeds não autentica o leitor de teste."""
    cabecalho = {"X-Device-Token": "dev-somente-local-controlador"}
    assert cliente.post("/api/v1/deteccoes", json=CORPO, headers=cabecalho).status_code == 401


def test_dispositivo_desconhecido_e_401(cliente: TestClient, leitor: DispositivoIot) -> None:
    corpo = {**CORPO, "id_leitor": "LEITOR_QUE_NAO_EXISTE"}
    cabecalho = {"X-Device-Token": TOKEN_LEITOR}
    assert cliente.post("/api/v1/deteccoes", json=corpo, headers=cabecalho).status_code == 401


def test_dispositivo_inativo_e_401(
    cliente: TestClient, semeado: Session, leitor: DispositivoIot
) -> None:
    leitor.status = StatusOperacao.INATIVO
    semeado.commit()
    cabecalho = {"X-Device-Token": TOKEN_LEITOR}
    assert cliente.post("/api/v1/deteccoes", json=CORPO, headers=cabecalho).status_code == 401


def test_uid_nao_cadastrado_e_403(cliente: TestClient, leitor: DispositivoIot) -> None:
    corpo = {**CORPO, "uid_tag": "00 11 22 33"}
    cabecalho = {"X-Device-Token": TOKEN_LEITOR}
    assert cliente.post("/api/v1/deteccoes", json=corpo, headers=cabecalho).status_code == 403


def test_autenticacao_atualiza_o_ultimo_contato(
    cliente: TestClient, semeado: Session, leitor: DispositivoIot, ambulancia: VeiculoEmergencia
) -> None:
    cliente.post("/api/v1/deteccoes", json=CORPO, headers={"X-Device-Token": TOKEN_LEITOR})

    semeado.refresh(leitor)
    assert leitor.ultimo_contato is not None
