"""O resumo que produz o número da entrega 10.1."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path

from analysis.resumo_conflitos import (
    ARQUIVO_CONFLITOS,
    ARQUIVO_EXECUCOES,
    PISO_EVENTOS_DE_TREINO,
    gerar_relatorio,
    ler_contagens,
    ler_episodios,
)

CABECALHO_EXECUCOES = (
    "cenario",
    "modo",
    "seed",
    "eventos_conflito",
    "eventos_conflito_decidiveis",
    "passos_em_conflito",
)

CABECALHO_CONFLITOS = (
    "cenario",
    "modo",
    "seed",
    "id_semaforo",
    "t_inicio_s",
    "duracao_s",
    "passos",
    "n_ves",
    "ids_veiculos",
    "tipos",
    "decidivel",
    "decidivel_em_algum_passo",
)


def _escrever(caminho: Path, cabecalho: Sequence[str], linhas: Sequence[Sequence[object]]) -> None:
    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(cabecalho)
        escritor.writerows(linhas)


def _dados(tmp_path: Path, execucoes: Sequence[Sequence[object]]) -> Path:
    _escrever(tmp_path / ARQUIVO_EXECUCOES, CABECALHO_EXECUCOES, execucoes)
    return tmp_path


def test_execucao_sem_as_colunas_novas_e_lida_como_zero(tmp_path: Path) -> None:
    """O piloto de 2026-08-26 não tem as colunas, e não pode quebrar o leitor."""
    _escrever(tmp_path / ARQUIVO_EXECUCOES, ("cenario", "modo", "seed"), [["leve", "FIXO", 1]])

    contagens = ler_contagens(tmp_path / ARQUIVO_EXECUCOES)

    assert len(contagens) == 1
    assert contagens[0].eventos == 0


def test_arquivo_ausente_devolve_vazio(tmp_path: Path) -> None:
    """Nenhum conflito em nenhuma execução é resultado, não é erro."""
    assert ler_episodios(tmp_path / ARQUIVO_CONFLITOS) == ()
    assert ler_contagens(tmp_path / ARQUIVO_EXECUCOES) == ()


def test_relatorio_soma_os_episodios_de_todas_as_execucoes(tmp_path: Path) -> None:
    dados = _dados(
        tmp_path,
        [
            ["multiplas_emergencias", "PREEMPCAO", 101, 6, 4, 300],
            ["multiplas_emergencias", "PREEMPCAO", 102, 8, 5, 400],
        ],
    )

    relatorio = gerar_relatorio(ler_contagens(dados / ARQUIVO_EXECUCOES), ())

    assert "Episódios de conflito: 14" in relatorio
    assert "Episódios decidíveis (sem preempção em curso): 9" in relatorio
    assert "Execuções: 2" in relatorio


def test_execucao_sem_conflito_entra_no_denominador(tmp_path: Path) -> None:
    """Ela não aparece no CSV de episódios, mas o mínimo por execução é zero."""
    dados = _dados(
        tmp_path,
        [
            ["multiplas_emergencias", "PREEMPCAO", 101, 4, 4, 200],
            ["moderado", "PREEMPCAO", 101, 0, 0, 0],
        ],
    )

    relatorio = gerar_relatorio(ler_contagens(dados / ARQUIVO_EXECUCOES), ())

    assert "Por execução, episódios: mín 0" in relatorio


def test_veredito_aponta_a_102_quando_o_volume_nao_alcanca_o_piso(tmp_path: Path) -> None:
    """É a decisão que a 10.1 existe para tomar."""
    dados = _dados(tmp_path, [["multiplas_emergencias", "PREEMPCAO", 101, 5, 3, 250]])

    relatorio = gerar_relatorio(ler_contagens(dados / ARQUIVO_EXECUCOES), ())

    assert f"abaixo do piso de {PISO_EVENTOS_DE_TREINO}" in relatorio
    assert "10.2" in relatorio


def test_veredito_dispensa_a_102_quando_o_piso_e_alcancado(tmp_path: Path) -> None:
    dados = _dados(tmp_path, [["multiplas_emergencias", "PREEMPCAO", 101, 200, 150, 9000]])

    relatorio = gerar_relatorio(ler_contagens(dados / ARQUIVO_EXECUCOES), ())

    assert "não é obrigatória por volume" in relatorio


def test_relatorio_descreve_a_forma_dos_episodios(tmp_path: Path) -> None:
    dados = _dados(tmp_path, [["multiplas_emergencias", "PREEMPCAO", 101, 2, 2, 30]])
    _escrever(
        tmp_path / ARQUIVO_CONFLITOS,
        CABECALHO_CONFLITOS,
        [
            [
                "multiplas_emergencias",
                "PREEMPCAO",
                101,
                "CRUZ_TESTE_1",
                310.0,
                1.5,
                15,
                2,
                "AMB|BMB",
                "AMBULANCIA|BOMBEIRO",
                1,
                1,
            ],
            [
                "multiplas_emergencias",
                "PREEMPCAO",
                101,
                "CRUZ_TESTE_1",
                910.0,
                1.5,
                15,
                2,
                "AMB|POL",
                "AMBULANCIA|POLICIA",
                1,
                1,
            ],
        ],
    )

    episodios = ler_episodios(tmp_path / ARQUIVO_CONFLITOS)
    relatorio = gerar_relatorio(ler_contagens(dados / ARQUIVO_EXECUCOES), episodios)

    assert episodios[0].ids_veiculos == ("AMB", "BMB")
    assert "CRUZ_TESTE_1: 2" in relatorio
    assert "AMBULANCIA+BOMBEIRO: 1" in relatorio


def _linha_com_criticidade(t: float, criticidades: str, mesmo_nivel: int, decidivel: int) -> list:
    return [
        "multiplas_emergencias",
        "PREEMPCAO",
        101,
        "CRUZ_TESTE_1",
        t,
        1.5,
        15,
        2,
        "AMB|BMB",
        "AMBULANCIA|BOMBEIRO",
        decidivel,
        decidivel,
        criticidades,
        mesmo_nivel,
    ]


def test_relatorio_separa_mesmo_nivel_de_nivel_misto(tmp_path: Path) -> None:
    """P20 — só o episódio decidível **e** de mesmo nível é do modelo.

    Três disputas: uma de mesmo nível em aberto (treinável), uma de mesmo nível
    suspensa pela guarda de oscilação, e uma de nível misto, que a regra de
    criticidade decide. O volume de treino é 1, não 3 nem 2.
    """
    dados = _dados(tmp_path, [["multiplas_emergencias", "PREEMPCAO", 101, 3, 2, 45]])
    _escrever(
        tmp_path / ARQUIVO_CONFLITOS,
        (*CABECALHO_CONFLITOS, "criticidades", "mesmo_nivel"),
        [
            _linha_com_criticidade(310.0, "1|1", 1, decidivel=1),
            _linha_com_criticidade(610.0, "2|2", 1, decidivel=0),
            _linha_com_criticidade(910.0, "1|3", 0, decidivel=1),
        ],
    )

    episodios = ler_episodios(tmp_path / ARQUIVO_CONFLITOS)
    relatorio = gerar_relatorio(ler_contagens(dados / ARQUIVO_EXECUCOES), episodios)

    assert episodios[2].criticidades == (1, 3)
    assert "Disputas de mesmo nível: 2" in relatorio
    assert "Disputas de nível misto: 1" in relatorio
    assert "Decidíveis e de mesmo nível: 1" in relatorio
    assert "1 episódios decidíveis, abaixo do piso" in relatorio


def test_dados_anteriores_a_p20_declaram_a_criticidade_indisponivel(tmp_path: Path) -> None:
    """`bloco10_conflitos/` não tem as colunas: lê, mas não inventa o valor."""
    dados = _dados(tmp_path, [["multiplas_emergencias", "PREEMPCAO", 101, 1, 1, 15]])
    _escrever(
        tmp_path / ARQUIVO_CONFLITOS,
        CABECALHO_CONFLITOS,
        [
            [
                "multiplas_emergencias",
                "PREEMPCAO",
                101,
                "CRUZ_TESTE_1",
                310.0,
                1.5,
                15,
                2,
                "AMB|BMB",
                "AMBULANCIA|BOMBEIRO",
                1,
                1,
            ]
        ],
    )

    episodios = ler_episodios(tmp_path / ARQUIVO_CONFLITOS)
    relatorio = gerar_relatorio(ler_contagens(dados / ARQUIVO_EXECUCOES), episodios)

    assert episodios[0].mesmo_nivel is None
    assert "Indisponível" in relatorio


def test_sem_execucao_nenhuma_o_relatorio_diz_o_que_fazer() -> None:
    assert "Rode o lote antes." in gerar_relatorio((), ())
