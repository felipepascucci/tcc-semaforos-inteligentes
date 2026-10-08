"""RF02 e H3 de ponta a ponta — `context/06` §2.

Duas partes, com papéis diferentes:

* **A cadeia, contra o dublê.** O carrinho lê a tag: a linha `Tag … lida` sai
  pelo USB do emissor e a detecção chega ao A0 do UNO pelo receptor. O UNO é o
  dublê (`adapters/hardware/simulado.py`), o modelo de referência do firmware, e
  a ponte casa as duas pontas como na bancada (`bridge/latencia.py`). Confere
  que a passagem vira `PREEMP_INI`, uma amostra de H3 e o verde exclusivo da
  rua, e que a que vira `FILA` não é amostra. **O número que sai daqui não é
  dado experimental**: a latência é a do dublê, arbitrária, e só se confere que
  fica no limite do RF02.
* **O dado gravado na bancada.** As 100 passagens de 2026-10-07 (sessão de
  `analysis.gerar_resultados_tcc.SESSAO_H3`) são a evidência de RF02 e H3
  (`06` §6, itens 7 e 7b). O teste não produz número nenhum: confere que o CSV
  versionado cumpre os critérios declarados, e quebra se ele for alterado.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest

from adapters.hardware.simulado import TransporteSimulado
from analysis.resumo_bancada import (
    CSV_DETECCOES,
    CSV_LATENCIA,
    LIMIAR_H3_MS,
    PASSAGENS_PREVISTAS,
    PREEMP_INI,
    ler_amostras,
    ler_leituras,
)
from bridge.latencia import JANELA_S, GravadorCsv, GravadorDesfechos
from bridge.ponte import Ponte
from bridge.protocolo import Deteccao, LeituraVeiculo, Regime
from bridge.tests.conftest import PortaRoteirizada, ate, transporte_rapido
from bridge.transporte import LinhaRecebida
from core.modelos import TipoVeiculo
from sim.controlador.coletor import percentil

#: RF02: do instante da detecção ao início da atuação, em até 3 s (decisão P14).
LIMITE_RF02_MS = 3000.0

#: As tags das ruas, como no cabeçalho de `veiculo_ambulancia.ino`.
UID_DA_RUA = {1: "F39BD606", 2: "1BD2308E", 3: "B7EF8FA0", 4: "97ABAFA0"}

AMB, BOMB = TipoVeiculo.AMBULANCIA, TipoVeiculo.BOMBEIRO


def _exclusivo(rua: int) -> str:
    return "".join("G" if i == rua - 1 else "R" for i in range(4))


@asynccontextmanager
async def _bancada(
    pasta: Path, autorizacoes: tuple[int, int, int] = (1, 2, 3)
) -> AsyncIterator[tuple[Ponte, TransporteSimulado, PortaRoteirizada]]:
    """A ponte com o dublê no USB do UNO e o emissor da ambulância no USB do notebook."""
    uno = transporte_rapido(autorizacoes=autorizacoes)
    emissor = PortaRoteirizada()
    sessao = datetime.now(UTC)
    ponte = Ponte(
        uno,
        transporte_veiculo=emissor,
        gravador=GravadorCsv(pasta / "latencia_bancada.csv", sessao=sessao, versao_codigo="teste"),
        gravador_desfechos=GravadorDesfechos(
            pasta / "deteccoes_bancada.csv", sessao=sessao, versao_codigo="teste"
        ),
    )
    tarefa = asyncio.create_task(ponte.rodar())
    try:
        await ate(lambda: ponte.uno_respondendo() and ponte.emissor_conectado)
        yield ponte, uno, emissor
    finally:
        ponte.parar()
        await asyncio.wait_for(tarefa, 5.0)


def _carrinho_da_ambulancia(uno: TransporteSimulado, emissor: PortaRoteirizada, rua: int) -> None:
    """A ambulância passa sobre a tag: imprime no USB e envia ao receptor."""
    emissor.entregar(
        LinhaRecebida(LeituraVeiculo(UID_DA_RUA[rua], rua).codificar(), time.perf_counter())
    )
    uno.simular_receptor(Deteccao(rua, AMB))


# ---------------------------------------------------------------------------
# A cadeia, contra o dublê
# ---------------------------------------------------------------------------


async def test_passagem_vira_preemp_ini_amostra_e_verde_exclusivo(tmp_path: Path) -> None:
    async with _bancada(tmp_path) as (ponte, uno, emissor):
        _carrinho_da_ambulancia(uno, emissor, rua=2)
        await ate(lambda: len(ponte.amostras_h3) == 1)
        await ate(
            lambda: (
                ponte.ultima_telemetria is not None
                and "".join(ponte.ultima_telemetria.cores) == _exclusivo(2)
            ),
            limite_s=10.0,
        )
        assert ponte.ultima_telemetria is not None
        assert ponte.ultima_telemetria.regime is Regime.EMERGENCIA

    amostra = ponte.amostras_h3[0]
    assert amostra.deteccao.rua == 2
    assert 0.0 <= amostra.latencia_total_ms < LIMITE_RF02_MS
    gravadas = ler_amostras(tmp_path / "latencia_bancada.csv")
    assert [a.rua for a in gravadas] == [2]
    leituras = ler_leituras(tmp_path / "deteccoes_bancada.csv")
    assert [(leitura.rua, leitura.desfecho) for leitura in leituras] == [(2, PREEMP_INI)]


async def test_passagem_que_vira_fila_nao_e_amostra(tmp_path: Path) -> None:
    """A ambulância com criticidade menor que a do bombeiro em verde vai para a fila."""
    async with _bancada(tmp_path, autorizacoes=(2, 1, 3)) as (ponte, uno, emissor):
        uno.simular_receptor(Deteccao(3, BOMB))
        await ate(lambda: any(ev.tipo.value == PREEMP_INI for _, ev in ponte.eventos))
        _carrinho_da_ambulancia(uno, emissor, rua=1)
        await ate(lambda: ponte.deteccoes_sem_amostra.get("FILA") == 1)

    assert ponte.amostras_h3 == []
    leituras = ler_leituras(tmp_path / "deteccoes_bancada.csv")
    assert [(leitura.rua, leitura.desfecho) for leitura in leituras] == [(1, "FILA")]


def test_janela_do_casamento_e_o_limite_do_rf02() -> None:
    """A janela que encerra a espera pela decisão é o próprio RF02, e não mais curta.

    Uma janela mais justa descartaria justamente as amostras lentas, a favor da
    hipótese (`bridge/latencia.py`).
    """
    assert JANELA_S * 1000.0 == LIMITE_RF02_MS


# ---------------------------------------------------------------------------
# O dado gravado na bancada (06 §6, itens 7 e 7b)
# ---------------------------------------------------------------------------


def _sessao_h3() -> str:
    pytest.importorskip("pandas", reason="extra analysis não instalado")
    from analysis.gerar_resultados_tcc import SESSAO_H3

    return SESSAO_H3


def _amostras_gravadas() -> list[float]:
    sessao = _sessao_h3()
    amostras = [a for a in ler_amostras(CSV_LATENCIA) if a.sessao == sessao]
    assert len(amostras) == PASSAGENS_PREVISTAS, "a sessão de H3 tem de ter as 100 passagens"
    return [a.latencia_total_ms for a in amostras]


def test_rf02_na_bancada_toda_preempcao_comeca_em_menos_de_3_s() -> None:
    assert max(_amostras_gravadas()) < LIMITE_RF02_MS


def test_h3_na_bancada_p95_abaixo_de_200_ms() -> None:
    assert percentil(_amostras_gravadas(), 95) < LIMIAR_H3_MS


def test_amostras_de_h3_sao_os_preemp_ini_das_leituras_da_mesma_sessao() -> None:
    """Os dois CSV da rodada concordam: uma amostra por leitura que virou `PREEMP_INI`."""
    sessao = _sessao_h3()
    leituras = [leitura for leitura in ler_leituras(CSV_DETECCOES) if leitura.sessao == sessao]
    assert sum(1 for leitura in leituras if leitura.desfecho == PREEMP_INI) == len(
        _amostras_gravadas()
    )
