"""Login do operador do dashboard: JWT simples, um perfil (`context/02` §6, Bloco 7).

Escopo de TCC, de propósito (`context/00` §8: "um login simples basta"):

* **Uma credencial só**, a do operador, lida do ambiente (`OPERADOR_USUARIO`,
  `OPERADOR_SENHA_HASH`). Sem tabela de usuários, sem cadastro, sem RBAC.
* **A senha nunca fica em claro.** O ambiente guarda um PBKDF2-SHA256 com sal,
  da biblioteca padrão. O texto do hash usa `:` como separador, e não `$`, para
  poder ir no `.env` e no compose sem escape.
* **Token HS256** assinado com `JWT_SEGREDO`, com validade fixa (8 h, um turno).
  Não há renovação nem revogação: trocar o segredo derruba todas as sessões.

Gerar o hash de uma senha nova:

    python -m app.services.autenticacao
"""

from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

import jwt

ALGORITMO: Final = "HS256"
PERFIL_OPERADOR: Final = "operador"
PREFIXO_HASH: Final = "pbkdf2_sha256"
#: Recomendação da OWASP para PBKDF2-SHA256 (2023). O número vai dentro do hash,
#: então um hash antigo continua conferindo se este valor mudar.
ITERACOES_PBKDF2: Final = 600_000
#: O PyJWT avisa abaixo de 32 bytes para HS256 (RFC 7518 §3.2).
TAMANHO_MINIMO_SEGREDO: Final = 32


class TokenInvalidoError(ValueError):
    """Token ausente da assinatura certa, malformado ou expirado."""


def _b64(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).decode("ascii").rstrip("=")


def _de_b64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def gerar_hash_senha(
    senha: str, *, sal: bytes | None = None, iteracoes: int = ITERACOES_PBKDF2
) -> str:
    """`pbkdf2_sha256:<iterações>:<sal>:<hash>`, sal e hash em base64 de URL."""
    sal = secrets.token_bytes(16) if sal is None else sal
    derivado = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), sal, iteracoes)
    return f"{PREFIXO_HASH}:{iteracoes}:{_b64(sal)}:{_b64(derivado)}"


def conferir_senha(senha: str, hash_armazenado: str) -> bool:
    """Compara em tempo constante. Hash malformado não confere, nunca levanta."""
    try:
        prefixo, iteracoes, sal, esperado = hash_armazenado.split(":")
        if prefixo != PREFIXO_HASH:
            return False
        derivado = hashlib.pbkdf2_hmac(
            "sha256", senha.encode("utf-8"), _de_b64(sal), int(iteracoes)
        )
        return hmac.compare_digest(derivado, _de_b64(esperado))
    except ValueError:
        return False


@dataclass(frozen=True)
class Sessao:
    """O que um token válido diz: quem é e até quando vale."""

    usuario: str
    expira_em: datetime
    perfil: str = PERFIL_OPERADOR


def emitir_token(
    usuario: str, segredo: str, validade_s: int, *, agora: datetime | None = None
) -> tuple[str, Sessao]:
    """Token do operador e a sessão que ele representa."""
    emitido = agora or datetime.now(UTC)
    sessao = Sessao(usuario=usuario, expira_em=emitido + timedelta(seconds=validade_s))
    claims = {"sub": usuario, "perfil": sessao.perfil, "iat": emitido, "exp": sessao.expira_em}
    return jwt.encode(claims, segredo, algorithm=ALGORITMO), sessao


def validar_token(token: str, segredo: str) -> Sessao:
    """A sessão do token, ou `TokenInvalidoError` com o motivo para o 401."""
    try:
        claims = jwt.decode(
            token, segredo, algorithms=[ALGORITMO], options={"require": ["sub", "exp"]}
        )
    except jwt.ExpiredSignatureError as erro:
        raise TokenInvalidoError("sessão expirada: entre de novo") from erro
    except jwt.InvalidTokenError as erro:
        raise TokenInvalidoError("token inválido") from erro
    if claims.get("perfil") != PERFIL_OPERADOR:
        raise TokenInvalidoError("token sem o perfil operador")
    return Sessao(usuario=str(claims["sub"]), expira_em=datetime.fromtimestamp(claims["exp"], UTC))


if __name__ == "__main__":
    senha = getpass.getpass("Senha do operador: ")
    if senha != getpass.getpass("Repita: "):
        raise SystemExit("As senhas não conferem.")
    print(f"OPERADOR_SENHA_HASH={gerar_hash_senha(senha)}")
