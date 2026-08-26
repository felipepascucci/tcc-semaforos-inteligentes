"""A malha construída — geometria, fases e detectores (entregas 3.1, 3.2, 3.5).

Marcado `sumo`: exige o binário instalado e a rede construída. Fora da execução
padrão (`context/06` §1); para rodar, `pytest -m sumo`.

O que estes testes protegem é o elo mais silencioso da cadeia: um `.net.xml`
desatualizado ou um mapa de fases que não corresponde à rede não quebram nada —
a simulação roda, os números saem, e descrevem uma malha que não existe.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.sumo

RAIZ = Path(__file__).resolve().parents[2]
REDE = RAIZ / "sim" / "rede" / "malha.net.xml"
DETECTORES = RAIZ / "sim" / "rede" / "malha.det.add.xml"

#: Rota do VE — o "U" pelos oito cruzamentos (context/04 §3).
ROTA_VE = ("A1_L0", "A1_L1", "A1_L2", "A1_L3", "T4_S1", "A2_O3", "A2_O2", "A2_O1", "A2_O0")


@pytest.fixture(scope="module", autouse=True)
def rede_construida() -> None:
    """Garante `malha.net.xml` em dia antes de qualquer teste deste módulo."""
    from sim.rede import construir

    if not REDE.is_file():
        construir.construir()


@pytest.fixture(scope="module")
def malha():  # tipo vem do sumolib, carregado em tempo de execução
    from adapters.sumo import topologia

    return topologia.carregar()


# ---------------------------------------------------------------------------
# 3.1 — geometria
# ---------------------------------------------------------------------------


def test_malha_tem_oito_cruzamentos_semaforizados(malha) -> None:
    """Grade 2x4 — o objetivo específico nº 1 do context/00 §4."""
    assert len(malha.semaforos) == 8
    assert malha.semaforos[0] == "CRUZ_01"


def test_construcao_e_reprodutivel_e_sem_avisos() -> None:
    """`make rede` a partir dos mesmos fontes precisa dar sempre a mesma rede."""
    from sim.rede import construir

    assert construir.verificar() == []


def test_rota_do_ve_atravessa_os_oito_cruzamentos(malha) -> None:
    """O corredor completo — é o que torna o efeito de coordenação mensurável."""
    atravessados = [
        malha.topologia.cruzamento_apos_via[via]
        for via in ROTA_VE
        if via in malha.topologia.cruzamento_apos_via
    ]

    assert len(atravessados) == 8
    assert len(set(atravessados)) == 8


def test_percurso_do_ve_tem_cerca_de_quatro_quilometros_e_meio(malha) -> None:
    """Os ~5 km do pré-projeto, medidos na rede e não declarados."""
    comprimento = sum(malha.topologia.comprimento(via) for via in ROTA_VE)

    assert 4_000 < comprimento < 5_000


def test_arterial_tem_duas_faixas_e_transversal_uma(malha) -> None:
    """A hierarquia viária é o que dá sentido a priorizar a arterial."""
    assert len(malha.faixas_do_acesso["A1_L0"]) == 2
    assert len(malha.faixas_do_acesso["T1_S0"]) == 1


# ---------------------------------------------------------------------------
# 3.5 — mapa de fases contra a rede
# ---------------------------------------------------------------------------


def test_mapa_de_fases_e_a_rede_descrevem_a_mesma_malha(malha) -> None:
    """Aproximação esquecida = vermelho eterno (I5); duplicada = conflito (I1)."""
    from adapters.sumo import topologia

    assert topologia.validar(malha) == []


def test_fase_verde_so_abre_a_propria_aproximacao(malha) -> None:
    """I1 aplicado à REDE, não ao motor.

    O motor pode estar corretíssimo: se a state string da fase arterial desse
    verde a um link da transversal, os dois verdes conflitantes aconteceriam na
    rua. A verificação é a mesma de `topologia.validar`, isolada aqui para que a
    falha aponte o invariante certo.
    """
    from adapters.sumo import topologia

    problemas = [p for p in topologia.validar(malha) if "verde" in p]
    assert problemas == []


def test_movimentos_do_ve_sao_servidos_por_fases_de_eixos_diferentes(malha) -> None:
    """Em CRUZ_04 o VE pede a arterial; em CRUZ_08, a transversal.

    O corredor muda de eixo no meio do percurso, e é isso que exercita E4 de
    verdade — um corredor que pedisse sempre a mesma fase não provaria nada.
    """
    cruz_04 = malha.topologia.cruzamento("CRUZ_04")
    cruz_08 = malha.topologia.cruzamento("CRUZ_08")

    assert cruz_04.fase_que_serve(("A1_L3", "T4_S1")) == 1
    assert cruz_08.fase_que_serve(("T4_S1", "A2_O3")) == 2


def test_duracoes_do_mapa_de_fases_batem_com_os_parametros(malha) -> None:
    """Os braços FIXO e PREEMPCAO precisam do MESMO ciclo base.

    No baseline quem conduz é o `.tll.xml`; nos modos com preempção, a máquina de
    estados de `core`. Se as durações divergissem, a diferença medida entre os
    braços incluiria a diferença de ciclo — e não seria atribuível à preempção.
    """
    from adapters.configuracao import carregar

    parametros = carregar("simulacao")
    for id_semaforo in malha.semaforos:
        for fase in malha.topologia.cruzamento(id_semaforo).fases:
            assert fase.duracao_base_s == 30.0
            assert fase.verde_min_s == parametros.verde_min_s
            assert fase.verde_max_s == parametros.verde_max_s


# ---------------------------------------------------------------------------
# 3.2 — detectores
# ---------------------------------------------------------------------------


def test_ha_um_detector_de_fila_por_faixa_de_aproximacao(malha) -> None:
    """Sem E2 não há como medir fila, e sem fila H2 fica sem evidência."""
    texto = DETECTORES.read_text(encoding="utf-8")

    for acesso, faixas in malha.faixas_do_acesso.items():
        for faixa in faixas:
            assert f'id="E2_{faixa}"' in texto, f"faltou detector de fila em {acesso}"


def test_detectores_cobrem_os_tres_tipos_do_contexto() -> None:
    """E2 (fila), E1 (throughput) e E3 (tempo de viagem) — context/04 §11."""
    texto = DETECTORES.read_text(encoding="utf-8")

    assert texto.count("<laneAreaDetector") == 48  # 8 cruzamentos x 6 faixas
    assert texto.count("<inductionLoop") == 48
    assert texto.count("<entryExitDetector") == 12  # 3 trechos internos x 4 sentidos


def test_saida_dos_detectores_usa_caminho_relativo() -> None:
    """Nome relativo é o que faz a saída cair na pasta da execução.

    O executor copia este arquivo para dentro da pasta da execução justamente
    porque o SUMO resolve `file` relativo a quem o declara. Um caminho absoluto
    aqui faria todas as 600 execuções escreverem por cima umas das outras.
    """
    texto = DETECTORES.read_text(encoding="utf-8")

    assert 'file="detectores_e2.xml"' in texto

    linhas_de_detector = [
        linha for linha in texto.splitlines() if "Detector" in linha or "inductionLoop" in linha
    ]
    assert linhas_de_detector
    assert not any(":\\" in linha or ":/" in linha for linha in linhas_de_detector)
