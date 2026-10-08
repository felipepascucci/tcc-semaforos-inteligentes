"""Inferência da política aprendida de E8 — entrega 10.6 (P19, P20).

O que se confere aqui é o que `context/10` §3 e §4 prometem para a banca:
antissimetria por construção, as duas regras acima do modelo (criticidade e
guarda de oscilação), o torneio com três ou mais VEs e o empate exato decidido
pelo E8. Os pesos dos testes são artificiais e redondos, exceto onde o teste diz
que usa os de `politica_desempate.yaml`.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Sequence

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core.excecoes import ConfiguracaoInvalidaError
from core.malha import TopologiaMalha
from core.modelos import Criticidade, EstadoMalha, TipoVeiculo, VeiculoEmergencia
from core.parametros import Parametros
from core.priorizacao.atributos import AtributosVE
from core.priorizacao.conflito import Disputa
from core.priorizacao.deteccao import DeteccaoVE
from core.priorizacao.motor import MotorDecisao
from core.priorizacao.politica import (
    ATRIBUTOS_DO_MODELO,
    ConsultaModelo,
    PesosPolitica,
    PoliticaAprendida,
    decidir,
    invictos,
    score,
    vetor_de_atributos,
)
from tests.core.conftest import (
    FASE_ARTERIAL,
    FASE_TRANSVERSAL,
    construir_estado,
    construir_parametros,
    construir_ve,
)

CRUZAMENTO = "CRUZ_TESTE_1"

#: Só a rota restante pesa, a favor de quem tem mais cruzamentos pela frente.
PREFERE_ROTA_LONGA = PesosPolitica(
    eta_s=0.0, velocidade_ms=0.0, fila_por_faixa=0.0, cruzamentos_restantes=1.0
)
#: O contrário: a favor de quem tem menos cruzamentos pela frente.
PREFERE_ROTA_CURTA = PesosPolitica(
    eta_s=0.0, velocidade_ms=0.0, fila_por_faixa=0.0, cruzamentos_restantes=-1.0
)
#: Só o ETA pesa, a favor de quem chega antes.
PREFERE_MENOR_ETA = PesosPolitica(
    eta_s=-1.0, velocidade_ms=0.0, fila_por_faixa=0.0, cruzamentos_restantes=0.0
)


def _atributos(
    eta_s: float = 20.0,
    velocidade_ms: float = 10.0,
    fila_por_faixa: float = 0.0,
    cruzamentos_restantes: int = 1,
) -> AtributosVE:
    return AtributosVE(
        eta_s=eta_s,
        velocidade_ms=velocidade_ms,
        fila_no_acesso=int(fila_por_faixa),
        fila_por_faixa=fila_por_faixa,
        cruzamentos_restantes=cruzamentos_restantes,
    )


def _disputa(
    id_veiculo: str,
    fase: int,
    criticidade: Criticidade = Criticidade.RISCO_COLETIVO,
    tipo: TipoVeiculo = TipoVeiculo.BOMBEIRO,
    eta_s: float = 20.0,
    ja_em_curso: bool = False,
) -> Disputa:
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


class _Tabela:
    """`atributos_de` de teste: devolve os atributos por id e anota quem foi consultado."""

    def __init__(self, atributos: dict[str, AtributosVE]) -> None:
        self.atributos = atributos
        self.consultados: list[str] = []

    def __call__(self, disputa: Disputa) -> AtributosVE:
        self.consultados.append(disputa.deteccao.id_veiculo)
        return self.atributos[disputa.deteccao.id_veiculo]


def _decidir(
    disputas: Sequence[Disputa],
    tabela: _Tabela,
    pesos: PesosPolitica,
    parametros: Parametros | None = None,
) -> Disputa | None:
    return decidir(disputas, tabela, pesos, parametros or construir_parametros())


# ---------------------------------------------------------------------------
# O score: forma e antissimetria
# ---------------------------------------------------------------------------

_reais = st.floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False)
_atributos_quaisquer = st.builds(
    _atributos,
    eta_s=st.floats(min_value=0.0, max_value=300.0),
    velocidade_ms=st.floats(min_value=0.0, max_value=40.0),
    fila_por_faixa=st.floats(min_value=0.0, max_value=50.0),
    cruzamentos_restantes=st.integers(min_value=0, max_value=12),
)
_pesos_quaisquer = st.builds(
    PesosPolitica,
    eta_s=_reais,
    velocidade_ms=_reais,
    fila_por_faixa=_reais,
    cruzamentos_restantes=_reais,
)


@given(pesos=_pesos_quaisquer, a=_atributos_quaisquer, b=_atributos_quaisquer)
def test_score_e_antissimetrico_por_construcao(
    pesos: PesosPolitica, a: AtributosVE, b: AtributosVE
) -> None:
    """`score(B, A) = -score(A, B)` exatamente, não só a menos de arredondamento."""
    assert score(pesos, b, a) == -score(pesos, a, b)


@given(pesos=_pesos_quaisquer, a=_atributos_quaisquer)
def test_score_contra_si_mesmo_e_zero(pesos: PesosPolitica, a: AtributosVE) -> None:
    """Sem intercepto: nenhum VE é preferido a uma cópia de si mesmo."""
    assert score(pesos, a, a) == 0.0


def test_score_e_o_produto_escalar_das_diferencas() -> None:
    pesos = PesosPolitica(
        eta_s=-0.5, velocidade_ms=-0.25, fila_por_faixa=2.0, cruzamentos_restantes=1.0
    )
    a = _atributos(eta_s=10.0, velocidade_ms=12.0, fila_por_faixa=1.0, cruzamentos_restantes=4)
    b = _atributos(eta_s=20.0, velocidade_ms=8.0, fila_por_faixa=3.0, cruzamentos_restantes=1)

    # -0,5 * (-10) - 0,25 * 4 + 2 * (-2) + 1 * 3 = 5 - 1 - 4 + 3
    assert score(pesos, a, b) == pytest.approx(3.0)


def test_vetor_segue_a_ordem_do_treino() -> None:
    """A ordem que vai ao produto escalar é a de `analysis/treino_politica.py`."""
    assert ATRIBUTOS_DO_MODELO == (
        "eta_s",
        "velocidade_ms",
        "fila_por_faixa",
        "cruzamentos_restantes",
    )
    atributos = _atributos(
        eta_s=1.0, velocidade_ms=2.0, fila_por_faixa=3.0, cruzamentos_restantes=4
    )
    assert vetor_de_atributos(atributos) == (1.0, 2.0, 3.0, 4.0)


def test_fila_que_entra_e_a_por_faixa_e_nao_a_somada() -> None:
    """Decisão da 10.5: a fila do modelo é `fila_por_faixa`."""
    pesos = PesosPolitica(
        eta_s=0.0, velocidade_ms=0.0, fila_por_faixa=1.0, cruzamentos_restantes=0.0
    )
    a = dataclasses.replace(_atributos(fila_por_faixa=5.0), fila_no_acesso=10)
    b = dataclasses.replace(_atributos(fila_por_faixa=5.0), fila_no_acesso=0)

    assert score(pesos, a, b) == 0.0


# ---------------------------------------------------------------------------
# Regra 1 — criticidade acima do modelo
# ---------------------------------------------------------------------------


def test_criticidade_vence_o_modelo() -> None:
    """O modelo preferiria o VE de nível 3, mas só o nível mais crítico disputa."""
    vida = _disputa("VIDA", FASE_ARTERIAL, criticidade=Criticidade.RISCO_VIDA)
    urgencia = _disputa("URG", FASE_TRANSVERSAL, criticidade=Criticidade.URGENCIA)
    tabela = _Tabela(
        {"VIDA": _atributos(cruzamentos_restantes=1), "URG": _atributos(cruzamentos_restantes=5)}
    )

    assert _decidir([vida, urgencia], tabela, PREFERE_ROTA_LONGA) == vida
    assert tabela.consultados == []


def test_criticidade_vence_preempcao_em_curso_de_nivel_menos_critico() -> None:
    """P20: o nível mais crítico vence, inclusive sobre a preempção em curso."""
    vida = _disputa("VIDA", FASE_ARTERIAL, criticidade=Criticidade.RISCO_VIDA)
    em_curso = _disputa("URG", FASE_TRANSVERSAL, criticidade=Criticidade.URGENCIA, ja_em_curso=True)
    tabela = _Tabela({})

    assert _decidir([em_curso, vida], tabela, PREFERE_ROTA_LONGA) == vida


def test_modelo_decide_so_entre_os_do_nivel_mais_critico() -> None:
    """Com dois de nível 1 e um de nível 2, o modelo nem vê o de nível 2."""
    curto = _disputa("CURTO", FASE_ARTERIAL, criticidade=Criticidade.RISCO_VIDA)
    longo = _disputa("LONGO", FASE_TRANSVERSAL, criticidade=Criticidade.RISCO_VIDA)
    outro = _disputa("OUTRO", FASE_TRANSVERSAL, criticidade=Criticidade.RISCO_COLETIVO)
    tabela = _Tabela(
        {
            "CURTO": _atributos(cruzamentos_restantes=1),
            "LONGO": _atributos(cruzamentos_restantes=3),
            "OUTRO": _atributos(cruzamentos_restantes=9),
        }
    )

    assert _decidir([outro, curto, longo], tabela, PREFERE_ROTA_LONGA) == longo
    assert sorted(tabela.consultados) == ["CURTO", "LONGO"]


# ---------------------------------------------------------------------------
# Regra 2 — guarda de oscilação acima do modelo
# ---------------------------------------------------------------------------


def test_no_mesmo_nivel_a_preempcao_em_curso_vence_o_modelo() -> None:
    """O modelo preferiria o outro, mas a troca entre iguais é governada pela regra."""
    em_curso = _disputa("EM_CURSO", FASE_ARTERIAL, ja_em_curso=True)
    desafiante = _disputa("DESAFIANTE", FASE_TRANSVERSAL)
    tabela = _Tabela(
        {
            "EM_CURSO": _atributos(cruzamentos_restantes=1),
            "DESAFIANTE": _atributos(cruzamentos_restantes=6),
        }
    )

    assert _decidir([desafiante, em_curso], tabela, PREFERE_ROTA_LONGA) == em_curso
    assert tabela.consultados == []


# ---------------------------------------------------------------------------
# Regra 3 — o modelo
# ---------------------------------------------------------------------------


def test_modelo_decide_entre_iguais_sem_preempcao_em_curso() -> None:
    a = _disputa("A", FASE_ARTERIAL, eta_s=5.0)
    b = _disputa("B", FASE_TRANSVERSAL, eta_s=30.0)
    tabela = _Tabela(
        {
            "A": _atributos(eta_s=5.0, cruzamentos_restantes=1),
            "B": _atributos(eta_s=30.0, cruzamentos_restantes=4),
        }
    )

    assert _decidir([a, b], tabela, PREFERE_ROTA_LONGA) == b
    assert _decidir([a, b], tabela, PREFERE_MENOR_ETA) == a


def test_mesma_fase_nao_e_conflito_e_o_modelo_nao_decide() -> None:
    """O mesmo verde serve os dois: decide o E8 de sempre (`None`)."""
    a = _disputa("A", FASE_ARTERIAL)
    b = _disputa("B", FASE_ARTERIAL)
    tabela = _Tabela({"A": _atributos(), "B": _atributos(cruzamentos_restantes=5)})

    assert _decidir([a, b], tabela, PREFERE_ROTA_LONGA) is None
    assert tabela.consultados == []


def test_sem_pedidos_nao_ha_decisao() -> None:
    assert _decidir([], _Tabela({}), PREFERE_ROTA_LONGA) is None


@given(ordem=st.permutations(["A", "B", "C"]), pesos=_pesos_quaisquer)
def test_torneio_nao_depende_da_ordem_de_apresentacao(
    ordem: list[str], pesos: PesosPolitica
) -> None:
    """Com três VEs, vence o invicto, qualquer que seja a ordem dos pedidos.

    Os pesos sorteados incluem zeros, e então há empate no modelo: o teste cobre
    também o desempate pelo E8, que não depende da ordem quando os ETAs diferem.
    """
    fases = {"A": FASE_ARTERIAL, "B": FASE_TRANSVERSAL, "C": FASE_TRANSVERSAL}
    etas = {"A": 12.0, "B": 25.0, "C": 7.0}
    tabela = _Tabela(
        {
            "A": _atributos(
                eta_s=12.0, velocidade_ms=9.0, fila_por_faixa=2.0, cruzamentos_restantes=3
            ),
            "B": _atributos(
                eta_s=25.0, velocidade_ms=14.0, fila_por_faixa=0.0, cruzamentos_restantes=1
            ),
            "C": _atributos(
                eta_s=7.0, velocidade_ms=4.0, fila_por_faixa=5.0, cruzamentos_restantes=2
            ),
        }
    )

    def pedidos(nomes: Sequence[str]) -> list[Disputa]:
        return [_disputa(nome, fases[nome], eta_s=etas[nome]) for nome in nomes]

    referencia = _decidir(pedidos(("A", "B", "C")), tabela, pesos)
    vencedor = _decidir(pedidos(ordem), tabela, pesos)

    assert vencedor is not None and referencia is not None
    assert vencedor.deteccao.id_veiculo == referencia.deteccao.id_veiculo


def test_torneio_com_tres_escolhe_o_que_bate_todos() -> None:
    """O de mais rota pela frente bate os outros dois, dois a dois."""
    a = _disputa("A", FASE_ARTERIAL)
    b = _disputa("B", FASE_TRANSVERSAL)
    c = _disputa("C", FASE_TRANSVERSAL)
    tabela = _Tabela(
        {
            "A": _atributos(cruzamentos_restantes=2),
            "B": _atributos(cruzamentos_restantes=4),
            "C": _atributos(cruzamentos_restantes=3),
        }
    )

    assert _decidir([a, b, c], tabela, PREFERE_ROTA_LONGA) == b
    assert _decidir([a, b, c], tabela, PREFERE_ROTA_CURTA) == a


def test_invictos_num_empate_exato_sao_todos_os_empatados() -> None:
    iguais = [_atributos(cruzamentos_restantes=3), _atributos(cruzamentos_restantes=3)]
    pior = _atributos(cruzamentos_restantes=1)

    assert invictos(PREFERE_ROTA_LONGA, [*iguais, pior]) == (0, 1)


@pytest.mark.parametrize("ordem", [("BOMB", "AMB"), ("AMB", "BOMB")])
def test_empate_exato_e_decidido_pelo_e8_entre_os_empatados(ordem: tuple[str, str]) -> None:
    """Decisão de 2026-10-07: no empate o modelo não tem preferência, e decide o E8.

    Mesmo nível, mesmos atributos: vence a ambulância pela ordem de tipo, em
    qualquer ordem de apresentação. O terceiro, que perde para os dois no
    modelo, não entra no desempate, mesmo tendo o menor ETA.
    """
    pedidos = {
        "AMB": _disputa("AMB", FASE_ARTERIAL, tipo=TipoVeiculo.AMBULANCIA),
        "BOMB": _disputa("BOMB", FASE_TRANSVERSAL, tipo=TipoVeiculo.BOMBEIRO),
    }
    terceiro = _disputa("POL", FASE_TRANSVERSAL, tipo=TipoVeiculo.AMBULANCIA, eta_s=1.0)
    tabela = _Tabela(
        {
            "AMB": _atributos(cruzamentos_restantes=3),
            "BOMB": _atributos(cruzamentos_restantes=3),
            "POL": _atributos(cruzamentos_restantes=1),
        }
    )

    vencedor = _decidir([terceiro, *(pedidos[nome] for nome in ordem)], tabela, PREFERE_ROTA_LONGA)

    assert vencedor == pedidos["AMB"]


def test_empate_exato_entre_mesmo_tipo_vai_ao_menor_eta() -> None:
    lento = _disputa("LENTO", FASE_ARTERIAL, eta_s=30.0)
    rapido = _disputa("RAPIDO", FASE_TRANSVERSAL, eta_s=10.0)
    tabela = _Tabela({"LENTO": _atributos(), "RAPIDO": _atributos()})

    assert _decidir([lento, rapido], tabela, PREFERE_ROTA_LONGA) == rapido


# ---------------------------------------------------------------------------
# Pesos: validação na carga
# ---------------------------------------------------------------------------

_PESOS_VALIDOS = {
    "eta_s": -0.04,
    "velocidade_ms": -0.15,
    "fila_por_faixa": 0.001,
    "cruzamentos_restantes": 0.5,
}


def test_pesos_validos_carregam() -> None:
    pesos = PesosPolitica.de_dicionario(list(ATRIBUTOS_DO_MODELO), _PESOS_VALIDOS)

    assert pesos.vetor() == (-0.04, -0.15, 0.001, 0.5)


@pytest.mark.parametrize(
    ("atributos", "pesos", "trecho"),
    [
        (
            ["velocidade_ms", "eta_s", "fila_por_faixa", "cruzamentos_restantes"],
            _PESOS_VALIDOS,
            "atributos",
        ),
        (
            ["eta_s", "velocidade_ms", "fila_no_acesso", "cruzamentos_restantes"],
            _PESOS_VALIDOS,
            "atributos",
        ),
        (
            list(ATRIBUTOS_DO_MODELO),
            {k: v for k, v in _PESOS_VALIDOS.items() if k != "eta_s"},
            "pesos",
        ),
        (list(ATRIBUTOS_DO_MODELO), {**_PESOS_VALIDOS, "tipo": 1.0}, "pesos"),
        (list(ATRIBUTOS_DO_MODELO), {**_PESOS_VALIDOS, "eta_s": "-0.04"}, "não é número"),
        (list(ATRIBUTOS_DO_MODELO), {**_PESOS_VALIDOS, "eta_s": True}, "não é número"),
        (list(ATRIBUTOS_DO_MODELO), {**_PESOS_VALIDOS, "eta_s": math.nan}, "não é finito"),
        (list(ATRIBUTOS_DO_MODELO), {**_PESOS_VALIDOS, "eta_s": math.inf}, "não é finito"),
    ],
    ids=["ordem", "fila-somada", "falta", "sobra", "texto", "booleano", "nan", "infinito"],
)
def test_pesos_de_outro_desenho_falham_na_carga(
    atributos: list[str], pesos: dict[str, object], trecho: str
) -> None:
    with pytest.raises(ConfiguracaoInvalidaError, match=trecho):
        PesosPolitica.de_dicionario(atributos, pesos)


# ---------------------------------------------------------------------------
# No motor, de ponta a ponta
# ---------------------------------------------------------------------------


def _transversal(id_veiculo: str = "TRV", posicao_na_via_m: float = 450.0) -> VeiculoEmergencia:
    """Um VE de nível 1 que atravessa `CRUZ_TESTE_1` pela transversal e sai."""
    return VeiculoEmergencia(
        id=id_veiculo,
        tipo=TipoVeiculo.AMBULANCIA,
        criticidade=Criticidade.RISCO_VIDA,
        posicao=(0.0, 0.0),
        velocidade=10.0,
        rota=("T1_IN", "T1_OUT"),
        indice_via_atual=0,
        posicao_na_via_m=posicao_na_via_m,
    )


def _veiculo_no_cruzamento(motor: MotorDecisao, estado: EstadoMalha) -> str | None:
    comandos = [c for c in motor.avaliar(estado) if c.id_semaforo == CRUZAMENTO]
    return comandos[0].id_veiculo if comandos else None


def _motor(
    topologia: TopologiaMalha, parametros: Parametros, pesos: PesosPolitica | None
) -> MotorDecisao:
    politica = None if pesos is None else PoliticaAprendida(pesos, topologia, parametros)
    return MotorDecisao(parametros=parametros, topologia=topologia, politica=politica)


def test_no_motor_o_modelo_troca_a_escolha_do_e8(
    topologia: TopologiaMalha, parametros: Parametros
) -> None:
    """Duas ambulâncias de nível 1: o E8 dá a de menor ETA, o modelo a de rota longa.

    A arterial tem três cruzamentos pela frente e chega em 9 s; a transversal,
    um cruzamento só, chega em 5 s.
    """
    arterial = construir_ve("ART", TipoVeiculo.AMBULANCIA, n_vias=4, posicao_na_via_m=410.0)
    estado = construir_estado(topologia, veiculos=(arterial, _transversal()))

    assert _veiculo_no_cruzamento(_motor(topologia, parametros, None), estado) == "TRV"
    assert (
        _veiculo_no_cruzamento(_motor(topologia, parametros, PREFERE_ROTA_LONGA), estado) == "ART"
    )


def test_no_motor_os_pesos_treinados_preferem_o_corredor(
    topologia: TopologiaMalha, parametros: Parametros
) -> None:
    """Com os pesos de `politica_desempate.yaml`, o corredor primeiro.

    É a regra que `context/10` §6 descreve: mais rota pela frente pesa a favor,
    salvo se o outro estiver bem mais perto.
    """
    from adapters.configuracao import carregar_politica

    pesos = carregar_politica()
    arterial = construir_ve("ART", TipoVeiculo.AMBULANCIA, n_vias=4, posicao_na_via_m=410.0)
    estado = construir_estado(topologia, veiculos=(arterial, _transversal()))

    assert _veiculo_no_cruzamento(_motor(topologia, parametros, pesos), estado) == "ART"


def test_no_motor_a_guarda_segura_a_preempcao_contra_o_modelo(
    topologia: TopologiaMalha, parametros: Parametros
) -> None:
    """A preempção em curso vence entre iguais, mesmo contra o modelo.

    A arterial abre a preempção sozinha; quando a transversal chega, o modelo a
    preferiria.
    """
    motor = _motor(topologia, parametros, PREFERE_ROTA_CURTA)
    arterial = construir_ve("ART", TipoVeiculo.AMBULANCIA, n_vias=4, posicao_na_via_m=410.0)

    assert _veiculo_no_cruzamento(motor, construir_estado(topologia, veiculos=(arterial,))) == "ART"

    arterial = construir_ve("ART", TipoVeiculo.AMBULANCIA, n_vias=4, posicao_na_via_m=411.0)
    estado = construir_estado(topologia, t=0.1, veiculos=(arterial, _transversal()))
    comandos = [c for c in motor.avaliar(estado) if c.id_semaforo == CRUZAMENTO]

    assert [c.id_veiculo for c in comandos] == ["ART"]
    assert "preempção já em curso" in comandos[0].motivo


def test_no_motor_a_criticidade_vence_o_modelo(
    topologia: TopologiaMalha, parametros: Parametros
) -> None:
    arterial = construir_ve(
        "ART",
        TipoVeiculo.POLICIA,
        n_vias=4,
        posicao_na_via_m=410.0,
        criticidade=Criticidade.URGENCIA,
    )
    estado = construir_estado(topologia, veiculos=(arterial, _transversal()))

    assert (
        _veiculo_no_cruzamento(_motor(topologia, parametros, PREFERE_ROTA_LONGA), estado) == "TRV"
    )


# ---------------------------------------------------------------------------
# Quem decidiu — a consulta ao modelo é observável (entrega 10.7)
# ---------------------------------------------------------------------------


class _Consultas:
    """`ao_consultar` de teste: guarda os candidatos e o escolhido de cada chamada."""

    def __init__(self) -> None:
        self.chamadas: list[tuple[list[str], str]] = []

    def __call__(self, candidatos: Sequence[Disputa], escolhido: Disputa) -> None:
        self.chamadas.append(
            ([d.deteccao.id_veiculo for d in candidatos], escolhido.deteccao.id_veiculo)
        )


def test_consulta_e_anunciada_quando_o_modelo_decide() -> None:
    a = _disputa("A", FASE_ARTERIAL)
    b = _disputa("B", FASE_TRANSVERSAL)
    tabela = _Tabela(
        {"A": _atributos(cruzamentos_restantes=1), "B": _atributos(cruzamentos_restantes=4)}
    )
    consultas = _Consultas()

    vencedor = decidir([a, b], tabela, PREFERE_ROTA_LONGA, construir_parametros(), consultas)

    assert vencedor == b
    assert consultas.chamadas == [(["A", "B"], "B")]


def test_consulta_traz_so_os_candidatos_do_nivel_mais_critico() -> None:
    curto = _disputa("CURTO", FASE_ARTERIAL, criticidade=Criticidade.RISCO_VIDA)
    longo = _disputa("LONGO", FASE_TRANSVERSAL, criticidade=Criticidade.RISCO_VIDA)
    outro = _disputa("OUTRO", FASE_TRANSVERSAL, criticidade=Criticidade.RISCO_COLETIVO)
    tabela = _Tabela(
        {
            "CURTO": _atributos(cruzamentos_restantes=1),
            "LONGO": _atributos(cruzamentos_restantes=3),
            "OUTRO": _atributos(cruzamentos_restantes=9),
        }
    )
    consultas = _Consultas()

    decidir([outro, curto, longo], tabela, PREFERE_ROTA_LONGA, construir_parametros(), consultas)

    assert consultas.chamadas == [(["CURTO", "LONGO"], "LONGO")]


@pytest.mark.parametrize(
    "disputas",
    [
        pytest.param(
            [
                _disputa("VIDA", FASE_ARTERIAL, criticidade=Criticidade.RISCO_VIDA),
                _disputa("URG", FASE_TRANSVERSAL, criticidade=Criticidade.URGENCIA),
            ],
            id="criticidade",
        ),
        pytest.param(
            [
                _disputa("EM_CURSO", FASE_ARTERIAL, ja_em_curso=True),
                _disputa("DESAFIANTE", FASE_TRANSVERSAL),
            ],
            id="guarda-de-oscilacao",
        ),
        pytest.param(
            [_disputa("A", FASE_ARTERIAL), _disputa("B", FASE_ARTERIAL)],
            id="mesma-fase",
        ),
        pytest.param([], id="sem-pedidos"),
    ],
)
def test_regra_que_decide_nao_conta_como_consulta(disputas: list[Disputa]) -> None:
    """O n de `context/07` §3.3.1 é o de decisões do modelo, e não das regras."""
    tabela = _Tabela({d.deteccao.id_veiculo: _atributos() for d in disputas})
    consultas = _Consultas()

    decidir(disputas, tabela, PREFERE_ROTA_LONGA, construir_parametros(), consultas)

    assert consultas.chamadas == []


def test_consulta_num_empate_traz_o_escolhido_pelo_e8() -> None:
    """No empate exato o escolhido é o do E8, e a consulta registra esse."""
    a = _disputa("A", FASE_ARTERIAL, eta_s=20.0)
    b = _disputa("B", FASE_TRANSVERSAL, eta_s=10.0)
    tabela = _Tabela({"A": _atributos(), "B": _atributos()})
    consultas = _Consultas()

    decidir([a, b], tabela, PREFERE_ROTA_LONGA, construir_parametros(), consultas)

    assert consultas.chamadas == [(["A", "B"], "B")]


def test_escolha_do_e8_e_a_chave_de_sempre_entre_os_candidatos() -> None:
    perto = _disputa("PERTO", FASE_ARTERIAL, eta_s=5.0)
    longe = _disputa("LONGE", FASE_TRANSVERSAL, eta_s=30.0)
    parametros = construir_parametros()

    concorda = ConsultaModelo(0.0, CRUZAMENTO, (perto, longe), perto)
    diverge = ConsultaModelo(0.0, CRUZAMENTO, (perto, longe), longe)

    assert concorda.escolha_do_e8(parametros) == perto
    assert not concorda.divergiu_do_e8(parametros)
    assert diverge.divergiu_do_e8(parametros)


def _motor_observado(
    topologia: TopologiaMalha, parametros: Parametros, pesos: PesosPolitica
) -> tuple[MotorDecisao, list[ConsultaModelo]]:
    consultas: list[ConsultaModelo] = []
    politica = PoliticaAprendida(pesos, topologia, parametros, observador=consultas.append)
    return MotorDecisao(parametros=parametros, topologia=topologia, politica=politica), consultas


def test_no_motor_a_consulta_diz_se_o_modelo_divergiu_do_e8(
    topologia: TopologiaMalha, parametros: Parametros
) -> None:
    """O mesmo cenário de `test_no_motor_o_modelo_troca_a_escolha_do_e8`.

    O E8 dá a transversal (menor ETA). Preferindo a rota longa, o modelo diverge;
    preferindo o menor ETA, concorda.
    """
    arterial = construir_ve("ART", TipoVeiculo.AMBULANCIA, n_vias=4, posicao_na_via_m=410.0)
    estado = construir_estado(topologia, veiculos=(arterial, _transversal()))

    motor, consultas = _motor_observado(topologia, parametros, PREFERE_ROTA_LONGA)
    motor.avaliar(estado)
    assert [(c.id_semaforo, c.escolhido.deteccao.id_veiculo) for c in consultas] == [
        (CRUZAMENTO, "ART")
    ]
    assert consultas[0].t == estado.t
    assert consultas[0].divergiu_do_e8(parametros)

    motor, consultas = _motor_observado(topologia, parametros, PREFERE_MENOR_ETA)
    motor.avaliar(estado)
    assert [c.escolhido.deteccao.id_veiculo for c in consultas] == ["TRV"]
    assert not consultas[0].divergiu_do_e8(parametros)


def test_no_motor_com_a_guarda_o_modelo_nao_e_consultado(
    topologia: TopologiaMalha, parametros: Parametros
) -> None:
    motor, consultas = _motor_observado(topologia, parametros, PREFERE_ROTA_CURTA)
    arterial = construir_ve("ART", TipoVeiculo.AMBULANCIA, n_vias=4, posicao_na_via_m=410.0)
    motor.avaliar(construir_estado(topologia, veiculos=(arterial,)))

    arterial = construir_ve("ART", TipoVeiculo.AMBULANCIA, n_vias=4, posicao_na_via_m=411.0)
    motor.avaliar(construir_estado(topologia, t=0.1, veiculos=(arterial, _transversal())))

    assert consultas == []


def test_observador_nao_muda_a_decisao(topologia: TopologiaMalha, parametros: Parametros) -> None:
    arterial = construir_ve("ART", TipoVeiculo.AMBULANCIA, n_vias=4, posicao_na_via_m=410.0)
    estado = construir_estado(topologia, veiculos=(arterial, _transversal()))
    observado, _ = _motor_observado(topologia, parametros, PREFERE_ROTA_LONGA)

    assert observado.avaliar(estado) == _motor(topologia, parametros, PREFERE_ROTA_LONGA).avaliar(
        estado
    )
