"""Critérios de descarte de execução — `context/06` §4.

O ponto destes testes: o critério que reprova uma execução precisa estar em
código versionado e testado, **antes** de os dados existirem. Descarte com
critério pré-definido é metodologia; descarte decidido depois de ver o resultado
é o contrário disso.

Puro — não roda SUMO, não escreve arquivo.
"""

from __future__ import annotations

from pathlib import Path

from adapters.configuracao import carregar as carregar_parametros
from core.modelos import Sinal, Transicao
from core.seguranca import Violacao
from sim.controlador.coletor import ColetorMetricas, ResultadoExecucao, ViagemVE, percentil
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


def test_aquecimento_fica_fora_das_medias(tmp_path: Path) -> None:
    """A malha começa vazia; o transiente de enchimento não é o regime medido.

    Quem parte nos primeiros minutos trafega numa via mais livre do que a que o
    cenário descreve. Incluí-lo puxa a espera transversal para baixo — e a
    espera transversal é justamente a evidência de H2, então o custo que a
    compensação existe para mitigar apareceria menor do que é.

    O descarte usa a mesma janela de `aquecimento_s` que `gerar_rotas.py` usa
    para soltar o primeiro VE, de modo que nenhum VE cai nele.
    """
    tripinfo = tmp_path / "tripinfo.xml"
    tripinfo.write_text(
        """<tripinfos>
    <tripinfo id="T1_SUL_0001" vType="carro" depart="10.00" duration="60.00"
              waitingTime="0.00" waitingCount="0" timeLoss="1.00" routeLength="900.00"/>
    <tripinfo id="T1_SUL_0002" vType="carro" depart="400.00" duration="90.00"
              waitingTime="30.00" waitingCount="1" timeLoss="31.00" routeLength="900.00"/>
    <tripinfo id="VE_ROTA_VE_CORREDOR_00" vType="ambulancia" depart="300.00" duration="240.00"
              waitingTime="0.00" waitingCount="0" timeLoss="12.00" routeLength="4500.00"/>
</tripinfos>
""",
        encoding="utf-8",
    )

    coletor = ColetorMetricas(cenario="moderado", modo="PREEMPCAO", seed=1)
    com_descarte = coletor.consolidar(
        tripinfo, duracao_s=3600.0, veiculos_planejados=3, aquecimento_s=300.0
    )
    sem_descarte = coletor.consolidar(tripinfo, duracao_s=3600.0, veiculos_planejados=3)

    # O carro do aquecimento (espera 0) diluiria a média pela metade.
    assert com_descarte.tempo_espera_medio_transversal_s == 30.0
    assert sem_descarte.tempo_espera_medio_transversal_s == 15.0

    # O VE parte no fim do aquecimento e continua contando.
    assert len(com_descarte.viagens_ve) == 1

    # `veiculos_completos` não é métrica de desempenho: conta todos.
    assert com_descarte.veiculos_completos == 3

    # E a janela usada fica registrada, para a análise saber o que foi descartado.
    assert com_descarte.aquecimento_s == 300.0


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
