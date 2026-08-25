"""O motor de decisão de ponta a ponta — E1 a E8 juntos."""

from __future__ import annotations

import pytest

from core.comandos import TipoComando
from core.malha import TopologiaMalha
from core.modelos import EstadoMalha, EstadoSemaforo, Sinal, TipoVeiculo
from core.parametros import Parametros
from core.priorizacao.motor import MotorDecisao
from tests.core.conftest import (
    FASE_ARTERIAL,
    FASE_TRANSVERSAL,
    construir_estado,
    construir_parametros,
    construir_topologia,
    construir_ve,
)


@pytest.fixture
def motor(topologia: TopologiaMalha, parametros: Parametros) -> MotorDecisao:
    return MotorDecisao(parametros=parametros, topologia=topologia)


# ---------------------------------------------------------------------------
# Quando não há nada a fazer
# ---------------------------------------------------------------------------


def test_sem_ve_nao_emite_comando(motor: MotorDecisao, topologia: TopologiaMalha) -> None:
    """O caso mais comum da simulação, e o mais barato."""
    assert motor.avaliar(construir_estado(topologia)) == []


def test_ve_longe_demais_nao_dispara_preempcao(
    motor: MotorDecisao, topologia: TopologiaMalha
) -> None:
    """E3: preemptar cedo trava a transversal de graça — o custo que H2 mede."""
    # 490 m do primeiro cruzamento a 10 m/s: ETA de 49 s, muito além da janela.
    longe = construir_ve(n_vias=4, posicao_na_via_m=10.0, velocidade=10.0)
    assert motor.avaliar(construir_estado(topologia, veiculos=(longe,))) == []


# ---------------------------------------------------------------------------
# Preempção
# ---------------------------------------------------------------------------


def test_ve_na_janela_dispara_transicao_para_a_fase_arterial(
    motor: MotorDecisao, topologia: TopologiaMalha
) -> None:
    """E1 → E2 → E3 → E4 → E5, com o cruzamento servindo a transversal."""
    # 90 m a 10 m/s: ETA de 9 s, dentro da janela de 10 s.
    chegando = construir_ve(n_vias=4, posicao_na_via_m=410.0, velocidade=10.0)
    estado = construir_estado(topologia, veiculos=(chegando,), fase_atual=FASE_TRANSVERSAL)

    comandos = motor.avaliar(estado)

    primeiro = next(c for c in comandos if c.id_semaforo == "CRUZ_TESTE_1")
    assert primeiro.tipo is TipoComando.IR_PARA_FASE
    assert primeiro.fase_alvo == FASE_ARTERIAL
    assert primeiro.id_veiculo == "VE_TESTE"


def test_fase_certa_ja_verde_gera_extensao_e_nao_nova_transicao(
    motor: MotorDecisao, topologia: TopologiaMalha
) -> None:
    """Fase alvo já verde vira extensão, não nova transição.

    `se fase_atual == fase_alvo: estender` — reiniciar a transição custaria um
    amarelo e um all-red desnecessários bem na frente do VE.
    """
    chegando = construir_ve(n_vias=4, posicao_na_via_m=410.0, velocidade=10.0)
    estado = construir_estado(
        topologia, veiculos=(chegando,), fase_atual=FASE_ARTERIAL, sinal=Sinal.VERDE
    )

    comando = next(c for c in motor.avaliar(estado) if c.id_semaforo == "CRUZ_TESTE_1")

    assert comando.tipo is TipoComando.ESTENDER_VERDE
    assert comando.duracao_s is not None
    assert comando.duracao_s <= 60.0  # verde_max_s


def test_todo_comando_traz_justificativa(motor: MotorDecisao, topologia: TopologiaMalha) -> None:
    """Um log de decisão sem justificativa não sustenta uma defesa (`context/01` §9)."""
    chegando = construir_ve(n_vias=4, posicao_na_via_m=410.0, velocidade=10.0)
    comandos = motor.avaliar(construir_estado(topologia, veiculos=(chegando,)))

    assert comandos
    for comando in comandos:
        assert comando.motivo.strip(), f"comando sem motivo: {comando}"


# ---------------------------------------------------------------------------
# Liberação e compensação — os dois braços do experimento
# ---------------------------------------------------------------------------


def _preemptar_e_soltar(motor: MotorDecisao, topologia: TopologiaMalha) -> list:
    chegando = construir_ve(n_vias=4, posicao_na_via_m=410.0, velocidade=10.0)
    motor.avaliar(construir_estado(topologia, t=0.0, veiculos=(chegando,)))
    # O VE atravessou e saiu do estado.
    return motor.avaliar(construir_estado(topologia, t=20.0, veiculos=(), fila=6))


def test_braco_com_compensacao_emite_compensar(topologia: TopologiaMalha) -> None:
    """`PREEMPCAO_COMPENSADA` — o braço que sustenta H2."""
    motor = MotorDecisao(construir_parametros(n_ciclos_compensacao=2), topologia)
    comandos = _preemptar_e_soltar(motor, topologia)

    comando = next(c for c in comandos if c.id_semaforo == "CRUZ_TESTE_1")
    assert comando.tipo is TipoComando.COMPENSAR
    assert motor.plano_de_compensacao("CRUZ_TESTE_1") is not None


def test_braco_sem_compensacao_emite_apenas_liberar(topologia: TopologiaMalha) -> None:
    """`PREEMPCAO` — isola o efeito de E7 e sai do mesmo código.

    Comparar apenas fixo contra compensado não permitiria afirmar nada sobre H2
    (`context/04` §6).
    """
    motor = MotorDecisao(construir_parametros(n_ciclos_compensacao=0), topologia)
    comandos = _preemptar_e_soltar(motor, topologia)

    comando = next(c for c in comandos if c.id_semaforo == "CRUZ_TESTE_1")
    assert comando.tipo is TipoComando.LIBERAR
    assert motor.plano_de_compensacao("CRUZ_TESTE_1") is None


def test_preempcao_expira_no_timeout(motor: MotorDecisao, topologia: TopologiaMalha) -> None:
    """E6 — um VE que travou não segura a transversal indefinidamente.

    O veículo entra na janela normalmente, a preempção começa, e então ele
    **para de andar**: continua no mesmo ponto da rota indefinidamente. Sem o
    timeout, o cruzamento ficaria preso ao corredor verde para sempre.
    """
    travado = construir_ve(n_vias=4, posicao_na_via_m=410.0, velocidade=10.0)
    motor.avaliar(construir_estado(topologia, t=0.0, veiculos=(travado,)))
    assert motor.preempcao_ativa("CRUZ_TESTE_1") is not None

    comandos = motor.avaliar(construir_estado(topologia, t=50.0, veiculos=(travado,)))

    comando = next(c for c in comandos if c.id_semaforo == "CRUZ_TESTE_1")
    assert comando.tipo in {TipoComando.LIBERAR, TipoComando.COMPENSAR}
    assert "timeout" in comando.motivo
    assert motor.preempcao_ativa("CRUZ_TESTE_1") is None


# ---------------------------------------------------------------------------
# I5 — starvation é responsabilidade do motor (contrato §9)
# ---------------------------------------------------------------------------


def test_motor_cede_a_vez_quando_uma_fase_esta_em_starvation(
    topologia: TopologiaMalha,
) -> None:
    """Segurança viária é invariante, não requisito negociável.

    Reter o corredor verde mais um pouco custa segundos ao VE; deixar uma
    transversal parada por dois minutos é o que I5 existe para impedir.
    """
    parametros = construir_parametros(vermelho_max_s=120.0)
    motor = MotorDecisao(parametros, topologia)

    # Cruzamento preso na arterial; a transversal não vê verde desde t=0.
    chegando = construir_ve(n_vias=4, posicao_na_via_m=410.0, velocidade=10.0)
    estado_tardio = EstadoMalha(
        t=118.0,
        semaforos={
            "CRUZ_TESTE_1": EstadoSemaforo(
                id="CRUZ_TESTE_1",
                fase_atual=FASE_ARTERIAL,
                tempo_na_fase=40.0,
                sinal=Sinal.VERDE,
            )
        },
        veiculos_emergencia=(chegando,),
    )
    motor._ultimo_verde["CRUZ_TESTE_1"] = {FASE_ARTERIAL: 118.0, FASE_TRANSVERSAL: 0.0}

    # O VE quer justamente a arterial — mas estender agora mataria a transversal.
    assert motor.avaliar(estado_tardio) == []


def test_starvation_nao_impede_preemptar_para_a_propria_fase_faminta(
    topologia: TopologiaMalha,
) -> None:
    """A guarda de I5 não pode ser cega.

    Se a fase que o VE pede é justamente a que está passando fome, preemptar
    para ela **resolve** a starvation em vez de agravá-la. Bloquear aí seria
    penalizar o VE por um problema que ele viria a corrigir.
    """
    motor = MotorDecisao(construir_parametros(vermelho_max_s=120.0), topologia)
    chegando = construir_ve(n_vias=4, posicao_na_via_m=410.0, velocidade=10.0)
    estado = EstadoMalha(
        t=118.0,
        semaforos={
            "CRUZ_TESTE_1": EstadoSemaforo(
                id="CRUZ_TESTE_1",
                fase_atual=FASE_TRANSVERSAL,
                tempo_na_fase=40.0,
                sinal=Sinal.VERDE,
            )
        },
        veiculos_emergencia=(chegando,),
    )
    motor._ultimo_verde["CRUZ_TESTE_1"] = {FASE_ARTERIAL: 0.0, FASE_TRANSVERSAL: 118.0}

    comandos = motor.avaliar(estado)

    assert [c.fase_alvo for c in comandos if c.tipo is TipoComando.IR_PARA_FASE] == [FASE_ARTERIAL]


# ---------------------------------------------------------------------------
# Conflito entre VEs
# ---------------------------------------------------------------------------


def test_dois_ves_conflitantes_geram_um_unico_comando_no_cruzamento(
    motor: MotorDecisao, topologia: TopologiaMalha
) -> None:
    """E8: nunca conceder as duas fases. Um espera."""
    ambulancia = construir_ve(
        "AMB", TipoVeiculo.AMBULANCIA, n_vias=4, posicao_na_via_m=410.0, velocidade=10.0
    )
    # Um segundo VE, pela transversal do mesmo cruzamento.
    from core.modelos import VeiculoEmergencia

    bombeiro = VeiculoEmergencia(
        id="BMB",
        tipo=TipoVeiculo.BOMBEIRO,
        posicao=(0.0, 0.0),
        velocidade=10.0,
        rota=("T1_IN", "T1_OUT"),
        indice_via_atual=0,
        posicao_na_via_m=410.0,
    )

    comandos = motor.avaliar(
        construir_estado(topologia, veiculos=(ambulancia, bombeiro), fase_atual=FASE_TRANSVERSAL)
    )

    do_cruzamento = [c for c in comandos if c.id_semaforo == "CRUZ_TESTE_1"]
    assert len(do_cruzamento) == 1
    assert do_cruzamento[0].id_veiculo == "AMB"  # ambulância tem precedência


# ---------------------------------------------------------------------------
# Corredor verde e reprodutibilidade
# ---------------------------------------------------------------------------


def test_corredor_verde_atinge_todos_os_cruzamentos_da_rota() -> None:
    """RF03 em miniatura: o VE percorre a arterial e cada cruzamento é servido.

    É o efeito de coordenação que dá sentido ao trabalho — com um cruzamento só
    não haveria corredor a medir (`context/04` §3).
    """
    topologia = construir_topologia(n_cruzamentos=3)
    motor = MotorDecisao(construir_parametros(), topologia)

    servidos: set[str] = set()
    t, percorrido = 0.0, 0.0
    while t <= 200.0:
        via, posicao = divmod(percorrido, 500.0)
        indice = min(int(via), 3)
        veiculo = construir_ve(n_vias=4, indice_via_atual=indice, posicao_na_via_m=posicao)
        for comando in motor.avaliar(
            construir_estado(topologia, t=t, veiculos=(veiculo,), fase_atual=FASE_TRANSVERSAL)
        ):
            if comando.fase_alvo == FASE_ARTERIAL or comando.tipo is TipoComando.ESTENDER_VERDE:
                servidos.add(comando.id_semaforo)
        t += 0.5
        percorrido += 5.0  # 10 m/s

    assert servidos == {"CRUZ_TESTE_1", "CRUZ_TESTE_2", "CRUZ_TESTE_3"}


def test_mesma_sequencia_de_estados_produz_os_mesmos_comandos(
    topologia: TopologiaMalha,
) -> None:
    """Reprodutibilidade: a regra de ouro do `CLAUDE.md`.

    O motor guarda estado entre chamadas, então determinismo não é automático —
    precisa ser verificado.
    """
    estados = [
        construir_estado(
            topologia,
            t=t / 2,
            veiculos=(construir_ve(n_vias=4, posicao_na_via_m=400.0 + t, velocidade=10.0),),
        )
        for t in range(40)
    ]

    def rodar() -> list[tuple[str, str, int | None]]:
        motor = MotorDecisao(construir_parametros(), topologia)
        return [
            (c.id_semaforo, c.tipo.value, c.fase_alvo)
            for estado in estados
            for c in motor.avaliar(estado)
        ]

    primeira_execucao = rodar()
    segunda_execucao = rodar()

    assert primeira_execucao == segunda_execucao
    assert primeira_execucao, "a sequência precisa produzir comandos, senão nada é comparado"


def test_abortar_devolve_fallback_e_limpa_o_estado(
    motor: MotorDecisao, topologia: TopologiaMalha
) -> None:
    """Fail-safe diante de invariante violado (`context/01` §6)."""
    chegando = construir_ve(n_vias=4, posicao_na_via_m=410.0, velocidade=10.0)
    motor.avaliar(construir_estado(topologia, veiculos=(chegando,)))
    assert motor.preempcao_ativa("CRUZ_TESTE_1") is not None

    comando = motor.abortar("CRUZ_TESTE_1", motivo="I1 violado em CRUZ_TESTE_1")

    assert comando.tipo is TipoComando.FALLBACK_SEGURO
    assert motor.preempcao_ativa("CRUZ_TESTE_1") is None
    assert motor.plano_de_compensacao("CRUZ_TESTE_1") is None
