"""RNF04 no dashboard — login do operador e rotas de escrita protegidas (Bloco 7).

Decisão do Bloco 7 (`context/09`): o token protege só as escritas do operador.
Os GETs e o WebSocket ficam abertos, `/deteccoes` continua com `X-Device-Token`,
e `/simulacoes/transmissao`, que o executor chama do host, continua aberta.

Sem banco: a autenticação é verificada antes de a rota abrir sessão, então uma
rota protegida que passa da autenticação responde 503 ("banco não configurado"),
e é isso que prova que o token foi aceito.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.configuracao import Configuracao
from app.main import criar_app
from app.services.autenticacao import emitir_token
from tests.api.conftest import (
    OPERADOR_TESTE,
    SEGREDO_TESTE,
    SENHA_TESTE,
    config_com_login,
    entrar,
)

#: As escritas do operador, com um corpo válido para cada uma.
ROTAS_PROTEGIDAS = [
    ("POST", "/api/v1/semaforos/PROTO_CRUZ_01/preempcao", {"rua": 3}),
    ("DELETE", "/api/v1/semaforos/PROTO_CRUZ_01/preempcao", None),
    ("POST", "/api/v1/ocorrencias", {"id_veiculo": 1, "criticidade": 1}),
    ("POST", "/api/v1/ocorrencias/1/encerramento", None),
    ("POST", "/api/v1/veiculos", {"placa": "TST1A23", "tipo": "AMBULANCIA"}),
    ("POST", "/api/v1/simulacoes", {"cenario": "moderado", "modo": "PREEMPCAO", "seed": 900}),
]
IDS = [f"{metodo} {caminho.removeprefix('/api/v1')}" for metodo, caminho, _ in ROTAS_PROTEGIDAS]


@pytest.fixture
def http() -> Iterator[TestClient]:
    with TestClient(criar_app(config_com_login())) as cliente:
        yield cliente


def _chamar(
    http: TestClient, metodo: str, caminho: str, corpo: object, token: str | None = None
) -> int:
    cabecalho = {} if token is None else {"Authorization": f"Bearer {token}"}
    return http.request(metodo, caminho, json=corpo, headers=cabecalho).status_code


def test_login_com_a_credencial_certa_devolve_um_token_que_abre_a_sessao(
    http: TestClient,
) -> None:
    resposta = http.post(
        "/api/v1/auth/login", json={"usuario": OPERADOR_TESTE, "senha": SENHA_TESTE}
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["token_type"] == "bearer"
    assert corpo["usuario"] == OPERADOR_TESTE
    assert corpo["perfil"] == "operador"
    validade = datetime.fromisoformat(corpo["expira_em"]) - datetime.now(UTC)
    assert timedelta(hours=7, minutes=59) < validade <= timedelta(hours=8)

    sessao = http.get(
        "/api/v1/auth/sessao", headers={"Authorization": f"Bearer {corpo['access_token']}"}
    )
    assert sessao.status_code == 200
    assert sessao.json()["usuario"] == OPERADOR_TESTE


@pytest.mark.parametrize(
    "credencial",
    [
        {"usuario": OPERADOR_TESTE, "senha": "senha-errada"},
        {"usuario": "outro", "senha": SENHA_TESTE},
        {"usuario": OPERADOR_TESTE.upper(), "senha": SENHA_TESTE},
    ],
    ids=["senha_errada", "usuario_errado", "usuario_com_caixa_trocada"],
)
def test_credencial_errada_e_401_sem_dizer_qual_parte_errou(
    http: TestClient, credencial: dict[str, str]
) -> None:
    resposta = http.post("/api/v1/auth/login", json=credencial)

    assert resposta.status_code == 401
    assert resposta.json()["detail"] == "usuário ou senha incorretos"
    assert "access_token" not in resposta.json()


def test_sessao_sem_token_e_401(http: TestClient) -> None:
    assert http.get("/api/v1/auth/sessao").status_code == 401


@pytest.mark.parametrize(("metodo", "caminho", "corpo"), ROTAS_PROTEGIDAS, ids=IDS)
def test_escrita_sem_token_e_401_com_o_desafio_bearer(
    http: TestClient, metodo: str, caminho: str, corpo: object
) -> None:
    resposta = http.request(metodo, caminho, json=corpo)

    assert resposta.status_code == 401
    assert resposta.headers["WWW-Authenticate"] == "Bearer"
    assert "login necessário" in resposta.json()["detail"]


@pytest.mark.parametrize(("metodo", "caminho", "corpo"), ROTAS_PROTEGIDAS, ids=IDS)
def test_escrita_com_token_expirado_ou_falso_e_401(
    http: TestClient, metodo: str, caminho: str, corpo: object
) -> None:
    expirado, _ = emitir_token(
        OPERADOR_TESTE, SEGREDO_TESTE, 3600, agora=datetime.now(UTC) - timedelta(hours=2)
    )
    falso, _ = emitir_token(OPERADOR_TESTE, "um-segredo-que-o-backend-nao-conhece!!", 3600)

    assert _chamar(http, metodo, caminho, corpo, expirado) == 401
    assert _chamar(http, metodo, caminho, corpo, falso) == 401
    assert _chamar(http, metodo, caminho, corpo, "nao-e-jwt") == 401


@pytest.mark.parametrize(("metodo", "caminho", "corpo"), ROTAS_PROTEGIDAS, ids=IDS)
def test_escrita_com_token_valido_passa_da_autenticacao(
    http: TestClient, metodo: str, caminho: str, corpo: object
) -> None:
    """Sem banco, quem passa responde 503; o DELETE, que não abre sessão, dá o 409."""
    status = _chamar(http, metodo, caminho, corpo, entrar(http))

    assert status in {409, 503}


@pytest.mark.parametrize(
    "caminho",
    ["/api/v1/health", "/api/v1/semaforos", "/api/v1/veiculos", "/api/v1/logs/prioridade"],
)
def test_leitura_continua_aberta(http: TestClient, caminho: str) -> None:
    assert http.get(caminho).status_code != 401


def test_transmissao_do_executor_continua_aberta(http: TestClient) -> None:
    transmissao = {
        "cenario": "moderado",
        "modo": "PREEMPCAO",
        "seed": 900,
        "t": 1.0,
        "semaforos": [],
    }
    assert http.post("/api/v1/simulacoes/transmissao", json=transmissao).status_code == 202


def test_sem_login_configurado_o_login_e_as_escritas_dao_503() -> None:
    """Falta de configuração não vira porta aberta."""
    with TestClient(criar_app(Configuracao())) as http:
        login = http.post("/api/v1/auth/login", json={"usuario": "a", "senha": "b"})
        escrita = http.delete("/api/v1/semaforos/CRUZ_01/preempcao")

    assert login.status_code == 503
    assert "OPERADOR_SENHA_HASH" in login.json()["detail"]
    assert escrita.status_code == 503
