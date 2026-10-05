"""`/auth` — login do operador do dashboard (`context/02` §6, Bloco 7).

Uma credencial, a do operador, lida do ambiente. O token vai no cabeçalho
`Authorization: Bearer …` das rotas de escrita (`app.api.dependencias`).
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, HTTPException, status

from app.api.dependencias import OperadorDep, RecursosDep
from app.schemas.autenticacao import PedidoLogin, RespostaLogin, SessaoSchema
from app.services.autenticacao import conferir_senha, emitir_token

router = APIRouter(tags=["autenticacao"])


@router.post(
    "/auth/login",
    response_model=RespostaLogin,
    summary="Login do operador",
    responses={
        401: {"description": "Usuário ou senha incorretos"},
        503: {"description": "Login não configurado no ambiente"},
    },
)
def entrar(pedido: PedidoLogin, recursos: RecursosDep) -> RespostaLogin:
    """Devolve o token do operador, válido por 8 h."""
    config = recursos.configuracao
    if (
        config.operador_usuario is None
        or config.operador_senha_hash is None
        or config.jwt_segredo is None
    ):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "login não configurado: defina OPERADOR_USUARIO, OPERADOR_SENHA_HASH e JWT_SEGREDO",
        )
    # A senha é conferida mesmo com o usuário errado: a resposta não pode ser
    # mais rápida para um usuário inexistente.
    usuario_ok = hmac.compare_digest(pedido.usuario.encode(), config.operador_usuario.encode())
    senha_ok = conferir_senha(pedido.senha, config.operador_senha_hash)
    if not (usuario_ok and senha_ok):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "usuário ou senha incorretos")
    token, sessao = emitir_token(
        config.operador_usuario, config.jwt_segredo, config.validade_token_s
    )
    return RespostaLogin(
        access_token=token,
        usuario=sessao.usuario,
        perfil=sessao.perfil,
        expira_em=sessao.expira_em,
    )


@router.get("/auth/sessao", response_model=SessaoSchema, summary="Sessão do token atual")
def sessao(operador: OperadorDep) -> SessaoSchema:
    """Para o dashboard conferir, ao abrir, se o token guardado ainda vale."""
    return SessaoSchema(
        usuario=operador.usuario, perfil=operador.perfil, expira_em=operador.expira_em
    )
