"""RF03 — o VE atravessa os cruzamentos priorizados sem parar (`context/06` §2).

O critério de `06` §2 é `waitingCount == 0` para o VE: nenhuma parada na rota
inteira. A evidência é o próprio experimento, as 650 execuções do Bloco 8
(`analysis/data/bloco8/ve_por_execucao.csv`, coluna `paradas`), e não uma
execução escolhida para o teste: uma seed só passaria ou falharia conforme a
seed.

**O critério literal não é cumprido, e este teste o diz em voz alta.** No
braço `PREEMPCAO`, parte dos VEs para ao menos uma vez (`context/09`,
2026-10-08). O teste de cumprimento fica `xfail` **estrito**, por decisão do
Felipe: enquanto falhar, a suíte registra a falha esperada; se um dia passar, a
suíte quebra, e o relatório e o `09` precisam ser revistos. Os testes sem
`xfail` fixam o que o dado de fato mostra, para que o texto do TCC não possa
dizer outra coisa sem que um teste quebre.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
CSV_VE = RAIZ / "analysis" / "data" / "bloco8" / "ve_por_execucao.csv"

BASELINE = "FIXO"
BRACOS_COM_PREEMPCAO = ("PREEMPCAO", "PREEMPCAO_COMPENSADA", "PREEMPCAO_ML")


def _paradas_por_braco() -> dict[tuple[str, str], list[int]]:
    with CSV_VE.open(encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    assert linhas, "o CSV do Bloco 8 está vazio"
    paradas: dict[tuple[str, str], list[int]] = {}
    for linha in linhas:
        paradas.setdefault((linha["cenario"], linha["modo"]), []).append(int(linha["paradas"]))
    return paradas


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RF03 FALHOU no Bloco 8: no braço PREEMPCAO, parte dos VEs para ao menos uma vez "
        "(context/09, 2026-10-08)"
    ),
)
def test_nenhum_ve_para_nos_bracos_com_preempcao() -> None:
    """O critério de `06` §2, ao pé da letra, sobre todas as travessias do experimento."""
    for (cenario, modo), paradas in _paradas_por_braco().items():
        if modo in BRACOS_COM_PREEMPCAO:
            assert max(paradas) == 0, f"{cenario}/{modo}: VE com parada"


def test_no_baseline_todo_ve_para() -> None:
    """O contraste que o RF03 pressupõe: sem preempção, o corredor não é verde."""
    for (cenario, modo), paradas in _paradas_por_braco().items():
        if modo == BASELINE:
            assert min(paradas) > 0, f"{cenario}: VE sem parada no FIXO"


def test_com_preempcao_o_ve_para_menos_que_no_baseline() -> None:
    """Sem meta declarada, só a direção: nenhum limiar foi escolhido olhando o dado.

    Em todo cenário e braço com preempção, a média de paradas por VE fica abaixo
    da do `FIXO` do mesmo cenário.
    """
    paradas = _paradas_por_braco()
    for (cenario, modo), valores in paradas.items():
        if modo not in BRACOS_COM_PREEMPCAO:
            continue
        base = paradas[(cenario, BASELINE)]
        assert sum(valores) / len(valores) < sum(base) / len(base), f"{cenario}/{modo}"
