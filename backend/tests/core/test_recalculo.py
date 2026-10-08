"""RF07 — a priorização é recalculada quando a rota do VE muda (`context/06` §2).

O motor não guarda a rota de ninguém: a cada passo, E1 e E2 refazem a lista de
cruzamentos a partir das vias que o `EstadoMalha` diz que faltam ao VE. Então
"recalcular" não é um caminho especial do código, é a mesma conta sobre a rota
nova. Estes testes fixam o que isso tem de produzir, numa bifurcação:

    E0 ──► CRUZ_A ──E1──► CRUZ_B ──E2──►
              │
              S1
              ▼
           CRUZ_C ──S2──►

Rota antiga: segue em frente (`E0, E1, E2`). Rota nova: vira em `CRUZ_A`
(`E0, S1, S2`). Malha artificial, sem SUMO, com os parâmetros do perfil de
simulação (`conftest.construir_parametros`).
"""

from __future__ import annotations

from dataclasses import replace

from core.comandos import Comando, TipoComando
from core.malha import Cruzamento, Fase, TopologiaMalha
from core.modelos import EstadoMalha, EstadoSemaforo, Sinal, VeiculoEmergencia
from core.parametros import Parametros
from core.priorizacao.deteccao import detectar
from core.priorizacao.motor import MotorDecisao
from tests.core.conftest import construir_parametros, construir_ve

COMPRIMENTO_M = 200.0

#: Fases: em frente, conversão e transversal em `CRUZ_A`; corredor e
#: transversal em `CRUZ_B` e `CRUZ_C`.
EM_FRENTE, CONVERSAO, TRANSVERSAL_A = 1, 2, 3
CORREDOR, TRANSVERSAL = 1, 2

ROTA_ANTIGA = ("E0", "E1", "E2")
ROTA_NOVA = ("E0", "S1", "S2")


def _fase(indice: int, *movimentos: tuple[str, str]) -> Fase:
    return Fase(
        indice=indice,
        descricao=f"FASE_TESTE_{indice}",
        movimentos=frozenset(movimentos),
        duracao_base_s=30.0,
        verde_min_s=7.0,
        verde_max_s=60.0,
    )


def _bifurcacao() -> TopologiaMalha:
    cruzamentos = {
        "CRUZ_A": Cruzamento(
            id="CRUZ_A",
            fases=(
                _fase(EM_FRENTE, ("E0", "E1")),
                _fase(CONVERSAO, ("E0", "S1")),
                _fase(TRANSVERSAL_A, ("TA_IN", "TA_OUT")),
            ),
        ),
        "CRUZ_B": Cruzamento(
            id="CRUZ_B",
            fases=(_fase(CORREDOR, ("E1", "E2")), _fase(TRANSVERSAL, ("TB_IN", "TB_OUT"))),
        ),
        "CRUZ_C": Cruzamento(
            id="CRUZ_C",
            fases=(_fase(CORREDOR, ("S1", "S2")), _fase(TRANSVERSAL, ("TC_IN", "TC_OUT"))),
        ),
    }
    vias = ("E0", "E1", "E2", "S1", "S2", "TA_IN", "TA_OUT", "TB_IN", "TB_OUT", "TC_IN", "TC_OUT")
    return TopologiaMalha(
        cruzamentos=cruzamentos,
        comprimento_via_m=dict.fromkeys(vias, COMPRIMENTO_M),
        cruzamento_apos_via={
            "E0": "CRUZ_A",
            "TA_IN": "CRUZ_A",
            "E1": "CRUZ_B",
            "TB_IN": "CRUZ_B",
            "S1": "CRUZ_C",
            "TC_IN": "CRUZ_C",
        },
        faixas_por_via=dict.fromkeys(vias, 1),
    )


TOPOLOGIA = _bifurcacao()


def _ve(rota: tuple[str, ...], faltam_m: float = 80.0) -> VeiculoEmergencia:
    """O VE na via `E0`, a `faltam_m` da linha de retenção de `CRUZ_A`."""
    return replace(construir_ve(posicao_na_via_m=COMPRIMENTO_M - faltam_m), rota=rota)


def _estado(t: float, ve: VeiculoEmergencia) -> EstadoMalha:
    """Todos os cruzamentos no verde da transversal, já acima do verde mínimo."""
    semaforos = {
        id_cruzamento: EstadoSemaforo(
            id=id_cruzamento,
            fase_atual=cruzamento.fases[-1].indice,
            tempo_na_fase=20.0,
            fila_por_acesso=dict.fromkeys(cruzamento.acessos(), 0),
            sinal=Sinal.VERDE,
        )
        for id_cruzamento, cruzamento in TOPOLOGIA.cruzamentos.items()
    }
    return EstadoMalha(t=t, semaforos=semaforos, veiculos_emergencia=(ve,))


def _por_cruzamento(comandos: list[Comando]) -> dict[str, Comando]:
    return {comando.id_semaforo: comando for comando in comandos}


# ---------------------------------------------------------------------------
# E1 e E2: os cruzamentos-alvo vêm da rota que falta
# ---------------------------------------------------------------------------


def test_rota_nova_troca_os_cruzamentos_alvo() -> None:
    """O critério do RF07: novo conjunto de TLS depois da mudança de rota."""
    parametros = construir_parametros()

    antes = detectar(TOPOLOGIA, _ve(ROTA_ANTIGA), parametros)
    depois = detectar(TOPOLOGIA, _ve(ROTA_NOVA), parametros)

    assert [d.id_semaforo for d in antes] == ["CRUZ_A", "CRUZ_B"]
    assert [d.id_semaforo for d in depois] == ["CRUZ_A", "CRUZ_C"]


def test_no_cruzamento_que_continua_na_rota_o_movimento_muda() -> None:
    """Em `CRUZ_A` o VE agora vira: o movimento pedido é outro, logo a fase também."""
    parametros = construir_parametros()

    antes = detectar(TOPOLOGIA, _ve(ROTA_ANTIGA), parametros)[0]
    depois = detectar(TOPOLOGIA, _ve(ROTA_NOVA), parametros)[0]

    assert (antes.id_semaforo, antes.movimento) == ("CRUZ_A", ("E0", "E1"))
    assert (depois.id_semaforo, depois.movimento) == ("CRUZ_A", ("E0", "S1"))
    assert antes.distancia_m == depois.distancia_m  # a posição não mudou, só a rota


# ---------------------------------------------------------------------------
# O motor: o que sai da rota é liberado, o que entra é preemptado
# ---------------------------------------------------------------------------


def _motor(parametros: Parametros) -> MotorDecisao:
    return MotorDecisao(topologia=TOPOLOGIA, parametros=parametros)


def test_motor_recalcula_a_priorizacao_no_passo_seguinte_a_mudanca() -> None:
    """Rota antiga preempta A (em frente) e B; a nova troca a fase de A, solta B e pega C.

    A margem de antecipação é aumentada só para os dois cruzamentos da rota
    caberem na janela de E3 ao mesmo tempo; o que se testa é o recálculo, não a
    janela. Sem compensação (o braço `PREEMPCAO`), soltar é `LIBERAR`; com ela,
    seria `COMPENSAR`, que solta do mesmo jeito.
    """
    parametros = construir_parametros(tempo_antecipacao_margem_s=30.0, n_ciclos_compensacao=0)
    motor = _motor(parametros)

    passo_1 = _por_cruzamento(motor.avaliar(_estado(0.0, _ve(ROTA_ANTIGA))))
    assert set(passo_1) == {"CRUZ_A", "CRUZ_B"}
    assert (passo_1["CRUZ_A"].tipo, passo_1["CRUZ_A"].fase_alvo) == (
        TipoComando.IR_PARA_FASE,
        EM_FRENTE,
    )
    assert (passo_1["CRUZ_B"].tipo, passo_1["CRUZ_B"].fase_alvo) == (
        TipoComando.IR_PARA_FASE,
        CORREDOR,
    )

    passo_2 = _por_cruzamento(motor.avaliar(_estado(1.0, _ve(ROTA_NOVA))))
    assert set(passo_2) == {"CRUZ_A", "CRUZ_B", "CRUZ_C"}
    assert (passo_2["CRUZ_A"].tipo, passo_2["CRUZ_A"].fase_alvo) == (
        TipoComando.IR_PARA_FASE,
        CONVERSAO,
    )
    assert passo_2["CRUZ_B"].tipo is TipoComando.LIBERAR
    assert (passo_2["CRUZ_C"].tipo, passo_2["CRUZ_C"].fase_alvo) == (
        TipoComando.IR_PARA_FASE,
        CORREDOR,
    )
    assert {comando.id_veiculo for comando in passo_2.values()} == {"VE_TESTE"}


def test_cruzamento_que_saiu_da_rota_nao_fica_preso_ao_ve() -> None:
    """Depois de liberado, `CRUZ_B` não volta a ser pedido pela rota nova."""
    parametros = construir_parametros(tempo_antecipacao_margem_s=30.0, n_ciclos_compensacao=0)
    motor = _motor(parametros)
    motor.avaliar(_estado(0.0, _ve(ROTA_ANTIGA)))
    motor.avaliar(_estado(1.0, _ve(ROTA_NOVA)))

    passo_3 = _por_cruzamento(motor.avaliar(_estado(2.0, _ve(ROTA_NOVA))))

    assert motor.preempcao_ativa("CRUZ_B") is None
    assert "CRUZ_B" not in passo_3
    assert motor.preempcao_ativa("CRUZ_C") is not None


def test_mesma_rota_de_volta_recalcula_de_novo() -> None:
    """O recálculo não depende de sentido: voltar à rota antiga refaz a conta antiga."""
    parametros = construir_parametros(tempo_antecipacao_margem_s=30.0, n_ciclos_compensacao=0)
    motor = _motor(parametros)
    motor.avaliar(_estado(0.0, _ve(ROTA_ANTIGA)))
    motor.avaliar(_estado(1.0, _ve(ROTA_NOVA)))

    passo_3 = _por_cruzamento(motor.avaliar(_estado(2.0, _ve(ROTA_ANTIGA))))

    assert passo_3["CRUZ_A"].fase_alvo == EM_FRENTE
    assert passo_3["CRUZ_C"].tipo is TipoComando.LIBERAR
    assert passo_3["CRUZ_B"].fase_alvo == CORREDOR
