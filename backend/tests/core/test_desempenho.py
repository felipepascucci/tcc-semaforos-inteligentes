"""RNF01 — latência de **decisão** abaixo de 100 ms (`context/06` §2).

Decisão P2: são duas métricas distintas, e esta é a de software puro —
`motor.avaliar()`, sem rede e sem I/O de banco. A latência fim-a-fim de H3
(< 200 ms) é outra coisa, medida no fluxo com detecção física e verificada em
`tests/e2e/`.

**Percentil, não média.** Sistema crítico se avalia pela cauda: média de 68 ms
com p99 de 400 ms não atende ao requisito, e a banca pode perguntar exatamente
isso (`context/04` §9.3).

Medir tempo em teste é sempre um pouco frágil — a máquina pode estar ocupada.
Por isso o teste usa `perf_counter` (o mesmo relógio da instrumentação real),
descarta um aquecimento e afere o **p95**, que é justamente a métrica menos
sensível a um pico isolado.
"""

from __future__ import annotations

import statistics
import time

import pytest

from core.malha import TopologiaMalha
from core.modelos import EstadoMalha, EstadoSemaforo, Sinal, TipoVeiculo, VeiculoEmergencia
from core.priorizacao.motor import MotorDecisao
from tests.core.conftest import (
    CRITICIDADE_TIPICA,
    FASE_TRANSVERSAL,
    construir_parametros,
    construir_topologia,
    construir_ve,
)

N_CHAMADAS = 10_000
N_AQUECIMENTO = 200

pytestmark = pytest.mark.lento


def _percentil(amostras: list[float], fracao: float) -> float:
    ordenadas = sorted(amostras)
    indice = min(int(len(ordenadas) * fracao), len(ordenadas) - 1)
    return ordenadas[indice]


def _medir(motor: MotorDecisao, estados: list[EstadoMalha]) -> list[float]:
    """Mede `avaliar()` em milissegundos, uma amostra por chamada."""
    for estado in estados[:N_AQUECIMENTO]:
        motor.avaliar(estado)

    amostras: list[float] = []
    for estado in estados:
        inicio = time.perf_counter()
        motor.avaliar(estado)
        amostras.append((time.perf_counter() - inicio) * 1000.0)
    return amostras


def _estados_da_malha(topologia: TopologiaMalha, n: int) -> list[EstadoMalha]:
    """Sequência de estados com um VE percorrendo o corredor."""
    estados = []
    for passo in range(n):
        percorrido = (passo * 5.0) % 1500.0
        via, posicao = divmod(percorrido, 500.0)
        veiculo = construir_ve(
            n_vias=4, indice_via_atual=min(int(via), 3), posicao_na_via_m=posicao
        )
        semaforos = {
            id_cruzamento: EstadoSemaforo(
                id=id_cruzamento,
                fase_atual=FASE_TRANSVERSAL,
                tempo_na_fase=float(passo % 30),
                fila_por_acesso=dict.fromkeys(cruzamento.acessos(), 4),
                sinal=Sinal.VERDE,
            )
            for id_cruzamento, cruzamento in topologia.cruzamentos.items()
        }
        estados.append(
            EstadoMalha(t=passo * 0.1, semaforos=semaforos, veiculos_emergencia=(veiculo,))
        )
    return estados


def test_p95_da_decisao_fica_sob_100_ms_em_10000_chamadas() -> None:
    """O critério do RNF01, na malha de 8 cruzamentos do experimento."""
    parametros = construir_parametros()
    topologia = construir_topologia(n_cruzamentos=8)
    motor = MotorDecisao(parametros, topologia)

    amostras = _medir(motor, _estados_da_malha(topologia, N_CHAMADAS))
    p95 = _percentil(amostras, 0.95)
    p99 = _percentil(amostras, 0.99)

    assert len(amostras) == N_CHAMADAS
    assert p95 < parametros.latencia_decisao_p95_max_ms, (
        f"p95={p95:.3f} ms excede o orçamento de "
        f"{parametros.latencia_decisao_p95_max_ms} ms "
        f"(média={statistics.mean(amostras):.3f} ms, p99={p99:.3f} ms)"
    )


def test_p99_tambem_cabe_no_orcamento() -> None:
    """A cauda é o que interessa num sistema crítico.

    O RNF01 fala em p95; medir o p99 junto é o que permite responder à pergunta
    "e o pior caso?" com número em vez de encolher de ombros.
    """
    parametros = construir_parametros()
    topologia = construir_topologia(n_cruzamentos=8)
    motor = MotorDecisao(parametros, topologia)

    amostras = _medir(motor, _estados_da_malha(topologia, N_CHAMADAS))
    p99 = _percentil(amostras, 0.99)

    assert p99 < parametros.latencia_decisao_p95_max_ms, f"p99={p99:.3f} ms"


def test_escala_para_malha_de_32_cruzamentos() -> None:
    """RNF03 — a malha pode crescer sem estourar o orçamento de latência."""
    parametros = construir_parametros()
    topologia = construir_topologia(n_cruzamentos=32)
    motor = MotorDecisao(parametros, topologia)

    amostras = _medir(motor, _estados_da_malha(topologia, 2_000))
    p95 = _percentil(amostras, 0.95)

    assert p95 < parametros.latencia_decisao_p95_max_ms, f"p95={p95:.3f} ms com 32 cruzamentos"


def test_multiplos_ves_nao_estouram_o_orcamento() -> None:
    """O cenário `multiplas_emergencias` é o mais caro em tempo de decisão."""
    parametros = construir_parametros()
    topologia = construir_topologia(n_cruzamentos=8)
    motor = MotorDecisao(parametros, topologia)

    tipos = [TipoVeiculo.AMBULANCIA, TipoVeiculo.BOMBEIRO, TipoVeiculo.POLICIA]
    estados = []
    for passo in range(2_000):
        veiculos = tuple(
            VeiculoEmergencia(
                id=f"VE_{indice}",
                tipo=tipos[indice % 3],
                criticidade=CRITICIDADE_TIPICA[tipos[indice % 3]],
                posicao=(0.0, 0.0),
                velocidade=10.0,
                rota=tuple(f"E{i}" for i in range(9)),
                indice_via_atual=indice % 8,
                posicao_na_via_m=float((passo * 5) % 500),
            )
            for indice in range(4)
        )
        semaforos = {
            id_cruzamento: EstadoSemaforo(
                id=id_cruzamento, fase_atual=FASE_TRANSVERSAL, tempo_na_fase=10.0
            )
            for id_cruzamento in topologia.cruzamentos
        }
        estados.append(
            EstadoMalha(t=passo * 0.1, semaforos=semaforos, veiculos_emergencia=veiculos)
        )

    p95 = _percentil(_medir(motor, estados), 0.95)
    assert p95 < parametros.latencia_decisao_p95_max_ms, f"p95={p95:.3f} ms com 4 VEs"
