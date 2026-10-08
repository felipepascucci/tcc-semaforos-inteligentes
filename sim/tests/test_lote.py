"""Montagem e consolidação da matriz experimental — `sim/controlador/lote.py`.

Puro: não sobe SUMO nem toca banco. O que se testa aqui é a **contabilidade** do
lote, e ela precisa estar certa antes de as 60 execuções do piloto (ou as 600 do
Bloco 8) rodarem — errar a escolha de exemplares ou perder uma linha na
consolidação são erros que só aparecem horas depois, com a máquina ocupada.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from sim.controlador import executor, lote
from sim.controlador.coletor import ARQUIVO_EXECUCOES, ARQUIVO_VE, CabecalhoDivergenteError


def _ponto(cenario: str = "leve", modo: str = "FIXO", seed: int = 1) -> lote.Ponto:
    return lote.Ponto(cenario, modo, seed)


def _resultado(ponto: lote.Ponto, **campos: object) -> lote.ResultadoDoPonto:
    base: dict[str, object] = {"ponto": ponto, "segundos": 1.0}
    base.update(campos)
    return lote.ResultadoDoPonto(**base)  # type: ignore[arg-type]


# --- seeds -----------------------------------------------------------------


def test_faixa_de_seeds() -> None:
    assert lote.analisar_seeds("1..5") == (1, 2, 3, 4, 5)


def test_lista_de_seeds() -> None:
    assert lote.analisar_seeds("1,3,7") == (1, 3, 7)


def test_faixa_e_lista_misturadas_sem_repeticao() -> None:
    assert lote.analisar_seeds("1..3,3,10") == (1, 2, 3, 10)


def test_faixa_invertida_e_erro() -> None:
    """Faixa invertida é erro, não lote vazio.

    `5..1` quase certamente é engano de digitação, e rodar zero execuções em
    silêncio seria pior do que falhar.
    """
    with pytest.raises(ValueError, match="invertida"):
        lote.analisar_seeds("5..1")


# --- matriz ----------------------------------------------------------------


def test_matriz_e_o_produto_dos_tres_eixos() -> None:
    pontos = lote.matriz(("leve", "intenso"), ("FIXO", "PREEMPCAO"), (1, 2))
    assert len(pontos) == 8
    assert len(set(pontos)) == 8


def test_matriz_agrupa_os_bracos_da_mesma_seed() -> None:
    """A ordem é seed → cenário → modo.

    Isso põe os três braços de um mesmo (cenário, seed) lado a lado — que é o
    conjunto que a comparação pareada consome — e faz uma interrupção do lote
    deixar seeds completas para trás.
    """
    pontos = lote.matriz(("leve",), ("FIXO", "PREEMPCAO", "PREEMPCAO_COMPENSADA"), (1, 2))
    assert [p.seed for p in pontos] == [1, 1, 1, 2, 2, 2]
    assert [p.modo for p in pontos[:3]] == ["FIXO", "PREEMPCAO", "PREEMPCAO_COMPENSADA"]


# --- exemplares (decisão P5) ------------------------------------------------


def test_um_exemplar_por_par_cenario_modo() -> None:
    pontos = lote.matriz(("leve", "intenso"), ("FIXO", "PREEMPCAO"), (1, 2, 3))
    marcados = lote.exemplares(pontos)
    assert len(marcados) == 4
    assert {(p.cenario, p.modo) for p in marcados} == {
        ("leve", "FIXO"),
        ("leve", "PREEMPCAO"),
        ("intenso", "FIXO"),
        ("intenso", "PREEMPCAO"),
    }


def test_exemplar_e_sempre_a_menor_seed() -> None:
    """O exemplar é a menor seed do par, sempre.

    A escolha não pode depender da ordem em que os processos terminam: é ela que
    decide quais execuções alimentam as figuras do capítulo 5.
    """
    pontos = lote.matriz(("leve",), ("FIXO",), (7, 3, 9))
    assert lote.exemplares(pontos) == frozenset({_ponto("leve", "FIXO", 3)})
    embaralhado = lote.matriz(("leve",), ("FIXO",), (9, 7, 3))
    assert lote.exemplares(embaralhado) == lote.exemplares(pontos)


# --- consolidação dos CSV ---------------------------------------------------


def _csv_parcial(pasta: Path, nome: str, linhas: list[list[str]]) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    with (pasta / nome).open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(("cenario", "modo", "seed"))
        escritor.writerows(linhas)


def test_consolidar_escreve_o_cabecalho_uma_vez(tmp_path: Path) -> None:
    primeira, segunda = tmp_path / "a", tmp_path / "b"
    _csv_parcial(primeira, ARQUIVO_EXECUCOES, [["leve", "FIXO", "1"]])
    _csv_parcial(segunda, ARQUIVO_EXECUCOES, [["leve", "PREEMPCAO", "1"]])

    lote.consolidar([primeira, segunda], tmp_path / "dados")

    linhas = (tmp_path / "dados" / ARQUIVO_EXECUCOES).read_text(encoding="utf-8").splitlines()
    assert linhas[0].startswith("cenario")
    assert len(linhas) == 3


def test_consolidar_preserva_a_ordem_da_matriz(tmp_path: Path) -> None:
    """A ordem das linhas é a da matriz, não a de término dos processos.

    Se variasse, o CSV mudaria a cada corrida do lote e o `diff` deixaria de
    valer nada.
    """
    for indice, modo in enumerate(("FIXO", "PREEMPCAO", "PREEMPCAO_COMPENSADA")):
        _csv_parcial(tmp_path / str(indice), ARQUIVO_VE, [["leve", modo, "1"]])

    lote.consolidar([tmp_path / "2", tmp_path / "0", tmp_path / "1"], tmp_path / "dados")

    linhas = (tmp_path / "dados" / ARQUIVO_VE).read_text(encoding="utf-8").splitlines()[1:]
    assert [linha.split(",")[1] for linha in linhas] == [
        "PREEMPCAO_COMPENSADA",
        "FIXO",
        "PREEMPCAO",
    ]


def test_consolidar_ignora_pasta_sem_o_arquivo(tmp_path: Path) -> None:
    _csv_parcial(tmp_path / "a", ARQUIVO_EXECUCOES, [["leve", "FIXO", "1"]])
    (tmp_path / "vazia").mkdir()
    contagem = lote.consolidar([tmp_path / "a", tmp_path / "vazia"], tmp_path / "dados")
    assert contagem[ARQUIVO_EXECUCOES] == 1


def test_consolidar_recusa_destino_com_outro_cabecalho_sem_escrever_nada(
    tmp_path: Path,
) -> None:
    """Acrescentar colunas a um CSV antigo o corromperia em silêncio.

    É o que aconteceria ao consolidar em `analysis/data/` — cujo `execucoes.csv`
    do piloto tem 22 colunas — execuções de uma versão com mais colunas. A
    checagem roda antes de qualquer escrita: nenhum arquivo fica pela metade.
    """
    destino = tmp_path / "dados"
    destino.mkdir()
    (destino / ARQUIVO_EXECUCOES).write_text("cenario,modo\nleve,FIXO\n", encoding="utf-8")
    _csv_parcial(tmp_path / "a", ARQUIVO_VE, [["leve", "FIXO", "1"]])
    _csv_parcial(tmp_path / "a", ARQUIVO_EXECUCOES, [["leve", "FIXO", "1"]])

    with pytest.raises(CabecalhoDivergenteError):
        lote.consolidar([tmp_path / "a"], destino)

    assert not (destino / ARQUIVO_VE).exists()
    assert (destino / ARQUIVO_EXECUCOES).read_text(encoding="utf-8") == "cenario,modo\nleve,FIXO\n"


def test_consolidar_recusa_execucoes_com_cabecalhos_diferentes(tmp_path: Path) -> None:
    """Execuções de versões diferentes do código não se misturam na mesma matriz."""
    _csv_parcial(tmp_path / "a", ARQUIVO_EXECUCOES, [["leve", "FIXO", "1"]])
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / ARQUIVO_EXECUCOES).write_text(
        "cenario,modo,seed,extra\nleve,PREEMPCAO,1,x\n", encoding="utf-8"
    )

    with pytest.raises(CabecalhoDivergenteError):
        lote.consolidar([tmp_path / "a", tmp_path / "b"], tmp_path / "dados")


# --- proteção contra consolidar o mesmo ponto duas vezes --------------------


def _dados_com(destino: Path, pontos: list[tuple[str, str, int]]) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    for nome in (ARQUIVO_EXECUCOES, ARQUIVO_VE):
        with (destino / nome).open("w", encoding="utf-8", newline="") as arquivo:
            escritor = csv.writer(arquivo)
            escritor.writerow(("cenario", "modo", "seed"))
            escritor.writerows(pontos)


def test_detecta_ponto_ja_consolidado(tmp_path: Path) -> None:
    _dados_com(tmp_path, [("leve", "FIXO", 1), ("leve", "PREEMPCAO", 1)])
    repetidos = lote.pontos_ja_no_csv(
        tmp_path, [_ponto("leve", "PREEMPCAO", 1), _ponto("leve", "FIXO", 9)]
    )
    assert repetidos == (_ponto("leve", "PREEMPCAO", 1),)


def test_sem_csv_de_destino_nada_repete(tmp_path: Path) -> None:
    assert lote.pontos_ja_no_csv(tmp_path, [_ponto()]) == ()


def test_rodar_recusa_duplicar_a_evidencia(tmp_path: Path) -> None:
    """A recusa vem antes de qualquer execução, não na hora de consolidar.

    Uma linha duplicada num CSV de 600 não aparece como erro: aparece como uma
    seed com peso dobrado na média do capítulo 5. E descobrir isso só no fim
    significaria descobri-lo depois de horas de máquina já gastas.
    """
    _dados_com(tmp_path, [("leve", "FIXO", 1)])
    with pytest.raises(lote.PontoJaConsolidadoError, match="--repetir"):
        lote.rodar([_ponto("leve", "FIXO", 1)], saida=tmp_path, persistir=False)


def test_remover_dos_csv_apaga_so_o_ponto_pedido(tmp_path: Path) -> None:
    _dados_com(tmp_path, [("leve", "FIXO", 1), ("leve", "FIXO", 2), ("intenso", "FIXO", 1)])
    apagadas = lote.remover_dos_csv(tmp_path, [_ponto("leve", "FIXO", 1)])

    assert apagadas[ARQUIVO_EXECUCOES] == 1
    with (tmp_path / ARQUIVO_EXECUCOES).open(encoding="utf-8", newline="") as arquivo:
        restantes = [(linha["cenario"], linha["seed"]) for linha in csv.DictReader(arquivo)]
    assert restantes == [("leve", "2"), ("intenso", "1")]


def test_pasta_da_execucao_e_limpa_antes_de_rodar(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Rodar o mesmo ponto duas vezes substitui o CSV da pasta, não acumula.

    Regressão do piloto do Bloco 4: quatro pontos exercitados antes num teste
    curto deixaram sobras na pasta, e o `execucoes.csv` consolidado saiu com 64
    linhas para 60 execuções. `gravar_csv()` acrescenta — correto para o arquivo
    consolidado, errado para a pasta de uma execução.
    """
    ponto = _ponto("leve", "FIXO", 1)
    monkeypatch.setattr(lote.executor, "SAIDA", tmp_path)
    _csv_parcial(ponto.pasta, ARQUIVO_EXECUCOES, [["leve", "FIXO", "1"]])
    assert (ponto.pasta / ARQUIVO_EXECUCOES).is_file()

    lote._limpar_csv_da_pasta(ponto)

    assert not (ponto.pasta / ARQUIVO_EXECUCOES).exists()


def test_limpar_pasta_inexistente_nao_falha(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(lote.executor, "SAIDA", tmp_path)
    lote._limpar_csv_da_pasta(_ponto("nunca", "FIXO", 99))


def test_remover_dos_csv_nao_toca_arquivo_sem_o_ponto(tmp_path: Path) -> None:
    _dados_com(tmp_path, [("intenso", "FIXO", 1)])
    assert lote.remover_dos_csv(tmp_path, [_ponto("leve", "FIXO", 1)]) == {}


# --- descartes (context/06 §4) ---------------------------------------------


def test_execucao_reprovada_nao_e_valida() -> None:
    reprovada = _resultado(_ponto(), problemas=("1 colisão(ões)",))
    assert not reprovada.valida
    assert _resultado(_ponto()).valida


def test_falha_de_execucao_nao_e_valida() -> None:
    assert not _resultado(_ponto(), erro="RuntimeError: SUMO caiu").valida


def test_descartes_registram_ponto_motivo_e_evidencia(tmp_path: Path) -> None:
    """Descarte silencioso é má prática; o registro é o que o torna metodologia."""
    ponto = _ponto("intenso", "PREEMPCAO", 4)
    escritas = lote.registrar_descartes(
        tmp_path,
        [_resultado(ponto, problemas=("3 teleporte(s) — gridlock",))],
        [],
    )
    assert escritas == 1

    with (tmp_path / lote.ARQUIVO_DESCARTES).open(encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    assert linhas[0]["tipo"] == "DESCARTE"
    assert linhas[0]["cenario"] == "intenso"
    assert linhas[0]["seed"] == "4"
    assert "gridlock" in linhas[0]["detalhe"]
    assert linhas[0]["evidencia"].endswith("intenso_PREEMPCAO_4")


def test_reexecucao_e_registrada_com_o_motivo(tmp_path: Path) -> None:
    """Reexecutar um ponto precisa deixar rastro.

    É justamente a fricção que a restrição única de (cenário, modo, seed) cria:
    apagar a linha anterior é o que torna o descarte visível.
    """
    lote.registrar_descartes(tmp_path, [], [(_ponto("leve", "FIXO", 2), "gridlock na primeira")])
    with (tmp_path / lote.ARQUIVO_DESCARTES).open(encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    assert linhas[0]["tipo"] == "REEXECUCAO"
    assert linhas[0]["detalhe"] == "gridlock na primeira"


def test_sem_descarte_nao_cria_arquivo(tmp_path: Path) -> None:
    assert lote.registrar_descartes(tmp_path, [_resultado(_ponto())], []) == 0
    assert not (tmp_path / lote.ARQUIVO_DESCARTES).exists()


# --- resumo -----------------------------------------------------------------


def test_resumo_separa_validas_de_descartadas() -> None:
    resumo = lote.ResumoDoLote(
        resultados=(
            _resultado(_ponto(seed=1)),
            _resultado(_ponto(seed=2), problemas=("1 colisão",)),
            _resultado(_ponto(seed=3), erro="boom"),
        ),
        segundos=10.0,
        linhas_csv={},
    )
    assert len(resumo.validas) == 1
    assert len(resumo.descartadas) == 2


# --- ajustes de parâmetro (calibração de P17) -------------------------------

_AJUSTE = (("ganho_compensacao_k", 1.5),)


def test_ponto_sem_ajuste_consolida_no_destino_de_sempre(tmp_path: Path) -> None:
    assert _ponto().destino(tmp_path) == tmp_path
    assert str(_ponto()) == "leve/FIXO/seed=1"


def test_ponto_com_ajuste_consolida_na_subpasta_da_combinacao(tmp_path: Path) -> None:
    """Os CSV não têm coluna de parâmetro: combinações no mesmo arquivo se confundiriam."""
    ponto = lote.Ponto("leve", "PREEMPCAO_COMPENSADA", 1, _AJUSTE)
    assert ponto.destino(tmp_path) == tmp_path / "ganho_compensacao_k-1.5"
    assert str(ponto).endswith("/ganho_compensacao_k-1.5")


def test_mesmo_ponto_com_ajustes_diferentes_sao_pontos_diferentes() -> None:
    a = lote.Ponto("leve", "PREEMPCAO_COMPENSADA", 1, (("ganho_compensacao_k", 0.5),))
    b = lote.Ponto("leve", "PREEMPCAO_COMPENSADA", 1, (("ganho_compensacao_k", 1.0),))
    assert a != b
    assert a.pasta != b.pasta


def test_matriz_propaga_os_ajustes() -> None:
    pontos = lote.matriz(["leve"], ["PREEMPCAO_COMPENSADA"], [1, 2], _AJUSTE)
    assert all(ponto.ajustes == _AJUSTE for ponto in pontos)


def test_um_exemplar_por_combinacao() -> None:
    pontos = lote.matriz(["leve"], ["PREEMPCAO_COMPENSADA"], [1, 2]) + lote.matriz(
        ["leve"], ["PREEMPCAO_COMPENSADA"], [1, 2], _AJUSTE
    )
    assert len(lote.exemplares(pontos)) == 2


def test_analisar_ajustes() -> None:
    assert lote.analisar_ajustes(["n_ciclos_compensacao=3", "ganho_compensacao_k=0.5"]) == (
        ("ganho_compensacao_k", 0.5),
        ("n_ciclos_compensacao", 3.0),
    )
    with pytest.raises(ValueError, match="NOME=VALOR"):
        lote.analisar_ajustes(["ganho_compensacao_k"])
    with pytest.raises(ValueError, match="não numérico"):
        lote.analisar_ajustes(["ganho_compensacao_k=alto"])


def test_rodar_recusa_ajuste_com_banco(tmp_path: Path) -> None:
    ponto = lote.Ponto("leve", "PREEMPCAO_COMPENSADA", 1, _AJUSTE)
    with pytest.raises(ValueError, match="execucao_simulacao"):
        lote.rodar([ponto], saida=tmp_path, persistir=True)


def test_duplicata_e_conferida_no_destino_da_combinacao(tmp_path: Path) -> None:
    """O ponto já consolidado na subpasta da combinação também é recusado."""
    ponto = lote.Ponto("leve", "PREEMPCAO_COMPENSADA", 1, _AJUSTE)
    _dados_com(ponto.destino(tmp_path), [("leve", "PREEMPCAO_COMPENSADA", 1)])
    with pytest.raises(lote.PontoJaConsolidadoError):
        lote.rodar([ponto], saida=tmp_path, persistir=False)


def test_mesmo_ponto_na_raiz_nao_bloqueia_a_combinacao(tmp_path: Path) -> None:
    """A linha sem ajuste na raiz é outro experimento, não duplicata."""
    _dados_com(tmp_path, [("leve", "PREEMPCAO_COMPENSADA", 1)])
    ponto = lote.Ponto("leve", "PREEMPCAO_COMPENSADA", 1, _AJUSTE)
    grupos = lote._por_destino([ponto], tmp_path)
    assert all(lote.pontos_ja_no_csv(d, m) == () for d, m in grupos.items())


# --- braço PREEMPCAO_ML só onde há disputa (entrega 10.7) --------------------


def test_braco_ml_fica_de_fora_dos_cenarios_de_um_ve() -> None:
    """Com um VE só não há disputa, e a execução repetiria a do `PREEMPCAO`."""
    pontos = lote.matriz(
        ("leve", "moderado", "intenso", "multiplas_emergencias"),
        ("FIXO", "PREEMPCAO", "PREEMPCAO_COMPENSADA", "PREEMPCAO_ML"),
        (1, 2),
    )

    assert {p.cenario for p in pontos if p.modo == "PREEMPCAO_ML"} == {"multiplas_emergencias"}
    assert len(pontos) == 2 * (4 * 3 + 1)


def test_matriz_do_bloco_8_tem_650_execucoes() -> None:
    """4 cenários x 3 braços x 50 seeds, mais o `PREEMPCAO_ML` no de múltiplos VEs."""
    pontos = lote.matriz(lote.CENARIOS_PADRAO, executor.MODOS, range(1, 51))
    assert len(pontos) == 650


def test_braco_ml_fica_ao_lado_dos_outros_da_mesma_seed() -> None:
    pontos = lote.matriz(("multiplas_emergencias",), executor.MODOS, (7,))
    assert [p.modo for p in pontos] == list(executor.MODOS)


def test_sem_braco_ml_a_matriz_nao_le_os_cenarios() -> None:
    """O corte só consulta `cenarios.yaml` quando o braço é pedido."""
    pontos = lote.matriz(("cenario_que_nao_existe",), ("FIXO",), (1,))
    assert [p.cenario for p in pontos] == ["cenario_que_nao_existe"]
