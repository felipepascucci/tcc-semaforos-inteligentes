"""Estruturas de estado do motor de decisão — `context/01` §5.1.

Duas escolhas merecem explicação, porque divergem em forma (não em conteúdo) do
que está escrito no `context/01` §5.1:

1. **Contêineres imutáveis.** O documento escreve `rota: list[str]` e
   `fila_por_acesso: dict[str, int]` dentro de `@dataclass(frozen=True)`. Mas
   `frozen=True` só impede reatribuir o atributo — a lista e o dicionário
   continuam mutáveis por dentro, e a razão declarada em `context/08` §3 para
   exigir estado imutável ("elimina uma classe inteira de bug de concorrência
   entre o loop de simulação e o broadcast do WebSocket") ficaria sem efeito.
   Usamos `tuple` e `Mapping` para que a garantia seja real.

2. **`posicao_na_via_m`.** Campo acrescentado. Sem ele, a distância ao longo da
   rota (E1) só teria resolução de via inteira — e o critério de aceitação do
   RF01 é distinguir 480 m de 520 m (`context/06` §2). O TraCI fornece o valor
   direto, por `traci.vehicle.getLanePosition()`.

Ambas estão registradas em `context/01` §5.1.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum


class TipoVeiculo(StrEnum):
    """Tipo do veículo de emergência. A ordem de prioridade vive nos parâmetros."""

    AMBULANCIA = "AMBULANCIA"
    BOMBEIRO = "BOMBEIRO"
    POLICIA = "POLICIA"


class Sinal(StrEnum):
    """Cor exibida por um grupo de movimentos."""

    VERDE = "VERDE"
    AMARELO = "AMARELO"
    VERMELHO = "VERMELHO"


@dataclass(frozen=True)
class VeiculoEmergencia:
    """Um VE ativo na malha, com sua rota planejada.

    Attributes:
        id: Identificador do veículo (id do SUMO ou placa no protótipo).
        tipo: Tipo do veículo, que define prioridade no desempate de E8.
        posicao: Coordenada (x, y) em metros. Usada só para o dashboard —
            **nunca** para calcular distância a cruzamento (ver `deteccao.py`).
        velocidade: Velocidade atual, em m/s.
        rota: Ids das vias que o veículo vai percorrer, em ordem.
        indice_via_atual: Índice, em `rota`, da via onde o veículo está agora.
        posicao_na_via_m: Distância já percorrida dentro da via atual, em metros.
    """

    id: str
    tipo: TipoVeiculo
    posicao: tuple[float, float]
    velocidade: float
    rota: tuple[str, ...]
    indice_via_atual: int
    posicao_na_via_m: float = 0.0

    @property
    def via_atual(self) -> str:
        """Id da via onde o veículo está."""
        return self.rota[self.indice_via_atual]

    def vias_restantes(self) -> Sequence[str]:
        """Vias que ainda serão percorridas, incluindo a atual."""
        return self.rota[self.indice_via_atual :]


@dataclass(frozen=True)
class EstadoSemaforo:
    """Estado observado de um cruzamento em um instante.

    Attributes:
        id: Código do cruzamento (id do TLS no SUMO, ou do controlador físico).
        fase_atual: Índice da fase em curso.
        tempo_na_fase: Há quantos segundos a fase atual está ativa.
        fila_por_acesso: Veículos parados por via de acesso.
        em_preempcao: Se há preempção ativa neste cruzamento.
        sinal: Cor da fase atual. `VERMELHO` significa all-red.
    """

    id: str
    fase_atual: int
    tempo_na_fase: float
    fila_por_acesso: Mapping[str, int] = field(default_factory=dict)
    em_preempcao: bool = False
    sinal: Sinal = Sinal.VERDE

    @property
    def fila_total(self) -> int:
        """Soma das filas de todos os acessos."""
        return sum(self.fila_por_acesso.values())


@dataclass(frozen=True)
class EstadoMalha:
    """Fotografia da malha inteira em um passo de simulação.

    É a única entrada de `MotorDecisao.avaliar()`. Tudo o que a decisão precisa
    saber sobre o mundo está aqui — é isso que torna o motor agnóstico ao
    atuador e testável sem SUMO e sem hardware.

    Attributes:
        t: Instante, em segundos de simulação ou epoch.
        semaforos: Estado de cada cruzamento, indexado pelo código.
        veiculos_emergencia: VEs ativos neste instante.
        densidade_por_via: Densidade por via, em veículos por metro.
    """

    t: float
    semaforos: Mapping[str, EstadoSemaforo]
    veiculos_emergencia: Sequence[VeiculoEmergencia] = ()
    densidade_por_via: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Transicao:
    """Uma mudança de sinalização em um cruzamento.

    É a unidade que vai para `estado_semaforo_amostra` (decisão P5) e sobre a
    qual os invariantes I2, I3 e I4 são verificados.

    Attributes:
        id_semaforo: Cruzamento onde ocorreu.
        t: Instante da transição, em segundos.
        fase_anterior: Fase que terminou. `None` na primeira transição.
        fase: Fase que começou.
        sinal: Cor com que a fase entrou.
        duracao_fase_anterior_s: Quanto durou a fase anterior. `None` na primeira.
        em_preempcao: Se a transição aconteceu sob preempção.
    """

    id_semaforo: str
    t: float
    fase: int
    sinal: Sinal
    fase_anterior: int | None = None
    duracao_fase_anterior_s: float | None = None
    em_preempcao: bool = False
