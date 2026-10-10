"""Etapas E4 e E5 — seleção de fase e transição segura (`context/01` §5.2).

Além de E4/E5, este módulo contém a **máquina de estados do controlador**: um
modelo puro e executável do que o `traci.trafficlight` faz com os comandos que o
motor emite. Desde 2026-10-05 o firmware do UNO não recebe comandos do motor: a
bancada decide sozinha, com uma regra própria (`context/01` §1 e §4,
`context/05` §3), e o dublê dela não reusa esta máquina.

Ela existe por três motivos:

1. Permite planejar a transição sabendo quanto tempo ela vai levar (E3 depende
   disso para escolher *quando* preemptar).
2. É o alvo do teste property-based de I1 (`context/06` §3): o Hypothesis
   dirige sequências aleatórias de comandos contra esta máquina e verifica os
   invariantes em **todo estado alcançado**.
3. Documenta, em código testável, a transição segura que o motor pressupõe na
   simulação. O firmware do UNO cumpre os mesmos invariantes I1 a I4 com uma
   máquina própria, de 2 fases e verde exclusivo, comparada linha por linha com
   o dublê da bancada, e não com esta (`context/05` §3.7).

A sequência de E5 é obrigatória e não tem atalho::

    se fase_atual == fase_alvo:  estender verde até min(necessário, VERDE_MAX)
    senão:  aguardar MIN_GREEN residual -> AMARELO -> ALL_RED -> fase_alvo
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import assert_never

from core.comandos import Comando, TipoComando
from core.excecoes import FaseInexistenteError
from core.malha import Cruzamento, Movimento
from core.modelos import Sinal, Transicao
from core.parametros import Parametros


@dataclass(frozen=True)
class Recusa:
    """Um comando que a máquina não pôde executar.

    Recusar é comportamento correto, não erro: a defesa em profundidade da
    decisão P13 depende de o atuador ter o direito de dizer não. *(Até
    2026-10-05 o firmware do UNO também recusava, com `NAK,<cmd>,<motivo>`;
    desde então ele não recebe comandos, e a recusa vive só nesta máquina.)*
    """

    comando: Comando
    motivo: str


@dataclass(frozen=True)
class EstadoControlador:
    """Estado interno do controlador de um cruzamento.

    Attributes:
        id_semaforo: Cruzamento controlado.
        fase_corrente: Fase que está sendo exibida.
        sinal: Cor da fase corrente. `VERMELHO` significa all-red — nenhuma fase
            com verde.
        t_mudanca: Instante em que o sinal atual começou.
        fase_alvo: Fase de destino, quando há transição em curso.
        em_preempcao: Se há preempção ativa.
        t_inicio_preempcao: Instante em que a preempção começou.
        verde_ate: Instante até o qual o verde corrente foi estendido.
        id_veiculo: VE que motivou a preempção em curso.
        t_ultimo_verde: Último instante em que cada fase teve verde (base de I5).
    """

    id_semaforo: str
    fase_corrente: int
    sinal: Sinal = Sinal.VERDE
    t_mudanca: float = 0.0
    fase_alvo: int | None = None
    em_preempcao: bool = False
    t_inicio_preempcao: float | None = None
    verde_ate: float | None = None
    id_veiculo: str | None = None
    t_ultimo_verde: Mapping[int, float] = field(default_factory=dict)

    def sinais(self, cruzamento: Cruzamento) -> Mapping[int, Sinal]:
        """Cor exibida por cada fase do cruzamento neste instante.

        É sobre este mapa que I1 é verificado. Repare que ele é construído a
        partir do estado, e não guardado: uma fase só aparece verde se for a
        corrente **e** o sinal for verde.
        """
        return {
            fase.indice: self.sinal if fase.indice == self.fase_corrente else Sinal.VERMELHO
            for fase in cruzamento.fases
        }

    def fases_verdes(self, cruzamento: Cruzamento) -> frozenset[int]:
        """Fases com verde aceso agora."""
        return frozenset(
            indice for indice, sinal in self.sinais(cruzamento).items() if sinal is Sinal.VERDE
        )

    def em_transicao(self) -> bool:
        """Se há troca de fase em andamento (amarelo ou all-red)."""
        return self.sinal is not Sinal.VERDE


@dataclass(frozen=True)
class Avanco:
    """Resultado de um passo da máquina.

    Attributes:
        estado: O novo estado do controlador.
        transicoes: Mudanças de sinalização ocorridas neste passo.
        recusas: Comandos rejeitados, com o motivo.
    """

    estado: EstadoControlador
    transicoes: tuple[Transicao, ...] = ()
    recusas: tuple[Recusa, ...] = ()


# ---------------------------------------------------------------------------
# E4 — seleção da fase
# ---------------------------------------------------------------------------


def selecionar_fase(cruzamento: Cruzamento, movimento: Movimento) -> int:
    """Etapa **E4** — escolhe a fase que serve o movimento do VE.

    Args:
        cruzamento: Cruzamento em questão.
        movimento: Par (via de entrada, via de saída) que o VE fará.

    Returns:
        Índice da fase que concede verde a esse movimento.

    Raises:
        FaseInexistenteError: se nenhuma fase do cruzamento servir o movimento —
            o que indica mapa de fases incompleto, não situação de operação.
    """
    indice = cruzamento.fase_que_serve(movimento)
    if indice is None:
        raise FaseInexistenteError(
            f"nenhuma fase de {cruzamento.id} serve o movimento {movimento[0]} -> {movimento[1]}"
        )
    return indice


# ---------------------------------------------------------------------------
# E5 — transição segura
# ---------------------------------------------------------------------------


def duracao_da_transicao_s(
    estado: EstadoControlador,
    cruzamento: Cruzamento,
    fase_alvo: int,
    parametros: Parametros,
    t: float,
) -> float:
    """Quanto tempo levará para acender o verde da fase alvo, a partir de agora.

    É o número que E3 usa para decidir *quando* começar a preempção. Inclui o
    verde mínimo residual, porque I4 proíbe truncar antes dele.

    Args:
        estado: Estado atual do controlador.
        cruzamento: Cruzamento em questão.
        fase_alvo: Fase de destino.
        parametros: Parâmetros do algoritmo.
        t: Instante atual, em segundos.

    Returns:
        Duração da transição, em segundos. Zero se a fase alvo já está em verde.
    """
    if estado.fase_corrente == fase_alvo and estado.sinal is Sinal.VERDE:
        return 0.0

    decorrido = t - estado.t_mudanca
    if estado.sinal is Sinal.VERDE:
        verde_min = cruzamento.fase(estado.fase_corrente).verde_min_s
        residual = max(verde_min - decorrido, 0.0)
        return residual + parametros.amarelo_s + parametros.all_red_s
    if estado.sinal is Sinal.AMARELO:
        return max(parametros.amarelo_s - decorrido, 0.0) + parametros.all_red_s
    return max(parametros.all_red_s - decorrido, 0.0)


def _iniciar(
    estado: EstadoControlador, sinal: Sinal, fase: int, t: float
) -> tuple[EstadoControlador, Transicao]:
    """Troca o sinal exibido e emite a transição correspondente."""
    duracao_anterior = t - estado.t_mudanca
    ultimo_verde = dict(estado.t_ultimo_verde)
    if sinal is Sinal.VERDE:
        ultimo_verde[fase] = t

    novo = replace(
        estado,
        fase_corrente=fase,
        sinal=sinal,
        t_mudanca=t,
        t_ultimo_verde=ultimo_verde,
        verde_ate=None if sinal is not Sinal.VERDE else estado.verde_ate,
    )
    transicao = Transicao(
        id_semaforo=estado.id_semaforo,
        t=t,
        fase=fase,
        sinal=sinal,
        fase_anterior=estado.fase_corrente,
        duracao_fase_anterior_s=duracao_anterior,
        em_preempcao=estado.em_preempcao,
    )
    return novo, transicao


# ---------------------------------------------------------------------------
# Máquina de estados
# ---------------------------------------------------------------------------


def _aplicar_comando(
    estado: EstadoControlador,
    comando: Comando,
    cruzamento: Cruzamento,
    parametros: Parametros,
    t: float,
) -> tuple[EstadoControlador, Recusa | None]:
    """Incorpora um comando ao estado, ou o recusa com motivo."""
    if comando.tipo is TipoComando.FALLBACK_SEGURO:
        # Fail-safe nunca é recusado. Abandona o alvo e volta ao ciclo fixo,
        # deixando a transição em curso terminar com segurança.
        return (
            replace(
                estado,
                fase_alvo=None,
                em_preempcao=False,
                t_inicio_preempcao=None,
                verde_ate=None,
                id_veiculo=None,
            ),
            None,
        )

    if comando.tipo is TipoComando.LIBERAR:
        if not estado.em_preempcao:
            return estado, Recusa(comando, "MODO")
        return (
            replace(
                estado,
                em_preempcao=False,
                t_inicio_preempcao=None,
                verde_ate=None,
                id_veiculo=None,
            ),
            None,
        )

    if comando.tipo is TipoComando.IR_PARA_FASE:
        if comando.fase_alvo is None:
            return estado, Recusa(comando, "FORMATO")
        if comando.fase_alvo not in cruzamento.indices_de_fase:
            return estado, Recusa(comando, "FASE_INVALIDA")
        if estado.em_transicao():
            # Trocar o destino no meio de um amarelo já iniciado deixaria o
            # cruzamento em estado inconsistente: o amarelo em curso pertence à
            # transição antiga. Espera terminar.
            return estado, Recusa(comando, "MODO")
        return (
            replace(
                estado,
                fase_alvo=comando.fase_alvo,
                em_preempcao=True,
                t_inicio_preempcao=estado.t_inicio_preempcao if estado.em_preempcao else t,
                id_veiculo=comando.id_veiculo,
            ),
            None,
        )

    if comando.tipo is TipoComando.ESTENDER_VERDE:
        if estado.sinal is not Sinal.VERDE:
            return estado, Recusa(comando, "MODO")
        fase = cruzamento.fase(estado.fase_corrente)
        pedido = comando.duracao_s if comando.duracao_s is not None else fase.duracao_base_s
        # `duracao_s` conta A PARTIR DE AGORA, não do início do verde. É a mesma
        # semântica de `PRE,<fase>,<dur_s>` no protocolo serial (contrato §5): o
        # atuador segura a fase por tanto tempo a contar do recebimento.
        #
        # A leitura antiga ("duração total do verde") transformava o comando em
        # seu oposto quando o verde já durava mais do que o pedido: o motor pede
        # `eta + margem` para segurar o corredor, e o verde fechava na cara do VE.
        # Só apareceu rodando a simulação — ver context/09, achado de 2026-08-25.
        #
        # I4 tem um irmão do outro lado: `verde_max`. Estender sem teto seria
        # starvation por construção nas demais fases (I5). O teto continua
        # ancorado no INÍCIO do verde, senão extensões sucessivas o empurrariam
        # para sempre.
        limite_de_verde = estado.t_mudanca + min(fase.verde_max_s, parametros.verde_max_s)
        teto = min(t + pedido, limite_de_verde)
        # Estender por causa de um VE é preempção; estender para compensar a
        # fila da transversal (E7) não é. A diferença está em haver ou não um VE
        # associado, e ela importa: `em_preempcao` viaja para
        # `estado_semaforo_amostra` e é por esse campo que o relatório separa o
        # custo do evento do custo da recuperação — que é justamente o que H2
        # mede.
        por_veiculo = comando.id_veiculo is not None
        return replace(
            estado,
            verde_ate=teto,
            em_preempcao=estado.em_preempcao or por_veiculo,
            t_inicio_preempcao=(
                t if por_veiculo and not estado.em_preempcao else estado.t_inicio_preempcao
            ),
            id_veiculo=comando.id_veiculo or estado.id_veiculo,
        ), None

    if comando.tipo is TipoComando.COMPENSAR:
        # A compensação altera durações de verde do ciclo, não a sinalização
        # corrente. Quem calcula é `compensacao.py`; aqui só se registra que o
        # cruzamento saiu da preempção.
        return replace(estado, em_preempcao=False, t_inicio_preempcao=None, verde_ate=None), None

    # Exaustividade verificada pelo mypy: acrescentar um `TipoComando` sem tratá-lo
    # aqui vira erro de tipagem, não comportamento silencioso na rua.
    assert_never(comando.tipo)


def avancar(
    estado: EstadoControlador,
    t: float,
    cruzamento: Cruzamento,
    parametros: Parametros,
    comandos: tuple[Comando, ...] = (),
) -> Avanco:
    """Avança a máquina até o instante `t`, aplicando os comandos recebidos.

    Esta é a função que garante E5 na prática: nenhum caminho aqui leva de verde
    a verde diretamente, nem de verde a vermelho sem amarelo, nem trunca um verde
    antes de `verde_min_s`.

    Args:
        estado: Estado atual do controlador.
        t: Novo instante, em segundos. Deve ser >= `estado.t_mudanca`.
        cruzamento: Cruzamento controlado.
        parametros: Parâmetros do algoritmo.
        comandos: Comandos a aplicar neste passo.

    Returns:
        O novo estado, as transições emitidas e os comandos recusados.
    """
    recusas: list[Recusa] = []
    for comando in comandos:
        estado, recusa = _aplicar_comando(estado, comando, cruzamento, parametros, t)
        if recusa is not None:
            recusas.append(recusa)

    estado = _expirar_preempcao(estado, t, parametros)

    if estado.sinal is Sinal.VERDE:
        estado, transicao = _do_verde(estado, t, cruzamento, parametros)
    elif estado.sinal is Sinal.AMARELO:
        estado, transicao = _do_amarelo(estado, t, parametros)
    else:
        estado, transicao = _do_all_red(estado, t, cruzamento, parametros)

    transicoes = () if transicao is None else (transicao,)
    return Avanco(estado=estado, transicoes=transicoes, recusas=tuple(recusas))


def _expirar_preempcao(
    estado: EstadoControlador, t: float, parametros: Parametros
) -> EstadoControlador:
    """Etapa **E6** — encerra a preempção que passou do timeout.

    Um backend travado, ou um VE que sumiu do estado, não pode bloquear a via
    transversal indefinidamente. Note que isto **não** força troca de fase: só
    devolve o cruzamento ao ciclo fixo, que então segue seu curso normalmente.
    """
    if (
        estado.em_preempcao
        and estado.t_inicio_preempcao is not None
        and t - estado.t_inicio_preempcao >= parametros.preempcao_timeout_s
    ):
        return replace(
            estado, em_preempcao=False, t_inicio_preempcao=None, verde_ate=None, fase_alvo=None
        )
    return estado


def _do_verde(
    estado: EstadoControlador, t: float, cruzamento: Cruzamento, parametros: Parametros
) -> tuple[EstadoControlador, Transicao | None]:
    """Verde → amarelo, quando o verde acaba ou uma troca foi pedida.

    O único caminho de saída do verde passa pelo amarelo (I2), e só depois de
    cumprido o verde mínimo (I4). Não há atalho aqui, e é de propósito.
    """
    fase = cruzamento.fase(estado.fase_corrente)
    quer_trocar = estado.fase_alvo is not None and estado.fase_alvo != estado.fase_corrente

    fim_natural = (
        estado.verde_ate if estado.verde_ate is not None else estado.t_mudanca + fase.duracao_base_s
    )
    # Teto absoluto: nem preempção nem extensão passam de verde_max. Sem ele, uma
    # extensão generosa viraria starvation nas demais fases (I5).
    fim_maximo = estado.t_mudanca + min(fase.verde_max_s, parametros.verde_max_s)
    expirou = t >= min(fim_natural, fim_maximo)

    if not (quer_trocar or expirou):
        return estado, None
    if t - estado.t_mudanca < fase.verde_min_s:  # I4
        return estado, None

    if not quer_trocar:
        estado = replace(estado, fase_alvo=cruzamento.proxima_fase(estado.fase_corrente))
    return _iniciar(estado, Sinal.AMARELO, estado.fase_corrente, t)


def _do_amarelo(
    estado: EstadoControlador, t: float, parametros: Parametros
) -> tuple[EstadoControlador, Transicao | None]:
    """Amarelo → all-red. I3 exige o cruzamento limpo antes da próxima fase."""
    if t - estado.t_mudanca < parametros.amarelo_s:
        return estado, None
    return _iniciar(estado, Sinal.VERMELHO, estado.fase_corrente, t)


def _do_all_red(
    estado: EstadoControlador, t: float, cruzamento: Cruzamento, parametros: Parametros
) -> tuple[EstadoControlador, Transicao | None]:
    """All-red → verde da fase alvo, ou da próxima do ciclo se não houver alvo."""
    if t - estado.t_mudanca < parametros.all_red_s:
        return estado, None

    alvo = estado.fase_alvo
    if alvo is None:
        alvo = cruzamento.proxima_fase(estado.fase_corrente)
    estado, transicao = _iniciar(estado, Sinal.VERDE, alvo, t)
    return replace(estado, fase_alvo=None), transicao


def estado_inicial(id_semaforo: str, cruzamento: Cruzamento, t: float = 0.0) -> EstadoControlador:
    """Estado de partida: primeira fase do ciclo, em verde."""
    primeira = cruzamento.indices_de_fase[0]
    return EstadoControlador(
        id_semaforo=id_semaforo,
        fase_corrente=primeira,
        sinal=Sinal.VERDE,
        t_mudanca=t,
        t_ultimo_verde={primeira: t},
    )
