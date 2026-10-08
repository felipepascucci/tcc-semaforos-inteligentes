"""Análise de H4, entrega 10.8 (`analysis/analise_h4.py`), com dado sintético."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from analysis.analise_h4 import (
    DESFAVORAVEL,
    FAVORAVEL,
    NULO,
    analisar,
    contar_disputas,
    gerar_markdown,
    main,
    veredito,
)
from analysis.carregar import DadosInvalidosError, ler_pasta
from analysis.estatistica import comparar_pareado
from analysis.tests.lote_sintetico import SEEDS, escrever_lote


def test_conta_o_denominador_de_cada_braco(tmp_path: Path) -> None:
    dados = ler_pasta(escrever_lote(tmp_path))

    base = contar_disputas(dados, "PREEMPCAO")
    ml = contar_disputas(dados, "PREEMPCAO_ML")

    assert base.disputas == 2 * len(SEEDS)
    assert base.mesmo_nivel == 2 * len(SEEDS)
    assert base.mesmo_nivel_decidiveis == len(SEEDS)
    assert base.mesmo_nivel_sob_preempcao == len(SEEDS)
    assert ml.mesmo_nivel == len(SEEDS)
    assert ml.decididas_pelo_modelo == len(SEEDS)
    assert ml.divergentes_do_e8 == len(SEEDS) // 2
    assert ml.execucoes_com_divergencia == len(SEEDS) // 2


def test_recusa_dado_anterior_a_p20(tmp_path: Path) -> None:
    pasta = escrever_lote(tmp_path)
    conflitos = pd.read_csv(pasta / "conflitos_por_execucao.csv")
    conflitos.drop(columns=["mesmo_nivel"]).to_csv(
        pasta / "conflitos_por_execucao.csv", index=False
    )

    with pytest.raises(DadosInvalidosError, match="P20"):
        contar_disputas(ler_pasta(pasta), "PREEMPCAO")


def test_ganho_do_modelo_e_favoravel(tmp_path: Path) -> None:
    resultado = analisar(ler_pasta(escrever_lote(tmp_path, ganho_ml_s=5.0)), reamostragens=200)

    assert resultado.comparacao is not None
    assert resultado.comparacao.mediana_diferenca == pytest.approx(-5.0)
    assert veredito(resultado.comparacao, resultado.comparacao.p_wilcoxon) == FAVORAVEL
    assert resultado.seeds_com_divergencia == tuple(s for s in SEEDS if s % 2 == 0)
    assert resultado.exploratoria is not None


def test_bracos_iguais_dao_nulo(tmp_path: Path) -> None:
    resultado = analisar(ler_pasta(escrever_lote(tmp_path, ganho_ml_s=0.0)), reamostragens=200)

    assert resultado.seeds_identicas == len(SEEDS)
    assert veredito(resultado.comparacao, resultado.comparacao.p_wilcoxon) == NULO  # type: ignore[union-attr]


def test_veredito_pela_regra_declarada() -> None:
    piora = comparar_pareado([110.0 + i for i in range(12)], [100.0 + i for i in range(12)],
                             reamostragens=100)  # fmt: skip
    assert veredito(piora, 0.001) == DESFAVORAVEL
    assert veredito(piora, 0.2) == NULO
    assert veredito(None, 0.001) == NULO


def test_relatorio_declara_o_denominador_e_o_veredito(tmp_path: Path) -> None:
    resultado = analisar(ler_pasta(escrever_lote(tmp_path)), reamostragens=200)
    texto = gerar_markdown(resultado)

    assert "Decididas pelo modelo" in texto
    assert "sob preempção em curso" in texto
    assert FAVORAVEL in texto
    assert "Exploratória" in texto


def test_cli_escreve_o_relatorio(tmp_path: Path) -> None:
    pasta = escrever_lote(tmp_path / "dados")
    destino = tmp_path / "h4.md"

    assert main(["--dados", str(pasta), "--saida", str(destino)]) == 0
    assert "H4" in destino.read_text(encoding="utf-8")


def test_cli_sem_dados_falha_com_mensagem(tmp_path: Path) -> None:
    assert main(["--dados", str(tmp_path)]) == 1
