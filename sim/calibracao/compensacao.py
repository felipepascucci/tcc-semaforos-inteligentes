"""Calibração de E7 — execução de P17 (`context/09`, "Critério da calibração").

    python -m sim.calibracao.compensacao --paralelo 6     # roda e avalia
    python -m sim.calibracao.compensacao --so-avaliar     # refaz a conta do disco

A grade, os cenários, as seeds e a regra de escolha estão aqui **exatamente**
como foram declarados e commitados antes deste código (`09c1c8d`). Mudar
qualquer um deles depois de ver resultado é o que a regra de parada proíbe: a
calibração é **uma rodada**, e a combinação escolhida é congelada mesmo que fique
abaixo da meta de H2. O veredito de H2 vem do Bloco 8, não daqui.

O QUE SE MEDE

Para cada cenário `c`, com as médias entre as seeds da espera média transversal
de cada execução (`tempo_espera_medio_transversal_s`)::

    M(c) = (PREEMPCAO - COMPENSADA) / (PREEMPCAO - FIXO)

que é a fração do **acréscimo** causado pela preempção que a compensação devolve
— a mesma conta de `resumir_h2` em `analysis/relatorio_piloto.py`. A pontuação de
uma combinação é a média de `M` nos dois cenários.

`FIXO` e `PREEMPCAO` rodam **uma vez** por (cenário, seed): nenhum dos dois
depende de `K` nem de `n` (`FIXO` não chama o motor, e `PREEMPCAO` zera
`n_ciclos_compensacao`). Só o braço compensado roda uma vez por combinação.
"""

from __future__ import annotations

import argparse
import csv
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from sim.controlador import executor, lote
from sim.controlador.coletor import ARQUIVO_EXECUCOES, DADOS

#: Grade declarada em `context/09` P17 antes do código. Não alterar.
GRADE_K = (0.25, 0.5, 0.7, 1.0, 1.5)
GRADE_N = (1, 2, 3)
CENARIOS = ("moderado", "intenso")
SEEDS = (101, 102, 103, 104, 105)

#: Onde os CSV da calibração ficam: fora de `analysis/data/` raiz, que guarda o
#: piloto de 2026-08-26, e fora de qualquer pasta de outro experimento.
SAIDA = DADOS / "calibracao_p17"
ARQUIVO_RESULTADO = "resultado_calibracao.csv"
ARQUIVO_BASELINES = "baselines_calibracao.csv"

BRACO_COMPENSADO = "PREEMPCAO_COMPENSADA"
BRACOS_BASE = ("FIXO", "PREEMPCAO")


class CalibracaoIncompletaError(RuntimeError):
    """Os baselines não têm todas as execuções válidas; não há contra o que medir."""


def ajustes_de(k: float, n: int) -> executor.Ajustes:
    """Os ajustes de uma combinação da grade, na forma que o lote espera."""
    return tuple(sorted((("ganho_compensacao_k", k), ("n_ciclos_compensacao", float(n)))))


def combinacoes() -> tuple[tuple[float, int], ...]:
    """As 15 combinações (K, n) da grade, em ordem estável."""
    return tuple((k, n) for n in GRADE_N for k in GRADE_K)


def pontos(seeds: Sequence[int] = SEEDS) -> tuple[lote.Ponto, ...]:
    """A matriz da calibração: baselines uma vez, braço compensado por combinação."""
    base = lote.matriz(CENARIOS, BRACOS_BASE, seeds)
    compensados = tuple(
        ponto
        for k, n in combinacoes()
        for ponto in lote.matriz(CENARIOS, (BRACO_COMPENSADO,), seeds, ajustes_de(k, n))
    )
    return base + compensados


# ---------------------------------------------------------------------------
# Avaliação — lê só o que está em disco, para poder ser refeita sem SUMO
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LinhaExecucao:
    """O que a avaliação usa de uma linha de `execucoes.csv`."""

    cenario: str
    modo: str
    seed: int
    espera_transversal_s: float
    travessia_ve_s: float
    incidentes: int


def ler_execucoes(arquivo: Path) -> tuple[LinhaExecucao, ...]:
    """Lê `execucoes.csv`; arquivo ausente é conjunto vazio."""
    if not arquivo.is_file():
        return ()
    with arquivo.open(encoding="utf-8", newline="") as entrada:
        return tuple(
            LinhaExecucao(
                cenario=linha["cenario"],
                modo=linha["modo"],
                seed=int(linha["seed"]),
                espera_transversal_s=float(linha["tempo_espera_medio_transversal_s"]),
                travessia_ve_s=float(linha["tempo_medio_travessia_ve_s"]),
                incidentes=int(linha["colisoes"])
                + int(linha["teleportes"])
                + int(linha["violacoes"]),
            )
            for linha in csv.DictReader(entrada)
        )


@dataclass(frozen=True)
class Baseline:
    """Os dois braços de referência de um cenário, já em média entre as seeds."""

    cenario: str
    espera_fixo_s: float
    espera_preempcao_s: float
    travessia_ve_fixo_s: float
    travessia_ve_preempcao_s: float

    @property
    def acrescimo_s(self) -> float:
        """Quanto a preempção acrescenta à espera transversal."""
        return self.espera_preempcao_s - self.espera_fixo_s

    @property
    def custo(self) -> float:
        """Acréscimo relativo ao baseline sem intervenção."""
        return self.acrescimo_s / self.espera_fixo_s


@dataclass(frozen=True)
class AvaliacaoCombinacao:
    """O resultado de uma combinação (K, n) da grade.

    Attributes:
        k: `ganho_compensacao_k`.
        n: `n_ciclos_compensacao`.
        validas: Execuções válidas do braço compensado, de todas as esperadas.
        esperadas: Quantas execuções a combinação deveria ter.
        mitigacao: `M(c)` por cenário; `None` onde faltou execução.
        travessia_ve_s: Tempo médio de travessia do VE no braço compensado.
    """

    k: float
    n: int
    validas: int
    esperadas: int
    mitigacao: Mapping[str, float | None]
    travessia_ve_s: Mapping[str, float | None]

    @property
    def eliminada(self) -> bool:
        """Regra 3 do critério: qualquer execução perdida elimina a combinação."""
        return self.validas < self.esperadas or any(m is None for m in self.mitigacao.values())

    @property
    def pontuacao(self) -> float | None:
        """Regra 2 do critério: média de `M` nos cenários. `None` se eliminada."""
        if self.eliminada:
            return None
        valores = [m for m in self.mitigacao.values() if m is not None]
        return statistics.fmean(valores)


def _media(valores: Sequence[float]) -> float:
    return statistics.fmean(valores)


def baselines(linhas: Sequence[LinhaExecucao], seeds: Sequence[int]) -> dict[str, Baseline]:
    """Médias de `FIXO` e `PREEMPCAO` por cenário.

    Raises:
        CalibracaoIncompletaError: se faltar alguma seed num dos dois braços, ou
            se alguma linha trouxer incidente. Sem baseline completo, `M` não
            seria comparável entre as combinações.
    """
    resultado: dict[str, Baseline] = {}
    for cenario in CENARIOS:
        por_modo: dict[str, list[LinhaExecucao]] = {}
        for modo in BRACOS_BASE:
            achadas = [
                linha
                for linha in linhas
                if linha.cenario == cenario and linha.modo == modo and linha.incidentes == 0
            ]
            if sorted(linha.seed for linha in achadas) != sorted(seeds):
                raise CalibracaoIncompletaError(
                    f"{cenario}/{modo}: seeds válidas {sorted(linha.seed for linha in achadas)},"
                    f" esperadas {sorted(seeds)}"
                )
            por_modo[modo] = achadas
        resultado[cenario] = Baseline(
            cenario=cenario,
            espera_fixo_s=_media([x.espera_transversal_s for x in por_modo["FIXO"]]),
            espera_preempcao_s=_media([x.espera_transversal_s for x in por_modo["PREEMPCAO"]]),
            travessia_ve_fixo_s=_media([x.travessia_ve_s for x in por_modo["FIXO"]]),
            travessia_ve_preempcao_s=_media([x.travessia_ve_s for x in por_modo["PREEMPCAO"]]),
        )
    return resultado


def avaliar_combinacao(
    k: float,
    n: int,
    linhas: Sequence[LinhaExecucao],
    base: Mapping[str, Baseline],
    seeds: Sequence[int],
) -> AvaliacaoCombinacao:
    """Calcula `M` por cenário para uma combinação, a partir das suas linhas."""
    mitigacao: dict[str, float | None] = {}
    travessia: dict[str, float | None] = {}
    validas = 0
    for cenario in CENARIOS:
        achadas = [
            linha
            for linha in linhas
            if linha.cenario == cenario
            and linha.modo == BRACO_COMPENSADO
            and linha.seed in seeds
            and linha.incidentes == 0
        ]
        validas += len(achadas)
        referencia = base[cenario]
        if sorted(linha.seed for linha in achadas) != sorted(seeds) or referencia.acrescimo_s <= 0:
            mitigacao[cenario] = None
            travessia[cenario] = None
            continue
        compensada = _media([x.espera_transversal_s for x in achadas])
        mitigacao[cenario] = (referencia.espera_preempcao_s - compensada) / referencia.acrescimo_s
        travessia[cenario] = _media([x.travessia_ve_s for x in achadas])
    return AvaliacaoCombinacao(
        k=k,
        n=n,
        validas=validas,
        esperadas=len(CENARIOS) * len(seeds),
        mitigacao=mitigacao,
        travessia_ve_s=travessia,
    )


def escolher(avaliacoes: Sequence[AvaliacaoCombinacao]) -> AvaliacaoCombinacao | None:
    """Regra 4 do critério: maior pontuação; empate exato, menor `n` e depois menor `K`.

    Returns:
        A combinação escolhida, ou `None` se todas foram eliminadas.
    """
    candidatas = [a for a in avaliacoes if a.pontuacao is not None]
    if not candidatas:
        return None
    return max(candidatas, key=lambda a: (a.pontuacao, -a.n, -a.k))


def avaliar(
    saida: Path = SAIDA, seeds: Sequence[int] = SEEDS
) -> tuple[dict[str, Baseline], tuple[AvaliacaoCombinacao, ...]]:
    """Lê os CSV consolidados da calibração e avalia as 15 combinações."""
    base = baselines(ler_execucoes(saida / ARQUIVO_EXECUCOES), seeds)
    avaliacoes = tuple(
        avaliar_combinacao(
            k,
            n,
            ler_execucoes(
                saida / executor.rotulo_dos_ajustes(ajustes_de(k, n)) / ARQUIVO_EXECUCOES
            ),
            base,
            seeds,
        )
        for k, n in combinacoes()
    )
    return base, avaliacoes


# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------


def _num(valor: float | None, casas: int = 4) -> str:
    return "" if valor is None else f"{valor:.{casas}f}"


def gravar(
    saida: Path,
    base: Mapping[str, Baseline],
    avaliacoes: Sequence[AvaliacaoCombinacao],
    escolhida: AvaliacaoCombinacao | None,
) -> None:
    """Escreve os dois CSV da calibração em `saida`."""
    saida.mkdir(parents=True, exist_ok=True)
    with (saida / ARQUIVO_BASELINES).open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(
            (
                "cenario",
                "espera_fixo_s",
                "espera_preempcao_s",
                "custo",
                "travessia_ve_fixo_s",
                "travessia_ve_preempcao_s",
            )
        )
        for cenario in CENARIOS:
            b = base[cenario]
            escritor.writerow(
                (
                    cenario,
                    _num(b.espera_fixo_s),
                    _num(b.espera_preempcao_s),
                    _num(b.custo),
                    _num(b.travessia_ve_fixo_s),
                    _num(b.travessia_ve_preempcao_s),
                )
            )

    with (saida / ARQUIVO_RESULTADO).open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(
            (
                "ganho_compensacao_k",
                "n_ciclos_compensacao",
                "execucoes_validas",
                "eliminada",
                *(f"mitigacao_{c}" for c in CENARIOS),
                "pontuacao",
                *(f"travessia_ve_compensada_{c}_s" for c in CENARIOS),
                "escolhida",
            )
        )
        for a in avaliacoes:
            escritor.writerow(
                (
                    f"{a.k:g}",
                    a.n,
                    f"{a.validas}/{a.esperadas}",
                    int(a.eliminada),
                    *(_num(a.mitigacao[c]) for c in CENARIOS),
                    _num(a.pontuacao),
                    *(_num(a.travessia_ve_s[c], 2) for c in CENARIOS),
                    int(a is escolhida),
                )
            )


def _pct(valor: float | None) -> str:
    return "—" if valor is None else f"{valor * 100:+.1f}%".replace(".", ",")


def relatorio(
    base: Mapping[str, Baseline],
    avaliacoes: Sequence[AvaliacaoCombinacao],
    escolhida: AvaliacaoCombinacao | None,
) -> str:
    """Resumo em texto para o terminal."""
    linhas = ["", "=== calibração de E7 (P17) ===", ""]
    for cenario in CENARIOS:
        b = base[cenario]
        linhas.append(
            f"  {cenario:<9} FIXO {b.espera_fixo_s:6.2f}s · PREEMPCAO {b.espera_preempcao_s:6.2f}s"
            f" · custo {_pct(b.custo)} · VE {b.travessia_ve_preempcao_s:6.1f}s"
        )
    linhas += [
        "",
        f"  {'K':>5} {'n':>2} {'válidas':>8} "
        + " ".join(f"{'M ' + c:>11}" for c in CENARIOS)
        + f" {'pontuação':>10}",
    ]
    for a in avaliacoes:
        marca = "  <- escolhida" if a is escolhida else (" (eliminada)" if a.eliminada else "")
        linhas.append(
            f"  {a.k:>5g} {a.n:>2} {a.validas:>4}/{a.esperadas:<3} "
            + " ".join(f"{_pct(a.mitigacao[c]):>11}" for c in CENARIOS)
            + f" {_pct(a.pontuacao):>10}{marca}"
        )
    linhas.append("")
    if escolhida is None:
        linhas.append("  nenhuma combinação sobreviveu à regra 3 do critério")
    else:
        linhas.append(
            f"  escolhida: K = {escolhida.k:g}, n = {escolhida.n}"
            f" (pontuação {_pct(escolhida.pontuacao)}; meta de H2 no Bloco 8: +15,0%)"
        )
    return "\n".join(linhas)


def main(argumentos: Sequence[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(description="Calibração de E7 — P17.")
    analisador.add_argument("--paralelo", type=int, default=6, help="processos simultâneos")
    analisador.add_argument("--saida", type=Path, default=SAIDA)
    analisador.add_argument(
        "--so-avaliar", action="store_true", help="não roda nada; refaz a conta dos CSV em disco"
    )
    opcoes = analisador.parse_args(argumentos)

    if not opcoes.so_avaliar:
        matriz = pontos()
        print(f"calibração P17: {len(matriz)} execuções · {opcoes.paralelo} processos")
        concluidas = 0

        def progresso(resultado: lote.ResultadoDoPonto) -> None:
            nonlocal concluidas
            concluidas += 1
            estado = "ok" if resultado.valida else "DESCARTE"
            print(f"  [{concluidas:>3}/{len(matriz)}] {resultado.ponto!s:<90} {estado}", flush=True)

        resumo = lote.rodar(
            matriz,
            paralelo=opcoes.paralelo,
            persistir=False,
            marcar_exemplares=False,
            saida=opcoes.saida,
            ao_terminar=progresso,
        )
        for resultado in resumo.descartadas:
            detalhe = resultado.erro or "; ".join(resultado.problemas)
            print(f"  ! {resultado.ponto}: {detalhe}")

    base, avaliacoes = avaliar(opcoes.saida)
    escolhida = escolher(avaliacoes)
    gravar(opcoes.saida, base, avaliacoes, escolhida)
    print(relatorio(base, avaliacoes, escolhida))
    return 0 if escolhida is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
