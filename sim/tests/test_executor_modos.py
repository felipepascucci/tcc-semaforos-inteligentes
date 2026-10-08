"""Os braços do experimento no executor — entrega 10.7 (P19).

O que se confere é a composição de cada braço: o `PREEMPCAO_ML` é o
`PREEMPCAO` com a política aprendida, e só ele tem política. É o que permite
atribuir a diferença medida em H4 à política (`context/10` §8). Só o último
teste, marcado `sumo`, sobe o simulador: o braço novo roda, mede o RNF01 e se
reproduz com a mesma seed.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from adapters.configuracao import carregar as carregar_parametros
from adapters.configuracao import carregar_politica
from app.models import ModoControle
from core.malha import TopologiaMalha
from core.priorizacao.conflito import EventoConflito
from core.priorizacao.politica import ConsultaModelo, PoliticaAprendida
from sim.controlador import executor
from sim.controlador.coletor import ResultadoExecucao

#: Malha vazia: a montagem do motor não a consulta.
TOPOLOGIA_VAZIA = TopologiaMalha(cruzamentos={})


def test_o_enum_do_banco_tem_os_mesmos_bracos_do_executor() -> None:
    """Um braço que o executor roda e o banco recusa só apareceria no lote."""
    assert [modo.value for modo in ModoControle] == list(executor.MODOS)
    assert executor.MODO_ML in executor.MODOS


def test_braco_ml_tem_os_parametros_do_preempcao() -> None:
    """Sem E7, como o baseline de H4: a política é a única diferença."""
    base = carregar_parametros("simulacao")
    assert base.n_ciclos_compensacao > 0

    ml = executor.parametros_do_modo(executor.MODO_ML, base)

    assert ml == executor.parametros_do_modo("PREEMPCAO", base)
    assert ml == replace(base, n_ciclos_compensacao=0)


@pytest.mark.parametrize("modo", ["FIXO", "PREEMPCAO", "PREEMPCAO_COMPENSADA"])
def test_so_o_braco_ml_tem_politica(modo: str) -> None:
    parametros = executor.parametros_do_modo(modo, carregar_parametros("simulacao"))
    motor = executor.montar_motor(modo, parametros, TOPOLOGIA_VAZIA, [], [])
    assert motor.politica is None


def test_braco_ml_usa_os_pesos_versionados_e_os_parametros_do_motor() -> None:
    parametros = executor.parametros_do_modo(executor.MODO_ML, carregar_parametros("simulacao"))
    conflitos: list[EventoConflito] = []
    consultas: list[ConsultaModelo] = []

    motor = executor.montar_motor(
        executor.MODO_ML, parametros, TOPOLOGIA_VAZIA, conflitos, consultas
    )

    politica = motor.politica
    assert isinstance(politica, PoliticaAprendida)
    assert politica.pesos == carregar_politica()
    assert politica.parametros is motor.parametros
    assert politica.topologia is motor.topologia
    assert politica.observador == consultas.append
    assert motor.observador_conflito == conflitos.append


@pytest.mark.parametrize(
    ("cenario", "esperado"),
    [("leve", 1), ("intenso", 1), ("multiplas_emergencias", 2), ("treino_multiplas", 2)],
)
def test_ves_simultaneos_le_as_duas_secoes_de_cenarios(cenario: str, esperado: int) -> None:
    assert executor.ves_simultaneos(cenario) == esperado


def test_ves_simultaneos_de_cenario_desconhecido_falha() -> None:
    with pytest.raises(ValueError, match="cenário desconhecido"):
        executor.ves_simultaneos("nao_existe")


# ---------------------------------------------------------------------------
# Ponta a ponta, com SUMO
# ---------------------------------------------------------------------------


@pytest.mark.sumo
def test_braco_ml_roda_mede_a_latencia_e_se_reproduz(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mesma seed, mesmo resultado, com o modelo consultado e o RNF01 medido.

    Seed 900, fora das reservadas. A primeira disputa abre em CRUZ_02 aos
    334,7 s, e nela os pesos treinados preferem o corredor, onde o E8 daria o VE
    de menor ETA; 400 s bastam para vê-la decidida pelo modelo.
    """
    monkeypatch.setattr(executor, "SAIDA", tmp_path / "saida")

    def rodar(pasta: str) -> ResultadoExecucao:
        return executor.executar(
            executor.Opcoes(
                cenario="multiplas_emergencias",
                modo=executor.MODO_ML,
                seed=900,
                duracao_s=400.0,
                persistir=False,
                diretorio_csv=tmp_path / pasta,
            )
        )

    primeira, segunda = rodar("a"), rodar("b")

    assert any(e.decidida_pelo_modelo and e.modelo_divergiu_do_e8 for e in primeira.conflitos)
    assert len(primeira.latencias_ms) == len(segunda.latencias_ms) == 4000
    assert primeira.latencia_p95_ms < 100.0
    assert primeira.violacoes == ()
    assert primeira.colisoes == primeira.teleportes == 0
    assert primeira.conflitos == segunda.conflitos
    assert primeira.transicoes == segunda.transicoes
    assert primeira.viagens_ve == segunda.viagens_ve
