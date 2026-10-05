"""Configuração do processo backend, lida do ambiente uma vez (`context/02` §4).

Os testes constroem a `Configuracao` à mão e passam a `criar_app()`. Assim nenhum
teste lê o `.env` do desenvolvedor e acaba falando com o banco de verdade.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

RAIZ: Final = Path(__file__).resolve().parents[2]

#: O cruzamento do protótipo nos seeds (`context/03` §5).
CODIGO_BANCADA: Final = "PROTO_CRUZ_01"


def _lista(bruto: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in bruto.split(",") if item.strip())


@dataclass(frozen=True)
class Configuracao:
    """O que o backend precisa saber do ambiente.

    Attributes:
        url_banco: `DATABASE_URL`. `None` deixa o backend de pé e o `/health`
            dizendo `nao_configurado`, sem fingir que há banco.
        url_ponte: Onde a ponte da bancada atende (`GET /estado`). `None`
            desliga a leitura. No compose é `host.docker.internal:8001`: a ponte
            roda no host, porque precisa da USB (`context/02` §3).
        intervalo_leitura_ponte_s: Período da leitura de `/estado`. 5 Hz, o
            mesmo ritmo do WebSocket (decisão de 2026-10-05).
        intervalo_difusao_s: Throttle do WebSocket (`context/01` §7).
        janela_dedup_s: Janela anti-replay das detecções (`context/02` §6).
        perfil_parametros: `simulacao` ou `hardware`.
        origens_cors: Origens aceitas pelo navegador.
        nivel_log: Nível mínimo dos logs.
        arquivo_cenarios: `sim/config/cenarios.yaml`, para validar
            `POST /simulacoes` (cenários e seeds reservadas).
    """

    url_banco: str | None = None
    url_ponte: str | None = None
    intervalo_leitura_ponte_s: float = 0.2
    intervalo_difusao_s: float = 0.2
    janela_dedup_s: float = 2.0
    perfil_parametros: str = "simulacao"
    origens_cors: tuple[str, ...] = ("http://localhost:5173",)
    nivel_log: str = "INFO"
    arquivo_cenarios: Path = field(default=RAIZ / "sim" / "config" / "cenarios.yaml")

    @classmethod
    def do_ambiente(cls) -> Configuracao:
        """Lê as variáveis do processo, com o `.env` da raiz como reserva.

        `override=False`: dentro do contêiner o `environment:` do compose vence o
        `.env`, que fala da perspectiva do host (`app/repositories/sessao.py`).
        """
        load_dotenv(RAIZ / ".env", override=False)
        return cls(
            url_banco=os.getenv("DATABASE_URL") or None,
            url_ponte=os.getenv("PONTE_URL") or None,
            perfil_parametros=os.getenv("PERFIL_PARAMETROS", "simulacao"),
            origens_cors=_lista(os.getenv("CORS_ORIGINS", "http://localhost:5173")),
            nivel_log=os.getenv("LOG_LEVEL", "INFO"),
        )
