"""Guarda dos arquivos de parâmetros (entrega 0.7).

Os valores conferidos aqui vêm de `context/01-arquitetura-sistema.md` §5.3 e da
decisão de perfil de bancada de 2026-08-24 (`context/09`, detalhada em
`docs/contrato-hardware-software.md` §7). Se alguém alterar um número sem
atualizar o contexto, este teste quebra — que é exatamente o ponto.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

CONFIG = Path(__file__).resolve().parents[1] / "config"


def _carregar(nome: str) -> dict[str, Any]:
    with (CONFIG / nome).open(encoding="utf-8") as arquivo:
        dados = yaml.safe_load(arquivo)
    assert isinstance(dados, dict)
    return dados


@pytest.fixture(scope="module")
def simulacao() -> dict[str, Any]:
    return _carregar("parametros.yaml")


@pytest.fixture(scope="module")
def hardware() -> dict[str, Any]:
    return _carregar("parametros.hardware.yaml")


@pytest.mark.parametrize(
    ("chave", "esperado"),
    [
        ("raio_deteccao_m", 500),
        ("tempo_antecipacao_margem_s", 5.0),
        ("verde_min_s", 7.0),
        ("verde_max_s", 60.0),
        ("amarelo_s", 3.0),
        ("all_red_s", 2.0),
        ("preempcao_timeout_s", 45.0),
        ("n_ciclos_compensacao", 2),
        ("ganho_compensacao_k", 0.7),
        ("velocidade_min_estimativa_ms", 4.0),
        ("prioridade_tipo", ["AMBULANCIA", "BOMBEIRO", "POLICIA"]),
    ],
)
def test_perfil_simulacao_bate_com_context_01(
    simulacao: dict[str, Any], chave: str, esperado: object
) -> None:
    """Cada valor de context/01 §5.3 está presente e inalterado."""
    assert simulacao[chave] == esperado


def test_perfil_simulacao_traz_limites_dos_invariantes(simulacao: dict[str, Any]) -> None:
    """I5 e I6 (context/01 §6) também são parâmetros, não números soltos no código."""
    assert simulacao["vermelho_max_s"] == 120.0
    assert simulacao["watchdog_s"] == 3.0


def test_orcamentos_de_latencia_seguem_a_decisao_p2(simulacao: dict[str, Any]) -> None:
    """RNF01 e H3 são métricas distintas e coexistem (decisão P2, context/09)."""
    assert simulacao["latencia_decisao_p95_max_ms"] == 100
    assert simulacao["latencia_fim_a_fim_p95_max_ms"] == 200


def test_perfil_hardware_e_sobreposicao_enxuta(
    hardware: dict[str, Any], simulacao: dict[str, Any]
) -> None:
    """O perfil de bancada só redefine o que muda; o resto é herdado."""
    assert set(hardware) < set(simulacao) | {"verde_s", "n_fases_prototipo"}
    assert "raio_deteccao_m" not in hardware


def test_ciclo_da_bancada_leva_24_segundos(hardware: dict[str, Any]) -> None:
    """4 fases x (verde + amarelo + all-red) = 24 s — decisão P13, contrato §7."""
    por_fase = hardware["verde_s"] + hardware["amarelo_s"] + hardware["all_red_s"]
    assert hardware["n_fases_prototipo"] * por_fase == 24.0


def test_bancada_nunca_trunca_verde(hardware: dict[str, Any]) -> None:
    """`verde_s == verde_min_s` é o que dispensa o caminho de truncamento no firmware."""
    assert hardware["verde_s"] == hardware["verde_min_s"] == 3.0


def test_simulacao_permite_truncamento_de_verde(simulacao: dict[str, Any]) -> None:
    """No perfil que gera os dados, I4 é exercitado de verdade."""
    assert simulacao["verde_min_s"] < simulacao["verde_max_s"]
