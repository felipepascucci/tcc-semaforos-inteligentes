"""Testes do treino da política de desempate (entrega 10.5)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
import yaml

np = pytest.importorskip("numpy", reason="extra analysis não instalado")
pytest.importorskip("scipy", reason="extra analysis não instalado")
pytest.importorskip("pandas", reason="extra analysis não instalado")

from scipy.optimize import check_grad  # noqa: E402

from analysis import treino_politica as tp  # noqa: E402
from analysis.resumo_rotulos import ARQUIVO_ROTULOS, divisao_de_seeds  # noqa: E402
from core.priorizacao.atributos import AtributosVE  # noqa: E402


def _conjunto(x, y, custo=None):  # type: ignore[no-untyped-def]
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    return tp.Conjunto(
        x=x,
        y=y,
        custo_s=np.ones(len(y)) if custo is None else np.asarray(custo, dtype=float),
        escolha_e8=np.ones(len(y)),
        id_semaforo=np.array(["CRUZ_02"] * len(y)),
    )


def _sintetico(n: int, semente: int = 0):  # type: ignore[no-untyped-def]
    gerador = np.random.default_rng(semente)
    x = gerador.normal(size=(n, 4)) * np.array([30.0, 5.0, 2.0, 3.0])
    verdadeiros = np.array([-0.05, -0.2, 0.1, 0.6])
    probabilidade = 1.0 / (1.0 + np.exp(-(x @ verdadeiros)))
    y = np.where(gerador.random(n) < probabilidade, 1.0, -1.0)
    custo = gerador.uniform(0.5, 60.0, size=n)
    return _conjunto(x, y, custo), verdadeiros


def test_atributos_sao_campos_de_atributos_ve() -> None:
    """O modelo só pode usar o que a inferência da 10.6 vai calcular."""
    campos = {campo.name for campo in dataclasses.fields(AtributosVE)}
    assert set(tp.ATRIBUTOS) <= campos
    assert "fila_por_faixa" in tp.ATRIBUTOS
    assert "fila_no_acesso" not in tp.ATRIBUTOS


def test_gradiente_confere_com_diferenca_finita() -> None:
    conjunto, _ = _sintetico(200)
    x = conjunto.x / np.sqrt(np.mean(conjunto.x**2, axis=0))
    for lambda_ in (0.0, 0.1):
        erro = check_grad(
            lambda w, lam=lambda_: tp.perda(w, x, conjunto.y, conjunto.custo_s, lam)[0],
            lambda w, lam=lambda_: tp.perda(w, x, conjunto.y, conjunto.custo_s, lam)[1],
            np.array([0.3, -0.2, 0.1, 0.5]),
        )
        assert erro < 1e-6


def test_recupera_a_direcao_dos_pesos_de_um_modelo_conhecido() -> None:
    conjunto, verdadeiros = _sintetico(20_000)
    ajuste = tp.ajustar(conjunto, 0.0)
    normas = np.linalg.norm(ajuste.pesos) * np.linalg.norm(verdadeiros)
    cosseno = ajuste.pesos @ verdadeiros / normas
    assert cosseno > 0.99


def test_nao_ha_intercepto_e_o_score_e_antissimetrico() -> None:
    conjunto, _ = _sintetico(500)
    ajuste = tp.ajustar(conjunto, 0.01)
    assert ajuste.pesos.shape == (len(tp.ATRIBUTOS),)
    escolha = tp.escolhas(ajuste.pesos, conjunto.x)
    trocada = tp.escolhas(ajuste.pesos, -conjunto.x)
    assert np.all(escolha == -trocada)


def test_escala_e_rms_sem_centralizar() -> None:
    """Subtrair a média criaria um intercepto escondido."""
    conjunto = _conjunto([[2.0, 1.0, 0.0, 2.0], [4.0, -1.0, 0.0, 2.0]], [1.0, -1.0])
    ajuste = tp.ajustar(conjunto, 1.0)
    assert ajuste.escala == pytest.approx([np.sqrt(10.0), 1.0, 1.0, 2.0])
    assert ajuste.pesos == pytest.approx(ajuste.pesos_escalados / ajuste.escala)


def test_espelhar_os_exemplos_nao_muda_o_ajuste() -> None:
    """Por isso o desequilíbrio A/B não se trata espelhando (decisão de 2026-10-06)."""
    conjunto, _ = _sintetico(400)
    espelhado = _conjunto(
        np.vstack([conjunto.x, -conjunto.x]),
        np.concatenate([conjunto.y, -conjunto.y]),
        np.concatenate([conjunto.custo_s, conjunto.custo_s]),
    )
    original = tp.ajustar(conjunto, 0.01)
    duplicado = tp.ajustar(espelhado, 0.01)
    assert duplicado.pesos_escalados == pytest.approx(original.pesos_escalados, rel=1e-5)


def test_exemplo_de_custo_zero_nao_influencia() -> None:
    conjunto, _ = _sintetico(400)
    ruido = _conjunto(
        np.vstack([conjunto.x, conjunto.x[:50]]),
        np.concatenate([conjunto.y, -conjunto.y[:50]]),
        np.concatenate([conjunto.custo_s, np.zeros(50)]),
    )
    # A escala muda com as linhas novas; com λ = 0 o ótimo não depende dela, e a
    # comparação é nas unidades originais.
    original = tp.ajustar(conjunto, 0.0)
    com_ruido = tp.ajustar(ruido, 0.0)
    assert com_ruido.pesos == pytest.approx(original.pesos, rel=1e-4)


def test_custo_pesa_no_ajuste() -> None:
    """Dois exemplos contraditórios: vence o de maior margem."""
    x = [[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]]
    assert tp.ajustar(_conjunto(x, [1.0, -1.0], [30.0, 1.0]), 0.01).pesos[0] > 0
    assert tp.ajustar(_conjunto(x, [1.0, -1.0], [1.0, 30.0]), 0.01).pesos[0] < 0


def test_score_zero_escolhe_b() -> None:
    assert tp.escolhas(np.zeros(4), np.ones((1, 4)))[0] == -1.0


def test_escolha_do_lambda_pela_menor_perda_e_maior_no_empate() -> None:
    assert tp.escolher_lambda([(0.0, 0.5), (0.01, 0.4), (0.1, 0.45)]) == 0.01
    assert tp.escolher_lambda([(0.0, 0.4), (0.01, 0.4), (0.1, 0.45)]) == 0.01


def test_desempenho_cobra_a_margem_de_cada_erro() -> None:
    conjunto = _conjunto(np.zeros((3, 4)), [1.0, -1.0, 1.0], [10.0, 4.0, 2.0])
    avaliado = tp.desempenho(np.array([1.0, 1.0, -1.0]), conjunto)
    assert avaliado.acertos == 1
    assert avaliado.custo_total_s == pytest.approx(6.0)
    assert avaliado.custo_medio_s == pytest.approx(2.0)


def test_avaliacao_traz_as_referencias_por_cruzamento() -> None:
    # A chega antes no primeiro exemplo (dif. de ETA < 0), B no segundo.
    conjunto = _conjunto([[-5.0, 0.0, 0.0, 1.0], [5.0, 0.0, 0.0, 1.0]], [1.0, 1.0], [3.0, 7.0])
    ajuste = tp.Ajuste(np.zeros(4), np.zeros(4), np.ones(4), 0.0)
    tabela = tp.avaliar(ajuste, {"treino": conjunto}).set_index(["cruzamento", "politica"])
    assert set(tabela.loc["todos"].index) == {"rotulo", "modelo", "e8", "menor_eta", "sempre_a"}
    assert tabela.loc[("todos", "rotulo"), "custo_total_s"] == 0.0
    assert tabela.loc[("todos", "modelo"), "escolhe_b"] == 2
    assert tabela.loc[("todos", "menor_eta"), "custo_total_s"] == pytest.approx(7.0)
    assert tabela.loc[("todos", "sempre_a"), "acertos"] == 2
    assert tabela.loc[("todos", "modelo"), "acertos"] == 0  # score zero escolhe B
    assert ("CRUZ_02", "e8") in tabela.index


CABECALHO_CSV = (
    "seed,id_semaforo,eta_a_s,eta_b_s,velocidade_a_ms,velocidade_b_ms,fila_faixa_a,"
    "fila_faixa_b,cruzamentos_restantes_a,cruzamentos_restantes_b,escolha_e8,"
    "minimax_se_a_s,minimax_se_b_s,rotulo\n"
)


def test_leitura_separa_por_seed_e_deixa_empate_e_descarte_fora(tmp_path: Path) -> None:
    caminho = tmp_path / "rotulos.csv"
    caminho.write_text(
        CABECALHO_CSV
        + "201,CRUZ_02,40,20,10,8,2.5,0,8,4,A,300.04,310.0,A\n"
        + "201,CRUZ_08,10,30,12,14,0,1,4,2,A,300,300,EMPATE\n"
        + "202,CRUZ_02,40,20,10,8,0,0,8,4,A,,,DESCARTADA\n"
        + "203,CRUZ_08,15,10,12,14,1,0,4,2,A,320,301.5,B\n",
        encoding="utf-8",
    )
    conjuntos = tp.ler_conjuntos(caminho, {"treino": (201, 202), "validacao": (203, 203)})
    treino, validacao = conjuntos["treino"], conjuntos["validacao"]
    assert len(treino) == 1
    assert treino.x[0] == pytest.approx([20.0, 2.0, 2.5, 4.0])
    assert treino.y[0] == 1.0
    assert treino.custo_s[0] == pytest.approx(10.0)
    assert len(validacao) == 1
    assert validacao.y[0] == -1.0
    assert validacao.escolha_e8[0] == 1.0
    assert validacao.custo_s[0] == pytest.approx(18.5)


def test_descricao_do_treino_conta_o_que_o_texto_cita(tmp_path: Path) -> None:
    caminho = tmp_path / "rotulos.csv"
    caminho.write_text(
        "seed,rotulo,escolha_e8,tipo_a,tipo_b,cruzamentos_restantes_a,cruzamentos_restantes_b,"
        "fila_faixa_a,fila_faixa_b,travessia_a_se_a_s,travessia_b_se_a_s,"
        "travessia_a_se_b_s,travessia_b_se_b_s\n"
        # A vence e é o pior no ramo A; E8 pela ordem (AMB antes de BOMB).
        "201,A,A,AMBULANCIA,BOMBEIRO,8,4,1.0,1.0,300,250,350,240\n"
        # B vence e, no ramo B, o pior é B; E8 contra a ordem.
        "201,B,A,POLICIA,BOMBEIRO,4,2,0.0,2.0,300,320,280,290\n"
        # Validação: fora da descrição.
        "203,A,A,AMBULANCIA,AMBULANCIA,1,4,0,0,1,1,1,1\n",
        encoding="utf-8",
    )
    linhas = tp.descrever_treino(
        caminho,
        {"treino": (201, 202), "validacao": (203, 203)},
        ["AMBULANCIA", "BOMBEIRO", "POLICIA"],
    )
    assert linhas == [
        "Exemplos de treino: 2",
        "VE mais prejudicado no ramo vencedor é o A (corredor): 1 de 2",
        "Diferença de cruzamentos_restantes (A - B): mín 2, máx 4, positiva em 2",
        "Diferença de fila_por_faixa igual a zero: 1",
        "Pares de tipos diferentes: 2; E8 seguiu a ordem de tipo em 1 de 2",
    ]


def test_pesos_versionados_saem_do_treino_sobre_os_rotulos_versionados() -> None:
    """O arquivo de pesos é o que o código versionado produz dos dados versionados."""
    with tp.ARQUIVO_PESOS.open(encoding="utf-8") as arquivo:
        versionado = yaml.safe_load(arquivo)
    caminho = tp.DADOS / ARQUIVO_ROTULOS
    divisao = divisao_de_seeds()
    conjuntos = tp.ler_conjuntos(caminho, divisao)
    ajuste, _ = tp.selecionar(conjuntos)
    refeito = tp.conteudo_pesos(ajuste, conjuntos, divisao, caminho)

    assert versionado["atributos"] == list(tp.ATRIBUTOS)
    assert versionado["treino"]["sha256_rotulos"] == refeito["treino"]["sha256_rotulos"]
    assert versionado["treino"]["lambda"] == refeito["treino"]["lambda"]
    for atributo in tp.ATRIBUTOS:
        assert versionado["pesos"][atributo] == pytest.approx(
            refeito["pesos"][atributo], rel=1e-6, abs=1e-9
        )
