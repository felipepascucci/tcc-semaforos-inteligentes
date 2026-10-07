"""O motor de decisão de ponta a ponta — E1 a E8 juntos."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pytest

from core.comandos import TipoComando
from core.malha import TopologiaMalha
from core.modelos import EstadoMalha, EstadoSemaforo, Sinal, TipoVeiculo, VeiculoEmergencia
from core.parametros import Parametros
from core.priorizacao.conflito import Disputa, EventoConflito
from core.priorizacao.motor import MotorDecisao
from tests.core.conftest import (
    CRITICIDADE_TIPICA,
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


def test_fila_a_frente_faz_o_motor_preemptar_mais_cedo(
    motor: MotorDecisao, topologia: TopologiaMalha
) -> None:
    """**Regressão de P16**, no motor inteiro e não só em E3.

    Mesma seed, mesmo VE, mesma distância — muda só a fila no acesso de entrada.
    Com a via livre o motor espera, porque abrir o verde 20 s antes travaria a
    transversal sem necessidade. Com seis veículos parados à frente, esperar
    faria o VE chegar ao verde com a fila ainda escoando, que é exatamente o que
    o piloto do Bloco 4 mediu como 2,76 paradas residuais no cenário `intenso`.

    O comando tem de sair para a fase **arterial**, e não para a que já está
    verde: antecipar sem trocar de fase não serviria o VE.
    """
    # 200 m do primeiro cruzamento a 10 m/s: ETA de 20 s, o dobro da janela sem fila.
    chegando = construir_ve(n_vias=4, posicao_na_via_m=300.0, velocidade=10.0)

    livre = construir_estado(topologia, veiculos=(chegando,), fase_atual=FASE_TRANSVERSAL, fila=0)
    assert motor.avaliar(livre) == []

    # `fila` do construtor é por acesso, e a topologia de teste tem uma faixa.
    congestionado = construir_estado(
        topologia, veiculos=(chegando,), fase_atual=FASE_TRANSVERSAL, fila=6
    )
    comandos = MotorDecisao(parametros=motor.parametros, topologia=topologia).avaliar(congestionado)

    do_primeiro = [c for c in comandos if c.id_semaforo == "CRUZ_TESTE_1"]
    assert len(do_primeiro) == 1
    assert do_primeiro[0].tipo is TipoComando.IR_PARA_FASE
    assert do_primeiro[0].fase_alvo == FASE_ARTERIAL


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


def test_compensacao_estende_de_fato_o_verde_das_fases(topologia: TopologiaMalha) -> None:
    """E7 precisa **agir**, não só calcular o plano.

    Este teste existe por causa de um defeito encontrado na primeira execução do
    Bloco 3: o motor calculava `PlanoCompensacao`, guardava, e nada nunca o
    aplicava. Os braços `PREEMPCAO` e `PREEMPCAO_COMPENSADA` saíam com
    resultados idênticos até o último dígito — E7 era um no-op e H2 não tinha
    mecanismo nenhum por trás.

    O que se verifica aqui é o efeito observável: enquanto a compensação vigora,
    cada fase que abre recebe `ESTENDER_VERDE` com o restante da duração
    planejada, e o comando sai **sem** `id_veiculo` — compensar não é preemptar.
    """
    motor = MotorDecisao(construir_parametros(n_ciclos_compensacao=2), topologia)
    _preemptar_e_soltar(motor, topologia)

    plano = motor.plano_de_compensacao("CRUZ_TESTE_1")
    assert plano is not None
    planejada = plano.duracao_por_fase_s[FASE_ARTERIAL]
    assert planejada > 30.0, "sem fila em nenhuma fase, o teste não prova nada"

    # Cruzamento servindo a fase arterial, 5 s de verde cumpridos.
    estado = construir_estado(
        topologia, t=30.0, veiculos=(), fase_atual=FASE_ARTERIAL, tempo_na_fase=5.0, fila=6
    )
    comando = next(c for c in motor.avaliar(estado) if c.id_semaforo == "CRUZ_TESTE_1")

    assert comando.tipo is TipoComando.ESTENDER_VERDE
    assert comando.duracao_s == pytest.approx(planejada - 5.0)
    assert comando.id_veiculo is None
    assert "compensação E7" in comando.motivo


def test_compensacao_termina_apos_os_ciclos_previstos(topologia: TopologiaMalha) -> None:
    """A compensação é transitória: `n_ciclos_compensacao` e acabou.

    Sem o encerramento, o cruzamento ficaria para sempre com o verde inflado
    pela fila de um evento que já passou — o que degradaria a via principal em
    vez de recuperar a transversal.
    """
    motor = MotorDecisao(construir_parametros(n_ciclos_compensacao=1), topologia)
    _preemptar_e_soltar(motor, topologia)

    # Uma fase de cada vez, alternando: com 2 fases e 1 ciclo, o plano rege dois
    # verdes e expira no terceiro.
    instante = 30.0
    for fase in (FASE_ARTERIAL, FASE_TRANSVERSAL, FASE_ARTERIAL):
        estado = construir_estado(
            topologia, t=instante, veiculos=(), fase_atual=fase, tempo_na_fase=1.0, fila=6
        )
        comandos = [c for c in motor.avaliar(estado) if c.id_semaforo == "CRUZ_TESTE_1"]
        instante += 40.0

    assert comandos == []
    assert motor.plano_de_compensacao("CRUZ_TESTE_1") is None


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


def test_ocorrencia_encerrada_no_meio_da_preempcao_libera_o_cruzamento(
    topologia: TopologiaMalha,
) -> None:
    """P20 — a central encerra a ocorrência com o VE ainda na aproximação.

    Quem monta o `EstadoMalha` deixa de entregar o VE (ele não está mais em
    serviço), e o motor libera o cruzamento pelo caminho normal de E6, sem
    esperar o timeout. Não há caminho novo no motor: o VE simplesmente some,
    e a transição de volta ao ciclo continua sendo a transição segura de sempre.
    """
    motor = MotorDecisao(construir_parametros(n_ciclos_compensacao=0), topologia)
    em_servico = construir_ve(n_vias=4, posicao_na_via_m=410.0, velocidade=10.0)
    motor.avaliar(construir_estado(topologia, t=0.0, veiculos=(em_servico,)))
    assert motor.preempcao_ativa("CRUZ_TESTE_1") is not None

    comandos = motor.avaliar(construir_estado(topologia, t=1.0, veiculos=()))

    comando = next(c for c in comandos if c.id_semaforo == "CRUZ_TESTE_1")
    assert comando.tipo is TipoComando.LIBERAR
    assert "timeout" not in comando.motivo
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
        criticidade=CRITICIDADE_TIPICA[TipoVeiculo.BOMBEIRO],
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
# Observação dos conflitos — entrega 10.1
# ---------------------------------------------------------------------------


def _ve_transversal(
    id_veiculo: str = "BMB",
    tipo: TipoVeiculo = TipoVeiculo.BOMBEIRO,
    posicao_na_via_m: float = 410.0,
) -> VeiculoEmergencia:
    """Um VE que atravessa `CRUZ_TESTE_1` pela transversal."""
    return VeiculoEmergencia(
        id=id_veiculo,
        tipo=tipo,
        criticidade=CRITICIDADE_TIPICA[tipo],
        posicao=(0.0, 0.0),
        velocidade=10.0,
        rota=("T1_IN", "T1_OUT"),
        indice_via_atual=0,
        posicao_na_via_m=posicao_na_via_m,
    )


def _motor_observado(
    topologia: TopologiaMalha, parametros: Parametros
) -> tuple[MotorDecisao, list[EventoConflito]]:
    """Motor com um buffer de conflitos, como o executor o monta."""
    eventos: list[EventoConflito] = []
    motor = MotorDecisao(
        parametros=parametros, topologia=topologia, observador_conflito=eventos.append
    )
    return motor, eventos


def test_conflito_entre_fases_distintas_e_publicado(
    topologia: TopologiaMalha, parametros: Parametros
) -> None:
    """A unidade que a 10.1 conta: dois VEs, duas fases, uma escolha."""
    motor, eventos = _motor_observado(topologia, parametros)
    ambulancia = construir_ve("AMB", TipoVeiculo.AMBULANCIA, n_vias=4, posicao_na_via_m=410.0)

    motor.avaliar(construir_estado(topologia, t=7.0, veiculos=(ambulancia, _ve_transversal())))

    evento = next(e for e in eventos if e.id_semaforo == "CRUZ_TESTE_1")
    assert evento.t == 7.0
    assert evento.ids_veiculos == ("AMB", "BMB")
    assert evento.decidivel
    assert evento.preempcao_em_curso is None


def test_ves_que_pedem_a_mesma_fase_nao_sao_conflito(
    topologia: TopologiaMalha, parametros: Parametros
) -> None:
    """O mesmo verde serve os dois: `resolver` os devolve em `atendidos_juntos`.

    Contar isso como conflito inflaria o número que decide o paradigma de P19
    com eventos em que não há escolha nenhuma a fazer.
    """
    motor, eventos = _motor_observado(topologia, parametros)
    primeiro = construir_ve("AMB", TipoVeiculo.AMBULANCIA, n_vias=4, posicao_na_via_m=410.0)
    segundo = construir_ve("POL", TipoVeiculo.POLICIA, n_vias=4, posicao_na_via_m=380.0)

    motor.avaliar(construir_estado(topologia, veiculos=(primeiro, segundo)))

    assert [e for e in eventos if e.id_semaforo == "CRUZ_TESTE_1"] == []


def test_um_unico_ve_nao_gera_evento(topologia: TopologiaMalha, parametros: Parametros) -> None:
    """Sem disputa não há evento — nem no cruzamento preemptado."""
    motor, eventos = _motor_observado(topologia, parametros)

    motor.avaliar(construir_estado(topologia, veiculos=(construir_ve(posicao_na_via_m=410.0),)))

    assert eventos == []


def test_evento_registra_a_preempcao_em_curso_e_deixa_de_ser_decidivel(
    topologia: TopologiaMalha, parametros: Parametros
) -> None:
    """A guarda de oscilação suspende a escolha, e o evento diz isso.

    É a distinção que separa o episódio treinável do episódio em que a decisão
    já está tomada por regra rígida acima do modelo (`context/09` P19).
    """
    motor, eventos = _motor_observado(topologia, parametros)
    ambulancia = construir_ve("AMB", TipoVeiculo.AMBULANCIA, n_vias=4, posicao_na_via_m=410.0)

    motor.avaliar(construir_estado(topologia, t=0.0, veiculos=(ambulancia,)))
    assert motor.preempcao_ativa("CRUZ_TESTE_1") is not None
    motor.avaliar(construir_estado(topologia, t=1.0, veiculos=(ambulancia, _ve_transversal())))

    evento = next(e for e in eventos if e.t == 1.0)
    assert evento.preempcao_em_curso == "AMB"
    assert not evento.decidivel


def test_conflito_e_publicado_mesmo_quando_o_timeout_de_e6_corta_a_decisao(
    topologia: TopologiaMalha, parametros: Parametros
) -> None:
    """A publicação precede `resolver`, e é por isso que ela não se perde.

    `_decidir_para` retorna no timeout de E6 antes de chegar a E8. Publicar
    depois faria a contagem depender do caminho que a decisão tomou, e não da
    disputa que de fato existiu.
    """
    motor, eventos = _motor_observado(topologia, parametros)
    travado = construir_ve("AMB", TipoVeiculo.AMBULANCIA, n_vias=4, posicao_na_via_m=410.0)

    motor.avaliar(construir_estado(topologia, t=0.0, veiculos=(travado,)))
    comandos = motor.avaliar(
        construir_estado(topologia, t=50.0, veiculos=(travado, _ve_transversal()))
    )

    assert "timeout" in next(c for c in comandos if c.id_semaforo == "CRUZ_TESTE_1").motivo
    assert [e.t for e in eventos if e.id_semaforo == "CRUZ_TESTE_1"] == [50.0]


def test_observador_ausente_nao_muda_a_decisao(
    topologia: TopologiaMalha, parametros: Parametros
) -> None:
    """A instrumentação é observação pura: com e sem ela, os mesmos comandos."""
    veiculos = (
        construir_ve("AMB", TipoVeiculo.AMBULANCIA, n_vias=4, posicao_na_via_m=410.0),
        _ve_transversal(),
    )
    estado = construir_estado(topologia, veiculos=veiculos)
    observado, _ = _motor_observado(topologia, parametros)
    surdo = MotorDecisao(parametros=parametros, topologia=topologia)

    assert observado.avaliar(estado) == surdo.avaliar(estado)


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


# ---------------------------------------------------------------------------
# Política de desempate e consulta de conflitos — P19 (10.4 e 10.6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Preferir:
    """Política de teste: prefere sempre o mesmo VE, quando ele disputa."""

    id_veiculo: str

    def escolher(
        self, id_semaforo: str, disputas: Sequence[Disputa], estado: EstadoMalha
    ) -> Disputa | None:
        del id_semaforo, estado
        return next((d for d in disputas if d.deteccao.id_veiculo == self.id_veiculo), None)


def _dois_iguais() -> tuple[VeiculoEmergencia, VeiculoEmergencia]:
    """Dois VEs de mesmo nível em fases conflitantes de `CRUZ_TESTE_1`."""
    arterial = construir_ve("ART", TipoVeiculo.AMBULANCIA, n_vias=4, posicao_na_via_m=410.0)
    transversal = VeiculoEmergencia(
        id="TRV",
        tipo=TipoVeiculo.AMBULANCIA,
        criticidade=arterial.criticidade,
        posicao=(0.0, 0.0),
        velocidade=10.0,
        rota=("T1_IN", "T1_OUT"),
        indice_via_atual=0,
        posicao_na_via_m=410.0,
    )
    return arterial, transversal


def _comando_no_cruzamento(motor: MotorDecisao, estado: EstadoMalha) -> str | None:
    comandos = [c for c in motor.avaliar(estado) if c.id_semaforo == "CRUZ_TESTE_1"]
    return comandos[0].id_veiculo if comandos else None


def test_politica_escolhe_quem_passa_entre_iguais(
    topologia: TopologiaMalha, parametros: Parametros
) -> None:
    estado = construir_estado(topologia, veiculos=_dois_iguais(), fase_atual=FASE_ARTERIAL)
    sem_politica = MotorDecisao(parametros=parametros, topologia=topologia)
    com_politica = MotorDecisao(
        parametros=parametros, topologia=topologia, politica=_Preferir("TRV")
    )

    assert _comando_no_cruzamento(sem_politica, estado) == "ART"
    assert _comando_no_cruzamento(com_politica, estado) == "TRV"


def test_politica_nao_passa_por_cima_da_criticidade_no_motor(
    topologia: TopologiaMalha, parametros: Parametros
) -> None:
    ambulancia = construir_ve("AMB", TipoVeiculo.AMBULANCIA, n_vias=4, posicao_na_via_m=410.0)
    motor = MotorDecisao(parametros=parametros, topologia=topologia, politica=_Preferir("BMB"))

    estado = construir_estado(topologia, veiculos=(ambulancia, _ve_transversal()))

    assert _comando_no_cruzamento(motor, estado) == "AMB"


def test_politica_que_nao_opina_mantem_o_e8(
    topologia: TopologiaMalha, parametros: Parametros
) -> None:
    estado = construir_estado(topologia, veiculos=_dois_iguais(), fase_atual=FASE_ARTERIAL)
    motor = MotorDecisao(parametros=parametros, topologia=topologia, politica=_Preferir("NINGUEM"))

    assert _comando_no_cruzamento(motor, estado) == "ART"


def test_conflitos_em_ve_a_disputa_sem_decidir(
    topologia: TopologiaMalha, parametros: Parametros
) -> None:
    """A consulta devolve o que `avaliar` publicaria, e não mexe no estado do motor."""
    motor, eventos = _motor_observado(topologia, parametros)
    estado = construir_estado(topologia, t=3.0, veiculos=_dois_iguais(), fase_atual=FASE_ARTERIAL)

    consultados = motor.conflitos_em(estado)

    assert motor.preempcao_ativa("CRUZ_TESTE_1") is None
    assert eventos == []
    motor.avaliar(estado)
    assert consultados == eventos
