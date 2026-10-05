"""`POST /deteccoes` — o contrato do V2I com rede (`context/01` §7, P20).

**Na bancada nenhum dispositivo chama esta rota** (decisão de 2026-10-05): os
NodeMCUs se falam por ESP-NOW e o UNO decide sozinho, e os eventos dele entram
pela leitura da ponte (`app/services/bancada.py`). A rota continua sendo o
contrato da arquitetura-alvo, de um leitor com rede, e é aqui que P20 vale na
API. É exercitada pelos testes e pelo Swagger.

A ordem das verificações é a de `context/02` §6:

1. **`X-Device-Token`**, contra o `token_hash` do dispositivo de `id_leitor`.
   Sem token, token errado, dispositivo desconhecido ou inativo: **401**, sem
   gravar nada, porque não se sabe quem está falando.
2. **Anti-replay de 2 s**: a mesma tag outra vez, ou uma `sequencia` que não
   avança no mesmo dispositivo, dentro da janela. O RC522 lê a mesma tag várias
   vezes por segundo. A repetição recebe a resposta da primeira e não grava nada,
   para não inflar o denominador do RNF05.
3. **`core.autorizacao.autorizar()`**: tag desconhecida ou inativa é **403**;
   tag reconhecida sem ocorrência é **200** com `SEM_OCORRENCIA` (P20).

**O que `PREEMPCAO_SOLICITADA` faz.** Grava a detecção e, se o leitor pertence a
um cruzamento, uma linha `SUCESSO` em `log_prioridade` com o mesmo
`id_correlacao`. **A API não comanda atuador**: na simulação o motor roda no
processo do executor, e na bancada quem decide é o UNO. `SUCESSO` registra que a
priorização foi concedida, e o `motivo` diz isso por extenso.
"""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

import structlog
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import DispositivoIot, StatusExecucao, StatusOperacao
from app.repositories import operacao
from app.repositories.cadastro import (
    buscar_dispositivo_por_codigo,
    buscar_veiculo_por_uid,
    normalizar_uid,
)
from app.repositories.ocorrencia import ocorrencia_ativa_do_veiculo
from app.schemas.deteccoes import PedidoDeteccao, RespostaDeteccao
from core.autorizacao import Autorizacao, MotivoAutorizacao, autorizar

log = structlog.get_logger(__name__)

#: O que o leitor mostraria no LCD, por desfecho (`context/01` §7).
LCD_SEM_OCORRENCIA: Final = "SEM OCORRENCIA\nSEM PRIORIDADE"
LCD_INATIVO: Final = "VEICULO INATIVO\nSEM PRIORIDADE"
LCD_NEGADO: Final = "TAG DESCONHECIDA\nACESSO NEGADO"


class DispositivoNaoAutenticadoError(PermissionError):
    """Token ausente ou errado, ou dispositivo desconhecido ou inativo: 401."""


@dataclass(frozen=True)
class Resultado:
    """A resposta e o código HTTP dela (200 ou 403)."""

    resposta: RespostaDeteccao
    status_http: int


def hash_token(token: str) -> str:
    """O mesmo SHA-256 dos seeds (`db/seeds/carregar.py`)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass
class Deduplicador:
    """Janela anti-replay de 2 s, em memória, por UID e por (dispositivo, sequência).

    A mesma tag lida de novo dentro da janela é a mesma passagem: o RC522 lê
    várias vezes por segundo. A mesma `sequencia` do mesmo dispositivo é o mesmo
    pacote reenviado. Nos dois casos a resposta é a da primeira vez, e nada é
    gravado.

    Em memória, e não no banco, porque a janela é de 2 s e o backend é um
    processo só: um reinício perde no máximo uma janela.
    """

    janela_s: float = 2.0
    relogio: Callable[[], float] = time.monotonic
    _vistos: dict[tuple[str, ...], tuple[float, Resultado]] = field(default_factory=dict)

    def repetida(self, uid: str, dispositivo: str, sequencia: int | None) -> Resultado | None:
        """A resposta original, se esta leitura repete uma da janela."""
        agora = self.relogio()
        for chave in self._chaves(uid, dispositivo, sequencia):
            visto = self._vistos.get(chave)
            if visto is not None and agora - visto[0] < self.janela_s:
                return visto[1]
        return None

    def lembrar(self, uid: str, dispositivo: str, sequencia: int | None, res: Resultado) -> None:
        agora = self.relogio()
        # Esquecer o que saiu da janela: sem isso o dicionário cresce sem fim (RNF02).
        self._vistos = {c: v for c, v in self._vistos.items() if agora - v[0] < self.janela_s}
        for chave in self._chaves(uid, dispositivo, sequencia):
            self._vistos[chave] = (agora, res)

    @staticmethod
    def _chaves(uid: str, dispositivo: str, sequencia: int | None) -> list[tuple[str, ...]]:
        chaves: list[tuple[str, ...]] = [("uid", uid)]
        if sequencia is not None:
            chaves.append(("sequencia", dispositivo, str(sequencia)))
        return chaves


def autenticar(sessao: Session, codigo: str, token: str | None) -> int:
    """O `id_dispositivo` do leitor, se o token confere.

    Raises:
        DispositivoNaoAutenticadoError: em qualquer falha. A mensagem é a mesma
            para todas, para não revelar quais dispositivos existem.
    """
    dispositivo = buscar_dispositivo_por_codigo(sessao, codigo)
    valido = (
        token is not None
        and dispositivo is not None
        and dispositivo.status is StatusOperacao.ATIVO
        and hmac.compare_digest(hash_token(token), dispositivo.token_hash)
    )
    if not valido or dispositivo is None:
        raise DispositivoNaoAutenticadoError("X-Device-Token ausente ou inválido")
    dispositivo.ultimo_contato = func.now()  # type: ignore[assignment]
    return dispositivo.id_dispositivo


def processar(
    sessao: Session,
    pedido: PedidoDeteccao,
    token: str | None,
    deduplicador: Deduplicador,
) -> Resultado:
    """Autentica, deduplica, autoriza e grava uma detecção."""
    id_dispositivo = autenticar(sessao, pedido.id_leitor, token)
    uid = normalizar_uid(pedido.uid_tag)

    if (anterior := deduplicador.repetida(uid, pedido.id_leitor, pedido.sequencia)) is not None:
        log.info("deteccao_repetida", uid=uid, dispositivo=pedido.id_leitor)
        return Resultado(
            anterior.resposta.model_copy(update={"duplicada": True}), anterior.status_http
        )

    id_correlacao = uuid.uuid4()
    structlog.contextvars.bind_contextvars(id_correlacao=str(id_correlacao))
    try:
        resultado = _decidir_e_gravar(sessao, pedido, uid, id_dispositivo, id_correlacao)
    finally:
        structlog.contextvars.unbind_contextvars("id_correlacao")
    deduplicador.lembrar(uid, pedido.id_leitor, pedido.sequencia, resultado)
    return resultado


def _decidir_e_gravar(
    sessao: Session,
    pedido: PedidoDeteccao,
    uid: str,
    id_dispositivo: int,
    id_correlacao: uuid.UUID,
) -> Resultado:
    veiculo = buscar_veiculo_por_uid(sessao, uid)
    ocorrencia = (
        None if veiculo is None else ocorrencia_ativa_do_veiculo(sessao, veiculo.id_veiculo)
    )
    ativo = None if veiculo is None else veiculo.status_operacional is StatusOperacao.ATIVO
    decisao = autorizar(ativo, ocorrencia)

    operacao.registrar_deteccao(
        sessao,
        id_correlacao=id_correlacao,
        origem=pedido.origem,
        reconhecido=veiculo is not None,
        uid_bruto=pedido.uid_tag,
        fk_dispositivo=id_dispositivo,
        fk_veiculo=None if veiculo is None else veiculo.id_veiculo,
        rssi=pedido.rssi,
        sequencia=pedido.sequencia,
        autorizado=decisao.autorizado,
        fk_ocorrencia=None if decisao.ocorrencia is None else decisao.ocorrencia.id_ocorrencia,
    )

    if veiculo is None:
        log.warning("deteccao_negada", motivo=decisao.motivo.value, uid=uid)
        return Resultado(
            RespostaDeteccao(
                reconhecido=False,
                autorizado=False,
                id_veiculo=None,
                tipo=None,
                criticidade=None,
                acao="ACESSO_NEGADO",
                id_log=None,
                mensagem_lcd=LCD_NEGADO,
            ),
            403,
        )

    id_log = None
    if decisao.autorizado:
        acao, lcd = "PREEMPCAO_SOLICITADA", f"{veiculo.tipo.value}\nPRIORIDADE ATIVA"
        id_log = _registrar_priorizacao(
            sessao, pedido, veiculo.id_veiculo, id_dispositivo, decisao, id_correlacao
        )
    elif decisao.motivo is MotivoAutorizacao.SEM_OCORRENCIA:
        acao, lcd = "SEM_OCORRENCIA", LCD_SEM_OCORRENCIA
    else:
        acao, lcd = "VEICULO_INATIVO", LCD_INATIVO

    log.info(
        "deteccao",
        acao=acao,
        id_veiculo=veiculo.id_veiculo,
        criticidade=None if decisao.criticidade is None else int(decisao.criticidade),
    )
    return Resultado(
        RespostaDeteccao(
            reconhecido=True,
            autorizado=decisao.autorizado,
            id_veiculo=veiculo.id_veiculo,
            tipo=veiculo.tipo,
            criticidade=None if decisao.criticidade is None else int(decisao.criticidade),
            acao=acao,  # type: ignore[arg-type]
            id_log=id_log,
            mensagem_lcd=lcd,
        ),
        200,
    )


def _registrar_priorizacao(
    sessao: Session,
    pedido: PedidoDeteccao,
    id_veiculo: int,
    id_dispositivo: int,
    decisao: Autorizacao,
    id_correlacao: uuid.UUID,
) -> int | None:
    """A linha de `log_prioridade` da detecção autorizada; `None` sem cruzamento."""
    dispositivo = sessao.get(DispositivoIot, id_dispositivo)
    if dispositivo is None or dispositivo.fk_semaforo is None:
        return None
    ocorrencia = decisao.ocorrencia
    assert ocorrencia is not None  # autorizado implica ocorrência (core/autorizacao)
    linha = operacao.registrar_log_prioridade(
        sessao,
        id_correlacao=id_correlacao,
        fk_semaforo=dispositivo.fk_semaforo,
        fk_veiculo=id_veiculo,
        timestamp_inicio=func.now(),  # type: ignore[arg-type]
        status_execucao=StatusExecucao.SUCESSO,
        motivo=(
            f"Priorização concedida por {pedido.origem} via {pedido.id_leitor}: ocorrência "
            f"{ocorrencia.id_ocorrencia}, criticidade {int(ocorrencia.criticidade)}. "
            "A API não comanda atuador (context/01 §7)"
        ),
    )
    return linha.id_log
