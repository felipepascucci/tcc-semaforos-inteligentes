"""`/ocorrencias`, `/veiculos`, `/semaforos` e `/logs/prioridade` (`context/01` §7)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import LogPrioridade, Semaforo, StatusExecucao, VeiculoEmergencia

pytestmark = pytest.mark.banco


# ---------------------------------------------------------------------------
# Ocorrências — a central de despacho simulada (P20)
# ---------------------------------------------------------------------------


def test_central_abre_lista_e_encerra(cliente: TestClient, ambulancia: VeiculoEmergencia) -> None:
    aberta = cliente.post(
        "/api/v1/ocorrencias",
        json={"id_veiculo": ambulancia.id_veiculo, "criticidade": 1, "descricao": "PCR"},
    )
    assert aberta.status_code == 201
    corpo = aberta.json()
    assert (corpo["id_veiculo"], corpo["criticidade"], corpo["aberta"]) == (
        ambulancia.id_veiculo,
        1,
        True,
    )

    ativas = cliente.get("/api/v1/ocorrencias", params={"ativas": True}).json()
    assert [o["id_ocorrencia"] for o in ativas] == [corpo["id_ocorrencia"]]

    encerrada = cliente.post(f"/api/v1/ocorrencias/{corpo['id_ocorrencia']}/encerramento")
    assert encerrada.status_code == 200
    assert encerrada.json()["aberta"] is False
    assert cliente.get("/api/v1/ocorrencias", params={"ativas": True}).json() == []
    assert len(cliente.get("/api/v1/ocorrencias").json()) == 1


def test_segunda_ocorrencia_aberta_e_409(
    cliente: TestClient, ambulancia: VeiculoEmergencia
) -> None:
    pedido = {"id_veiculo": ambulancia.id_veiculo, "criticidade": 3}
    assert cliente.post("/api/v1/ocorrencias", json=pedido).status_code == 201
    assert cliente.post("/api/v1/ocorrencias", json=pedido).status_code == 409


@pytest.mark.parametrize(
    ("pedido", "esperado"),
    [
        ({"id_veiculo": 999_999, "criticidade": 1}, 404),
        ({"id_veiculo": 1, "criticidade": 0}, 422),
        ({"id_veiculo": 1, "criticidade": 4}, 422),
    ],
    ids=["veiculo_inexistente", "criticidade_0", "criticidade_4"],
)
def test_pedido_de_ocorrencia_invalido(
    cliente: TestClient, pedido: dict[str, int], esperado: int
) -> None:
    assert cliente.post("/api/v1/ocorrencias", json=pedido).status_code == esperado


def test_encerrar_duas_vezes_e_409_e_inexistente_e_404(
    cliente: TestClient, ambulancia: VeiculoEmergencia
) -> None:
    aberta = cliente.post(
        "/api/v1/ocorrencias", json={"id_veiculo": ambulancia.id_veiculo, "criticidade": 2}
    ).json()
    caminho = f"/api/v1/ocorrencias/{aberta['id_ocorrencia']}/encerramento"
    assert cliente.post(caminho).status_code == 200
    assert cliente.post(caminho).status_code == 409
    assert cliente.post("/api/v1/ocorrencias/999999/encerramento").status_code == 404


# ---------------------------------------------------------------------------
# Veículos
# ---------------------------------------------------------------------------


def test_cadastra_ve_com_tag_normalizada(cliente: TestClient) -> None:
    resposta = cliente.post(
        "/api/v1/veiculos",
        json={"placa": "tst2b02", "tipo": "BOMBEIRO", "uid_tag": "b7 ef 8f a1"},
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["placa"] == "TST2B02"
    assert corpo["tags"] == [{"uid": "B7EF8FA1", "ativo": True}]
    assert corpo["status_operacional"] == "ATIVO"
    assert corpo["em_servico"] is False


@pytest.mark.parametrize(
    "corpo",
    [
        {"placa": "TST1234", "tipo": "POLICIA"},
        {"placa": "TST2B02", "tipo": "HELICOPTERO"},
        {"placa": "TST2B02", "tipo": "POLICIA", "uid_tag": "não é hex"},
    ],
    ids=["placa_antiga", "tipo_desconhecido", "uid_invalido"],
)
def test_cadastro_invalido_e_422(cliente: TestClient, corpo: dict[str, str]) -> None:
    assert cliente.post("/api/v1/veiculos", json=corpo).status_code == 422


def test_placa_ou_uid_repetidos_sao_409(cliente: TestClient, ambulancia: VeiculoEmergencia) -> None:
    placa = cliente.post("/api/v1/veiculos", json={"placa": "TST1A01", "tipo": "AMBULANCIA"})
    uid = cliente.post(
        "/api/v1/veiculos", json={"placa": "TST9Z99", "tipo": "POLICIA", "uid_tag": "A34F219C"}
    )
    assert (placa.status_code, uid.status_code) == (409, 409)


def test_lista_veiculos_e_quem_esta_em_servico(
    cliente: TestClient, ambulancia: VeiculoEmergencia
) -> None:
    cliente.post(
        "/api/v1/ocorrencias", json={"id_veiculo": ambulancia.id_veiculo, "criticidade": 1}
    )
    por_placa = {v["placa"]: v for v in cliente.get("/api/v1/veiculos").json()}

    assert por_placa["TST1A01"]["em_servico"] is True
    assert por_placa["AMB1A01"]["em_servico"] is False  # dos seeds: ninguém em serviço


# ---------------------------------------------------------------------------
# Semáforos
# ---------------------------------------------------------------------------


def test_lista_os_nove_semaforos_dos_seeds(cliente: TestClient) -> None:
    semaforos = cliente.get("/api/v1/semaforos").json()

    codigos = [s["codigo_externo"] for s in semaforos]
    assert codigos == [f"CRUZ_0{i}" for i in range(1, 9)] + ["PROTO_CRUZ_01"]
    # Sem ponte nem simulação transmitindo, nada está ao vivo — e isso aparece.
    assert all(s["ao_vivo"] is None for s in semaforos)


def test_detalhe_da_bancada_tem_as_duas_fases(cliente: TestClient) -> None:
    detalhe = cliente.get("/api/v1/semaforos/PROTO_CRUZ_01").json()

    assert detalhe["tempo_ciclo"] == 12
    assert [f["indice_fase"] for f in detalhe["fases"]] == [1, 2]
    assert detalhe["logs_recentes"] == []
    assert cliente.get("/api/v1/semaforos/CRUZ_99").status_code == 404


def test_preempcao_manual_so_existe_na_bancada(cliente: TestClient) -> None:
    pedido = {"rua": 3, "veiculo": "AMBULANCIA"}
    assert cliente.post("/api/v1/semaforos/CRUZ_03/preempcao", json=pedido).status_code == 409
    # Sem PONTE_URL não há como chegar ao UNO.
    resposta = cliente.post("/api/v1/semaforos/PROTO_CRUZ_01/preempcao", json=pedido)
    assert resposta.status_code == 503


@pytest.mark.parametrize("codigo", ["PROTO_CRUZ_01", "CRUZ_03"])
def test_cancelamento_e_sempre_409_com_o_motivo(cliente: TestClient, codigo: str) -> None:
    resposta = cliente.delete(f"/api/v1/semaforos/{codigo}/preempcao")
    assert resposta.status_code == 409
    assert resposta.json()["detail"]


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


def _logs(sessao: Session, n: int) -> list[uuid.UUID]:
    proto = sessao.query(Semaforo).filter_by(codigo_externo="PROTO_CRUZ_01").one()
    cruz = sessao.query(Semaforo).filter_by(codigo_externo="CRUZ_01").one()
    inicio = datetime(2026, 10, 5, 12, tzinfo=UTC)
    ids = []
    for i in range(n):
        id_correlacao = uuid.uuid4()
        ids.append(id_correlacao)
        sessao.add(
            LogPrioridade(
                id_correlacao=id_correlacao,
                fk_semaforo=(proto if i % 2 else cruz).id_semaforo,
                timestamp_inicio=inicio + timedelta(seconds=i),
                status_execucao=StatusExecucao.FALHA if i == 0 else StatusExecucao.SUCESSO,
                motivo=f"teste {i}",
            )
        )
    sessao.commit()
    return ids


def test_logs_paginados_do_mais_novo_para_o_mais_antigo(
    cliente: TestClient, semeado: Session
) -> None:
    _logs(semeado, 5)

    pagina = cliente.get("/api/v1/logs/prioridade", params={"limite": 2, "deslocamento": 1}).json()

    assert pagina["total"] == 5
    assert [item["motivo"] for item in pagina["itens"]] == ["teste 3", "teste 2"]


def test_logs_filtrados(cliente: TestClient, semeado: Session) -> None:
    ids = _logs(semeado, 5)

    def total(**filtros: str) -> int:
        return int(cliente.get("/api/v1/logs/prioridade", params=filtros).json()["total"])

    assert total(semaforo="PROTO_CRUZ_01") == 2
    assert total(status_execucao="FALHA") == 1
    assert total(id_correlacao=str(ids[4])) == 1
    assert total(desde="2026-10-05T12:00:03Z") == 2
    item = cliente.get("/api/v1/logs/prioridade", params={"id_correlacao": str(ids[1])}).json()
    assert item["itens"][0]["codigo_semaforo"] == "PROTO_CRUZ_01"
