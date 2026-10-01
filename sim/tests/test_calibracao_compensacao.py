"""Calibração de E7 — `sim/calibracao/compensacao.py` (P17).

Puro: os CSV são escritos à mão com valores redondos, obviamente artificiais
(`context/08` §4.2). O que se testa é que o código implementa o critério
commitado antes dele — a grade, a conta de `M` e a regra de escolha —, e não
outro.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from sim.calibracao import compensacao as cal
from sim.controlador import executor
from sim.controlador.coletor import ARQUIVO_EXECUCOES

SEEDS = (101, 102)
CAMPOS = (
    "cenario",
    "modo",
    "seed",
    "tempo_espera_medio_transversal_s",
    "tempo_medio_travessia_ve_s",
    "colisoes",
    "teleportes",
    "violacoes",
)


def _escrever(arquivo: Path, linhas: list[tuple[str, str, int, float]]) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    with arquivo.open("w", encoding="utf-8", newline="") as saida:
        escritor = csv.writer(saida)
        escritor.writerow(CAMPOS)
        for cenario, modo, seed, espera in linhas:
            escritor.writerow((cenario, modo, seed, espera, 300.0, 0, 0, 0))


def _baselines(raiz: Path) -> None:
    """FIXO 10 s e PREEMPCAO 20 s nos dois cenários: acréscimo de 10 s."""
    _escrever(
        raiz / ARQUIVO_EXECUCOES,
        [
            (cenario, modo, seed, espera)
            for cenario in cal.CENARIOS
            for modo, espera in (("FIXO", 10.0), ("PREEMPCAO", 20.0))
            for seed in SEEDS
        ],
    )


def _compensada(raiz: Path, k: float, n: int, espera_por_cenario: dict[str, float]) -> None:
    pasta = raiz / executor.rotulo_dos_ajustes(cal.ajustes_de(k, n))
    _escrever(
        pasta / ARQUIVO_EXECUCOES,
        [
            (cenario, "PREEMPCAO_COMPENSADA", seed, espera)
            for cenario, espera in espera_por_cenario.items()
            for seed in SEEDS
        ],
    )


# --- a grade é a declarada --------------------------------------------------


def test_grade_e_a_declarada_no_criterio() -> None:
    """`context/09` P17, commit 09c1c8d. Mudar aqui exige mudar lá, antes de rodar."""
    assert cal.GRADE_K == (0.25, 0.5, 0.7, 1.0, 1.5)
    assert cal.GRADE_N == (1, 2, 3)
    assert cal.CENARIOS == ("moderado", "intenso")
    assert cal.SEEDS == (101, 102, 103, 104, 105)
    assert len(cal.combinacoes()) == 15


def test_seeds_fora_do_bloco_8() -> None:
    """Guarda de P16: calibrar sobre 1..50 contaminaria a amostra que valida."""
    assert all(seed > 50 for seed in cal.SEEDS)


def test_matriz_tem_170_execucoes() -> None:
    """20 de baseline (2 braços x 2 cenários x 5 seeds) + 150 compensadas."""
    pontos = cal.pontos()
    assert len(pontos) == 170
    assert len(set(pontos)) == 170
    assert sum(1 for p in pontos if not p.ajustes) == 20
    assert all(p.modo == "PREEMPCAO_COMPENSADA" for p in pontos if p.ajustes)


def test_baselines_nao_tem_ajuste() -> None:
    """FIXO e PREEMPCAO não dependem de K nem de n: rodam uma vez só."""
    assert all(not p.ajustes for p in cal.pontos() if p.modo != "PREEMPCAO_COMPENSADA")


# --- a conta ----------------------------------------------------------------


def test_mitigacao_e_a_fracao_do_acrescimo(tmp_path: Path) -> None:
    """Compensada 18 s, preempção 20 s, fixo 10 s: devolveu 2 de 10 s = 20%."""
    _baselines(tmp_path)
    for k, n in cal.combinacoes():
        _compensada(tmp_path, k, n, {"moderado": 18.0, "intenso": 18.0})
    _, avaliacoes = cal.avaliar(tmp_path, SEEDS)
    assert avaliacoes[0].mitigacao == {
        "moderado": pytest.approx(0.2),
        "intenso": pytest.approx(0.2),
    }
    assert avaliacoes[0].pontuacao == pytest.approx(0.2)


def test_pontuacao_e_a_media_dos_dois_cenarios(tmp_path: Path) -> None:
    _baselines(tmp_path)
    for k, n in cal.combinacoes():
        _compensada(tmp_path, k, n, {"moderado": 20.0, "intenso": 15.0})
    _, avaliacoes = cal.avaliar(tmp_path, SEEDS)
    assert avaliacoes[0].pontuacao == pytest.approx((0.0 + 0.5) / 2)


def test_compensacao_que_piora_da_mitigacao_negativa(tmp_path: Path) -> None:
    _baselines(tmp_path)
    for k, n in cal.combinacoes():
        _compensada(tmp_path, k, n, {"moderado": 21.0, "intenso": 21.0})
    _, avaliacoes = cal.avaliar(tmp_path, SEEDS)
    assert avaliacoes[0].pontuacao == pytest.approx(-0.1)


# --- a regra de escolha -----------------------------------------------------


def test_escolhe_a_maior_pontuacao(tmp_path: Path) -> None:
    _baselines(tmp_path)
    for k, n in cal.combinacoes():
        espera = 15.0 if (k, n) == (1.0, 3) else 19.0
        _compensada(tmp_path, k, n, {"moderado": espera, "intenso": espera})
    _, avaliacoes = cal.avaliar(tmp_path, SEEDS)
    escolhida = cal.escolher(avaliacoes)
    assert escolhida is not None
    assert (escolhida.k, escolhida.n) == (1.0, 3)


def test_empate_exato_prefere_menor_n_e_depois_menor_k(tmp_path: Path) -> None:
    _baselines(tmp_path)
    for k, n in cal.combinacoes():
        _compensada(tmp_path, k, n, {"moderado": 15.0, "intenso": 15.0})
    _, avaliacoes = cal.avaliar(tmp_path, SEEDS)
    escolhida = cal.escolher(avaliacoes)
    assert escolhida is not None
    assert (escolhida.k, escolhida.n) == (0.25, 1)


def test_escolhe_mesmo_abaixo_da_meta(tmp_path: Path) -> None:
    """Regra de parada: congela-se a melhor, ainda que negativa. Não há 2ª rodada."""
    _baselines(tmp_path)
    for k, n in cal.combinacoes():
        _compensada(tmp_path, k, n, {"moderado": 22.0, "intenso": 22.0})
    _, avaliacoes = cal.avaliar(tmp_path, SEEDS)
    assert cal.escolher(avaliacoes) is not None


def test_combinacao_com_execucao_perdida_e_eliminada(tmp_path: Path) -> None:
    """Regra 3: a reprovada não entra no CSV, e a combinação sai da disputa."""
    _baselines(tmp_path)
    for k, n in cal.combinacoes():
        _compensada(tmp_path, k, n, {"moderado": 19.0, "intenso": 19.0})
    melhor = tmp_path / executor.rotulo_dos_ajustes(cal.ajustes_de(1.5, 3)) / ARQUIVO_EXECUCOES
    _escrever(melhor, [("moderado", "PREEMPCAO_COMPENSADA", 101, 10.0)])

    _, avaliacoes = cal.avaliar(tmp_path, SEEDS)
    eliminada = next(a for a in avaliacoes if (a.k, a.n) == (1.5, 3))
    assert eliminada.eliminada
    assert eliminada.pontuacao is None
    escolhida = cal.escolher(avaliacoes)
    assert escolhida is not None and (escolhida.k, escolhida.n) != (1.5, 3)


def test_baseline_incompleto_falha_alto(tmp_path: Path) -> None:
    _escrever(tmp_path / ARQUIVO_EXECUCOES, [("moderado", "FIXO", 101, 10.0)])
    with pytest.raises(cal.CalibracaoIncompletaError, match="moderado/FIXO"):
        cal.avaliar(tmp_path, SEEDS)


def test_grava_os_dois_csv(tmp_path: Path) -> None:
    _baselines(tmp_path)
    for k, n in cal.combinacoes():
        _compensada(tmp_path, k, n, {"moderado": 18.0, "intenso": 18.0})
    base, avaliacoes = cal.avaliar(tmp_path, SEEDS)
    escolhida = cal.escolher(avaliacoes)
    cal.gravar(tmp_path, base, avaliacoes, escolhida)

    with (tmp_path / cal.ARQUIVO_RESULTADO).open(encoding="utf-8") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    assert len(linhas) == 15
    assert sum(int(linha["escolhida"]) for linha in linhas) == 1
    assert (tmp_path / cal.ARQUIVO_BASELINES).is_file()
