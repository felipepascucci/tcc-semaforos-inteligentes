"""Relatório de validação — `analysis/gerar_relatorio_validacao.py`.

Os XML do JUnit daqui são escritos à mão, com nomes de teste artificiais: testam
a leitura, não registram resultado de suíte nenhuma. O teste de ponta a ponta
usa os dados versionados do repositório, como o próprio relatório, sem o banco.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from analysis import gerar_relatorio_validacao as rv

RAIZ = Path(__file__).resolve().parents[2]

XML_PYTEST = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" timestamp="2026-10-08T12:00:00">
<testcase classname="backend.tests.core.test_teste_a" name="test_passa" time="0.1"/>
<testcase classname="backend.tests.core.test_teste_a" name="test_falha" time="0.1">
  <failure message="x">assert False</failure></testcase>
<testcase classname="tests.e2e.test_teste_b" name="test_esperada" time="0.1">
  <skipped type="pytest.xfail" message="falha esperada"/></testcase>
<testcase classname="sim.tests.test_teste_c" name="test_pulado" time="0.1">
  <skipped type="pytest.skip" message="sem SUMO"/></testcase>
<testcase classname="sim.tests.test_teste_c" name="test_com_propriedade" time="0.1">
  <properties><property name="rss_max_mb" value="101.5"/></properties></testcase>
<testcase classname="backend.tests.api.test_teste_a" name="test_outro_pacote" time="0.1"/>
</testsuite></testsuites>
"""

XML_VITEST = """<?xml version="1.0" encoding="UTF-8" ?>
<testsuites name="vitest tests" tests="3">
<testsuite name="src/stream/reducer.test.ts" timestamp="2026-10-08T12:00:00">
<testcase classname="src/stream/reducer.test.ts" name="aplica o estado" time="0.01"/>
</testsuite>
<testsuite name="src/stream/conexao.test.tsx">
<testcase classname="src/stream/conexao.test.tsx" name="reconecta" time="0.01"/>
</testsuite>
<testsuite name="src/stream/sub/fundo.test.ts">
<testcase classname="src/stream/sub/fundo.test.ts" name="fora do glob" time="0.01"/>
</testsuite>
</testsuites>
"""


def _casos(tmp_path: Path) -> list[rv.CasoDeTeste]:
    (tmp_path / "pytest_padrao.xml").write_text(XML_PYTEST, encoding="utf-8")
    (tmp_path / "vitest.xml").write_text(XML_VITEST, encoding="utf-8")
    return [caso for suite in rv.ler_suites(tmp_path) for caso in suite.casos]


# ---------------------------------------------------------------------------
# JUnit
# ---------------------------------------------------------------------------


def test_desfechos_do_junit(tmp_path: Path) -> None:
    casos = {c.nome: c for c in _casos(tmp_path)}

    assert casos["test_passa"].desfecho == rv.PASSOU
    assert casos["test_falha"].desfecho == rv.FALHOU
    assert casos["test_esperada"].desfecho == rv.XFAIL
    assert casos["test_pulado"].desfecho == rv.PULADO
    assert casos["test_com_propriedade"].propriedades == {"rss_max_mb": "101.5"}


def test_instante_da_suite(tmp_path: Path) -> None:
    _casos(tmp_path)
    assert rv.ler_junit(tmp_path / "pytest_padrao.xml").instante == "2026-10-08T12:00:00"


def test_arquivo_pelo_nome_casa_em_qualquer_pacote(tmp_path: Path) -> None:
    nomes = {c.nome for c in rv.casos_do_arquivo(_casos(tmp_path), "test_teste_a.py")}
    assert nomes == {"test_passa", "test_falha", "test_outro_pacote"}


def test_arquivo_pelo_caminho_casa_so_com_aquele(tmp_path: Path) -> None:
    casos = rv.casos_do_arquivo(_casos(tmp_path), "backend/tests/api/test_teste_a.py")
    assert [c.nome for c in casos] == ["test_outro_pacote"]


def test_arquivos_do_frontend_pelo_padrao_de_06(tmp_path: Path) -> None:
    casos = rv.casos_do_arquivo(_casos(tmp_path), "frontend/src/stream/*.test.ts(x)")
    assert {c.nome for c in casos} == {"aplica o estado", "reconecta"}


def test_placar() -> None:
    def caso(desfecho: str) -> rv.CasoDeTeste:
        return rv.CasoDeTeste("s", "m", "t", desfecho)

    assert rv.Placar.de([]).status == "SEM TESTE"
    assert rv.Placar.de([caso(rv.PASSOU), caso(rv.PULADO)]).status == rv.PASSOU
    assert rv.Placar.de([caso(rv.PASSOU), caso(rv.FALHOU)]).status == rv.FALHOU
    assert rv.Placar.de([caso(rv.PASSOU), caso(rv.XFAIL)]).status.startswith(rv.FALHOU)
    assert rv.Placar.de([caso(rv.PULADO)]).status == "NÃO EXECUTADO"
    assert rv.Placar.de([caso(rv.PASSOU), caso(rv.XFAIL)]).texto() == "1/2 passaram, 1 xfail"


def test_status_junta_testes_e_bancada() -> None:
    passou = rv.Placar(passou=3)
    boa = rv.EvidenciaDeBancada("x", True)
    ruim = rv.EvidenciaDeBancada("x", False)

    assert rv._status_final(passou, boa) == rv.PASSOU
    assert rv._status_final(passou, ruim) == rv.FALHOU
    assert rv._status_final(rv.Placar(), boa) == rv.PASSOU
    assert rv._status_final(rv.Placar(), None) == "SEM TESTE"
    assert rv._status_final(rv.Placar(passou=1, xfail=1), ruim).startswith(rv.FALHOU)


# ---------------------------------------------------------------------------
# context/, lido dos arquivos
# ---------------------------------------------------------------------------


def test_rastreabilidade_de_06_tem_os_requisitos() -> None:
    codigos = {r.codigo for r in rv.ler_rastreabilidade()}
    assert {"RF01", "RF02", "RF03", "RF04", "RF05", "RF06", "RF07", "H3"} <= codigos
    assert {"RNF01", "RNF02", "RNF03", "RNF04", "RNF05", "RNF07"} <= codigos


def test_todo_arquivo_de_teste_citado_em_06_existe() -> None:
    """A lacuna achada em 2026-10-08 não volta: arquivo citado em `06` §2 existe."""
    arquivos = {a for r in rv.ler_rastreabilidade() for a in r.arquivos_de_teste}
    faltando = []
    for arquivo in sorted(arquivos):
        if arquivo.startswith("frontend/"):
            padrao = arquivo.replace("(x)", "*")
            existe = any(RAIZ.glob(padrao))
        elif "/" in arquivo:
            existe = (RAIZ / arquivo).is_file()
        else:
            existe = any(p for p in RAIZ.glob(f"**/{arquivo}") if ".venv" not in p.parts)
        if not existe:
            faltando.append(arquivo)
    assert faltando == []


def test_checklist_de_06_tem_os_itens() -> None:
    itens = [item.item for item in rv.ler_checklist()]
    assert itens[:3] == ["1", "2", "3"]
    assert {"5b", "7b", "15"} <= set(itens)


def test_cada_falha_casa_com_uma_linha_de_09() -> None:
    registros = rv.ler_registros_de_09()
    assert len(registros) == len(rv.FALHAS_EM_09)
    assert all(r.data.startswith("2026-") for r in registros)


def test_chave_que_nao_casa_e_erro() -> None:
    with pytest.raises(ValueError, match="0 linhas"):
        rv.ler_registros_de_09(("**Nada com este nome**",))


def test_equipe_de_00() -> None:
    equipe = rv.ler_equipe()
    assert len(equipe) == 3
    assert equipe[0].startswith("Felipe")


def test_sessao_de_h3_e_a_do_capitulo_5() -> None:
    pytest.importorskip("pandas", reason="extra analysis não instalado")
    from analysis.gerar_resultados_tcc import SESSAO_H3

    assert rv.SESSAO_H3 == SESSAO_H3


# ---------------------------------------------------------------------------
# Bancada
# ---------------------------------------------------------------------------


def test_vermelho_mais_longo() -> None:
    seq = [(0, "RRRR"), (1000, "GGRR"), (4000, "YYRR"), (6000, "RRRR"), (7000, "RRGG")]
    # S3 e S4 ficam vermelhos de 0 a 7000; S1 e S2, de 6000 até o fim (sem fechar).
    assert rv._vermelho_mais_longo(seq) == 7000


# ---------------------------------------------------------------------------
# O relatório inteiro, sobre os dados do repositório
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def relatorio(tmp_path_factory: pytest.TempPathFactory) -> str:
    pasta = tmp_path_factory.mktemp("junit")
    (pasta / "pytest_padrao.xml").write_text(XML_PYTEST, encoding="utf-8")
    entradas = rv.carregar(date(2026, 10, 8), pasta, url_banco=None, com_ambiente=False)
    return rv.gerar(entradas)


def test_relatorio_tem_as_nove_secoes_na_ordem(relatorio: str) -> None:
    titulos = [linha for linha in relatorio.splitlines() if linha.startswith("## ")]
    assert [t.split(" ")[1] for t in titulos] == [f"{n}." for n in range(1, 10)]


def test_relatorio_conta_as_execucoes_do_csv(relatorio: str) -> None:
    from analysis.gerar_relatorio_validacao import ler_lote

    lote = ler_lote()
    assert f"- Válidas (`execucoes.csv`): {len(lote.execucoes)}" in relatorio
    assert f"- Planejadas (primeira linha de `lote_bloco8.log`): {lote.planejadas}" in relatorio


def test_rf03_sai_falhou(relatorio: str) -> None:
    linha = next(x for x in relatorio.splitlines() if x.startswith("| RF03 |"))
    assert "**FALHOU" in linha


def test_item_5_so_e_julgado_nas_rodadas_dele(relatorio: str) -> None:
    secao = relatorio[relatorio.index("### 8.1") : relatorio.index("### 8.2")]
    linhas = [x for x in secao.splitlines() if x.startswith("|")]
    coluna = [c.strip() for c in linhas[0].split("|")].index("5")
    for linha in linhas[2:]:
        celulas = [c.strip() for c in linha.split("|")]
        rodada = any(rv.sessao_curta(s) in linha for s in rv.SESSOES_ITEM_5)
        assert (celulas[coluna] == "não julgado") is not rodada, linha


def test_assinatura_de_cada_membro(relatorio: str) -> None:
    for nome in rv.ler_equipe():
        assert nome.split(" (")[0] in relatorio.split("### 8.2")[1]


def test_fotos_ficam_a_anexar(relatorio: str) -> None:
    assert "A anexar" in relatorio.split("## 9.")[1]


def test_suja_segue_a_regra_do_executor() -> None:
    from sim.controlador.executor import FORA_DA_VERSAO

    assert rv.FORA_DA_VERSAO == FORA_DA_VERSAO


def test_sessao_curta() -> None:
    assert rv.sessao_curta("2026-10-07T18:18:37.223864+00:00") == "2026-10-07 18:18:37Z"


def test_largura_das_colunas_segue_o_conteudo() -> None:
    separador = rv._tabela(("#", "Texto"), [("1", "x" * 200), ("15", "curto")])[1]
    tracos = [len(c.strip()) for c in separador.strip("|").split("|")]
    assert tracos == [3, rv.TETO_DA_COLUNA]


def test_markdown_do_pdf_so_troca_br_e_caixa_marcada() -> None:
    texto = "| a<br>b | ☑ |\n≥ → `x_y`"
    assert rv.markdown_para_pdf(texto) == "| a; b | OK |\n≥ → `x_y`"


def test_comando_do_pandoc_usa_a_imagem_fixada_e_o_filtro() -> None:
    comando = rv.comando_pandoc("C:/tmp", "r.md", "r.pdf")
    assert rv.IMAGEM_PANDOC in comando
    assert "--lua-filter=/data/quebrar_codigo.lua" in comando
    assert "--pdf-engine=lualatex" in comando
    assert (rv.PASTA_PDF / "cabecalho.tex").is_file()
    assert (rv.PASTA_PDF / "quebrar_codigo.lua").is_file()
