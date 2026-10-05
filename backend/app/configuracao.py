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

from app.services.autenticacao import TAMANHO_MINIMO_SEGREDO

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
        operador_usuario: Login do operador do dashboard (`context/02` §6).
        operador_senha_hash: PBKDF2 da senha (`app.services.autenticacao`).
        jwt_segredo: Chave HS256 dos tokens. Sem os três, o login e as rotas de
            escrita respondem 503: falta configuração não vira porta aberta.
        validade_token_s: Quanto vale um token. 8 h, um turno.
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
    operador_usuario: str | None = None
    operador_senha_hash: str | None = None
    jwt_segredo: str | None = None
    validade_token_s: int = 8 * 3600

    def __post_init__(self) -> None:
        if self.jwt_segredo is not None and len(self.jwt_segredo) < TAMANHO_MINIMO_SEGREDO:
            raise ValueError(
                f"JWT_SEGREDO precisa de pelo menos {TAMANHO_MINIMO_SEGREDO} caracteres"
            )

    @property
    def login_configurado(self) -> bool:
        return None not in (self.operador_usuario, self.operador_senha_hash, self.jwt_segredo)

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
            operador_usuario=os.getenv("OPERADOR_USUARIO") or None,
            operador_senha_hash=os.getenv("OPERADOR_SENHA_HASH") or None,
            jwt_segredo=os.getenv("JWT_SEGREDO") or None,
        )
