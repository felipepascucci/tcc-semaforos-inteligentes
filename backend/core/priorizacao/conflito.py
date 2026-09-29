"""Etapa E8 — conflito entre múltiplos VEs (`context/01` §5.2).

Cenário obrigatório de teste, e o cenário experimental `multiplas_emergencias`
existe para exercitá-lo. A regra é curta e não admite exceção: **se dois VEs
demandam fases conflitantes no mesmo cruzamento, um espera. Nunca conceder as
duas.**

Ordem de desempate, exatamente como em `context/01` §5.2:

1. Maior prioridade por tipo — configurável, padrão `AMBULANCIA > BOMBEIRO > POLICIA`.
2. Menor ETA ao cruzamento.
3. Preempção já em curso vence, o que evita oscilação entre dois pedidos empatados.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from core.malha import Cruzamento
from core.parametros import Parametros
from core.priorizacao.deteccao import DeteccaoVE


@dataclass(frozen=True)
class Disputa:
    """Um pedido de preempção em um cruzamento.

    Attributes:
        deteccao: A detecção que originou o pedido.
        fase_desejada: Fase que serviria o movimento do VE.
        ja_em_curso: Se este VE já é o dono da preempção ativa no cruzamento.
    """

    deteccao: DeteccaoVE
    fase_desejada: int
    ja_em_curso: bool = False


@dataclass(frozen=True)
class EventoConflito:
    """Um instante em que mais de um VE demanda fases distintas no mesmo cruzamento.

    É a unidade que a entrega 10.1 conta, e o gatilho que a rotulagem por
    bifurcação (10.4) vai usar. Note que o evento é publicado **antes** de E8
    desempatar: ele descreve a disputa, não o desfecho.

    Attributes:
        t: Instante da observação, em segundos.
        id_semaforo: Cruzamento disputado.
        disputas: Os pedidos concorrentes, na ordem em que foram levantados.
        preempcao_em_curso: Id do VE que já detém a preempção no cruzamento, ou
            `None`. Quando há um, a decisão está **suspensa** pela guarda de
            oscilação, que é regra rígida acima de qualquer política aprendida
            (`context/09` P19) — por isso o campo, e não um simples contador.
    """

    t: float
    id_semaforo: str
    disputas: tuple[Disputa, ...]
    preempcao_em_curso: str | None = None

    @property
    def decidivel(self) -> bool:
        """Se a escolha do vencedor está em aberto neste instante."""
        return self.preempcao_em_curso is None

    @property
    def ids_veiculos(self) -> tuple[str, ...]:
        """Ids dos VEs em disputa, ordenados — a identidade do episódio."""
        return tuple(sorted(disputa.deteccao.id_veiculo for disputa in self.disputas))


@dataclass(frozen=True)
class Resolucao:
    """Quem foi atendido e quem esperou.

    Attributes:
        id_semaforo: Cruzamento disputado.
        vencedor: Pedido atendido.
        atendidos_juntos: Pedidos que pedem a **mesma** fase do vencedor e,
            portanto, são servidos pelo mesmo verde sem conflito nenhum.
        adiados: Pedidos que precisam esperar. Cada um vira uma linha em
            `log_prioridade` com `status_execucao = 'CONFLITO_ADIADO'`.
        motivo: Justificativa legível do desempate.
    """

    id_semaforo: str
    vencedor: Disputa
    atendidos_juntos: tuple[Disputa, ...] = ()
    adiados: tuple[Disputa, ...] = ()
    motivo: str = ""


def _chave_de_desempate(disputa: Disputa, parametros: Parametros) -> tuple[int, float, int]:
    """Chave de ordenação: menor vence, na ordem 1 → 2 → 3 de `context/01` §5.2."""
    return (
        parametros.indice_prioridade(disputa.deteccao.tipo),
        disputa.deteccao.eta_s,
        0 if disputa.ja_em_curso else 1,
    )


def resolver(
    id_semaforo: str,
    disputas: Sequence[Disputa],
    cruzamento: Cruzamento,
    parametros: Parametros,
) -> Resolucao | None:
    """Etapa **E8** — decide quem recebe o verde e quem espera.

    Args:
        id_semaforo: Cruzamento disputado.
        disputas: Pedidos concorrentes no mesmo cruzamento.
        cruzamento: Topologia, que define quais fases conflitam.
        parametros: Parâmetros do algoritmo, com a ordem de prioridade por tipo.

    Returns:
        A resolução, ou `None` se não houver pedido nenhum.
    """
    if not disputas:
        return None

    ordenadas = sorted(disputas, key=lambda d: _chave_de_desempate(d, parametros))
    vencedor = ordenadas[0]

    juntos: list[Disputa] = []
    adiados: list[Disputa] = []
    for disputa in ordenadas[1:]:
        if disputa.fase_desejada == vencedor.fase_desejada:
            # Mesma fase: o mesmo verde serve os dois. Não há conflito.
            juntos.append(disputa)
        elif cruzamento.conflitam(vencedor.fase_desejada, disputa.fase_desejada):
            adiados.append(disputa)
        else:
            # Fases distintas e compatíveis poderiam coexistir em um controlador
            # multi-anel. Este projeto opera um verde por vez, então o pedido
            # espera — conservador, e coerente com o protótipo em split phasing.
            adiados.append(disputa)

    return Resolucao(
        id_semaforo=id_semaforo,
        vencedor=vencedor,
        atendidos_juntos=tuple(juntos),
        adiados=tuple(adiados),
        motivo=_motivo(vencedor, adiados, parametros),
    )


def _motivo(vencedor: Disputa, adiados: Iterable[Disputa], parametros: Parametros) -> str:
    """Texto que explica o desempate, para o log e para a banca."""
    veiculo = vencedor.deteccao
    base = (
        f"{veiculo.tipo} {veiculo.id_veiculo} atendido na fase {vencedor.fase_desejada} "
        f"(ETA {veiculo.eta_s:.1f}s)"
    )
    lista = list(adiados)
    if not lista:
        return base

    perdedor = lista[0].deteccao
    if parametros.indice_prioridade(veiculo.tipo) < parametros.indice_prioridade(perdedor.tipo):
        criterio = f"prioridade de tipo sobre {perdedor.tipo}"
    elif veiculo.eta_s < perdedor.eta_s:
        criterio = f"menor ETA que {perdedor.id_veiculo} ({perdedor.eta_s:.1f}s)"
    else:
        criterio = "preempção já em curso"
    adiados_txt = ", ".join(d.deteccao.id_veiculo for d in lista)
    return f"{base}; venceu por {criterio}; adiados: {adiados_txt}"
