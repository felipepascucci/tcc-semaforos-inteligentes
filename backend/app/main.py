"""Aplicação FastAPI do backend — rotas de `context/01` §7 (Bloco 6).

`criar_app()` monta o app a partir de uma `Configuracao`. O uvicorn usa
`app.main:app`, que lê o ambiente; os testes passam a configuração deles e nunca
tocam o banco de desenvolvimento.

O `lifespan` abre o que o processo mantém:

* o engine do banco, se há `DATABASE_URL`;
* o difusor do WebSocket (throttle de 5 Hz);
* a leitura da ponte da bancada, se há `PONTE_URL`: `GET /estado` a 5 Hz,
  gravação em `log_prioridade` e `metrica_latencia`, e o WebSocket (decisão de
  2026-10-05). Ponte fora do ar não impede o backend de subir.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dependencias import Recursos
from app.api.v1.autenticacao import router as router_autenticacao
from app.api.v1.deteccoes import router as router_deteccoes
from app.api.v1.health import VERSAO
from app.api.v1.health import router as router_health
from app.api.v1.logs import router as router_logs
from app.api.v1.metricas import router as router_metricas
from app.api.v1.ocorrencias import router as router_ocorrencias
from app.api.v1.semaforos import router as router_semaforos
from app.api.v1.simulacoes import router as router_simulacoes
from app.api.v1.veiculos import router as router_veiculos
from app.api.v1.ws import router as router_ws
from app.configuracao import Configuracao
from app.logs import configurar_logs
from app.repositories.sessao import criar_engine, criar_fabrica_sessao
from app.services.ao_vivo import SimulacaoAoVivo
from app.services.bancada import GravadorBancada, LeitorPonte
from app.services.deteccoes import Deduplicador
from app.services.difusao import Difusor

PREFIXO_API = "/api/v1"

log = structlog.get_logger(__name__)


async def _abrir(config: Configuracao) -> Recursos:
    configurar_logs(config.nivel_log)
    difusor = Difusor(config.intervalo_difusao_s)
    recursos = Recursos(
        configuracao=config,
        difusor=difusor,
        ao_vivo=SimulacaoAoVivo(difusor),
        deduplicador=Deduplicador(config.janela_dedup_s),
        laco=asyncio.get_running_loop(),
    )
    if config.url_banco is not None:
        recursos.engine = criar_engine(config.url_banco)
        recursos.fabrica = criar_fabrica_sessao(recursos.engine)
    if config.url_ponte is not None:
        recursos.leitor = LeitorPonte(
            cliente=httpx.AsyncClient(base_url=config.url_ponte),
            difusor=difusor,
            gravador=None if recursos.fabrica is None else GravadorBancada(recursos.fabrica),
            intervalo_s=config.intervalo_leitura_ponte_s,
        )
        recursos.tarefas.append(asyncio.create_task(recursos.leitor.rodar(), name="ponte"))
    log.info(
        "backend_no_ar",
        banco=config.url_banco is not None,
        ponte=config.url_ponte,
        perfil=config.perfil_parametros,
        login=config.login_configurado,
    )
    return recursos


async def _fechar(recursos: Recursos) -> None:
    if recursos.leitor is not None:
        recursos.leitor.parar()
    for tarefa in recursos.tarefas:
        with contextlib.suppress(asyncio.CancelledError, TimeoutError):
            await asyncio.wait_for(tarefa, 3.0)
    if recursos.leitor is not None:
        await recursos.leitor.cliente.aclose()
    if recursos.engine is not None:
        recursos.engine.dispose()


def criar_app(configuracao: Configuracao | None = None) -> FastAPI:
    """Monta o backend.

    Args:
        configuracao: `None` lê o ambiente (`Configuracao.do_ambiente()`).
    """
    config = configuracao or Configuracao.do_ambiente()

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
        recursos = await _abrir(config)
        app.state.recursos = recursos
        try:
            yield
        finally:
            await _fechar(recursos)

    app = FastAPI(
        title="TCC — Controle Dinâmico de Semáforos",
        description=(
            "Priorização de veículos de emergência em ambientes urbanos. "
            "UNIP, Ciência da Computação, 2026."
        ),
        version=VERSAO,
        lifespan=ciclo_de_vida,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.origens_cors),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for router in (
        router_health,
        router_autenticacao,
        router_deteccoes,
        router_semaforos,
        router_veiculos,
        router_ocorrencias,
        router_logs,
        router_simulacoes,
        router_metricas,
        router_ws,
    ):
        app.include_router(router, prefix=PREFIXO_API)
    return app


app = criar_app()
