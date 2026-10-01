"""Etapas E1, E2 e E3 — detecção, ETA e janela de ativação (`context/01` §5.2).

**A regra mais importante deste módulo: distância ao longo da rota, nunca
euclidiana.** Um cruzamento pode estar a 100 m em linha reta e o VE nunca passar
por ele — priorizá-lo trava a transversal de graça e não ajuda ninguém. É o erro
clássico, e por isso `math.dist` não aparece em lugar nenhum daqui.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.malha import Movimento, TopologiaMalha
from core.modelos import Criticidade, EstadoSemaforo, TipoVeiculo, VeiculoEmergencia
from core.parametros import Parametros


@dataclass(frozen=True)
class DeteccaoVE:
    """Um VE detectado na aproximação de um cruzamento.

    Attributes:
        id_veiculo: Veículo detectado.
        tipo: Tipo do veículo — segundo critério do desempate de E8.
        criticidade: Criticidade da ocorrência — primeiro critério de E8 (P20).
        id_semaforo: Cruzamento que ele vai atravessar.
        distancia_m: Distância **ao longo da rota** até a linha de retenção.
        eta_s: Tempo estimado de chegada, em segundos.
        movimento: Par (via de entrada, via de saída) que o VE fará.
    """

    id_veiculo: str
    tipo: TipoVeiculo
    criticidade: Criticidade
    id_semaforo: str
    distancia_m: float
    eta_s: float
    movimento: Movimento


def distancia_ao_longo_da_rota(
    topologia: TopologiaMalha, veiculo: VeiculoEmergencia, id_semaforo: str
) -> float | None:
    """Distância que o VE ainda percorrerá até a linha de retenção do cruzamento.

    Percorre as vias restantes da rota somando comprimentos, até encontrar a via
    que desemboca no cruzamento pedido.

    Args:
        topologia: Geometria da malha.
        veiculo: O VE, com rota e posição na via atual.
        id_semaforo: Cruzamento de interesse.

    Returns:
        A distância em metros, ou `None` se o cruzamento não estiver à frente na
        rota do veículo — o que inclui o caso de ele já ter passado por lá.
    """
    acumulada = 0.0
    for posicao, via in enumerate(veiculo.vias_restantes()):
        comprimento = topologia.comprimento(via)
        # Na via atual, só o trecho que falta percorrer conta.
        restante = comprimento - veiculo.posicao_na_via_m if posicao == 0 else comprimento
        acumulada += max(restante, 0.0)
        if topologia.cruzamento_apos_via.get(via) == id_semaforo:
            return acumulada
    return None


def calcular_eta_s(distancia_m: float, velocidade_ms: float, velocidade_min_ms: float) -> float:
    """Etapa **E2** — estima o tempo até o cruzamento.

    O piso de velocidade não é arredondamento: sem ele, um VE parado em fila
    produziria ETA infinito e nunca entraria na janela de ativação — justamente
    o veículo que mais precisa de prioridade.

    Args:
        distancia_m: Distância ao longo da rota, em metros.
        velocidade_ms: Velocidade atual do veículo, em m/s.
        velocidade_min_ms: Piso de velocidade para a estimativa, em m/s.

    Returns:
        Tempo estimado de chegada, em segundos.
    """
    return distancia_m / max(velocidade_ms, velocidade_min_ms)


def _movimento_no_cruzamento(
    topologia: TopologiaMalha, veiculo: VeiculoEmergencia, id_semaforo: str
) -> Movimento | None:
    """Par (via de entrada, via de saída) que o VE fará no cruzamento.

    Returns:
        O movimento, ou `None` se o cruzamento for o fim da rota — sem via de
        saída não há movimento a servir, e E4 não teria fase para escolher.
    """
    restantes = list(veiculo.vias_restantes())
    for posicao, via in enumerate(restantes):
        if topologia.cruzamento_apos_via.get(via) != id_semaforo:
            continue
        if posicao + 1 >= len(restantes):
            return None
        return (via, restantes[posicao + 1])
    return None


def detectar(
    topologia: TopologiaMalha, veiculo: VeiculoEmergencia, parametros: Parametros
) -> tuple[DeteccaoVE, ...]:
    """Etapas **E1 + E2** — cruzamentos da rota dentro do raio, com ETA.

    Args:
        topologia: Geometria e fases da malha.
        veiculo: O VE a avaliar.
        parametros: Parâmetros do algoritmo.

    Returns:
        As detecções, ordenadas da mais próxima para a mais distante.
    """
    deteccoes: list[DeteccaoVE] = []
    for id_semaforo in topologia.cruzamentos:
        distancia_m = distancia_ao_longo_da_rota(topologia, veiculo, id_semaforo)
        if distancia_m is None or distancia_m > parametros.raio_deteccao_m:
            continue
        movimento = _movimento_no_cruzamento(topologia, veiculo, id_semaforo)
        if movimento is None:
            continue
        deteccoes.append(
            DeteccaoVE(
                id_veiculo=veiculo.id,
                tipo=veiculo.tipo,
                criticidade=veiculo.criticidade,
                id_semaforo=id_semaforo,
                distancia_m=distancia_m,
                eta_s=calcular_eta_s(
                    distancia_m, veiculo.velocidade, parametros.velocidade_min_estimativa_ms
                ),
                movimento=movimento,
            )
        )
    return tuple(sorted(deteccoes, key=lambda d: d.distancia_m))


def verde_min_residual_s(
    estado: EstadoSemaforo, verde_min_s: float, sinal_e_verde: bool = True
) -> float:
    """Quanto ainda falta cumprir do verde mínimo na fase atual (I4).

    Args:
        estado: Estado observado do cruzamento.
        verde_min_s: Piso de verde da fase corrente, em segundos.
        sinal_e_verde: Se a fase atual está em verde. Em amarelo ou all-red não
            há verde mínimo a cumprir.

    Returns:
        Segundos restantes de verde mínimo; zero se já foi cumprido.
    """
    if not sinal_e_verde:
        return 0.0
    return max(verde_min_s - estado.tempo_na_fase, 0.0)


def fila_por_faixa(estado: EstadoSemaforo, topologia: TopologiaMalha, acesso: str) -> float:
    """Fila do acesso dividida pelas faixas que ele tem (E3, P16).

    Os detectores E2 entregam a fila **somada sobre as faixas** do acesso, mas o
    que atrasa o VE são os veículos à frente **na faixa dele**. Numa arterial de
    duas faixas, usar a soma estimaria o dobro do tempo de dissipação real.

    Args:
        estado: Estado observado do cruzamento.
        topologia: Geometria da malha, que sabe quantas faixas o acesso tem.
        acesso: Via de entrada pela qual o VE chegará ao cruzamento.

    Returns:
        Veículos parados por faixa no acesso.
    """
    return estado.fila_por_acesso.get(acesso, 0) / topologia.faixas(acesso)


def dentro_da_janela(
    deteccao: DeteccaoVE,
    parametros: Parametros,
    verde_min_residual: float = 0.0,
    tempo_dissipacao_s: float = 0.0,
) -> bool:
    """Etapa **E3** — decide se já é hora de preemptar.

    Preemptar cedo demais trava a via transversal sem necessidade, e esse é
    exatamente o custo que H2 quer minimizar. Preemptar tarde demais não dá tempo
    de completar a transição segura **nem de a fila escoar** antes de o VE
    chegar — foi o segundo caso que o piloto do Bloco 4 mediu (P16): o corredor
    abria a tempo e não esvaziava a tempo.

    Args:
        deteccao: A detecção avaliada.
        parametros: Parâmetros do algoritmo.
        verde_min_residual: Verde mínimo ainda a cumprir no cruzamento, em
            segundos — a transição não pode começar antes disso (I4).
        tempo_dissipacao_s: Tempo estimado para a fila do acesso de entrada
            escoar, em segundos.

    Returns:
        `True` se a preempção deve começar agora.
    """
    return deteccao.eta_s <= parametros.tempo_antecipacao_s(verde_min_residual, tempo_dissipacao_s)
