"""Hash da senha e token do operador (`app.services.autenticacao`, Bloco 7)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.configuracao import Configuracao
from app.services.autenticacao import (
    ALGORITMO,
    TokenInvalidoError,
    conferir_senha,
    emitir_token,
    gerar_hash_senha,
    validar_token,
)

SEGREDO = "segredo-de-teste-com-pelo-menos-32-caracteres"


def _hash(senha: str) -> str:
    return gerar_hash_senha(senha, iteracoes=1_000)


def test_a_senha_certa_confere_e_a_errada_nao() -> None:
    armazenado = _hash("senha-de-teste")

    assert conferir_senha("senha-de-teste", armazenado)
    assert not conferir_senha("senha-de-teste ", armazenado)
    assert not conferir_senha("", armazenado)


def test_o_hash_nao_contem_a_senha_e_muda_com_o_sal() -> None:
    primeiro, segundo = _hash("senha-de-teste"), _hash("senha-de-teste")

    assert "senha-de-teste" not in primeiro
    assert primeiro != segundo
    assert primeiro.startswith("pbkdf2_sha256:1000:")


def test_o_hash_nao_tem_cifrao_para_ir_no_compose_sem_escape() -> None:
    assert "$" not in gerar_hash_senha("x", iteracoes=1_000)


@pytest.mark.parametrize(
    "malformado",
    ["", "texto", "md5:1:a:b", "pbkdf2_sha256:mil:a:b", "pbkdf2_sha256:1000:!!:??", "a:b:c"],
)
def test_hash_malformado_nao_confere_nem_levanta(malformado: str) -> None:
    assert not conferir_senha("qualquer", malformado)


def test_token_emitido_e_validado_devolve_a_sessao() -> None:
    agora = datetime.now(UTC).replace(microsecond=0)
    token, emitida = emitir_token("operador", SEGREDO, 3600, agora=agora)

    sessao = validar_token(token, SEGREDO)

    assert sessao == emitida
    assert sessao.usuario == "operador"
    assert sessao.perfil == "operador"
    assert sessao.expira_em == agora + timedelta(hours=1)


def test_token_expirado_e_recusado_com_o_motivo() -> None:
    passado = datetime.now(UTC) - timedelta(hours=9)
    token, _ = emitir_token("operador", SEGREDO, 8 * 3600, agora=passado)

    with pytest.raises(TokenInvalidoError, match="expirada"):
        validar_token(token, SEGREDO)


def test_token_assinado_com_outro_segredo_e_recusado() -> None:
    token, _ = emitir_token("operador", "outro-segredo-tambem-com-32-caracteres!", 3600)

    with pytest.raises(TokenInvalidoError, match="inválido"):
        validar_token(token, SEGREDO)


def test_token_sem_assinatura_e_recusado() -> None:
    """`alg: none` é o ataque clássico: o token só é aceito em HS256."""
    token = jwt.encode(
        {"sub": "operador", "perfil": "operador", "exp": datetime.now(UTC) + timedelta(hours=1)},
        key=None,
        algorithm="none",
    )

    with pytest.raises(TokenInvalidoError):
        validar_token(token, SEGREDO)


def test_token_sem_o_perfil_operador_e_recusado() -> None:
    claims = {"sub": "alguem", "perfil": "admin", "exp": datetime.now(UTC) + timedelta(hours=1)}
    token = jwt.encode(claims, SEGREDO, algorithm=ALGORITMO)

    with pytest.raises(TokenInvalidoError, match="perfil"):
        validar_token(token, SEGREDO)


def test_lixo_no_lugar_do_token_e_recusado() -> None:
    with pytest.raises(TokenInvalidoError):
        validar_token("isto.nao.e-um-jwt", SEGREDO)


def test_segredo_curto_derruba_a_configuracao_na_subida() -> None:
    with pytest.raises(ValueError, match="32"):
        Configuracao(jwt_segredo="curto")


def test_login_so_esta_configurado_com_as_tres_variaveis() -> None:
    completo = {
        "operador_usuario": "operador",
        "operador_senha_hash": _hash("x"),
        "jwt_segredo": SEGREDO,
    }
    assert Configuracao(**completo).login_configurado
    for falta in completo:
        assert not Configuracao(**{**completo, falta: None}).login_configurado
