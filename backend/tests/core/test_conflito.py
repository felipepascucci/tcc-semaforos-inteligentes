"""E8 — conflito entre múltiplos VEs.

Cenário obrigatório de teste (`context/01` §5.2) e razão de existir do cenário
experimental `multiplas_emergencias`.
"""

from __future__ import annotations

from core.malha import Cruzamento
from core.modelos import TipoVeiculo
from core.parametros import Parametros
from core.priorizacao.conflito import Disputa, resolver
from core.priorizacao.deteccao import DeteccaoVE
from tests.core.conftest import FASE_ARTERIAL, FASE_TRANSVERSAL, construir_parametros

CRUZAMENTO = "CRUZ_TESTE_1"


def _disputa(
    id_veiculo: str,
    tipo: TipoVeiculo,
    eta_s: float,
    fase: int,
    ja_em_curso: bool = False,
) -> Disputa:
    return Disputa(
        deteccao=DeteccaoVE(
            id_veiculo=id_veiculo,
            tipo=tipo,
            id_semaforo=CRUZAMENTO,
            distancia_m=eta_s * 10.0,
            eta_s=eta_s,
            movimento=("E0", "E1"),
        ),
        fase_desejada=fase,
        ja_em_curso=ja_em_curso,
    )


# ---------------------------------------------------------------------------
# Ordem de desempate: tipo -> ETA -> preempção em curso
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


def test_resolucao_sem_adiados_tem_motivo_simples(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    unico = _disputa("AMB", TipoVeiculo.AMBULANCIA, eta_s=8.0, fase=FASE_ARTERIAL)
    resolucao = resolver(CRUZAMENTO, [unico], cruzamento, parametros)

    assert resolucao is not None
    assert "adiados" not in resolucao.motivo
    assert resolucao.motivo
