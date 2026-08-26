"""Demanda de fundo por entrada da malha — entrega 3.3.

Traduz "o cenário `intenso` tem 1.200 veíc./h na arterial" nas doze correntes de
tráfego que efetivamente entram na malha: quatro pelas arteriais e oito pelas
transversais.

**TRÁFEGO PASSANTE, SEM CONVERSÕES.** Todo veículo de fundo entra por uma
fronteira e sai pela oposta, em linha reta. É uma simplificação declarada, e ela
tem uma razão metodológica além da simplicidade: sem conversões, o fluxo de cada
aproximação é exatamente o fluxo declarado do cenário, então o v/c **derivado**
em `sim/calibracao/cenarios.py` e o v/c **medido** na malha (entrega 3.4) medem a
mesma coisa e podem ser confrontados. Com conversões, a demanda se redistribuiria
entre aproximações segundo uma matriz origem-destino que o pré-projeto não
fornece — e inventá-la cairia na mesma armadilha que P11 existe para evitar.

Limitação a declarar no texto: as conversões permissivas à esquerda existem na
rede mas não são exercitadas pelo tráfego de fundo. As únicas conversões do
experimento são as duas do VE, à direita, no corredor.

Este módulo é puro: não lê SUMO, não escreve arquivo, e por isso é testável na
suíte padrão.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sim.calibracao import cenarios as calibracao

#: Correntes arteriais: (nome, vias percorridas, de ponta a ponta).
ENTRADAS_ARTERIAIS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("A1_LESTE", ("A1_L0", "A1_L1", "A1_L2", "A1_L3", "A1_L4")),
    ("A1_OESTE", ("A1_O4", "A1_O3", "A1_O2", "A1_O1", "A1_O0")),
    ("A2_LESTE", ("A2_L0", "A2_L1", "A2_L2", "A2_L3", "A2_L4")),
    ("A2_OESTE", ("A2_O4", "A2_O3", "A2_O2", "A2_O1", "A2_O0")),
)

#: Correntes transversais, geradas pelas quatro colunas nos dois sentidos.
ENTRADAS_TRANSVERSAIS: tuple[tuple[str, tuple[str, ...]], ...] = tuple(
    entrada
    for coluna in (1, 2, 3, 4)
    for entrada in (
        (f"T{coluna}_SUL", (f"T{coluna}_S0", f"T{coluna}_S1", f"T{coluna}_S2")),
        (f"T{coluna}_NORTE", (f"T{coluna}_N2", f"T{coluna}_N1", f"T{coluna}_N0")),
    )
)


@dataclass(frozen=True)
class CorrenteDeTrafego:
    """Uma corrente de veículos entrando na malha por uma fronteira.

    Attributes:
        nome: Identificador da corrente — vira prefixo do id dos veículos.
        aproximacao: `"arterial"` ou `"transversal"`.
        vias: Vias percorridas, em ordem.
        fluxo_veic_h: Demanda da corrente, em veículos por hora.
    """

    nome: str
    aproximacao: str
    vias: tuple[str, ...]
    fluxo_veic_h: float

    @property
    def intervalo_medio_s(self) -> float:
        """Intervalo médio entre chegadas, em segundos."""
        return 3600.0 / self.fluxo_veic_h if self.fluxo_veic_h > 0 else float("inf")


def correntes_do_cenario(
    nome_cenario: str,
    linhas_calibradas: Sequence[calibracao.LinhaCenario],
) -> tuple[CorrenteDeTrafego, ...]:
    """Monta as doze correntes de um cenário.

    Args:
        nome_cenario: Cenário de `cenarios.yaml`.
        linhas_calibradas: Saída de `sim.calibracao.cenarios.montar_tabela`, de
            onde vem o fluxo transversal derivado.

    Returns:
        As correntes, arteriais primeiro.

    Raises:
        KeyError: se o cenário não estiver na tabela de calibração.
    """
    por_nome = {linha.cenario: linha for linha in linhas_calibradas}
    if nome_cenario not in por_nome:
        raise KeyError(f"cenário {nome_cenario!r} não está na tabela de calibração")
    linha = por_nome[nome_cenario]

    arteriais = tuple(
        CorrenteDeTrafego(nome, "arterial", vias, linha.fluxo_arterial_veic_h)
        for nome, vias in ENTRADAS_ARTERIAIS
    )
    transversais = tuple(
        CorrenteDeTrafego(nome, "transversal", vias, linha.fluxo_transversal_veic_h)
        for nome, vias in ENTRADAS_TRANSVERSAIS
    )
    return arteriais + transversais


def demanda_total_veic_h(correntes: Sequence[CorrenteDeTrafego]) -> float:
    """Soma da demanda de todas as correntes, em veíc./h."""
    return sum(corrente.fluxo_veic_h for corrente in correntes)


def rotas_de_emergencia(
    configuracao: Mapping[str, object], nome_cenario: str
) -> tuple[tuple[str, float], ...]:
    """Rotas dos VEs de um cenário, com o atraso de partida de cada uma.

    Args:
        configuracao: Conteúdo de `cenarios.yaml`.
        nome_cenario: Cenário avaliado.

    Returns:
        Pares `(id_da_rota, atraso_s)`. Um par no caso normal; dois no cenário
        `multiplas_emergencias`, o segundo deslocado para encontrar o primeiro
        em CRUZ_02.
    """
    emergencias: Mapping[str, object] = configuracao["emergencias"]  # type: ignore[assignment]
    cenario: Mapping[str, object] = configuracao["cenarios"][nome_cenario]  # type: ignore[index]

    rotas: list[tuple[str, float]] = [(str(emergencias["rota"]), 0.0)]
    if int(cenario.get("ves_simultaneos", 1)) > 1:
        rotas.append(
            (
                str(cenario["rota_secundaria"]),
                float(cenario.get("atraso_secundario_s", 0.0)),
            )
        )
    return tuple(rotas)
