"""Apoio aos testes da API: o app sobre o banco efêmero, com os seeds aplicados.

O app é montado com `criar_app(Configuracao(...))`, nunca a partir do ambiente:
um teste que lesse o `.env` falaria com o banco de desenvolvimento.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.configuracao import Configuracao
from app.main import criar_app
from app.models import DispositivoIot, Semaforo, TagRfid, TipoVeiculo, VeiculoEmergencia
from app.services.autenticacao import gerar_hash_senha
from app.services.deteccoes import hash_token
from db.seeds.carregar import aplicar, carregar_dados

#: Token de teste do leitor criado por `leitor`; obviamente artificial.
TOKEN_LEITOR = "token-de-teste-do-leitor"
CODIGO_LEITOR = "LEITOR_TESTE_01"
UID_AMBULANCIA = "A34F219C"

#: Operador de teste (Bloco 7). Mil iterações em vez de 600 mil: o número vai
#: dentro do hash, e o teste não precisa pagar o custo de produção a cada login.
OPERADOR_TESTE = "operador_teste"
SENHA_TESTE = "senha-de-teste"
SEGREDO_TESTE = "segredo-de-teste-com-pelo-menos-32-caracteres"
HASH_TESTE = gerar_hash_senha(SENHA_TESTE, iteracoes=1_000)


def config_com_login(**campos: Any) -> Configuracao:
    """Uma `Configuracao` de teste com o operador de teste configurado."""
    return Configuracao(
        operador_usuario=OPERADOR_TESTE,
        operador_senha_hash=HASH_TESTE,
        jwt_segredo=SEGREDO_TESTE,
        **campos,
    )


def entrar(http: TestClient) -> str:
    """Faz o login do operador de teste e devolve o token."""
    resposta = http.post(
        "/api/v1/auth/login", json={"usuario": OPERADOR_TESTE, "senha": SENHA_TESTE}
    )
    assert resposta.status_code == 200, resposta.text
    token: str = resposta.json()["access_token"]
    return token


@pytest.fixture
def semeado(sessao: Session) -> Session:
    """O banco com os seeds de `context/03` §5."""
    aplicar(sessao, carregar_dados())
    sessao.commit()
    return sessao


@pytest.fixture
def anonimo(_schema_migrado: str, semeado: Session) -> Iterator[TestClient]:
    """O backend sobre o banco efêmero, sem ponte e sem login feito."""
    app = criar_app(config_com_login(url_banco=_schema_migrado))
    with TestClient(app) as http:
        yield http


@pytest.fixture
def cliente(anonimo: TestClient) -> TestClient:
    """O mesmo backend, com o operador logado: as rotas de escrita exigem o token."""
    anonimo.headers["Authorization"] = f"Bearer {entrar(anonimo)}"
    return anonimo


@pytest.fixture
def leitor(semeado: Session) -> DispositivoIot:
    """Um leitor V2I com rede, no cruzamento CRUZ_01, com token conhecido."""
    semaforo = semeado.query(Semaforo).filter_by(codigo_externo="CRUZ_01").one()
    dispositivo = DispositivoIot(
        codigo=CODIGO_LEITOR,
        tipo="LEITOR_V2I",
        fk_semaforo=semaforo.id_semaforo,
        token_hash=hash_token(TOKEN_LEITOR),
    )
    semeado.add(dispositivo)
    semeado.commit()
    return dispositivo


@pytest.fixture
def ambulancia(semeado: Session) -> VeiculoEmergencia:
    """Uma ambulância com tag ativa, sem ocorrência."""
    veiculo = VeiculoEmergencia(placa="TST1A01", tipo=TipoVeiculo.AMBULANCIA)
    veiculo.tags.append(TagRfid(uid=UID_AMBULANCIA, ativo=True))
    semeado.add(veiculo)
    semeado.commit()
    return veiculo
