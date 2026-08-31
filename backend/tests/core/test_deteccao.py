"""E1, E2 e E3 — e o critério de aceitação do RF01 (`context/06` §2)."""

from __future__ import annotations

import pytest

from core.modelos import EstadoSemaforo, TipoVeiculo, VeiculoEmergencia
from core.parametros import Parametros
from core.priorizacao.deteccao import (
    calcular_eta_s,
    dentro_da_janela,
    detectar,
    distancia_ao_longo_da_rota,
    fila_por_faixa,
)
from tests.core.conftest import construir_parametros, construir_topologia, construir_ve

# Corredor com um único cruzamento ao fim de uma via de 1000 m: permite posicionar
# o VE com precisão em torno do limiar de 500 m.
TOPOLOGIA_LIMIAR = construir_topologia(n_cruzamentos=1, comprimento_via_m=1000.0)
CRUZAMENTO = "CRUZ_TESTE_1"


def _ve_em(posicao_na_via_m: float, velocidade: float = 10.0) -> VeiculoEmergencia:
    return construir_ve(n_vias=2, posicao_na_via_m=posicao_na_via_m, velocidade=velocidade)


# ---------------------------------------------------------------------------
# RF01 — limiar de detecção
# ---------------------------------------------------------------------------


def test_ve_a_480_m_na_rota_e_detectado(parametros: Parametros) -> None:
    """Critério de aceitação do RF01: detecção exata no limiar."""
    veiculo = _ve_em(posicao_na_via_m=520.0)  # faltam 480 m

    distancia = distancia_ao_longo_da_rota(TOPOLOGIA_LIMIAR, veiculo, CRUZAMENTO)
    assert distancia == pytest.approx(480.0)

    deteccoes = detectar(TOPOLOGIA_LIMIAR, veiculo, parametros)
    assert [d.id_semaforo for d in deteccoes] == [CRUZAMENTO]


def test_ve_a_520_m_na_rota_nao_e_detectado(parametros: Parametros) -> None:
    """Do outro lado do limiar, nada é detectado."""
    veiculo = _ve_em(posicao_na_via_m=480.0)  # faltam 520 m

    assert distancia_ao_longo_da_rota(TOPOLOGIA_LIMIAR, veiculo, CRUZAMENTO) == pytest.approx(520.0)
    assert detectar(TOPOLOGIA_LIMIAR, veiculo, parametros) == ()


def test_exatamente_no_raio_e_detectado(parametros: Parametros) -> None:
    """500 m é `<=`, não `<`: o limiar pertence à zona de detecção."""
    veiculo = _ve_em(posicao_na_via_m=500.0)
    assert len(detectar(TOPOLOGIA_LIMIAR, veiculo, parametros)) == 1


# ---------------------------------------------------------------------------
# RF01 — distância de rota, nunca euclidiana
# ---------------------------------------------------------------------------


def test_ve_proximo_em_linha_reta_mas_fora_da_rota_nao_e_detectado(
    parametros: Parametros,
) -> None:
    """O erro clássico que `context/01` §5.2 manda evitar pelo nome.

    O veículo está a 100 m do cruzamento em linha reta — e a coordenada dele diz
    isso —, mas sua rota é a transversal de saída: ele nunca vai atravessar
    aquele cruzamento. Priorizá-lo travaria a via principal de graça.
    """
    topologia = construir_topologia(n_cruzamentos=1)
    fora_da_rota = VeiculoEmergencia(
        id="VE_FORA_DA_ROTA",
        tipo=TipoVeiculo.AMBULANCIA,
        posicao=(100.0, 0.0),  # perto no mapa
        velocidade=10.0,
        rota=("T1_OUT",),  # mas já saindo do cruzamento
        indice_via_atual=0,
    )

    assert distancia_ao_longo_da_rota(topologia, fora_da_rota, CRUZAMENTO) is None
    assert detectar(topologia, fora_da_rota, parametros) == ()


def test_cruzamento_ja_ultrapassado_nao_e_detectado(parametros: Parametros) -> None:
    """A rota é olhada só para a frente: o que ficou para trás não conta."""
    topologia = construir_topologia(n_cruzamentos=3)
    # Já na segunda via: CRUZ_TESTE_1 ficou para trás.
    veiculo = construir_ve(n_vias=4, indice_via_atual=1, posicao_na_via_m=100.0)

    assert distancia_ao_longo_da_rota(topologia, veiculo, "CRUZ_TESTE_1") is None
    detectados = {d.id_semaforo for d in detectar(topologia, veiculo, parametros)}
    assert "CRUZ_TESTE_1" not in detectados
    assert "CRUZ_TESTE_2" in detectados


def test_deteccoes_vem_ordenadas_da_mais_proxima(parametros: Parametros) -> None:
    topologia = construir_topologia(n_cruzamentos=3)
    veiculo = construir_ve(n_vias=4, posicao_na_via_m=490.0)

    deteccoes = detectar(topologia, veiculo, parametros)
    distancias = [d.distancia_m for d in deteccoes]
    assert distancias == sorted(distancias)
    assert deteccoes[0].id_semaforo == "CRUZ_TESTE_1"


def test_movimento_detectado_e_o_par_entrada_saida(parametros: Parametros) -> None:
    """E4 precisa do movimento, não só do cruzamento."""
    topologia = construir_topologia(n_cruzamentos=2)
    veiculo = construir_ve(n_vias=3, posicao_na_via_m=490.0)

    primeira = detectar(topologia, veiculo, parametros)[0]
    assert primeira.movimento == ("E0", "E1")


def test_ultimo_cruzamento_da_rota_nao_gera_deteccao(parametros: Parametros) -> None:
    """Sem via de saída não há movimento, e E4 não teria fase para escolher."""
    topologia = construir_topologia(n_cruzamentos=1)
    # Rota termina em E0, que desemboca no cruzamento: o VE sai da malha ali.
    veiculo = construir_ve(n_vias=1, posicao_na_via_m=100.0)

    assert distancia_ao_longo_da_rota(topologia, veiculo, CRUZAMENTO) == pytest.approx(400.0)
    assert detectar(topologia, veiculo, parametros) == ()


# ---------------------------------------------------------------------------
# E2 — ETA
# ---------------------------------------------------------------------------


def test_eta_e_distancia_sobre_velocidade() -> None:
    assert calcular_eta_s(500.0, 10.0, 4.0) == pytest.approx(50.0)


def test_ve_parado_nao_produz_eta_infinito() -> None:
    """O piso de velocidade existe para o veículo que mais precisa de prioridade.

    Sem ele, um VE parado em fila teria ETA infinito e nunca entraria na janela
    de ativação — exatamente o caso em que a preempção mais importa.
    """
    eta = calcular_eta_s(400.0, velocidade_ms=0.0, velocidade_min_ms=4.0)
    assert eta == pytest.approx(100.0)


def test_velocidade_abaixo_do_piso_usa_o_piso() -> None:
    assert calcular_eta_s(400.0, 1.0, 4.0) == calcular_eta_s(400.0, 0.0, 4.0)


# ---------------------------------------------------------------------------
# E3 — janela de ativação
# ---------------------------------------------------------------------------


def test_janela_de_ativacao_depende_do_tempo_de_transicao(parametros: Parametros) -> None:
    """`TEMPO_ANTECIPACAO = amarelo + all_red + verde_min_residual + MARGEM`."""
    topologia = construir_topologia(n_cruzamentos=1)
    # 100 m a 10 m/s: ETA de 10 s.
    veiculo = construir_ve(n_vias=2, posicao_na_via_m=400.0, velocidade=10.0)
    deteccao = detectar(topologia, veiculo, parametros)[0]
    assert deteccao.eta_s == pytest.approx(10.0)

    # Janela sem verde mínimo pendente: 3 + 2 + 5 = 10 s. ETA de 10 s entra.
    assert dentro_da_janela(deteccao, parametros) is True


def test_preempcao_nao_comeca_cedo_demais(parametros: Parametros) -> None:
    """Preemptar antes da hora trava a transversal de graça — o custo que H2 mede."""
    topologia = construir_topologia(n_cruzamentos=1)
    # 480 m a 10 m/s: ETA de 48 s, muito além da janela de 10 s.
    veiculo = construir_ve(n_vias=2, posicao_na_via_m=20.0, velocidade=10.0)
    deteccao = detectar(topologia, veiculo, parametros)[0]

    assert deteccao.eta_s == pytest.approx(48.0)
    assert dentro_da_janela(deteccao, parametros) is False


def test_verde_minimo_pendente_antecipa_a_janela(parametros: Parametros) -> None:
    """Verde mínimo pendente adianta o início da preempção.

    Se o cruzamento ainda deve verde mínimo, a transição demora mais — e a
    preempção precisa começar mais cedo para o VE não pegar vermelho.
    """
    topologia = construir_topologia(n_cruzamentos=1)
    veiculo = construir_ve(n_vias=2, posicao_na_via_m=350.0, velocidade=10.0)
    deteccao = detectar(topologia, veiculo, parametros)[0]
    assert deteccao.eta_s == pytest.approx(15.0)

    assert dentro_da_janela(deteccao, parametros, verde_min_residual=0.0) is False
    assert dentro_da_janela(deteccao, parametros, verde_min_residual=5.0) is True


# ---------------------------------------------------------------------------
# E3 — dissipação da fila (P16)
# ---------------------------------------------------------------------------


def test_fila_no_acesso_antecipa_a_janela(parametros: Parametros) -> None:
    """**Regressão de P16.** Abrir o verde a tempo não basta: a fila tem de escoar.

    O piloto do Bloco 4 mediu 2,76 paradas residuais do VE no cenário `intenso`
    contra 0,76 no `moderado` — o corredor abria a tempo e não esvaziava a
    tempo. Com a janela fixa em 10 s, um VE com ETA de 20 s ficava de fora;
    com seis veículos parados à frente (6 x 2,13 = 12,8 s de dissipação) ele
    passa a entrar.
    """
    topologia = construir_topologia(n_cruzamentos=1)
    # 200 m a 10 m/s: ETA de 20 s, o dobro da janela sem fila.
    veiculo = construir_ve(n_vias=2, posicao_na_via_m=300.0, velocidade=10.0)
    deteccao = detectar(topologia, veiculo, parametros)[0]
    assert deteccao.eta_s == pytest.approx(20.0)

    assert dentro_da_janela(deteccao, parametros) is False

    dissipacao = parametros.tempo_dissipacao_fila_s(fila_por_faixa=6)
    assert dissipacao == pytest.approx(12.78)
    assert dentro_da_janela(deteccao, parametros, tempo_dissipacao_s=dissipacao) is True


def test_sem_fila_a_janela_e_a_mesma_de_antes(parametros: Parametros) -> None:
    """A correção de P16 não muda o comportamento onde não há fila.

    Importa porque os cenários `leve` e `moderado` já atingiam a meta: uma
    correção que mexesse neles também obrigaria a explicar por que os números
    de H1 mudaram onde não havia defeito.
    """
    assert parametros.tempo_dissipacao_fila_s(fila_por_faixa=0) == 0.0
    assert parametros.tempo_antecipacao_s(tempo_dissipacao_s=0.0) == pytest.approx(10.0)
    assert parametros.tempo_antecipacao_s() == pytest.approx(10.0)


def test_janela_nao_passa_do_teto_derivado_do_timeout(parametros: Parametros) -> None:
    """Antecipar mais que a preempção sobrevive derrubaria o corredor no rosto do VE.

    `_liberar` dispara por `preempcao_timeout_s`; se a janela fosse maior que
    isso, a preempção começaria, expiraria e o VE chegaria no vermelho — pior
    que não ter preemptado. O teto é derivado, não é parâmetro novo.
    """
    assert parametros.antecipacao_max_s == pytest.approx(40.0)  # 45 - (3 + 2)

    # Fila absurda: 100 veículos por faixa dariam 213 s de dissipação.
    enorme = parametros.tempo_dissipacao_fila_s(fila_por_faixa=100)
    assert enorme == pytest.approx(213.0)
    assert parametros.tempo_antecipacao_s(tempo_dissipacao_s=enorme) == pytest.approx(40.0)


def test_fila_e_dividida_pelas_faixas_do_acesso() -> None:
    """Doze parados em duas faixas são seis à frente do VE, não doze.

    Os detectores E2 somam as faixas do acesso; usar a soma estimaria o dobro do
    tempo de dissipação numa arterial de duas faixas, e a preempção começaria
    cedo demais — o custo transversal que H2 mede, pago sem necessidade.
    """
    de_duas = construir_topologia(n_cruzamentos=1, faixas=2)
    de_uma = construir_topologia(n_cruzamentos=1, faixas=1)
    estado = EstadoSemaforo(
        id="CRUZ_TESTE_1", fase_atual=1, tempo_na_fase=0.0, fila_por_acesso={"E0": 12}
    )

    assert fila_por_faixa(estado, de_duas, "E0") == pytest.approx(6.0)
    assert fila_por_faixa(estado, de_uma, "E0") == pytest.approx(12.0)


def test_via_sem_faixa_declarada_conta_como_uma() -> None:
    """Desconhecida vale 1 — o palpite que antecipa mais, não menos.

    Errar para o lado de antecipar demais custa espera transversal; errar para o
    outro custa o VE parar, que é o defeito que P16 corrige.
    """
    topologia = construir_topologia(n_cruzamentos=1)
    assert topologia.faixas("VIA_QUE_NAO_EXISTE") == 1
    assert topologia.faixas("E0") == 1


def test_raio_de_deteccao_vem_dos_parametros() -> None:
    """Nenhum número mágico no meio da função (`context/08` §4.3)."""
    veiculo = _ve_em(posicao_na_via_m=480.0)  # 520 m
    assert detectar(TOPOLOGIA_LIMIAR, veiculo, construir_parametros()) == ()
    assert len(detectar(TOPOLOGIA_LIMIAR, veiculo, construir_parametros(raio_deteccao_m=600))) == 1
