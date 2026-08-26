"""Critérios de descarte de execução — `context/06` §4.

O ponto destes testes: o critério que reprova uma execução precisa estar em
código versionado e testado, **antes** de os dados existirem. Descarte com
critério pré-definido é metodologia; descarte decidido depois de ver o resultado
é o contrário disso.

Puro — não roda SUMO, não escreve arquivo.
"""

from __future__ import annotations

from adapters.configuracao import carregar as carregar_parametros
from core.modelos import Sinal, Transicao
from core.seguranca import Violacao
from sim.controlador.coletor import ResultadoExecucao, ViagemVE, percentil
from sim.validacao.execucao import validar_execucao

#: Os parâmetros reais do perfil de simulação — testar contra outros tornaria o
#: teste um espelho de si mesmo.
PARAMETROS = carregar_parametros("simulacao")


def _resultado(**sobrescritas: object) -> ResultadoExecucao:
    """Uma execução perfeita, para ser estragada um campo por vez."""
    base: dict[str, object] = {
        "cenario": "moderado",
        "modo": "PREEMPCAO",
        "seed": 1,
        "duracao_s": 3600.0,
        "viagens_ve": (
            ViagemVE("VE_0", "ambulancia", 240.0, 0.0, 0, 18.5, 12.0),
            ViagemVE("VE_1", "bombeiro", 250.0, 0.0, 0, 18.0, 14.0),
        ),
        "veiculos_planejados": 100,
        "veiculos_completos": 98,
        "latencias_ms": (0.02, 0.03, 0.05),
    }
    base.update(sobrescritas)
    return ResultadoExecucao(**base)  # type: ignore[arg-type]


def test_execucao_limpa_passa() -> None:
    assert validar_execucao(_resultado(), PARAMETROS, ves_planejados=2) == []


def test_colisao_reprova() -> None:
    """O pré-projeto afirma zero colisões; afirmar exige verificar."""
    problemas = validar_execucao(_resultado(colisoes=1), PARAMETROS)
    assert any("colis" in problema for problema in problemas)


def test_teleporte_reprova_porque_significa_gridlock() -> None:
    """Com `time-to-teleport = -1`, teleporte não deveria existir."""
    problemas = validar_execucao(_resultado(teleportes=3), PARAMETROS)
    assert any("gridlock" in problema for problema in problemas)


def test_violacao_de_invariante_reprova_e_diz_qual() -> None:
    violacoes = (
        Violacao("I1", "CRUZ_01", 12.0, "fases conflitantes"),
        Violacao("I4", "CRUZ_02", 30.0, "verde truncado"),
    )
    problemas = validar_execucao(_resultado(violacoes=violacoes), PARAMETROS)

    assert len(problemas) == 1
    assert "I1=1" in problemas[0] and "I4=1" in problemas[0]


def test_latencia_acima_do_orcamento_reprova() -> None:
    """RNF01 é sobre o percentil, não sobre a média (context/04 §9.3)."""
    # 10% de decisões lentas: média de ~16 ms (dentro), p95 de 150 ms (fora).
    lentas = tuple([1.0] * 90 + [150.0] * 10)
    problemas = validar_execucao(_resultado(latencias_ms=lentas), PARAMETROS)

    assert any("p95" in problema for problema in problemas)


def test_ve_que_nao_chegou_reprova_a_execucao() -> None:
    """Um VE que não completa a rota enviesaria a média para baixo."""
    problemas = validar_execucao(_resultado(), PARAMETROS, ves_planejados=5)
    assert any("VEs completaram" in problema for problema in problemas)


def test_execucao_incompleta_nao_cobra_os_ves() -> None:
    """Numa execução deliberadamente curta, VE em trânsito é esperado."""
    problemas = validar_execucao(_resultado(), PARAMETROS, ves_planejados=5, completa=False)
    assert problemas == []


def test_percentil_devolve_valor_observado() -> None:
    """Posto mais próximo, sem interpolação: o número aconteceu de verdade."""
    amostras = [1.0, 2.0, 3.0, 4.0, 100.0]

    assert percentil(amostras, 95) == 100.0
    assert percentil(amostras, 50) == 3.0
    assert percentil([], 95) == 0.0


def test_transicao_e_o_que_vai_para_o_banco() -> None:
    """P5: uma linha por troca de fase, com o que I2/I3/I4 precisam."""
    transicao = Transicao(
        id_semaforo="CRUZ_01",
        t=33.0,
        fase=1,
        sinal=Sinal.AMARELO,
        fase_anterior=1,
        duracao_fase_anterior_s=30.0,
        em_preempcao=False,
    )
    resultado = _resultado(transicoes=(transicao,))

    assert resultado.transicoes[0].duracao_fase_anterior_s == 30.0
