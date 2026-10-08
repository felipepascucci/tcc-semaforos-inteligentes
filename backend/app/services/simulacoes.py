"""Pedidos de simulação pela API (decisões de 2026-10-05, Bloco 6).

O backend não roda o SUMO: grava o pedido, e o atendente do host
(`python -m sim.controlador.atendente`) o executa. As regras ficam aqui e no
atendente, que confere de novo antes de rodar:

* o cenário precisa existir em `sim/config/cenarios.yaml`;
* a seed não pode estar em `execucao.seeds_reservadas` (1..50 do Bloco 8,
  101..105 da calibração, 201..250 do treino do modelo de P19). Uma execução de
  demonstração ocuparia em `execucao_simulacao` o ponto do lote, que o rodaria
  sem registro no banco.

Cada faixa traz o seu `uso`, que o dashboard mostra ao lado do campo de seed
(`GET /simulacoes/seeds-reservadas`): as faixas e a explicação vêm do mesmo
arquivo que a regra, e não há uma segunda cópia na tela para envelhecer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import PedidoSimulacao
from app.schemas.simulacoes import PedidoSimulacaoEntrada


class CenarioDesconhecidoError(ValueError):
    """O cenário não está em `cenarios.yaml`."""


class SeedReservadaError(ValueError):
    """A seed pertence ao experimento (Bloco 8, calibração ou treino do modelo)."""


@dataclass(frozen=True)
class RegrasSimulacao:
    cenarios: frozenset[str]
    seeds_reservadas: tuple[tuple[int, int], ...]
    usos: Mapping[tuple[int, int], str] = field(default_factory=dict)

    @classmethod
    def de_arquivo(cls, arquivo: Path) -> RegrasSimulacao:
        with arquivo.open(encoding="utf-8") as entrada:
            configuracao = yaml.safe_load(entrada)
        itens = configuracao["execucao"]["seeds_reservadas"]
        faixas = tuple((int(item["faixa"][0]), int(item["faixa"][1])) for item in itens)
        return cls(
            cenarios=frozenset(configuracao["cenarios"]),
            seeds_reservadas=faixas,
            usos={faixa: str(item["uso"]) for faixa, item in zip(faixas, itens, strict=True)},
        )

    def faixas(self) -> list[tuple[int, int, str]]:
        """`(início, fim, uso)` de cada faixa reservada, em ordem crescente."""
        return [
            (inicio, fim, self.usos.get((inicio, fim), ""))
            for inicio, fim in sorted(self.seeds_reservadas)
        ]

    def reservada(self, seed: int) -> tuple[int, int] | None:
        """A faixa reservada que contém `seed`, ou `None`."""
        return next((f for f in self.seeds_reservadas if f[0] <= seed <= f[1]), None)

    def validar(self, cenario: str, seed: int) -> None:
        if cenario not in self.cenarios:
            raise CenarioDesconhecidoError(
                f"cenário {cenario!r} não existe; use um de {', '.join(sorted(self.cenarios))}"
            )
        if (faixa := self.reservada(seed)) is not None:
            uso = self.usos.get(faixa)
            raise SeedReservadaError(
                f"seed {seed} é do experimento ({faixa[0]}..{faixa[1]}"
                f"{f': {uso}' if uso else ''}); "
                "demonstração usa seed fora das faixas reservadas"
            )


def criar_pedido(
    sessao: Session, entrada: PedidoSimulacaoEntrada, regras: RegrasSimulacao
) -> PedidoSimulacao:
    """Grava o pedido como `PENDENTE`.

    Raises:
        CenarioDesconhecidoError: cenário fora de `cenarios.yaml`.
        SeedReservadaError: seed do experimento.
    """
    regras.validar(entrada.cenario, entrada.seed)
    pedido = PedidoSimulacao(
        nome_cenario=entrada.cenario,
        modo=entrada.modo,
        seed=entrada.seed,
        duracao_s=entrada.duracao_s,
        velocidade=entrada.velocidade,
    )
    sessao.add(pedido)
    sessao.flush()
    sessao.refresh(pedido)
    return pedido


def listar_pedidos(sessao: Session, limite: int = 50) -> list[PedidoSimulacao]:
    consulta = (
        select(PedidoSimulacao)
        .options(selectinload(PedidoSimulacao.execucao))
        .order_by(PedidoSimulacao.criado_em.desc(), PedidoSimulacao.id_pedido.desc())
        .limit(limite)
    )
    return list(sessao.scalars(consulta))


def buscar_pedido(sessao: Session, id_pedido: int) -> PedidoSimulacao | None:
    consulta = (
        select(PedidoSimulacao)
        .options(selectinload(PedidoSimulacao.execucao))
        .where(PedidoSimulacao.id_pedido == id_pedido)
    )
    return sessao.scalars(consulta).one_or_none()
