"""Testes das métricas da política de desempate (Guia do Usuário v2.0, Seção 4)."""

from __future__ import annotations

from pathlib import Path

import pytest

np = pytest.importorskip("numpy", reason="extra analysis não instalado")
pd = pytest.importorskip("pandas", reason="extra analysis não instalado")
pytest.importorskip("scipy", reason="extra analysis não instalado")

from analysis import metricas_politica as mp  # noqa: E402
from analysis import treino_politica as tp  # noqa: E402

AVALIACAO = tp.SAIDA_DADOS / "avaliacao.csv"


def test_matriz_e_metricas_de_um_caso_feito_a_mao() -> None:
    y = np.array([1.0, 1.0, 1.0, -1.0, -1.0])
    previsto = np.array([1.0, 1.0, -1.0, -1.0, 1.0])
    matriz = mp.matriz_confusao(y, previsto)
    assert matriz.loc["A"].tolist() == [2, 1]
    assert matriz.loc["B"].tolist() == [1, 1]

    tabela = mp.metricas(matriz).set_index("classe")
    assert tabela.loc["A", "precisao"] == pytest.approx(2 / 3)
    assert tabela.loc["A", "revocacao"] == pytest.approx(2 / 3)
    assert tabela.loc["B", "precisao"] == pytest.approx(1 / 2)
    assert tabela.loc["B", "revocacao"] == pytest.approx(1 / 2)
    assert tabela.loc["B", "f1"] == pytest.approx(1 / 2)
    assert tabela.loc["macro", "f1"] == pytest.approx((2 / 3 + 1 / 2) / 2)
    assert tabela["acuracia"].tolist() == pytest.approx([3 / 5] * 3)


def test_classe_nunca_escolhida_tem_precisao_indefinida() -> None:
    matriz = mp.matriz_confusao(np.array([1.0, -1.0]), np.array([1.0, 1.0]))
    tabela = mp.metricas(matriz).set_index("classe")
    assert np.isnan(tabela.loc["B", "precisao"])
    assert tabela.loc["B", "revocacao"] == 0.0


def test_saida_confere_com_a_avaliacao_do_treino(tmp_path: Path) -> None:
    """Os acertos e as escolhas de B batem com o `avaliacao.csv` versionado do treino."""
    assert mp.main(["--saida", str(tmp_path)]) == 0
    avaliacao = pd.read_csv(AVALIACAO)
    modelo = avaliacao[(avaliacao["politica"] == "modelo") & (avaliacao["cruzamento"] == "todos")]
    matriz = pd.read_csv(tmp_path / "matriz_confusao.csv")
    for _, esperado in modelo.iterrows():
        parte = matriz[matriz["divisao"] == esperado["divisao"]].set_index("rotulo")
        assert int(parte.to_numpy()[:, 1:].sum()) == esperado["exemplos"]
        assert int(parte.loc["A", "A"] + parte.loc["B", "B"]) == esperado["acertos"]
        assert int(parte["B"].sum()) == esperado["escolhe_b"]

    predicoes = pd.read_csv(tmp_path / "predicoes.csv")
    assert (predicoes["score"] > 0).eq(predicoes["escolha_modelo"] == "A").all()
    assert predicoes["acerto"].eq(predicoes["rotulo"] == predicoes["escolha_modelo"]).all()


def test_identificacao_alinhada_com_os_atributos_do_treino() -> None:
    from analysis.resumo_rotulos import ARQUIVO_ROTULOS, divisao_de_seeds

    divisao = divisao_de_seeds()
    caminho = tp.DADOS / ARQUIVO_ROTULOS
    conjuntos = tp.ler_conjuntos(caminho, divisao)
    ident = mp.identificacao(caminho, divisao)
    tabela = pd.read_csv(caminho)
    for nome, conjunto in conjuntos.items():
        assert len(ident[nome]) == len(conjunto)
        assert (ident[nome]["id_semaforo"].to_numpy(str) == conjunto.id_semaforo).all()
        # A primeira coluna de x é eta_a - eta_b da mesma linha identificada.
        linhas = tabela.set_index(["seed", "t_s", "ve_a", "ve_b"]).loc[
            list(ident[nome][["seed", "t_s", "ve_a", "ve_b"]].itertuples(index=False))
        ]
        assert np.allclose(conjunto.x[:, 0], (linhas["eta_a_s"] - linhas["eta_b_s"]).to_numpy())


def test_nao_escreve_nos_artefatos_versionados(tmp_path: Path) -> None:
    pesos = tp.ARQUIVO_PESOS
    antes = {p: p.stat().st_mtime_ns for p in [pesos, *tp.SAIDA_DADOS.glob("*")]}
    mp.main(["--saida", str(tmp_path)])
    assert {p: p.stat().st_mtime_ns for p in antes} == antes
