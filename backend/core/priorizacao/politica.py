"""Inferência da política aprendida de E8 — entrega 10.6 (P19, P20).

O modelo foi treinado fora (`analysis/treino_politica.py`, entrega 10.5) e
exportado como **dado**: quatro pesos em `backend/config/politica_desempate.yaml`.
Quem lê o arquivo é `adapters/configuracao.py`, e este módulo recebe só os
números. A inferência é um produto escalar em Python puro:

    score(A, B) = Σ pesos[a] · (x_A[a] - x_B[a])      A vence B se score > 0

com `x = (eta_s, velocidade_ms, fila_por_faixa, cruzamentos_restantes)`, os
atributos de `atributos.py` — a mesma função da rotulagem, para que o modelo não
seja treinado sobre uma coisa e consultado sobre outra. Os pesos já estão nas
unidades originais, então não há escala a aplicar aqui.

ORDEM DE DECISÃO NO BRAÇO `PREEMPCAO_ML` (`context/10` §3)

1. **Criticidade, regra.** Só disputam os VEs do nível mais crítico, inclusive
   contra uma preempção em curso de nível menos crítico (P20).
2. **Guarda de oscilação, regra.** No mesmo nível, a preempção em curso vence
   (P19). É o que mantém o argumento de I4 e I5 independente do que o modelo
   aprendeu.
3. **Modelo**, só entre os VEs que sobraram, e só se eles pedirem fases
   distintas: pedidos pela mesma fase são servidos pelo mesmo verde, não há
   conflito, e decide o E8 de sempre.

As duas regras estão aqui, antes do modelo, e não dependem dos pesos. A
criticidade é ainda conferida por `resolver`, que recusa qualquer proposta de
nível menos crítico — a garantia continua por construção.

ANTISSIMETRIA E TORNEIO

Sobre diferenças e sem intercepto, `score(B, A) = -score(A, B)` por construção,
e em ponto flutuante a igualdade é exata: cada termo troca de sinal sem mudar de
módulo, e a soma, na mesma ordem, também. Com três ou mais VEs a disputa é um
torneio todos-contra-todos, e vence o **invicto**, o VE que ninguém bate. Como o
score é linear, `score(A, B) = s(A) - s(B)` com `s(X) = pesos · x_X`, então o
invicto é o de maior `s` e não há ciclo possível. Só há mais de um invicto num
**empate exato**, e aí o modelo não tem preferência: decide a chave do E8 entre
os empatados (decisão da equipe, 2026-10-07). Seguir "senão B" ao pé da letra
faria o resultado depender da ordem em que os pedidos chegam.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields
from typing import TYPE_CHECKING

from core.excecoes import ConfiguracaoInvalidaError
from core.malha import TopologiaMalha
from core.parametros import Parametros
from core.priorizacao.atributos import AtributosVE, atributos_do_ve
from core.priorizacao.conflito import Disputa, chave_de_desempate

if TYPE_CHECKING:
    from core.modelos import EstadoMalha


@dataclass(frozen=True)
class PesosPolitica:
    """Os pesos do modelo, nas unidades originais dos atributos.

    A ordem dos campos é a ordem dos atributos no treino, e é dela que sai
    `ATRIBUTOS_DO_MODELO`.

    Attributes:
        eta_s: Peso por segundo de diferença de ETA.
        velocidade_ms: Peso por m/s de diferença de velocidade.
        fila_por_faixa: Peso por veículo parado por faixa.
        cruzamentos_restantes: Peso por cruzamento semaforizado à frente.
    """

    eta_s: float
    velocidade_ms: float
    fila_por_faixa: float
    cruzamentos_restantes: float

    @classmethod
    def de_dicionario(
        cls, atributos: Sequence[object], pesos: Mapping[str, object]
    ) -> PesosPolitica:
        """Constrói a partir do que o YAML do treino traz.

        Args:
            atributos: A lista `atributos` do arquivo, na ordem do treino.
            pesos: O mapeamento `pesos` do arquivo.

        Returns:
            Os pesos validados.

        Raises:
            ConfiguracaoInvalidaError: se os atributos não forem exatamente os
                do modelo, na mesma ordem, ou se algum peso faltar, sobrar ou
                não for um número finito. Um arquivo de outro desenho tem de
                falhar na carga, e não virar uma decisão errada no meio do lote.
        """
        if list(atributos) != list(ATRIBUTOS_DO_MODELO):
            raise ConfiguracaoInvalidaError(
                f"atributos da política {list(atributos)} diferem dos do modelo "
                f"{list(ATRIBUTOS_DO_MODELO)}"
            )
        if set(pesos) != set(ATRIBUTOS_DO_MODELO):
            raise ConfiguracaoInvalidaError(
                f"pesos da política {sorted(pesos)} diferem dos atributos do modelo "
                f"{sorted(ATRIBUTOS_DO_MODELO)}"
            )
        valores: dict[str, float] = {}
        for nome in ATRIBUTOS_DO_MODELO:
            valor = pesos[nome]
            if isinstance(valor, bool) or not isinstance(valor, int | float):
                raise ConfiguracaoInvalidaError(f"peso de {nome} não é número: {valor!r}")
            if not math.isfinite(valor):
                raise ConfiguracaoInvalidaError(f"peso de {nome} não é finito: {valor!r}")
            valores[nome] = float(valor)
        return cls(**valores)

    def vetor(self) -> tuple[float, ...]:
        """Os pesos na ordem de `ATRIBUTOS_DO_MODELO`."""
        return tuple(getattr(self, nome) for nome in ATRIBUTOS_DO_MODELO)


#: Os atributos que o modelo vê, na ordem do treino (`analysis/treino_politica.py`).
ATRIBUTOS_DO_MODELO: tuple[str, ...] = tuple(campo.name for campo in fields(PesosPolitica))


def vetor_de_atributos(atributos: AtributosVE) -> tuple[float, ...]:
    """O `x` de um VE, na ordem de `ATRIBUTOS_DO_MODELO`."""
    return tuple(float(getattr(atributos, nome)) for nome in ATRIBUTOS_DO_MODELO)


def score(pesos: PesosPolitica, a: AtributosVE, b: AtributosVE) -> float:
    """`Σ pesos[a] · (x_A[a] - x_B[a])`: positivo, o modelo prefere A; negativo, B."""
    return sum(
        peso * (x_a - x_b)
        for peso, x_a, x_b in zip(
            pesos.vetor(), vetor_de_atributos(a), vetor_de_atributos(b), strict=True
        )
    )


def invictos(pesos: PesosPolitica, atributos: Sequence[AtributosVE]) -> tuple[int, ...]:
    """Torneio todos-contra-todos: os índices dos VEs que ninguém bate.

    Com o score linear, é um índice só, salvo empate exato no topo. Se a
    aritmética de ponto flutuante produzisse um ciclo — não produz com quatro
    termos, mas a função não depende disso —, ninguém seria invicto, e todos
    voltam como empatados.
    """
    indices = range(len(atributos))
    resultado = tuple(
        i
        for i in indices
        if not any(score(pesos, atributos[j], atributos[i]) > 0.0 for j in indices if j != i)
    )
    return resultado or tuple(indices)


def decidir(
    disputas: Sequence[Disputa],
    atributos_de: Callable[[Disputa], AtributosVE],
    pesos: PesosPolitica,
    parametros: Parametros,
) -> Disputa | None:
    """O vencedor de E8 no braço `PREEMPCAO_ML`, ou `None` para o E8 decidir.

    Args:
        disputas: Pedidos concorrentes num cruzamento.
        atributos_de: Os atributos de um pedido. Só é chamada se o modelo for
            de fato consultado, depois das duas regras.
        pesos: Os pesos do modelo.
        parametros: Parâmetros do algoritmo, para o desempate do E8 num empate
            exato do modelo.

    Returns:
        O pedido que deve vencer. `None` quando não há o que decidir — nenhum
        pedido, ou os pedidos do nível mais crítico pedem todos a mesma fase.
    """
    if not disputas:
        return None

    # 1. Criticidade: só o nível mais crítico disputa, com ou sem preempção em curso.
    nivel = min(disputa.deteccao.criticidade for disputa in disputas)
    candidatos = [disputa for disputa in disputas if disputa.deteccao.criticidade == nivel]
    if len(candidatos) == 1:
        return candidatos[0]

    # 2. Guarda de oscilação: no mesmo nível, quem já tem a preempção a mantém.
    for disputa in candidatos:
        if disputa.ja_em_curso:
            return disputa

    # Mesma fase para todos: o mesmo verde serve todos, e não há conflito a decidir.
    if len({disputa.fase_desejada for disputa in candidatos}) < 2:
        return None

    # 3. Modelo.
    topo = invictos(pesos, [atributos_de(disputa) for disputa in candidatos])
    if len(topo) == 1:
        return candidatos[topo[0]]
    return min(
        (candidatos[i] for i in topo),
        key=lambda disputa: chave_de_desempate(disputa, parametros),
    )


@dataclass(frozen=True)
class PoliticaAprendida:
    """`PoliticaDesempate` do braço `PREEMPCAO_ML`: os pesos de P19 aplicados a E8.

    Attributes:
        pesos: Os pesos do modelo, lidos por `adapters.configuracao.carregar_politica`.
        topologia: A mesma topologia do motor, para calcular os atributos.
        parametros: Os mesmos parâmetros do motor, para o desempate num empate.
    """

    pesos: PesosPolitica
    topologia: TopologiaMalha
    parametros: Parametros

    def escolher(
        self, id_semaforo: str, disputas: Sequence[Disputa], estado: EstadoMalha
    ) -> Disputa | None:
        """O pedido que deve vencer em `id_semaforo`, pelas regras e pelo modelo."""
        del id_semaforo
        return decidir(
            disputas,
            lambda disputa: atributos_do_ve(disputa, estado, self.topologia),
            self.pesos,
            self.parametros,
        )
