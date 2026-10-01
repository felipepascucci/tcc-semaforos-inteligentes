"""Resumo da contagem de conflitos entre VEs — entrega 10.1 do Bloco 10.

Responde à pergunta que P19 deixou aberta e que trava o resto do bloco:
**quantos eventos de conflito entre veículos de emergência existem por
execução?** Sem esse número não se escolhe regularização, não se divide treino e
teste, e não se sabe se o cenário `multiplas_emergencias` sustenta um modelo ou
se a entrega 10.2 (cenário mais denso) é obrigatória.

O que conta como evento está definido em `sim/controlador/coletor.py`: um
**episódio**, isto é, uma disputa contígua no mesmo cruzamento entre o mesmo
conjunto de VEs. E o que conta como evento **treinável** é o episódio decidível
— aquele em que não havia preempção em curso, porque a guarda de oscilação é
regra rígida acima do modelo (`context/09` P19).

Este módulo não faz estatística inferencial nem produz resultado do capítulo 5.
Ele descreve um conjunto de execuções para uma decisão de projeto.
"""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DADOS = RAIZ / "analysis" / "data"

ARQUIVO_EXECUCOES = "execucoes.csv"
ARQUIVO_CONFLITOS = "conflitos_por_execucao.csv"

#: Piso declarado em P19: abaixo disso, o conjunto de treino sustenta o desenho
#: mas a conclusão de H4 nasce com poder estatístico baixo — e isso tem de ser
#: declarado na análise, não descoberto na arguição.
PISO_EVENTOS_DE_TREINO = 100


@dataclass(frozen=True)
class Episodio:
    """Uma linha de `conflitos_por_execucao.csv`."""

    cenario: str
    modo: str
    seed: int
    id_semaforo: str
    t_inicio_s: float
    duracao_s: float
    passos: int
    n_ves: int
    ids_veiculos: tuple[str, ...]
    tipos: tuple[str, ...]
    decidivel: bool
    decidivel_em_algum_passo: bool
    criticidades: tuple[int, ...] | None = None
    mesmo_nivel: bool | None = None

    @property
    def chave(self) -> tuple[str, str, int]:
        """O ponto experimental de onde o episódio veio."""
        return (self.cenario, self.modo, self.seed)

    @property
    def treinavel(self) -> bool:
        """Se o modelo de P19 decide este episódio.

        Precisa estar em aberto (decidível) **e**, desde a P20, ser entre VEs de
        mesma criticidade — entre níveis diferentes a regra decide. Em dados
        anteriores à P20, sem a coluna, vale só a primeira condição.
        """
        return self.decidivel and self.mesmo_nivel is not False


@dataclass(frozen=True)
class ContagemDaExecucao:
    """Os agregados de conflito de uma linha de `execucoes.csv`."""

    cenario: str
    modo: str
    seed: int
    eventos: int
    decidiveis: int
    passos: int

    @property
    def chave(self) -> tuple[str, str, int]:
        """O ponto experimental."""
        return (self.cenario, self.modo, self.seed)


def ler_episodios(caminho: Path) -> tuple[Episodio, ...]:
    """Lê `conflitos_por_execucao.csv`.

    Args:
        caminho: Caminho do arquivo.

    Returns:
        Um episódio por linha, ou vazio se o arquivo não existir — nenhum
        conflito em nenhuma execução é um resultado possível, e é justamente o
        resultado que tornaria a 10.2 obrigatória.

    As colunas `criticidades` e `mesmo_nivel` entraram com a P20. Arquivos
    anteriores — `analysis/data/bloco10_conflitos/` é o caso — são lidos assim
    mesmo, com os dois campos `None`: a informação não existe, e inventar um
    valor padrão seria afirmar algo que a execução não mediu.
    """
    if not caminho.is_file():
        return ()
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return tuple(
            Episodio(
                cenario=linha["cenario"],
                modo=linha["modo"],
                seed=int(linha["seed"]),
                id_semaforo=linha["id_semaforo"],
                t_inicio_s=float(linha["t_inicio_s"]),
                duracao_s=float(linha["duracao_s"]),
                passos=int(linha["passos"]),
                n_ves=int(linha["n_ves"]),
                ids_veiculos=tuple(linha["ids_veiculos"].split("|")),
                tipos=tuple(linha["tipos"].split("|")),
                decidivel=linha["decidivel"] == "1",
                decidivel_em_algum_passo=linha["decidivel_em_algum_passo"] == "1",
                criticidades=(
                    tuple(int(nivel) for nivel in linha["criticidades"].split("|"))
                    if linha.get("criticidades")
                    else None
                ),
                mesmo_nivel=(linha["mesmo_nivel"] == "1" if linha.get("mesmo_nivel") else None),
            )
            for linha in csv.DictReader(arquivo)
        )


def ler_contagens(caminho: Path) -> tuple[ContagemDaExecucao, ...]:
    """Lê os agregados de conflito de `execucoes.csv`.

    As três colunas entraram com a 10.1, então execuções gravadas antes dela não
    as têm — o piloto de 2026-08-26 é o caso. Elas são lidas com padrão zero em
    vez de quebrar, porque uma execução sem a coluna de fato não contou conflito
    nenhum.

    Args:
        caminho: Caminho do arquivo.

    Returns:
        Uma contagem por execução, ou vazio se o arquivo não existir.
    """
    if not caminho.is_file():
        return ()
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return tuple(
            ContagemDaExecucao(
                cenario=linha["cenario"],
                modo=linha["modo"],
                seed=int(linha["seed"]),
                eventos=int(linha.get("eventos_conflito") or 0),
                decidiveis=int(linha.get("eventos_conflito_decidiveis") or 0),
                passos=int(linha.get("passos_em_conflito") or 0),
            )
            for linha in csv.DictReader(arquivo)
        )


def _distribuicao(valores: Iterable[object]) -> str:
    """Formata uma contagem por categoria, da mais frequente para a menos."""
    contagem = Counter(str(valor) for valor in valores)
    if not contagem:
        return "—"
    return ", ".join(
        f"{categoria}: {quantas}"
        for categoria, quantas in sorted(contagem.items(), key=lambda par: (-par[1], par[0]))
    )


def _faixa(valores: Sequence[int]) -> str:
    """Formata mínimo, mediana e máximo de uma amostra de inteiros."""
    if not valores:
        return "—"
    return f"mín {min(valores)} · mediana {statistics.median(valores):.1f} · máx {max(valores)}"


def gerar_relatorio(contagens: Sequence[ContagemDaExecucao], episodios: Sequence[Episodio]) -> str:
    """Monta o relatório de texto.

    Args:
        contagens: Agregados por execução, de `execucoes.csv`. São eles que
            definem o denominador, porque uma execução sem conflito nenhum não
            aparece em `conflitos_por_execucao.csv`.
        episodios: Episódios individuais, para a distribuição.

    Returns:
        O relatório, pronto para imprimir.
    """
    linhas = ["# Conflitos entre VEs — entrega 10.1", ""]

    if not contagens:
        linhas.append("Nenhuma execução encontrada. Rode o lote antes.")
        return "\n".join(linhas)

    total_eventos = sum(contagem.eventos for contagem in contagens)
    total_decidiveis = sum(contagem.decidiveis for contagem in contagens)
    total_passos = sum(contagem.passos for contagem in contagens)
    por_execucao = [contagem.eventos for contagem in contagens]
    decidiveis_por_execucao = [contagem.decidiveis for contagem in contagens]

    linhas += [
        f"Execuções: {len(contagens)}",
        f"Cenários: {_distribuicao(contagem.cenario for contagem in contagens)}",
        f"Modos: {_distribuicao(contagem.modo for contagem in contagens)}",
        "",
        "## Volume",
        "",
        f"Episódios de conflito: {total_eventos}",
        f"Episódios decidíveis (sem preempção em curso): {total_decidiveis}",
        f"Passos de simulação em conflito: {total_passos}",
        "",
        f"Por execução, episódios: {_faixa(por_execucao)}",
        f"Por execução, decidíveis: {_faixa(decidiveis_por_execucao)}",
        "",
    ]

    if total_eventos:
        fracao = 100.0 * total_decidiveis / total_eventos
        linhas.append(f"Fração decidível: {fracao:.1f}%")
    if total_eventos and total_passos:
        linhas.append(
            f"Passos por episódio, em média: {total_passos / total_eventos:.1f} "
            "— é o fator que separar episódio de passo evita inflar."
        )
    linhas.append("")

    if episodios:
        duracoes = [episodio.duracao_s for episodio in episodios]
        linhas += [
            "## Forma dos episódios",
            "",
            f"VEs por episódio: {_distribuicao(episodio.n_ves for episodio in episodios)}",
            f"Por cruzamento: {_distribuicao(episodio.id_semaforo for episodio in episodios)}",
            f"Pares de tipos: {_distribuicao('+'.join(episodio.tipos) for episodio in episodios)}",
            (f"Duração: mediana {statistics.median(duracoes):.1f}s · máx {max(duracoes):.1f}s"),
            "",
        ]

    treinaveis = total_decidiveis
    linhas += ["## Criticidade (P20)", ""]
    if not episodios:
        linhas.append("Sem episódios.")
    elif any(episodio.mesmo_nivel is None for episodio in episodios):
        linhas.append(
            "Indisponível: os dados são anteriores à P20 e não registram a "
            "criticidade. O volume abaixo usa só a condição de decidível."
        )
    else:
        mesmo = [episodio for episodio in episodios if episodio.mesmo_nivel]
        treinaveis = sum(1 for episodio in episodios if episodio.treinavel)
        linhas += [
            f"Disputas de mesmo nível: {len(mesmo)} — o domínio do modelo de P19",
            f"Disputas de nível misto: {len(episodios) - len(mesmo)} — decididas pela regra",
            f"Decidíveis e de mesmo nível: {treinaveis}",
            "Níveis por episódio: "
            + _distribuicao(
                "+".join(str(nivel) for nivel in episodio.criticidades or ())
                for episodio in episodios
            ),
        ]
    linhas.append("")

    linhas += [
        "## O que isto decide",
        "",
        _veredito(treinaveis),
        "",
        "A divisão treino/teste é por seed, com o treino fora do intervalo 1..50 "
        "do Bloco 8 (guarda de P16), então o conjunto de treino é um subconjunto "
        "do total acima.",
    ]
    return "\n".join(linhas)


def _veredito(decidiveis: int) -> str:
    """A leitura do número contra o piso declarado em P19, sem enfeite.

    `decidiveis` é o que o modelo de fato pode aprender: desde a P20, só os
    episódios decidíveis **e** de mesmo nível de criticidade.
    """
    if decidiveis >= PISO_EVENTOS_DE_TREINO:
        return (
            f"{decidiveis} episódios decidíveis, contra o piso de "
            f"{PISO_EVENTOS_DE_TREINO} declarado em P19. O cenário atual sustenta "
            "o treino; a entrega 10.2 (cenário mais denso) não é obrigatória por "
            "volume — desde que a divisão treino/teste preserve o piso."
        )
    return (
        f"{decidiveis} episódios decidíveis, abaixo do piso de "
        f"{PISO_EVENTOS_DE_TREINO} declarado em P19. Ou a entrega 10.2 cria um "
        "cenário mais denso em VEs para treinar, ou a conclusão de H4 nasce com "
        "poder estatístico baixo e isso precisa ser declarado na análise."
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada: `python -m analysis.resumo_conflitos`."""
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument("--dados", type=Path, default=DADOS)
    analisador.add_argument("--saida", type=Path, default=None)
    opcoes = analisador.parse_args(argv)

    relatorio = gerar_relatorio(
        ler_contagens(opcoes.dados / ARQUIVO_EXECUCOES),
        ler_episodios(opcoes.dados / ARQUIVO_CONFLITOS),
    )
    if opcoes.saida is not None:
        opcoes.saida.parent.mkdir(parents=True, exist_ok=True)
        opcoes.saida.write_text(relatorio + "\n", encoding="utf-8")
    print(relatorio)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
