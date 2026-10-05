"""Recursos do processo e dependências das rotas.

Os recursos nascem no `lifespan` de `app.main` e ficam em `app.state.recursos`.
Os testes montam o app com `criar_app(Configuracao(...))` e nunca tocam o banco
de desenvolvimento.

**Commit explícito.** As rotas que gravam chamam `sessao.commit()` antes de
responder. A dependência só fecha a sessão, e desfaz o que não foi confirmado.
Assim um erro de banco vira 500 antes de a resposta sair, e nunca um 201 seguido
de rollback.

**Login do operador (Bloco 7).** As rotas de escrita do dashboard exigem o token
de `POST /auth/login` (`exigir_operador`). Os GETs e o WebSocket ficam abertos;
`/deteccoes` continua com `X-Device-Token`, e `/simulacoes/transmissao`, que o
executor chama do host, continua sem autenticação (limitação declarada,
`context/02` §6).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import cached_property
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.configuracao import Configuracao
from app.services.ao_vivo import SimulacaoAoVivo
from app.services.autenticacao import Sessao, TokenInvalidoError, validar_token
from app.services.bancada import LeitorPonte
from app.services.deteccoes import Deduplicador
from app.services.difusao import Difusor
from app.services.simulacoes import RegrasSimulacao


@dataclass
class Recursos:
    configuracao: Configuracao
    difusor: Difusor
    ao_vivo: SimulacaoAoVivo
    deduplicador: Deduplicador
    laco: asyncio.AbstractEventLoop
    engine: Engine | None = None
    fabrica: sessionmaker[Session] | None = None
    leitor: LeitorPonte | None = None
    tarefas: list[asyncio.Task[None]] = field(default_factory=list)

    @cached_property
    def regras_simulacao(self) -> RegrasSimulacao:
        return RegrasSimulacao.de_arquivo(self.configuracao.arquivo_cenarios)

    def publicar_evento(self, dados: dict[str, Any]) -> None:
        """Evento no WebSocket a partir de uma rota síncrona (que roda numa thread)."""
        self.laco.call_soon_threadsafe(self.difusor.publicar_evento, dados)


def obter_recursos(request: Request) -> Recursos:
    recursos: Recursos = request.app.state.recursos
    return recursos


def obter_sessao(request: Request) -> Iterator[Session]:
    fabrica = obter_recursos(request).fabrica
    if fabrica is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "banco não configurado")
    with fabrica() as sessao:
        try:
            yield sessao
        finally:
            sessao.rollback()  # desfaz só o que a rota não confirmou


RecursosDep = Annotated[Recursos, Depends(obter_recursos)]
SessaoDep = Annotated[Session, Depends(obter_sessao)]

_bearer = HTTPBearer(auto_error=False, description="O `access_token` de `POST /auth/login`")


def exigir_operador(
    recursos: RecursosDep,
    credenciais: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Sessao:
    """Rotas de escrita do operador (`context/02` §6, decisão do Bloco 7).

    Sem login configurado, 503: o backend não aceita escrita anônima por falta
    de configuração. Sem token, ou com token inválido ou expirado, 401.
    """
    config = recursos.configuracao
    if config.jwt_segredo is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "login não configurado: defina OPERADOR_USUARIO, OPERADOR_SENHA_HASH e JWT_SEGREDO",
        )
    if credenciais is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "login necessário: rota de escrita do operador",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return validar_token(credenciais.credentials, config.jwt_segredo)
    except TokenInvalidoError as erro:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, str(erro), headers={"WWW-Authenticate": "Bearer"}
        ) from erro


OperadorDep = Annotated[Sessao, Depends(exigir_operador)]
#: Para o `dependencies=[...]` das rotas que não usam a sessão.
EXIGE_OPERADOR = Depends(exigir_operador)
