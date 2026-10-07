"""E8 — conflito entre múltiplos VEs.

Cenário obrigatório de teste (`context/01` §5.2) e razão de existir do cenário
experimental `multiplas_emergencias`.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from core.malha import Cruzamento
from core.modelos import Criticidade, TipoVeiculo
from core.parametros import Parametros
from core.priorizacao.conflito import Disputa, resolver
from core.priorizacao.deteccao import DeteccaoVE
from tests.core.conftest import (
    CRITICIDADE_TIPICA,
    FASE_ARTERIAL,
    FASE_TRANSVERSAL,
    construir_cruzamento,
    construir_parametros,
)

CRUZAMENTO = "CRUZ_TESTE_1"


def _disputa(
    id_veiculo: str,
    tipo: TipoVeiculo,
    eta_s: float,
    fase: int,
    ja_em_curso: bool = False,
    criticidade: Criticidade = Criticidade.RISCO_VIDA,
) -> Disputa:
    """Um pedido de preempção artificial.

    A criticidade padrão é a **mesma** para todos: os testes que não a informam
    exercitam o desempate *dentro* de um nível — tipo, ETA, preempção em curso —,
    que é exatamente o E8 de antes da P20.
    """
    return Disputa(
        deteccao=DeteccaoVE(
            id_veiculo=id_veiculo,
            tipo=tipo,
            criticidade=criticidade,
            id_semaforo=CRUZAMENTO,
            distancia_m=eta_s * 10.0,
            eta_s=eta_s,
            movimento=("E0", "E1"),
        ),
        fase_desejada=fase,
        ja_em_curso=ja_em_curso,
    )


# ---------------------------------------------------------------------------
# Critério 0 — criticidade da ocorrência (P20)
# ---------------------------------------------------------------------------


def test_criticidade_vence_o_tipo(cruzamento: Cruzamento, parametros: Parametros) -> None:
    """Incêndio com vítima não espera ambulância com caso leve.

    É o caso que os critérios de relevância da equipe existem para cobrir: a
    precedência é da ocorrência, não do veículo.
    """
    bombeiro = _disputa(
        "BMB",
        TipoVeiculo.BOMBEIRO,
        eta_s=10.0,
        fase=FASE_ARTERIAL,
        criticidade=Criticidade.RISCO_VIDA,
    )
    ambulancia = _disputa(
        "AMB",
        TipoVeiculo.AMBULANCIA,
        eta_s=10.0,
        fase=FASE_TRANSVERSAL,
        criticidade=Criticidade.RISCO_COLETIVO,
    )

    resolucao = resolver(CRUZAMENTO, [ambulancia, bombeiro], cruzamento, parametros)

    assert resolucao is not None
    assert resolucao.vencedor.deteccao.id_veiculo == "BMB"
    assert [d.deteccao.id_veiculo for d in resolucao.adiados] == ["AMB"]


def test_criticidade_vence_o_eta(cruzamento: Cruzamento, parametros: Parametros) -> None:
    """Chegar antes não compensa ser menos crítico."""
    critica = _disputa(
        "POL_A",
        TipoVeiculo.POLICIA,
        eta_s=30.0,
        fase=FASE_ARTERIAL,
        criticidade=Criticidade.RISCO_VIDA,
    )
    urgente = _disputa(
        "POL_B",
        TipoVeiculo.POLICIA,
        eta_s=4.0,
        fase=FASE_TRANSVERSAL,
        criticidade=Criticidade.URGENCIA,
    )

    resolucao = resolver(CRUZAMENTO, [urgente, critica], cruzamento, parametros)

    assert resolucao is not None
    assert resolucao.vencedor.deteccao.id_veiculo == "POL_A"


def test_criticidade_vence_preempcao_em_curso(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    """Nível mais crítico toma o verde de quem já o detém.

    Não gera oscilação: a troca só acontece para um nível estritamente mais
    crítico, e o nível menos crítico nunca toma de volta (`context/09` P20).
    """
    em_curso = _disputa(
        "AMB_LEVE",
        TipoVeiculo.AMBULANCIA,
        eta_s=10.0,
        fase=FASE_ARTERIAL,
        ja_em_curso=True,
        criticidade=Criticidade.URGENCIA,
    )
    grave = _disputa(
        "AMB_GRAVE",
        TipoVeiculo.AMBULANCIA,
        eta_s=10.0,
        fase=FASE_TRANSVERSAL,
        criticidade=Criticidade.RISCO_VIDA,
    )

    resolucao = resolver(CRUZAMENTO, [em_curso, grave], cruzamento, parametros)

    assert resolucao is not None
    assert resolucao.vencedor.deteccao.id_veiculo == "AMB_GRAVE"


def _chave_anterior_a_p20(disputa: Disputa, parametros: Parametros) -> tuple[int, float, int]:
    """A chave de E8 como era antes da P20: tipo → ETA → preempção em curso."""
    return (
        parametros.indice_prioridade(disputa.deteccao.tipo),
        disputa.deteccao.eta_s,
        0 if disputa.ja_em_curso else 1,
    )


_TIPOS = st.sampled_from(list(TipoVeiculo))
_DISPUTA = st.tuples(
    _TIPOS,
    st.floats(min_value=0.0, max_value=120.0, allow_nan=False),
    st.sampled_from([FASE_ARTERIAL, FASE_TRANSVERSAL]),
    st.booleans(),
)


@given(st.lists(_DISPUTA, min_size=1, max_size=5))
def test_criticidade_tipica_decide_como_a_chave_anterior(
    pedidos: list[tuple[TipoVeiculo, float, int, bool]],
) -> None:
    """A propriedade que garante que nenhum número já medido muda.

    Nos cenários do experimento, cada VE atende a ocorrência típica do seu tipo
    (ambulância → 1, bombeiro → 2, polícia → 3). Com essa atribuição e a ordem
    padrão de `prioridade_tipo`, o vencedor tem de ser **o mesmo** que a chave de
    antes da P20 escolheria — para qualquer combinação de tipos, ETAs, fases e
    preempção em curso.
    """
    parametros = construir_parametros()
    cruzamento = construir_cruzamento()
    disputas = [
        _disputa(
            f"VE_{indice}",
            tipo,
            eta_s=eta,
            fase=fase,
            ja_em_curso=em_curso,
            criticidade=CRITICIDADE_TIPICA[tipo],
        )
        for indice, (tipo, eta, fase, em_curso) in enumerate(pedidos)
    ]

    resolucao = resolver(CRUZAMENTO, disputas, cruzamento, parametros)
    esperado = min(disputas, key=lambda d: _chave_anterior_a_p20(d, parametros))

    assert resolucao is not None
    assert _chave_anterior_a_p20(resolucao.vencedor, parametros) == _chave_anterior_a_p20(
        esperado, parametros
    )


# ---------------------------------------------------------------------------
# Dentro do mesmo nível: tipo -> ETA -> preempção em curso
# ---------------------------------------------------------------------------


def test_ambulancia_vence_viatura_mesmo_chegando_depois(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    """Critério 1 tem precedência sobre o 2: tipo antes de ETA."""
    ambulancia = _disputa("AMB", TipoVeiculo.AMBULANCIA, eta_s=20.0, fase=FASE_ARTERIAL)
    policia = _disputa("POL", TipoVeiculo.POLICIA, eta_s=5.0, fase=FASE_TRANSVERSAL)

    resolucao = resolver(CRUZAMENTO, [policia, ambulancia], cruzamento, parametros)

    assert resolucao is not None
    assert resolucao.vencedor.deteccao.id_veiculo == "AMB"
    assert [d.deteccao.id_veiculo for d in resolucao.adiados] == ["POL"]


def test_entre_iguais_vence_o_menor_eta(cruzamento: Cruzamento, parametros: Parametros) -> None:
    """Critério 2, quando o 1 empata."""
    perto = _disputa("AMB_PERTO", TipoVeiculo.AMBULANCIA, eta_s=6.0, fase=FASE_ARTERIAL)
    longe = _disputa("AMB_LONGE", TipoVeiculo.AMBULANCIA, eta_s=25.0, fase=FASE_TRANSVERSAL)

    resolucao = resolver(CRUZAMENTO, [longe, perto], cruzamento, parametros)

    assert resolucao is not None
    assert resolucao.vencedor.deteccao.id_veiculo == "AMB_PERTO"


def test_preempcao_em_curso_desempata_e_evita_oscilacao(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    """Critério 3, quando 1 e 2 empatam.

    Sem ele, dois VEs equivalentes fariam o cruzamento alternar de alvo a cada
    passo — thrashing, e nenhum dos dois passaria.
    """
    em_curso = _disputa(
        "AMB_A", TipoVeiculo.AMBULANCIA, eta_s=10.0, fase=FASE_ARTERIAL, ja_em_curso=True
    )
    novo = _disputa("AMB_B", TipoVeiculo.AMBULANCIA, eta_s=10.0, fase=FASE_TRANSVERSAL)

    resolucao = resolver(CRUZAMENTO, [novo, em_curso], cruzamento, parametros)

    assert resolucao is not None
    assert resolucao.vencedor.deteccao.id_veiculo == "AMB_A"


def test_ordem_de_prioridade_vem_dos_parametros(cruzamento: Cruzamento) -> None:
    """`prioridade_tipo` é configurável (`context/01` §5.3), não constante do código."""
    invertida = construir_parametros(prioridade_tipo=["POLICIA", "BOMBEIRO", "AMBULANCIA"])
    ambulancia = _disputa("AMB", TipoVeiculo.AMBULANCIA, eta_s=10.0, fase=FASE_ARTERIAL)
    policia = _disputa("POL", TipoVeiculo.POLICIA, eta_s=10.0, fase=FASE_TRANSVERSAL)

    resolucao = resolver(CRUZAMENTO, [ambulancia, policia], cruzamento, invertida)

    assert resolucao is not None
    assert resolucao.vencedor.deteccao.id_veiculo == "POL"


# ---------------------------------------------------------------------------
# Nunca conceder as duas
# ---------------------------------------------------------------------------


def test_fases_conflitantes_nunca_sao_concedidas_juntas(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    """A regra dura de E8: um espera, e isso vira `CONFLITO_ADIADO`."""
    arterial = _disputa("AMB", TipoVeiculo.AMBULANCIA, eta_s=8.0, fase=FASE_ARTERIAL)
    transversal = _disputa("BMB", TipoVeiculo.BOMBEIRO, eta_s=8.0, fase=FASE_TRANSVERSAL)
    assert cruzamento.conflitam(FASE_ARTERIAL, FASE_TRANSVERSAL)

    resolucao = resolver(CRUZAMENTO, [arterial, transversal], cruzamento, parametros)

    assert resolucao is not None
    assert resolucao.atendidos_juntos == ()
    assert len(resolucao.adiados) == 1


def test_mesma_fase_serve_os_dois_sem_conflito(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    """Dois VEs pelo mesmo movimento não disputam nada — o mesmo verde os serve."""
    primeiro = _disputa("AMB", TipoVeiculo.AMBULANCIA, eta_s=8.0, fase=FASE_ARTERIAL)
    segundo = _disputa("BMB", TipoVeiculo.BOMBEIRO, eta_s=12.0, fase=FASE_ARTERIAL)

    resolucao = resolver(CRUZAMENTO, [primeiro, segundo], cruzamento, parametros)

    assert resolucao is not None
    assert resolucao.adiados == ()
    assert [d.deteccao.id_veiculo for d in resolucao.atendidos_juntos] == ["BMB"]


def test_sem_disputa_nao_ha_resolucao(cruzamento: Cruzamento, parametros: Parametros) -> None:
    assert resolver(CRUZAMENTO, [], cruzamento, parametros) is None


# ---------------------------------------------------------------------------
# Justificativa
# ---------------------------------------------------------------------------


def test_motivo_explica_o_desempate(cruzamento: Cruzamento, parametros: Parametros) -> None:
    """É o texto que vai para `log_prioridade.motivo` e para a banca."""
    ambulancia = _disputa("AMB", TipoVeiculo.AMBULANCIA, eta_s=20.0, fase=FASE_ARTERIAL)
    policia = _disputa("POL", TipoVeiculo.POLICIA, eta_s=5.0, fase=FASE_TRANSVERSAL)

    resolucao = resolver(CRUZAMENTO, [ambulancia, policia], cruzamento, parametros)

    assert resolucao is not None
    assert "AMB" in resolucao.motivo
    assert "prioridade de tipo" in resolucao.motivo
    assert "POL" in resolucao.motivo


def test_motivo_nomeia_a_criticidade_quando_ela_decide(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    """O log precisa dizer qual critério decidiu — e cabe em `motivo VARCHAR(200)`."""
    bombeiro = _disputa(
        "VE_ROTA_VE_CORREDOR_00",
        TipoVeiculo.BOMBEIRO,
        eta_s=63.5,
        fase=FASE_ARTERIAL,
        criticidade=Criticidade.RISCO_VIDA,
    )
    ambulancia = _disputa(
        "VE_ROTA_VE_TRANSVERSAL_00",
        TipoVeiculo.AMBULANCIA,
        eta_s=12.8,
        fase=FASE_TRANSVERSAL,
        criticidade=Criticidade.URGENCIA,
    )

    resolucao = resolver(CRUZAMENTO, [ambulancia, bombeiro], cruzamento, parametros)

    assert resolucao is not None
    assert "criticidade 1 sobre 3" in resolucao.motivo
    assert len(resolucao.motivo) <= 200


def test_resolucao_sem_adiados_tem_motivo_simples(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    unico = _disputa("AMB", TipoVeiculo.AMBULANCIA, eta_s=8.0, fase=FASE_ARTERIAL)
    resolucao = resolver(CRUZAMENTO, [unico], cruzamento, parametros)

    assert resolucao is not None
    assert "adiados" not in resolucao.motivo
    assert resolucao.motivo


# ---------------------------------------------------------------------------
# Vencedor imposto por uma política de desempate (P19, entregas 10.4 e 10.6)
# ---------------------------------------------------------------------------


def test_politica_decide_entre_iguais(cruzamento: Cruzamento, parametros: Parametros) -> None:
    """No mesmo nível, a proposta da política vence a chave de E8."""
    rapida = _disputa("RAPIDA", TipoVeiculo.AMBULANCIA, eta_s=8.0, fase=FASE_ARTERIAL)
    lenta = _disputa("LENTA", TipoVeiculo.AMBULANCIA, eta_s=30.0, fase=FASE_TRANSVERSAL)

    resolucao = resolver(CRUZAMENTO, [rapida, lenta], cruzamento, parametros, imposto=lenta)

    assert resolucao is not None
    assert resolucao.vencedor == lenta
    assert resolucao.adiados == (rapida,)
    assert "política de desempate" in resolucao.motivo


def test_politica_nao_passa_por_cima_da_criticidade(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    """A criticidade é regra acima de qualquer política (P20): a proposta é ignorada."""
    vida = _disputa("VIDA", TipoVeiculo.POLICIA, eta_s=30.0, fase=FASE_ARTERIAL)
    urgencia = _disputa(
        "URGENCIA",
        TipoVeiculo.AMBULANCIA,
        eta_s=8.0,
        fase=FASE_TRANSVERSAL,
        criticidade=Criticidade.URGENCIA,
    )

    resolucao = resolver(CRUZAMENTO, [vida, urgencia], cruzamento, parametros, imposto=urgencia)

    assert resolucao is not None
    assert resolucao.vencedor == vida
    assert "criticidade 1 sobre 3" in resolucao.motivo


def test_proposta_fora_das_disputas_e_ignorada(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    rapida = _disputa("RAPIDA", TipoVeiculo.AMBULANCIA, eta_s=8.0, fase=FASE_ARTERIAL)
    lenta = _disputa("LENTA", TipoVeiculo.AMBULANCIA, eta_s=30.0, fase=FASE_TRANSVERSAL)
    estranha = _disputa("OUTRA", TipoVeiculo.AMBULANCIA, eta_s=1.0, fase=FASE_TRANSVERSAL)

    resolucao = resolver(CRUZAMENTO, [rapida, lenta], cruzamento, parametros, imposto=estranha)

    assert resolucao is not None
    assert resolucao.vencedor == rapida
