"""O capítulo 5 gerado de ponta a ponta sobre um lote sintético."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from analysis.carregar import ler_pasta
from analysis.gerar_resultados_tcc import (
    ACEITA,
    CRUZAMENTO_FIGURAS,
    PARCIAL,
    REJEITADA,
    calcular,
    fidelidade_do_traco,
    gerar,
    ler_traco,
    main,
    tabela_t6,
    veredito_h1,
    veredito_h2,
)
from analysis.tabelas import Tabela, escapar_latex, pct_sinal
from analysis.tests.lote_sintetico import ESPERA, SEEDS, escrever_lote
from core.modelos import Sinal, Transicao
from sim.controlador.traco import Traco, gravar

VC = {"moderado": 0.4, "intenso": 0.7, "multiplas_emergencias": 0.4}


def test_reducao_e_mitigacao_acima_das_metas_aceitam_h1_e_h2(tmp_path: Path) -> None:
    r = calcular(ler_pasta(escrever_lote(tmp_path)), vc=VC, reamostragens=200)

    # (400 + s - 280 - s) / (400 + s): entre 29,3% e 29,9%.
    assert 0.29 < r.reducoes[("moderado", "PREEMPCAO")].media < 0.30
    # Espera 10, 14 e 13: devolve 1 de 4 segundos de acréscimo.
    assert r.mitigacoes["intenso"].mitigacao == pytest.approx(0.25)
    assert veredito_h1(r) == ACEITA
    assert veredito_h2(r) == ACEITA


def test_h1_parcial_quando_so_um_cenario_atinge(tmp_path: Path) -> None:
    pasta = escrever_lote(tmp_path, com_multiplas=False)
    ves = pd.read_csv(pasta / "ve_por_execucao.csv")
    lento = (ves["cenario"] == "intenso") & (ves["modo"] == "PREEMPCAO")
    ves.loc[lento, "tempo_viagem_s"] = ves.loc[lento, "tempo_viagem_s"] + 80.0  # ~10%
    ves.to_csv(pasta / "ve_por_execucao.csv", index=False)

    r = calcular(ler_pasta(pasta), reamostragens=200)

    assert veredito_h1(r) == PARCIAL


def test_h2_rejeitada_quando_a_compensacao_devolve_pouco(tmp_path: Path) -> None:
    espera = {**ESPERA, "PREEMPCAO_COMPENSADA": 13.8}
    r = calcular(ler_pasta(escrever_lote(tmp_path, espera=espera)), reamostragens=200)

    assert r.mitigacoes["moderado"].mitigacao == pytest.approx(0.05)
    assert veredito_h2(r) == REJEITADA


def test_holm_cobre_o_capitulo_inteiro(tmp_path: Path) -> None:
    r = calcular(ler_pasta(escrever_lote(tmp_path)), reamostragens=200)

    # T1: 2 + 2 + 2; T3: 3 + 3 + 2; H4: 1.
    assert len(r.comparacoes) == 15
    assert all(c.p_holm >= c.resultado.p_wilcoxon for c in r.comparacoes)


def test_t6_traz_as_seis_linhas_e_o_veredito_de_h4(tmp_path: Path) -> None:
    r = calcular(ler_pasta(escrever_lote(tmp_path)), bancada=[20.0] * 100, reamostragens=200)
    linhas = {linha[0]: linha for linha in tabela_t6(r).linhas}

    assert set(linhas) == {"H1", "H1 (exploratório)", "H2", "H3", "RNF01", "H4"}
    assert linhas["H3"][3] == ACEITA
    assert linhas["RNF01"][3] == "ATENDE"
    assert linhas["H4"][3] == "FAVORÁVEL"


def test_gerar_escreve_a_pasta_inteira(tmp_path: Path) -> None:
    dados = ler_pasta(escrever_lote(tmp_path / "dados"))
    saida = tmp_path / "saida"

    destino = gerar(dados, saida, vc=VC, reamostragens=200)

    texto = destino.read_text(encoding="utf-8")
    assert "Caracterização das execuções" in texto
    assert "T4 adaptada" in texto
    assert "sem o traço" in texto
    for codigo in ("T1", "T1b", "T2", "T3", "T3b", "T4", "T5", "T6"):
        assert (saida / "tabelas" / f"{codigo}.tex").is_file()
    assert (saida / "h4.md").is_file()
    assert (saida / "figuras" / "F1_travessia_ve.pdf").is_file()
    assert (saida / "figuras" / "F5_reducao_saturacao.pdf").is_file()
    with (saida / "comparacoes.csv").open(encoding="utf-8") as arquivo:
        assert len(list(csv.DictReader(arquivo))) == 15


def test_mesmo_dado_da_os_mesmos_arquivos(tmp_path: Path) -> None:
    """Reprodutibilidade: o bootstrap tem semente fixa e o PDF não leva data."""
    dados = ler_pasta(escrever_lote(tmp_path / "dados"))
    primeira = gerar(dados, tmp_path / "a", vc=VC, reamostragens=200)
    segunda = gerar(dados, tmp_path / "b", vc=VC, reamostragens=200)

    assert primeira.read_bytes() == segunda.read_bytes()
    assert (tmp_path / "a" / "comparacoes.csv").read_bytes() == (
        tmp_path / "b" / "comparacoes.csv"
    ).read_bytes()
    assert (tmp_path / "a" / "figuras" / "F1_travessia_ve.pdf").read_bytes() == (
        tmp_path / "b" / "figuras" / "F1_travessia_ve.pdf"
    ).read_bytes()


def test_traco_que_confere_com_o_lote(tmp_path: Path) -> None:
    dados = ler_pasta(escrever_lote(tmp_path / "dados", com_multiplas=False))
    tracos = [
        Traco(modo=modo, viagens=[(f"VE_TESTE_0{i}", base + 1) for i in range(2)])
        for modo, base in (("FIXO", 400.0), ("PREEMPCAO", 280.0))
    ]
    gravar(tracos, "intenso", 1, tmp_path / "traco")

    traco = ler_traco(tmp_path / "traco")
    assert traco is not None
    comparados, divergentes, _ = fidelidade_do_traco(traco, dados)
    assert (comparados, divergentes) == (4, 0)

    tracos[1].viagens[0] = ("VE_TESTE_00", 300.0)
    gravar(tracos, "intenso", 1, tmp_path / "traco")
    _, divergentes, maior = fidelidade_do_traco(ler_traco(tmp_path / "traco"), dados)  # type: ignore[arg-type]
    assert divergentes == 1
    assert maior == pytest.approx(19.0)


def test_com_o_traco_gera_f3_f4_e_f6(tmp_path: Path) -> None:
    dados = ler_pasta(escrever_lote(tmp_path / "dados", com_multiplas=False))
    tracos = []
    for modo, velocidade in (("FIXO", 5.0), ("PREEMPCAO", 10.0)):
        sinal = [Transicao(CRUZAMENTO_FIGURAS, 0.0, 1, Sinal.VERDE)]
        if modo == "PREEMPCAO":
            sinal += [
                Transicao(CRUZAMENTO_FIGURAS, 400.0, 1, Sinal.AMARELO, em_preempcao=True),
                Transicao(CRUZAMENTO_FIGURAS, 403.0, 1, Sinal.VERMELHO, em_preempcao=True),
                Transicao(CRUZAMENTO_FIGURAS, 405.0, 2, Sinal.VERDE, em_preempcao=True),
                Transicao(CRUZAMENTO_FIGURAS, 440.0, 2, Sinal.AMARELO),
            ]
        tracos.append(
            Traco(
                modo=modo,
                ve=[(t, "VE_TESTE_00", (t - 300) * velocidade, velocidade, "A1_L0")
                    for t in range(300, 500)],
                fila=[(t, CRUZAMENTO_FIGURAS, "T1_S0", t % 5) for t in range(300, 700)],
                sinal=sinal,
                viagens=[("VE_TESTE_00", 401.0 if modo == "FIXO" else 281.0)],
            )
        )  # fmt: skip
    gravar(tracos, "intenso", 1, tmp_path / "traco")

    gerar(dados, tmp_path / "saida", traco=ler_traco(tmp_path / "traco"), reamostragens=200)

    for nome in ("F3_espaco_tempo.pdf", "F4_fila_transversal.pdf", "F6_fases.pdf"):
        assert (tmp_path / "saida" / "figuras" / nome).is_file()


def test_cli(tmp_path: Path) -> None:
    pasta = escrever_lote(tmp_path / "dados")
    saida = tmp_path / "saida"
    argumentos = ["--dados", str(pasta), "--saida", str(saida), "--reamostragens", "200"]

    assert main([*argumentos, "--sem-figuras", "--traco", str(tmp_path / "nada")]) == 0
    assert (saida / "resultados.md").is_file()
    assert not (saida / "figuras").exists()
    assert main(["--dados", str(tmp_path / "vazia")]) == 1


def test_latex_escapa_e_leva_o_rotulo() -> None:
    tabela = Tabela("T9", "Teste 100%", ("Modo_x", "δ"), [["PREEMPCAO_ML", "≥ 15%"]])
    latex = tabela.latex()

    assert r"\label{tab:t9}" in latex
    assert r"PREEMPCAO\_ML & $\geq$ 15\% \\" in latex
    assert escapar_latex("a & b") == r"a \& b"
    assert len(SEEDS) >= 12  # o lote sintético precisa de poder para o Wilcoxon


def test_percentual_com_sinal() -> None:
    assert pct_sinal(0.153) == "+15,3%"
    assert pct_sinal(-0.02) == "-2,0%"
    assert pct_sinal(None) == "—"
