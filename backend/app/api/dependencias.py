"""Recursos do processo e dependências das rotas.

Os recursos nascem no `lifespan` de `app.main` e ficam em `app.state.recursos`.
Os testes montam o app com `criar_app(Configuracao(...))` e nunca tocam o banco
de desenvolvimento.

**Commit explícito.** As rotas que gravam chamam `sessao.commit()` antes de
responder. A dependência só fecha a sessão, e desfaz o que não foi confirmado.
Assim um erro de banco vira 500 antes de a resposta sair, e nunca um 201 seguido
de rollback.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import cached_property
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.configuracao import Configuracao
from app.services.ao_vivo import SimulacaoAoVivo
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
