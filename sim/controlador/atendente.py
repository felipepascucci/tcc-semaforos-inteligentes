"""Atendente de pedidos de simulação — roda no host, onde está o SUMO (Bloco 6).

    python -m sim.controlador.atendente              # atende até Ctrl+C
    python -m sim.controlador.atendente --uma-vez    # atende o que houver e sai

`POST /simulacoes` grava um pedido em `pedido_simulacao`, e o backend, no
contêiner, não tem SUMO (`context/02` §3). Este processo pega o pendente mais
antigo, roda o executor com transmissão ao vivo e grava o desfecho.

O QUE ELE GARANTE

* **Nada de `analysis/data/`.** Os CSV vão para a pasta da própria execução, em
  `sim/saida/`, que é limpa antes de rodar. É demonstração, não experimento.
* **Seed reservada é recusada de novo**, mesmo que o pedido tenha entrado no banco
  por outro caminho que não a API (decisão de 2026-10-05).
* **Um pedido por vez, e um atendente por pedido.** A escolha usa
  `FOR UPDATE SKIP LOCKED`: dois atendentes nunca pegam o mesmo pedido.
* **Repetir um ponto é permitido**, para assistir de novo. Mesma seed e mesma
  configuração dão o mesmo resultado, então só a primeira execução do ponto
  grava em `execucao_simulacao`; as seguintes apontam para ela.
"""

from __future__ import annotations

import argparse
import os
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.logs import configurar_logs
from app.models import ModoControle, PedidoSimulacao
from app.repositories.experimento import buscar_execucao
from app.repositories.sessao import criar_engine, criar_fabrica_sessao, sessao_de
from app.services.simulacoes import RegrasSimulacao
from sim.controlador import executor
from sim.controlador.coletor import ResultadoExecucao
from sim.controlador.lote import ARQUIVOS_CSV

log = structlog.get_logger(__name__)

CENARIOS = executor.CENARIOS_YAML
TAMANHO_MENSAGEM = 200

Executar = Callable[[executor.Opcoes], ResultadoExecucao]


@dataclass(frozen=True)
class Tarefa:
    """O que o atendente precisa do pedido, já fora da sessão."""

    id_pedido: int
    cenario: str
    modo: str
    seed: int
    duracao_s: int | None


def pegar_proximo(sessao: Session) -> Tarefa | None:
    """Marca o pendente mais antigo como `RODANDO` e o devolve."""
    pedido = sessao.scalars(
        select(PedidoSimulacao)
        .where(PedidoSimulacao.status == "PENDENTE")
        .order_by(PedidoSimulacao.criado_em, PedidoSimulacao.id_pedido)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).one_or_none()
    if pedido is None:
        return None
    pedido.status = "RODANDO"
    pedido.iniciado_em = datetime.now(UTC)
    return Tarefa(
        pedido.id_pedido, pedido.nome_cenario, pedido.modo.value, pedido.seed, pedido.duracao_s
    )


def resumo(resultado: ResultadoExecucao, pasta: Path) -> dict[str, Any]:
    """O que `GET /simulacoes/{id}` mostra. Medido nesta execução; não é capítulo 5."""
    return {
        "tempo_medio_travessia_ve_s": round(resultado.tempo_medio_travessia_ve_s, 2),
        "viagens_ve": len(resultado.viagens_ve),
        "paradas_ve": sum(viagem.paradas for viagem in resultado.viagens_ve),
        "tempo_espera_medio_transversal_s": round(resultado.tempo_espera_medio_transversal_s, 2),
        "latencia_p95_ms": round(resultado.latencia_p95_ms, 3),
        "latencia_max_ms": round(resultado.latencia_max_ms, 3),
        "veiculos_completos": resultado.veiculos_completos,
        "veiculos_planejados": resultado.veiculos_planejados,
        "violacoes": len(resultado.violacoes),
        "colisoes": resultado.colisoes,
        "teleportes": resultado.teleportes,
        "pasta": str(pasta),
    }


def atender(
    fabrica: sessionmaker[Session],
    tarefa: Tarefa,
    *,
    url_backend: str | None,
    regras: RegrasSimulacao,
    executar: Executar = executor.executar,
) -> str:
    """Roda a tarefa e grava o desfecho. Devolve o status final."""
    log.info("pedido_iniciado", id_pedido=tarefa.id_pedido, cenario=tarefa.cenario)
    try:
        regras.validar(tarefa.cenario, tarefa.seed)
        with sessao_de(fabrica) as sessao:
            ja_existia = (
                buscar_execucao(
                    sessao,
                    nome_cenario=tarefa.cenario,
                    modo=ModoControle(tarefa.modo),
                    seed=tarefa.seed,
                )
                is not None
            )
        pasta = executor.pasta_de_saida(tarefa.cenario, tarefa.modo, tarefa.seed)
        for nome in ARQUIVOS_CSV:
            (pasta / nome).unlink(missing_ok=True)
        resultado = executar(
            executor.Opcoes(
                cenario=tarefa.cenario,
                modo=tarefa.modo,
                seed=tarefa.seed,
                duracao_s=None if tarefa.duracao_s is None else float(tarefa.duracao_s),
                persistir=not ja_existia,
                diretorio_csv=pasta,
                transmitir=url_backend,
                id_pedido=tarefa.id_pedido,
            )
        )
    except Exception as erro:
        log.error("pedido_falhou", id_pedido=tarefa.id_pedido, erro=repr(erro))
        traceback.print_exc()
        _finalizar(fabrica, tarefa, "FALHA", f"{type(erro).__name__}: {erro}", None)
        return "FALHA"

    _finalizar(fabrica, tarefa, "CONCLUIDA", None, resumo(resultado, pasta))
    log.info("pedido_concluido", id_pedido=tarefa.id_pedido)
    return "CONCLUIDA"


def _finalizar(
    fabrica: sessionmaker[Session],
    tarefa: Tarefa,
    status: str,
    mensagem: str | None,
    dados: dict[str, Any] | None,
) -> None:
    with sessao_de(fabrica) as sessao:
        pedido = sessao.get(PedidoSimulacao, tarefa.id_pedido)
        assert pedido is not None
        execucao = buscar_execucao(
            sessao, nome_cenario=tarefa.cenario, modo=ModoControle(tarefa.modo), seed=tarefa.seed
        )
        pedido.status = status
        pedido.mensagem = None if mensagem is None else mensagem[:TAMANHO_MENSAGEM]
        pedido.resumo = dados
        pedido.fk_execucao = None if execucao is None else execucao.id_execucao
        pedido.finalizado_em = datetime.now(UTC)


def atender_pendentes(
    fabrica: sessionmaker[Session],
    *,
    url_backend: str | None,
    regras: RegrasSimulacao,
    executar: Executar = executor.executar,
) -> int:
    """Atende até não sobrar pendente. Devolve quantos atendeu."""
    atendidos = 0
    while True:
        with sessao_de(fabrica) as sessao:
            tarefa = pegar_proximo(sessao)
        if tarefa is None:
            return atendidos
        atender(fabrica, tarefa, url_backend=url_backend, regras=regras, executar=executar)
        atendidos += 1


def main(argumentos: list[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(description="Atende os pedidos de POST /simulacoes.")
    analisador.add_argument("--uma-vez", action="store_true", help="atende o que houver e sai")
    analisador.add_argument("--intervalo", type=float, default=2.0, help="segundos entre consultas")
    analisador.add_argument(
        "--backend",
        default=os.getenv("BACKEND_URL", "http://localhost:8000"),
        help="para onde transmitir o estado ao vivo",
    )
    analisador.add_argument("--sem-transmissao", action="store_true")
    opcoes = analisador.parse_args(argumentos)

    configurar_logs(os.getenv("LOG_LEVEL", "INFO"))
    fabrica = criar_fabrica_sessao(criar_engine())
    regras = RegrasSimulacao.de_arquivo(CENARIOS)
    url = None if opcoes.sem_transmissao else opcoes.backend
    log.info("atendente_no_ar", backend=url)
    try:
        while True:
            atender_pendentes(fabrica, url_backend=url, regras=regras)
            if opcoes.uma_vez:
                return 0
            time.sleep(opcoes.intervalo)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
