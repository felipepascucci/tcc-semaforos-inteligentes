"""Ajustes de parâmetro por execução — `sim/controlador/executor.py` (P17).

Puro: não sobe SUMO. Os ajustes existem para a calibração de E7, e o que se
testa é que eles não abrem brecha: só os parâmetros de E7 mudam, nada é
truncado em silêncio, e execução ajustada não grava no banco.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.configuracao import carregar as carregar_parametros
from core.excecoes import ConfiguracaoInvalidaError
from sim.controlador import executor


@pytest.fixture
def base():  # type: ignore[no-untyped-def]
    return carregar_parametros("simulacao")


def test_sem_ajuste_devolve_os_parametros_do_yaml(base) -> None:  # type: ignore[no-untyped-def]
    assert executor.aplicar_ajustes(base, ()) is base


def test_ajuste_substitui_os_dois_parametros_de_e7(base) -> None:  # type: ignore[no-untyped-def]
    ajustados = executor.aplicar_ajustes(
        base, (("ganho_compensacao_k", 1.5), ("n_ciclos_compensacao", 3.0))
    )
    assert ajustados.ganho_compensacao_k == 1.5
    assert ajustados.n_ciclos_compensacao == 3
    assert isinstance(ajustados.n_ciclos_compensacao, int)
    assert ajustados.verde_min_s == base.verde_min_s


def test_parametro_fora_de_e7_e_recusado(base) -> None:  # type: ignore[no-untyped-def]
    """Qualquer outro parâmetro só muda por commit no YAML."""
    with pytest.raises(ValueError, match="não ajustável: verde_min_s"):
        executor.aplicar_ajustes(base, (("verde_min_s", 5.0),))


def test_ajuste_repetido_e_recusado(base) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match="mais de uma vez"):
        executor.aplicar_ajustes(base, (("ganho_compensacao_k", 0.5), ("ganho_compensacao_k", 1.0)))


def test_inteiro_com_fracao_nao_e_truncado(base) -> None:  # type: ignore[no-untyped-def]
    """Truncar 2,5 para 2 mudaria o ponto da grade sem ninguém ver."""
    with pytest.raises(ValueError, match="inteiro"):
        executor.aplicar_ajustes(base, (("n_ciclos_compensacao", 2.5),))


def test_ajuste_incoerente_e_recusado_pela_validacao(base) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ConfiguracaoInvalidaError, match="ganho_compensacao_k"):
        executor.aplicar_ajustes(base, (("ganho_compensacao_k", -1.0),))


def test_preempcao_continua_sem_compensar_mesmo_com_ajuste(base) -> None:  # type: ignore[no-untyped-def]
    """O braço de controle de H2 não pode ser contaminado pela grade."""
    ajustados = executor.aplicar_ajustes(base, (("n_ciclos_compensacao", 3.0),))
    assert executor.parametros_do_modo("PREEMPCAO", ajustados).n_ciclos_compensacao == 0


def test_rotulo_e_estavel_e_independe_da_ordem() -> None:
    a = executor.rotulo_dos_ajustes((("n_ciclos_compensacao", 2.0), ("ganho_compensacao_k", 0.5)))
    b = executor.rotulo_dos_ajustes((("ganho_compensacao_k", 0.5), ("n_ciclos_compensacao", 2.0)))
    assert a == b == "ganho_compensacao_k-0.5__n_ciclos_compensacao-2"
    assert executor.rotulo_dos_ajustes(()) == ""


def test_pasta_sem_ajuste_e_a_de_sempre(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(executor, "SAIDA", tmp_path)
    assert executor.pasta_de_saida("leve", "FIXO", 1) == tmp_path / "leve_FIXO_1"


def test_combinacoes_diferentes_nao_dividem_pasta(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Rodam em paralelo; na mesma pasta, uma sobrescreveria o tripinfo da outra."""
    monkeypatch.setattr(executor, "SAIDA", tmp_path)
    uma = executor.pasta_de_saida(
        "leve", "PREEMPCAO_COMPENSADA", 1, (("ganho_compensacao_k", 0.5),)
    )
    outra = executor.pasta_de_saida(
        "leve", "PREEMPCAO_COMPENSADA", 1, (("ganho_compensacao_k", 1.0),)
    )
    assert uma != outra


def test_execucao_ajustada_nao_grava_no_banco() -> None:
    """O snapshot de execucao_simulacao é o do YAML; a linha mentiria."""
    opcoes = executor.Opcoes(
        cenario="leve",
        modo="PREEMPCAO_COMPENSADA",
        seed=1,
        persistir=True,
        ajustes=(("ganho_compensacao_k", 1.0),),
    )
    with pytest.raises(ValueError, match="execucao_simulacao"):
        executor.executar(opcoes)
