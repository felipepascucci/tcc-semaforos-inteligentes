"""Leitura e pareamento dos CSV do lote (`analysis/carregar.py`)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from analysis.carregar import (
    DadosInvalidosError,
    fila_maxima_transversal,
    indice_do_par,
    ler_pasta,
    pior_ve_pareado,
    por_seed,
    travessia_pareada,
)
from analysis.tests.lote_sintetico import MULTIPLAS, SEEDS, escrever_lote


def test_le_a_pasta_e_ordena_cenarios_e_modos(tmp_path: Path) -> None:
    dados = ler_pasta(escrever_lote(tmp_path))

    assert dados.cenarios() == ["moderado", "intenso", MULTIPLAS]
    assert dados.modos(MULTIPLAS) == ["FIXO", "PREEMPCAO", "PREEMPCAO_ML"]
    assert dados.versoes == ["teste00"]


def test_recusa_ponto_duplicado(tmp_path: Path) -> None:
    pasta = escrever_lote(tmp_path, com_multiplas=False)
    execucoes = pd.read_csv(pasta / "execucoes.csv")
    pd.concat([execucoes, execucoes.head(1)]).to_csv(pasta / "execucoes.csv", index=False)

    with pytest.raises(DadosInvalidosError, match="duplicados"):
        ler_pasta(pasta)


def test_recusa_pasta_sem_execucoes(tmp_path: Path) -> None:
    with pytest.raises(DadosInvalidosError, match="não achei"):
        ler_pasta(tmp_path)


def test_travessia_pareada_media_sobre_os_ves_comuns(tmp_path: Path) -> None:
    dados = ler_pasta(escrever_lote(tmp_path))
    pareada = travessia_pareada(dados, "moderado", ["FIXO", "PREEMPCAO"])

    assert list(pareada.por_seed.index) == list(SEEDS)
    assert pareada.por_seed.loc[1, "FIXO"] == 401.0
    assert pareada.por_seed.loc[1, "PREEMPCAO"] == 281.0
    assert pareada.ves_comuns == 2 * len(SEEDS)
    assert pareada.ves_descartados == 0


def test_travessia_pareada_descarta_o_ve_que_falta_num_braco(tmp_path: Path) -> None:
    """O `TRANSVERSAL_02` só chegou no `PREEMPCAO`: sai da média e é contado."""
    dados = ler_pasta(escrever_lote(tmp_path))
    pareada = travessia_pareada(dados, MULTIPLAS, ["FIXO", "PREEMPCAO", "PREEMPCAO_ML"])

    assert pareada.ves_descartados == len(SEEDS)
    assert pareada.ves_comuns == 4 * len(SEEDS)


def test_indice_do_par() -> None:
    assert indice_do_par("VE_ROTA_VE_CORREDOR_03") == "03"
    assert indice_do_par("SEM_SUFIXO") is None


def test_pior_ve_e_o_maior_tempo_do_par_media_sobre_os_pares(tmp_path: Path) -> None:
    dados = ler_pasta(escrever_lote(tmp_path, ganho_ml_s=5.0))
    pior = pior_ve_pareado(dados, MULTIPLAS, ["PREEMPCAO", "PREEMPCAO_ML"])

    # Corredor 250 + seed contra transversal 150 + seed: o pior é o corredor.
    assert pior.por_seed.loc[1, "PREEMPCAO"] == 251.0
    assert pior.por_seed.loc[1, "PREEMPCAO_ML"] == 246.0
    assert pior.pares_comuns == 2 * len(SEEDS)
    assert pior.pares_descartados == len(SEEDS)  # o par 02, incompleto


def test_por_seed_so_com_os_bracos_todos(tmp_path: Path) -> None:
    dados = ler_pasta(escrever_lote(tmp_path, com_multiplas=False))
    tabela = por_seed(dados, "intenso", "tempo_espera_medio_transversal_s", ["FIXO", "PREEMPCAO"])

    assert tabela.shape == (len(SEEDS), 2)
    assert tabela.loc[10, "PREEMPCAO"] == pytest.approx(15.0)


def test_fila_maxima_so_dos_acessos_transversais(tmp_path: Path) -> None:
    dados = ler_pasta(escrever_lote(tmp_path, com_multiplas=False))
    filas = fila_maxima_transversal(dados)

    assert set(filas["fila_maxima"]) == {5}
