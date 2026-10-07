"""O resumo dos rótulos da entrega 10.4."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from analysis.resumo_rotulos import (
    ARQUIVO_ROTULOS,
    Rotulo,
    divisao_de_seeds,
    gerar_relatorio,
    ler_rotulos,
)
from sim.controlador.rotulagem import COLUNAS

DIVISAO = {"treino": (201, 202), "validacao": (203, 203)}


def _rotulo(
    seed: int = 201,
    rotulo: str = "A",
    escolha_e8: str = "A",
    se_a: float | None = 200.0,
    se_b: float | None = 210.0,
    fiel: bool = True,
) -> Rotulo:
    return Rotulo(
        seed=seed,
        id_semaforo="CRUZ_TESTE",
        escolha_e8=escolha_e8,
        minimax_se_a_s=se_a,
        minimax_se_b_s=se_b,
        replay_fiel=fiel,
        rotulo=rotulo,
        motivo_descarte="" if rotulo != "DESCARTADA" else "motivo de teste",
    )


def test_custo_do_e8_e_zero_quando_acerta_e_a_margem_quando_erra() -> None:
    assert _rotulo(rotulo="A", escolha_e8="A").custo_do_e8_s == 0.0
    assert _rotulo(rotulo="A", escolha_e8="B").custo_do_e8_s == 10.0
    assert _rotulo(rotulo="EMPATE", se_a=200.0, se_b=200.0).custo_do_e8_s is None


def test_so_a_e_b_viram_exemplo() -> None:
    assert _rotulo(rotulo="A").treinavel
    assert _rotulo(rotulo="B").treinavel
    assert not _rotulo(rotulo="EMPATE").treinavel
    assert not _rotulo(rotulo="DESCARTADA", se_b=None).treinavel


def test_relatorio_separa_treino_e_validacao() -> None:
    rotulos = [
        _rotulo(seed=201, rotulo="A", escolha_e8="A"),
        _rotulo(seed=202, rotulo="B", escolha_e8="A", se_a=230.0, se_b=200.0),
        _rotulo(seed=202, rotulo="EMPATE", se_a=200.0, se_b=200.0),
        _rotulo(seed=203, rotulo="A", escolha_e8="B"),
    ]

    relatorio = gerar_relatorio(rotulos, DIVISAO)

    assert "## Treino (seeds 201..202)" in relatorio
    assert "Exemplos de treino (A ou B): 2" in relatorio
    assert "E8 faz a escolha do rótulo em 1 de 2 (50.0%)" in relatorio
    assert "## Validacao (seeds 203..203)" in relatorio
    assert "Não é resultado de H4" in relatorio


def test_relatorio_conta_reexecucao_infiel() -> None:
    relatorio = gerar_relatorio([_rotulo(), _rotulo(fiel=False, rotulo="DESCARTADA")], DIVISAO)

    assert "Reexecução fiel: 1 de 2" in relatorio


def test_leitura_do_csv_da_rotulagem(tmp_path: Path) -> None:
    """O resumo lê exatamente as colunas que a rotulagem escreve."""
    linha = dict.fromkeys(COLUNAS, "")
    linha.update(
        seed="201",
        id_semaforo="CRUZ_02",
        escolha_e8="B",
        minimax_se_a_s="250.5",
        minimax_se_b_s="240.0",
        replay_fiel="1",
        rotulo="B",
    )
    with (tmp_path / ARQUIVO_ROTULOS).open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS)
        escritor.writeheader()
        escritor.writerow(linha)

    (lido,) = ler_rotulos(tmp_path / ARQUIVO_ROTULOS)

    assert lido.rotulo == "B"
    assert lido.margem_s == pytest.approx(10.5)
    assert lido.custo_do_e8_s == 0.0


def test_divisao_vem_do_cenarios_yaml() -> None:
    assert divisao_de_seeds() == {"treino": (201, 240), "validacao": (241, 250)}
