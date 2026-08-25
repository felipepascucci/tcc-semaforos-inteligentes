"""Property-based testing dos invariantes de segurança (`context/06` §3).

O Hypothesis gera **milhares de sequências aleatórias de comandos** — incluindo
combinações que nenhum humano escreveria — e a máquina de estados precisa manter
os invariantes em *todo estado alcançado*. É um argumento de qualidade muito mais
forte na banca que "testamos manualmente": não se está afirmando que os casos
pensados passam, e sim que não se achou contraexemplo em milhares de tentativas.

**Divisão de responsabilidade** (contrato §9, tabela de invariantes):

* **I1, I2, I3, I4** são garantidos pela máquina de estados sozinha, sob qualquer
  sequência de comandos. É o que se verifica aqui.
* **I5** (starvation) é responsabilidade do **motor**, não do controlador: uma
  sequência adversária de extensões de verde *pode* matar de fome uma
  aproximação, e é justamente por isso que a decisão de preemptar precisa
  consultar o histórico de verdes. Verificado em `test_motor.py`.

Quando um contraexemplo aparece, o Hypothesis o reduz ao menor caso que ainda
falha — normalmente três ou quatro comandos, legíveis de imediato.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.comandos import Comando, TipoComando
from core.malha import Cruzamento, Fase
from core.modelos import Sinal
from core.parametros import Parametros
from core.priorizacao.fases import EstadoControlador, avancar, estado_inicial
from core.seguranca import verificar_i1, verificar_par_de_transicoes, verificar_transicao
from tests.core.conftest import construir_parametros, construir_topologia

PASSO_S = 0.5

CRUZAMENTO_2_FASES = construir_topologia(n_cruzamentos=1).cruzamento("CRUZ_TESTE_1")

#: O protótipo: 4 aproximações em *split phasing*, toda fase conflitando com
#: todas as outras (decisão P13). Sob esse regime I1 vira `contar_verdes() <= 1`.
CRUZAMENTO_4_FASES = Cruzamento(
    id="PROTO_CRUZ_01",
    fases=tuple(
        Fase(
            indice=indice,
            descricao=f"Aproximação S{indice}",
            movimentos=frozenset({(f"IN{indice}", f"OUT{indice}")}),
            duracao_base_s=3.0,
            verde_min_s=3.0,
            verde_max_s=30.0,
        )
        for indice in (1, 2, 3, 4)
    ),
)

PARAMETROS_BANCADA = construir_parametros(
    verde_min_s=3.0, verde_max_s=30.0, amarelo_s=2.0, all_red_s=1.0, preempcao_timeout_s=30.0
)


def _comandos(cruzamento: Cruzamento) -> st.SearchStrategy[Comando]:
    """Comandos plausíveis e implausíveis, de propósito.

    Fases inválidas e durações absurdas entram na geração: o controlador precisa
    recusá-las com `NAK`, e recusar é comportamento correto, não erro.
    """
    indices = list(cruzamento.indices_de_fase)
    return st.one_of(
        st.builds(
            Comando,
            tipo=st.just(TipoComando.IR_PARA_FASE),
            id_semaforo=st.just(cruzamento.id),
            fase_alvo=st.sampled_from([*indices, 0, 99, -1]),
            motivo=st.just("hypothesis"),
        ),
        st.builds(
            Comando,
            tipo=st.just(TipoComando.ESTENDER_VERDE),
            id_semaforo=st.just(cruzamento.id),
            duracao_s=st.floats(min_value=-10.0, max_value=500.0, allow_nan=False),
            motivo=st.just("hypothesis"),
        ),
        st.builds(
            Comando,
            tipo=st.sampled_from(
                [TipoComando.LIBERAR, TipoComando.COMPENSAR, TipoComando.FALLBACK_SEGURO]
            ),
            id_semaforo=st.just(cruzamento.id),
            motivo=st.just("hypothesis"),
        ),
    )


def _executar(
    cruzamento: Cruzamento,
    parametros: Parametros,
    roteiro: list[tuple[int, Comando]],
    n_passos: int,
) -> list:
    """Roda a máquina, verificando os invariantes em cada estado alcançado.

    Returns:
        Todas as violações encontradas. Vazio é o único resultado aceitável.
    """
    por_passo: dict[int, list[Comando]] = {}
    for passo, comando in roteiro:
        por_passo.setdefault(passo % n_passos, []).append(comando)

    estado: EstadoControlador = estado_inicial(cruzamento.id, cruzamento)
    anterior = None
    violacoes: list = []
    t = 0.0

    for passo in range(n_passos):
        t = round(t + PASSO_S, 4)
        avanco = avancar(estado, t, cruzamento, parametros, tuple(por_passo.get(passo, ())))
        estado = avanco.estado

        # I1 — sobre o estado alcançado.
        violacoes.extend(verificar_i1(estado, cruzamento, t))

        # I4 sobre cada transição; I2 e I3 sobre pares consecutivos.
        for transicao in avanco.transicoes:
            violacoes.extend(verificar_transicao(transicao, cruzamento))
            if anterior is not None:
                violacoes.extend(verificar_par_de_transicoes(anterior, transicao, cruzamento))
            anterior = transicao

    return violacoes


# ---------------------------------------------------------------------------
# I1 a I4 sob sequências arbitrárias
# ---------------------------------------------------------------------------


@settings(max_examples=400, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    roteiro=st.lists(
        st.tuples(st.integers(min_value=0, max_value=200), _comandos(CRUZAMENTO_2_FASES)),
        max_size=25,
    )
)
def test_invariantes_resistem_a_qualquer_sequencia_de_comandos(
    roteiro: list[tuple[int, Comando]],
) -> None:
    """Malha de simulação, 2 fases, verde mínimo de 7 s."""
    violacoes = _executar(CRUZAMENTO_2_FASES, construir_parametros(), roteiro, n_passos=200)
    assert violacoes == [], f"invariante violado: {[str(v) for v in violacoes]}"


@settings(max_examples=400, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    roteiro=st.lists(
        st.tuples(st.integers(min_value=0, max_value=200), _comandos(CRUZAMENTO_4_FASES)),
        max_size=25,
    )
)
def test_invariantes_resistem_no_prototipo_em_split_phasing(
    roteiro: list[tuple[int, Comando]],
) -> None:
    """Protótipo, 4 aproximações, matriz de conflito total (decisão P13)."""
    violacoes = _executar(CRUZAMENTO_4_FASES, PARAMETROS_BANCADA, roteiro, n_passos=200)
    assert violacoes == [], f"invariante violado: {[str(v) for v in violacoes]}"


@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    roteiro=st.lists(
        st.tuples(st.integers(min_value=0, max_value=200), _comandos(CRUZAMENTO_4_FASES)),
        max_size=25,
    )
)
def test_nunca_ha_mais_de_um_verde_no_prototipo(roteiro: list[tuple[int, Comando]]) -> None:
    """`contar_verdes() <= 1` — a forma que I1 assume sob *split phasing*.

    É a mesma verificação que o relatório de validação faz sobre a telemetria
    `ST,...` do Arduino: contar os `G` na string de estado e exigir zero
    ocorrências com dois ou mais.
    """
    por_passo: dict[int, list[Comando]] = {}
    for passo, comando in roteiro:
        por_passo.setdefault(passo % 200, []).append(comando)

    estado = estado_inicial(CRUZAMENTO_4_FASES.id, CRUZAMENTO_4_FASES)
    t = 0.0
    for passo in range(200):
        t = round(t + PASSO_S, 4)
        estado = avancar(
            estado, t, CRUZAMENTO_4_FASES, PARAMETROS_BANCADA, tuple(por_passo.get(passo, ()))
        ).estado

        verdes = [
            indice
            for indice, sinal in estado.sinais(CRUZAMENTO_4_FASES).items()
            if sinal is Sinal.VERDE
        ]
        assert len(verdes) <= 1, f"t={t}: verdes simultâneos em {verdes}"


# ---------------------------------------------------------------------------
# Propriedades estruturais da máquina
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    roteiro=st.lists(
        st.tuples(st.integers(min_value=0, max_value=150), _comandos(CRUZAMENTO_2_FASES)),
        max_size=20,
    )
)
def test_comando_recusado_nao_altera_a_sinalizacao(roteiro: list[tuple[int, Comando]]) -> None:
    """Recusar é seguro: um `NAK` nunca deixa efeito colateral pela metade."""
    parametros = construir_parametros()
    por_passo: dict[int, list[Comando]] = {}
    for passo, comando in roteiro:
        por_passo.setdefault(passo % 150, []).append(comando)

    estado = estado_inicial(CRUZAMENTO_2_FASES.id, CRUZAMENTO_2_FASES)
    t = 0.0
    for passo in range(150):
        t = round(t + PASSO_S, 4)
        anterior = estado
        avanco = avancar(estado, t, CRUZAMENTO_2_FASES, parametros, tuple(por_passo.get(passo, ())))
        estado = avanco.estado

        if avanco.recusas and not avanco.transicoes:
            assert estado.sinal is anterior.sinal
            assert estado.fase_corrente == anterior.fase_corrente


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    roteiro=st.lists(
        st.tuples(st.integers(min_value=0, max_value=300), _comandos(CRUZAMENTO_2_FASES)),
        max_size=20,
    )
)
def test_maquina_nunca_trava(roteiro: list[tuple[int, Comando]]) -> None:
    """O controlador sempre volta a girar — nenhum comando o congela.

    É o análogo em software do requisito que mais assusta na bancada: o Arduino
    não pode ficar com um verde aceso para sempre porque alguém mandou o comando
    errado.
    """
    parametros = construir_parametros()
    por_passo: dict[int, list[Comando]] = {}
    for passo, comando in roteiro:
        por_passo.setdefault(passo % 300, []).append(comando)

    estado = estado_inicial(CRUZAMENTO_2_FASES.id, CRUZAMENTO_2_FASES)
    t = 0.0
    verdes_vistos: set[int] = set()
    for passo in range(300):  # 150 s: mais de dois ciclos completos de 70 s
        t = round(t + PASSO_S, 4)
        avanco = avancar(estado, t, CRUZAMENTO_2_FASES, parametros, tuple(por_passo.get(passo, ())))
        estado = avanco.estado
        for transicao in avanco.transicoes:
            if transicao.sinal is Sinal.VERDE:
                verdes_vistos.add(transicao.fase)

    assert verdes_vistos, "nenhuma fase recebeu verde em 150 s de simulação"
