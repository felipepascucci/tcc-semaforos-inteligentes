"""Apoio aos testes da API: o app sobre o banco efêmero, com os seeds aplicados.

O app é montado com `criar_app(Configuracao(...))`, nunca a partir do ambiente:
um teste que lesse o `.env` falaria com o banco de desenvolvimento.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.configuracao import Configuracao
from app.main import criar_app
from app.models import DispositivoIot, Semaforo, TagRfid, TipoVeiculo, VeiculoEmergencia
from app.services.deteccoes import hash_token
from db.seeds.carregar import aplicar, carregar_dados

#: Token de teste do leitor criado por `leitor`; obviamente artificial.
TOKEN_LEITOR = "token-de-teste-do-leitor"
CODIGO_LEITOR = "LEITOR_TESTE_01"
UID_AMBULANCIA = "A34F219C"


@pytest.fixture
def semeado(sessao: Session) -> Session:
    """O banco com os seeds de `context/03` §5."""
    aplicar(sessao, carregar_dados())
    sessao.commit()
    return sessao


@pytest.fixture
def cliente(_schema_migrado: str, semeado: Session) -> Iterator[TestClient]:
    """O backend sobre o banco efêmero, sem ponte."""
    app = criar_app(Configuracao(url_banco=_schema_migrado))
    with TestClient(app) as http:
        yield http


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
