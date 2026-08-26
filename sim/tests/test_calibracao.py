"""Calibração dos cenários — a aritmética de P11, sem SUMO.

Estes testes rodam na execução padrão de propósito. A metade **medida** da
entrega 3.0 exige o simulador; a metade **derivada** é aritmética, e aritmética
que sustenta a caracterização do experimento merece teste rápido e permanente.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from sim.calibracao.cenarios import (
    Aproximacao,
    Programa,
    capacidade_veic_h,
    carregar_configuracao,
    carregar_medicao,
    classificar,
    conferir_plausibilidade,
    fluxo_para_grau,
    grau_de_saturacao,
    montar_tabela,
    verde_efetivo_s,
)
from sim.calibracao.fluxo_saturacao import fluxo_veic_h, headway_de_saturacao

RAIZ = Path(__file__).resolve().parents[2]
TLL = RAIZ / "sim" / "rede" / "malha.tll.xml"


# ---------------------------------------------------------------------------
# Medição: a aritmética do headway (a coleta em si é que exige SUMO)
# ---------------------------------------------------------------------------


def test_headway_de_saturacao_descarta_a_partida() -> None:
    """Os primeiros veículos ainda estão acelerando: entram como perda, não como taxa."""
    # Quatro veículos lentos na partida (3 s), depois regime de 2 s.
    travessias = [3.0, 6.0, 9.0, 12.0, 14.0, 16.0, 18.0, 20.0]
    headway, perda = headway_de_saturacao(travessias, inicio_do_verde_s=0.0, descartados=4)

    assert headway == pytest.approx(2.0)
    assert perda == pytest.approx(4.0)  # 4 veículos x 1 s de excesso


def test_headway_ignora_travessias_fora_da_janela_do_verde() -> None:
    """Fluxo de saturação é a taxa de escoamento DURANTE o verde.

    Sem o recorte, os veículos do fim da fila — que já cruzam em velocidade de
    fluxo livre, com headway bem menor — inflariam o número e descreveriam um
    regime que o cruzamento nunca vive.
    """
    # Sete veículos em regime de descarga (2 s) e três já em fluxo livre (0,5 s).
    travessias = [2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 15.5, 16.0, 16.5]

    com_janela, _ = headway_de_saturacao(travessias, 0.0, descartados=4, janela_s=15.0)
    sem_janela, _ = headway_de_saturacao(travessias, 0.0, descartados=4)

    assert com_janela == pytest.approx(2.0)
    assert sem_janela < com_janela


def test_amostra_pequena_demais_e_recusada() -> None:
    """Medir saturação com dois carros não mede nada — e falhar alto é melhor."""
    with pytest.raises(ValueError, match="amostra insuficiente"):
        headway_de_saturacao([1.0, 2.0], 0.0, descartados=4)


def test_fluxo_e_o_inverso_do_headway() -> None:
    assert fluxo_veic_h(2.0) == pytest.approx(1800.0)


# ---------------------------------------------------------------------------
# Derivação: capacidade, v/c e classificação
# ---------------------------------------------------------------------------


@pytest.fixture
def programa() -> Programa:
    """O baseline: 2 fases, 30 s de verde, ciclo de 70 s."""
    return Programa(n_fases=2, verde_s=30.0, amarelo_s=3.0, all_red_s=2.0)


def test_ciclo_sai_das_fases(programa: Programa) -> None:
    assert programa.ciclo_s == pytest.approx(70.0)


def test_verde_efetivo_desconta_a_perda_medida(programa: Programa) -> None:
    """Verde efetivo = verde + amarelo - perda de partida. O all-red é perda inteira."""
    assert verde_efetivo_s(programa, 0.0) == pytest.approx(33.0)
    assert verde_efetivo_s(programa, 2.5) == pytest.approx(30.5)


def test_capacidade_e_saturacao_vezes_razao_de_verde(programa: Programa) -> None:
    """`c = faixas x s x g/C`, a fórmula de fluxo interrompido."""
    arterial = Aproximacao("arterial", faixas=2, fluxo_saturacao_veic_h_faixa=1800.0)
    esperado = 2 * 1800.0 * (33.0 / 70.0)

    assert capacidade_veic_h(arterial, programa) == pytest.approx(esperado)


def test_limiares_de_classificacao_sao_os_do_contexto() -> None:
    """context/04 §5: leve < 40%, moderado 40 a 75%, intenso > 75%."""
    assert classificar(0.39, 0.40, 0.75) == "leve"
    assert classificar(0.40, 0.40, 0.75) == "moderado"
    assert classificar(0.75, 0.40, 0.75) == "moderado"
    assert classificar(0.76, 0.40, 0.75) == "intenso"


def test_fluxo_transversal_e_derivado_do_mesmo_grau_de_saturacao() -> None:
    """A demanda transversal não é escolhida: é a que iguala o v/c da arterial."""
    capacidade = 800.0
    fluxo = fluxo_para_grau(0.45, capacidade)

    assert fluxo == pytest.approx(360.0)
    assert grau_de_saturacao(fluxo, capacidade) == pytest.approx(0.45)


def test_capacidade_zero_e_erro_e_nao_infinito() -> None:
    with pytest.raises(ValueError):
        grau_de_saturacao(700.0, 0.0)


# ---------------------------------------------------------------------------
# Coerência entre os arquivos do repositório
# ---------------------------------------------------------------------------


def test_programa_do_yaml_bate_com_o_tll_versionado() -> None:
    """`cenarios.yaml` e `malha.tll.xml` precisam descrever o MESMO ciclo.

    A conta de capacidade usa o YAML; a simulação roda o `.tll.xml`. Divergirem
    em silêncio produziria um v/c calculado sobre um ciclo que não é o que roda —
    e o erro não apareceria em lugar nenhum até a arguição.
    """
    programa = carregar_configuracao()["programa"]
    texto = TLL.read_text(encoding="utf-8")

    for nome, chave in (
        ("verde_arterial", "verde_s"),
        ("amarelo_arterial", "amarelo_s"),
        ("all_red", "all_red_s"),
    ):
        marca = f'duration="{programa[chave]}"'
        assert f"{marca} state=" in texto or marca in texto, (
            f"duração de {nome} ({programa[chave]} s) não aparece em malha.tll.xml"
        )


def test_medicao_de_saturacao_esta_no_repositorio_e_e_plausivel() -> None:
    """O CSV da medição é versionado — é dele que sai todo o resto.

    E o valor medido é confrontado com a faixa reportada para via urbana. Isso
    não valida o resultado: é guarda contra o modelo estar grosseiramente fora de
    esquadro, como manda o encaminhamento de P11.
    """
    configuracao = carregar_configuracao()
    medicao = carregar_medicao()

    assert set(medicao) == {"arterial", "transversal"}

    from sim.calibracao.cenarios import aproximacoes_medidas

    aproximacoes = aproximacoes_medidas(configuracao, medicao)
    avisos = conferir_plausibilidade(
        aproximacoes, configuracao["faixa_plausivel_saturacao_veic_h_faixa"]
    )
    assert avisos == [], "\n".join(avisos)


def test_tabela_de_cenarios_cobre_os_quatro_cenarios() -> None:
    configuracao = carregar_configuracao()
    medicao = carregar_medicao()

    from sim.calibracao.cenarios import aproximacoes_medidas

    arterial, transversal = aproximacoes_medidas(configuracao, medicao)
    linhas = montar_tabela(
        configuracao["cenarios"],
        arterial,
        transversal,
        Programa(
            n_fases=int(configuracao["programa"]["n_fases"]),
            verde_s=float(configuracao["programa"]["verde_s"]),
            amarelo_s=float(configuracao["programa"]["amarelo_s"]),
            all_red_s=float(configuracao["programa"]["all_red_s"]),
        ),
        configuracao["limiares_saturacao"],
    )

    assert {linha.cenario for linha in linhas} == set(configuracao["cenarios"])
    # O grau de saturação cresce com o fluxo — o mínimo que a conta precisa fazer.
    por_fluxo = sorted(linhas, key=lambda linha: linha.fluxo_arterial_veic_h)
    graus = [linha.grau_saturacao for linha in por_fluxo]
    assert graus == sorted(graus)
    assert all(math.isfinite(grau) for grau in graus)
