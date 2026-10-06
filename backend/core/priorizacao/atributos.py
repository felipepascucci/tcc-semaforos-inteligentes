"""Atributos de um VE numa disputa — a entrada do modelo de P19.

O desenho de P19 (`context/09`) fixa a entrada do modelo como as **diferenças**
entre os dois VEs em `(eta_s, velocidade_ms, fila_no_acesso,
cruzamentos_restantes)`. Este módulo calcula esses atributos para um VE, a partir
do que o motor já tem no instante da decisão.

**Por que no núcleo, e não na rotulagem.** A rotulagem (10.4) grava os atributos
de cada disputa para o treino, e a inferência (10.6) vai calculá-los de novo na
hora de decidir. Se fossem duas implementações, uma diferença sutil entre elas —
a fila somada ou por faixa, o cruzamento atual contado ou não — faria o modelo
ser treinado sobre uma coisa e consultado sobre outra, sem erro nenhum. Uma
função só fecha essa classe de defeito por construção.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.malha import TopologiaMalha
from core.modelos import EstadoMalha, VeiculoEmergencia
from core.priorizacao.conflito import Disputa
from core.priorizacao.deteccao import fila_por_faixa


@dataclass(frozen=True)
class AtributosVE:
    """O que o modelo sabe de um VE no instante da disputa.

    Attributes:
        eta_s: Tempo estimado até a linha de retenção do cruzamento disputado.
        velocidade_ms: Velocidade atual, em m/s.
        fila_no_acesso: Veículos parados no acesso pelo qual o VE entra, somados
            sobre as faixas — como os detectores E2 entregam.
        fila_por_faixa: A mesma fila dividida pelas faixas do acesso, que é a que
            o VE tem à frente e a que E3 usa (P16). As duas são gravadas; qual
            entra no modelo é decisão da 10.5.
        cruzamentos_restantes: Cruzamentos semaforizados que o VE ainda vai
            atravessar, **incluindo** o disputado. É o que dá caráter
            sequencial à decisão.
    """

    eta_s: float
    velocidade_ms: float
    fila_no_acesso: int
    fila_por_faixa: float
    cruzamentos_restantes: int


def cruzamentos_restantes(topologia: TopologiaMalha, veiculo: VeiculoEmergencia) -> int:
    """Quantos cruzamentos semaforizados ainda estão à frente na rota.

    Conta pela mesma regra de E1/E4: um cruzamento conta se a via restante
    desemboca nele **e** há via de saída depois dele. O fim da rota não conta,
    porque ali não há movimento a servir.
    """
    restantes = list(veiculo.vias_restantes())
    return sum(
        1
        for posicao, via in enumerate(restantes)
        if topologia.cruzamento_apos_via.get(via) in topologia.cruzamentos
        and posicao + 1 < len(restantes)
    )


def atributos_do_ve(
    disputa: Disputa, estado: EstadoMalha, topologia: TopologiaMalha
) -> AtributosVE:
    """Os atributos de um VE numa disputa.

    Args:
        disputa: O pedido do VE no cruzamento disputado.
        estado: Estado da malha no instante da disputa.
        topologia: Geometria da malha.

    Returns:
        Os atributos do VE.

    Raises:
        KeyError: se o VE ou o cruzamento não estiverem no estado — a disputa
            não pode ter vindo deste estado.
    """
    deteccao = disputa.deteccao
    veiculo = {ve.id: ve for ve in estado.veiculos_emergencia}[deteccao.id_veiculo]
    semaforo = estado.semaforos[deteccao.id_semaforo]
    acesso = deteccao.movimento[0]
    return AtributosVE(
        eta_s=deteccao.eta_s,
        velocidade_ms=veiculo.velocidade,
        fila_no_acesso=int(semaforo.fila_por_acesso.get(acesso, 0)),
        fila_por_faixa=fila_por_faixa(semaforo, topologia, acesso),
        cruzamentos_restantes=cruzamentos_restantes(topologia, veiculo),
    )
