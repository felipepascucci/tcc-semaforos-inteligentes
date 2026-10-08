"""`/simulacoes` e `/metricas/resumo` — pedidos ao atendente, transmissão e agregados."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import MetricaLatencia

pytestmark = pytest.mark.banco


def test_pedido_valido_fica_pendente(cliente: TestClient) -> None:
    resposta = cliente.post(
        "/api/v1/simulacoes",
        json={"cenario": "moderado", "modo": "PREEMPCAO", "seed": 1001, "duracao_s": 600},
    )

    assert resposta.status_code == 201
    pedido = resposta.json()
    assert (pedido["status"], pedido["execucao"], pedido["resumo"]) == ("PENDENTE", None, None)
    detalhe = cliente.get(f"/api/v1/simulacoes/{pedido['id_pedido']}").json()
    assert detalhe == pedido
    assert [p["id_pedido"] for p in cliente.get("/api/v1/simulacoes").json()] == [
        pedido["id_pedido"]
    ]


def test_seeds_reservadas_vem_com_o_uso_de_cada_faixa(cliente: TestClient) -> None:
    """O dashboard explica cada faixa com o texto de `cenarios.yaml`, sem cópia própria."""
    resposta = cliente.get("/api/v1/simulacoes/seeds-reservadas")

    assert resposta.status_code == 200
    faixas = resposta.json()
    assert [(f["inicio"], f["fim"]) for f in faixas] == [(1, 50), (101, 105), (201, 250)]
    assert all(f["uso"] for f in faixas)
    assert "Bloco 8" in faixas[0]["uso"]


@pytest.mark.parametrize("seed", [1, 50, 101, 105, 201, 250])
def test_seed_do_experimento_e_recusada(cliente: TestClient, seed: int) -> None:
    """Um pedido do dashboard não pode ocupar o ponto do lote do Bloco 8 (2026-10-05)."""
    resposta = cliente.post(
        "/api/v1/simulacoes", json={"cenario": "leve", "modo": "FIXO", "seed": seed}
    )
    assert resposta.status_code == 422
    assert "reservada" in resposta.text or "experimento" in resposta.text


@pytest.mark.parametrize("seed", [0, 51, 100, 106])
def test_seed_vizinha_das_reservadas_e_aceita(cliente: TestClient, seed: int) -> None:
    resposta = cliente.post(
        "/api/v1/simulacoes", json={"cenario": "leve", "modo": "FIXO", "seed": seed}
    )
    assert resposta.status_code == 201


def test_velocidade_padrao_e_tempo_real(cliente: TestClient) -> None:
    """O dashboard é para acompanhar a olho (Bloco 7)."""
    corpo = {"cenario": "leve", "modo": "FIXO", "seed": 1001}
    assert cliente.post("/api/v1/simulacoes", json=corpo).json()["velocidade"] == 1


@pytest.mark.parametrize("velocidade", [1, 2, 5, 10, None])
def test_velocidades_aceitas(cliente: TestClient, velocidade: int | None) -> None:
    """Nula é o mais rápido possível, como o lote."""
    corpo = {"cenario": "leve", "modo": "FIXO", "seed": 1001, "velocidade": velocidade}
    resposta = cliente.post("/api/v1/simulacoes", json=corpo)
    assert resposta.status_code == 201
    assert resposta.json()["velocidade"] == velocidade


@pytest.mark.parametrize("velocidade", [0, 3, 100, -1])
def test_velocidade_fora_da_lista_e_422(cliente: TestClient, velocidade: int) -> None:
    corpo = {"cenario": "leve", "modo": "FIXO", "seed": 1001, "velocidade": velocidade}
    assert cliente.post("/api/v1/simulacoes", json=corpo).status_code == 422


def test_banco_recusa_velocidade_fora_da_lista(semeado: Session) -> None:
    """O CHECK da migration vale mesmo para quem grava sem passar pela API."""
    from sqlalchemy.exc import IntegrityError

    from app.models import ModoControle, PedidoSimulacao

    semeado.add(
        PedidoSimulacao(nome_cenario="leve", modo=ModoControle.FIXO, seed=1001, velocidade=3)
    )
    with pytest.raises(IntegrityError, match="velocidade_conhecida"):
        semeado.commit()
    semeado.rollback()


def test_cenario_desconhecido_e_422(cliente: TestClient) -> None:
    resposta = cliente.post(
        "/api/v1/simulacoes", json={"cenario": "caotico", "modo": "FIXO", "seed": 1001}
    )
    assert resposta.status_code == 422
    assert cliente.get("/api/v1/simulacoes/999999").status_code == 404


def _transmissao(t: float, em_preempcao: bool = False) -> dict[str, object]:
    return {
        "cenario": "moderado",
        "modo": "PREEMPCAO",
        "seed": 1001,
        "t": t,
        "semaforos": [
            {"id": "CRUZ_03", "fase": 0, "sinal": "VERDE", "em_preempcao": em_preempcao},
        ],
        "veiculos": [
            {
                "id": "ve_amb_0",
                "tipo": "AMBULANCIA",
                "criticidade": 1,
                "lat": -23.55,
                "lon": -46.62,
                "velocidade": 11.2,
            }
        ],
        "latencia_ms": 0.12,
    }


def test_transmissao_aparece_no_estado_dos_semaforos(cliente: TestClient) -> None:
    assert (
        cliente.post("/api/v1/simulacoes/transmissao", json=_transmissao(42.0, True)).status_code
        == 202
    )

    por_codigo = {s["codigo_externo"]: s for s in cliente.get("/api/v1/semaforos").json()}
    ao_vivo = por_codigo["CRUZ_03"]["ao_vivo"]
    assert (ao_vivo["fonte"], ao_vivo["sinal"], ao_vivo["em_preempcao"]) == (
        "SIMULACAO",
        "VERDE",
        True,
    )
    assert ao_vivo["t_simulacao"] == 42.0
    assert por_codigo["CRUZ_01"]["ao_vivo"] is None
    assert cliente.get("/api/v1/health").json()["simulacao_ao_vivo"] is True


def test_resumo_de_metricas(cliente: TestClient, semeado: Session) -> None:
    """Na bancada, mín/mediana/máx com o n — sem p95 sobre 5 amostras (2026-08-31)."""
    t0 = datetime(2026, 10, 5, 12, tzinfo=UTC)
    for i, ms in enumerate((40, 45, 52)):
        semeado.add(
            MetricaLatencia(
                id_correlacao=uuid.uuid4(),
                t_deteccao=t0 + timedelta(seconds=i),
                t_decisao=None,
                t_atuacao=t0 + timedelta(seconds=i, milliseconds=ms),
                latencia_total_ms=ms,
                ambiente="HARDWARE",
            )
        )
    semeado.commit()

    resumo = cliente.get("/api/v1/metricas/resumo").json()

    assert resumo["latencia"]["hardware"] == {
        "n": 3,
        "min_total_ms": 40,
        "mediana_total_ms": 45,
        "max_total_ms": 52,
    }
    assert resumo["latencia"]["simulacao"]["n"] == 0
    assert resumo["ocorrencias_ativas"] == 0
    assert resumo["ao_vivo"] == {"bancada": False, "simulacao": False}


def test_latencia_da_bancada_tem_t_decisao_nulo(semeado: Session) -> None:
    """A migration de 2026-10-05 aceita a linha, e a latência de decisão sai nula sozinha."""
    t0 = datetime(2026, 10, 5, 12, tzinfo=UTC)
    linha = MetricaLatencia(
        id_correlacao=uuid.uuid4(),
        t_deteccao=t0,
        t_decisao=None,
        t_atuacao=t0 + timedelta(milliseconds=45),
        latencia_total_ms=45,
        ambiente="HARDWARE",
    )
    semeado.add(linha)
    semeado.commit()
    semeado.refresh(linha)

    assert linha.latencia_decisao_ms is None
    assert linha.latencia_total_ms == 45
