"""Topologia da malha — configuração estática, não estado.

Enquanto `modelos.py` descreve *o que está acontecendo agora*, este módulo
descreve *como a malha é*: quais fases cada cruzamento tem, que movimento cada
fase serve, quais fases conflitam entre si e onde cada via desemboca.

A fonte concreta é `sim/config/mapa_fases.yaml` mais a geometria do
`malha.net.xml` (Bloco 3) e, no protótipo, a tabela `fase_semaforo`. A carga
acontece fora daqui — `core/` é puro.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from core.excecoes import ConfiguracaoInvalidaError, FaseInexistenteError

#: Um movimento é o par (via de entrada, via de saída). É assim que E4 traduz
#: "por onde o VE vai passar" em "qual fase precisa estar verde".
Movimento = tuple[str, str]


@dataclass(frozen=True)
class Fase:
    """Combinação de movimentos que recebem verde simultaneamente sem conflito.

    Attributes:
        indice: Índice da fase no cruzamento, como o SUMO e o firmware a veem.
        descricao: Nome legível — "Eixo Principal A-B".
        movimentos: Movimentos servidos por esta fase.
        duracao_base_s: Duração no ciclo fixo, sem intervenção.
        verde_min_s: Piso de I4 para esta fase.
        verde_max_s: Teto de verde para esta fase.
    """

    indice: int
    descricao: str
    movimentos: frozenset[Movimento]
    duracao_base_s: float
    verde_min_s: float
    verde_max_s: float

    @property
    def acessos(self) -> frozenset[str]:
        """Vias de entrada servidas por esta fase."""
        return frozenset(entrada for entrada, _ in self.movimentos)


@dataclass(frozen=True)
class Cruzamento:
    """Um cruzamento semaforizado e suas fases.

    Attributes:
        id: Código do TLS (SUMO) ou do controlador físico.
        fases: Fases do cruzamento, em ordem de índice.
        conflitos: Para cada fase, as fases com que ela conflita.
    """

    id: str
    fases: tuple[Fase, ...]
    conflitos: Mapping[int, frozenset[int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.fases:
            raise ConfiguracaoInvalidaError(f"cruzamento {self.id} sem fases")
        indices = [fase.indice for fase in self.fases]
        if len(set(indices)) != len(indices):
            raise ConfiguracaoInvalidaError(f"cruzamento {self.id} tem índice de fase repetido")
        if not self.conflitos:
            # Padrão CONSERVADOR: toda fase conflita com todas as outras — que é
            # exatamente o regime de *split phasing* do protótipo (decisão P13),
            # onde I1 se reduz a `contar_verdes() <= 1`.
            #
            # A escolha do padrão importa: uma matriz permissiva por omissão
            # deixaria de acusar conflito num cruzamento mal configurado, e o
            # erro só apareceria como dois verdes simultâneos na rua.
            object.__setattr__(
                self,
                "conflitos",
                {i: frozenset(j for j in indices if j != i) for i in indices},
            )

    @property
    def indices_de_fase(self) -> tuple[int, ...]:
        """Índices das fases, em ordem."""
        return tuple(fase.indice for fase in self.fases)

    def fase(self, indice: int) -> Fase:
        """Devolve a fase pelo índice.

        Raises:
            FaseInexistenteError: se o índice não existir no cruzamento.
        """
        for fase in self.fases:
            if fase.indice == indice:
                return fase
        raise FaseInexistenteError(f"fase {indice} não existe em {self.id}")

    def fase_que_serve(self, movimento: Movimento) -> int | None:
        """Etapa **E4** — qual fase serve o movimento pedido.

        Args:
            movimento: Par (via de entrada, via de saída).

        Returns:
            O índice da fase, ou `None` se nenhuma fase servir o movimento.
        """
        for fase in self.fases:
            if movimento in fase.movimentos:
                return fase.indice
        return None

    def conflitam(self, fase_a: int, fase_b: int) -> bool:
        """Diz se duas fases não podem estar verdes ao mesmo tempo (I1)."""
        if fase_a == fase_b:
            return False
        return fase_b in self.conflitos.get(fase_a, frozenset())

    def acessos(self) -> frozenset[str]:
        """Todas as vias de entrada do cruzamento."""
        return frozenset().union(*(fase.acessos for fase in self.fases))

    def proxima_fase(self, indice: int) -> int:
        """Próxima fase do ciclo fixo, circularmente."""
        indices = self.indices_de_fase
        return indices[(indices.index(indice) + 1) % len(indices)]

    def duracao_do_ciclo_s(self, amarelo_s: float, all_red_s: float) -> float:
        """Duração do ciclo fixo completo, em segundos."""
        return sum(fase.duracao_base_s + amarelo_s + all_red_s for fase in self.fases)


@dataclass(frozen=True)
class TopologiaMalha:
    """A malha inteira: cruzamentos e a geometria necessária para E1.

    Attributes:
        cruzamentos: Cruzamentos, indexados pelo código.
        comprimento_via_m: Comprimento de cada via, em metros.
        cruzamento_apos_via: Cruzamento em que cada via desemboca. Vias que
            saem da malha não aparecem.
        faixas_por_via: Número de faixas de cada via. E3 precisa dele para
            converter a fila do acesso — que os detectores E2 entregam somada
            sobre as faixas — na fila **por faixa**, que é a que o VE tem à
            frente. Ignorar as faixas superestimaria a fila da arterial (duas
            faixas) pelo dobro.
    """

    cruzamentos: Mapping[str, Cruzamento]
    comprimento_via_m: Mapping[str, float] = field(default_factory=dict)
    cruzamento_apos_via: Mapping[str, str] = field(default_factory=dict)
    faixas_por_via: Mapping[str, int] = field(default_factory=dict)

    def cruzamento(self, id_cruzamento: str) -> Cruzamento:
        """Devolve um cruzamento pelo código.

        Raises:
            ConfiguracaoInvalidaError: se o código não existir na topologia.
        """
        try:
            return self.cruzamentos[id_cruzamento]
        except KeyError as erro:
            raise ConfiguracaoInvalidaError(f"cruzamento desconhecido: {id_cruzamento}") from erro

    def comprimento(self, id_via: str) -> float:
        """Comprimento de uma via, em metros. Vias desconhecidas valem 0."""
        return self.comprimento_via_m.get(id_via, 0.0)

    def faixas(self, id_via: str) -> int:
        """Número de faixas de uma via.

        Via desconhecida vale **1**, e não 0: o valor é divisor do cálculo de
        dissipação de fila em E3, e uma faixa é o palpite conservador — divide
        menos, logo estima uma fila por faixa maior e antecipa mais. Errar para
        o lado de antecipar demais custa espera transversal; errar para o outro
        custa o VE parar, que é o que P16 existe para corrigir.
        """
        return max(self.faixas_por_via.get(id_via, 1), 1)

    def validar(self) -> None:
        """Confere a coerência interna da topologia.

        Raises:
            ConfiguracaoInvalidaError: se houver referência a cruzamento
                inexistente ou via sem comprimento declarado.
        """
        problemas: list[str] = []
        for via, id_cruzamento in self.cruzamento_apos_via.items():
            if id_cruzamento not in self.cruzamentos:
                problemas.append(f"via {via} aponta para cruzamento inexistente {id_cruzamento}")
            if via not in self.comprimento_via_m:
                problemas.append(f"via {via} não tem comprimento declarado")
        for id_cruzamento, cruzamento in self.cruzamentos.items():
            if cruzamento.id != id_cruzamento:
                problemas.append(f"chave {id_cruzamento} não bate com o id {cruzamento.id}")
        if problemas:
            raise ConfiguracaoInvalidaError("; ".join(problemas))


def matriz_totalmente_conflitante(indices: Iterable[int]) -> dict[int, frozenset[int]]:
    """Matriz de conflito de *split phasing*: toda fase conflita com todas.

    É o regime do protótipo (decisão P13), em que I1 vira `contar_verdes() <= 1`.
    """
    todos = tuple(indices)
    return {i: frozenset(j for j in todos if j != i) for i in todos}
