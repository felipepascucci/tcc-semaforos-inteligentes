"""Grau de saturação dos cenários — entrega 3.0, encaminhamento de P11.

Converte os fluxos do pré-projeto (300 / 700 / 1200 veíc./h, que **não mudam**)
no grau de saturação de cada cenário, usando o fluxo de saturação **medido** por
`fluxo_saturacao.py`. É o que permite afirmar "saturação moderada a intensa" — a
condição de H1, decisão P1 — por medição em vez de por decreto.

A cadeia inteira, e onde cada elo vive::

    fluxo de saturação medido      analysis/data/fluxo_saturacao.csv
      -> capacidade da aproximação   capacidade_veic_h(), aqui
      -> v/c derivado                grau_de_saturacao(), aqui
      -> v/c medido na malha         sim/validacao/ (entrega 3.4)

Este módulo é **aritmética pura**: nenhuma linha depende do SUMO estar instalado,
e é por isso que ele tem teste unitário rodando na suíte padrão. A separação
também deixa explícito onde termina a medição e começa a interpretação.

    python -m sim.calibracao.cenarios          # gera a tabela da metodologia

ALERTA METODOLÓGICO — FLUXO INTERROMPIDO, NÃO ININTERRUPTO. Os limiares de
veíc./h/faixa que circulam para classificar trânsito (leve até ~700, moderado
até ~1400) são de **fluxo ininterrupto**: rodovia, capacidade 1800 a 2200 por
faixa. Aqui é arterial urbana semaforizada, em que a capacidade é o fluxo de
saturação multiplicado pela razão de verde — com 30 s de verde em 70 s de ciclo,
menos da metade. Aplicar os limiares de rodovia reclassificaria o cenário
`intenso` como `moderado` e derrubaria a formulação de H1.
"""

from __future__ import annotations

import argparse
import csv
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from adapters.terminal import saida_utf8

RAIZ = Path(__file__).resolve().parents[2]
CENARIOS_YAML = RAIZ / "sim" / "config" / "cenarios.yaml"
MEDICAO_CSV = RAIZ / "analysis" / "data" / "fluxo_saturacao.csv"
SAIDA_CSV = RAIZ / "analysis" / "data" / "calibracao_cenarios.csv"


# ---------------------------------------------------------------------------
# Estruturas
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Programa:
    """Programa semafórico do baseline, do ponto de vista da capacidade.

    Attributes:
        n_fases: Fases do ciclo.
        verde_s: Verde de cada fase, em segundos.
        amarelo_s: Amarelo de cada fase, em segundos.
        all_red_s: All-red entre fases, em segundos.
    """

    n_fases: int
    verde_s: float
    amarelo_s: float
    all_red_s: float

    @property
    def ciclo_s(self) -> float:
        """Duração do ciclo completo, em segundos."""
        return self.n_fases * (self.verde_s + self.amarelo_s + self.all_red_s)


@dataclass(frozen=True)
class Aproximacao:
    """Uma aproximação semaforizada, com o fluxo de saturação medido nela.

    Attributes:
        nome: `"arterial"` ou `"transversal"`.
        faixas: Faixas por sentido.
        fluxo_saturacao_veic_h_faixa: Medido em `fluxo_saturacao.py`.
        tempo_perdido_partida_s: Medido junto, na mesma execução.
    """

    nome: str
    faixas: int
    fluxo_saturacao_veic_h_faixa: float
    tempo_perdido_partida_s: float = 0.0


@dataclass(frozen=True)
class LinhaCenario:
    """Uma linha da tabela de calibração — um cenário, as duas aproximações.

    Attributes:
        cenario: Nome do cenário.
        fluxo_arterial_veic_h: Demanda da aproximação arterial (do pré-projeto).
        capacidade_arterial_veic_h: Capacidade calculada da arterial.
        grau_saturacao: v/c da arterial. É ele que classifica o cenário.
        classificacao: `"leve"`, `"moderado"` ou `"intenso"`.
        fluxo_transversal_veic_h: Demanda **derivada** da transversal.
        capacidade_transversal_veic_h: Capacidade calculada da transversal.
    """

    cenario: str
    fluxo_arterial_veic_h: float
    capacidade_arterial_veic_h: float
    grau_saturacao: float
    classificacao: str
    fluxo_transversal_veic_h: float
    capacidade_transversal_veic_h: float


# ---------------------------------------------------------------------------
# Aritmética — pura e testável sem SUMO
# ---------------------------------------------------------------------------


def verde_efetivo_s(programa: Programa, tempo_perdido_partida_s: float) -> float:
    """Verde efetivo de uma fase, em segundos.

    `verde + amarelo - tempo perdido na partida`. As três parcelas, uma a uma:

    * o **verde** escoa fila à taxa de saturação;
    * o **amarelo** também escoa — quem já não consegue parar atravessa, e é
      assim que o SUMO se comporta;
    * o **all-red** é perda de liberação, integralmente: ninguém entra no
      cruzamento;
    * o **tempo perdido na partida** é medido junto com o fluxo de saturação, no
      mesmo experimento, e não estimado.

    Nada aqui é convenção escolhida a posteriori: é a definição clássica de verde
    efetivo com o tempo perdido substituído por medição.
    """
    return programa.verde_s + programa.amarelo_s - tempo_perdido_partida_s


def capacidade_veic_h(
    aproximacao: Aproximacao, programa: Programa, verde_da_fase_s: float | None = None
) -> float:
    """Capacidade da aproximação, em veículos por hora.

    `c = faixas x fluxo_de_saturação x verde_efetivo / ciclo`.

    Args:
        aproximacao: Aproximação, com o fluxo de saturação medido nela.
        programa: Programa semafórico do baseline.
        verde_da_fase_s: Verde desta aproximação, se diferente do padrão do
            programa.

    Returns:
        Capacidade em veíc./h.
    """
    efetivo = verde_efetivo_s(programa, aproximacao.tempo_perdido_partida_s)
    if verde_da_fase_s is not None:
        efetivo = verde_da_fase_s + programa.amarelo_s - aproximacao.tempo_perdido_partida_s
    razao_de_verde = efetivo / programa.ciclo_s
    return aproximacao.faixas * aproximacao.fluxo_saturacao_veic_h_faixa * razao_de_verde


def grau_de_saturacao(fluxo_veic_h: float, capacidade_veic_h_: float) -> float:
    """Razão v/c — demanda dividida por capacidade.

    Raises:
        ValueError: se a capacidade não for positiva.
    """
    if capacidade_veic_h_ <= 0:
        raise ValueError("capacidade precisa ser > 0")
    return fluxo_veic_h / capacidade_veic_h_


def classificar(grau: float, leve_ate: float, moderado_ate: float) -> str:
    """Classifica o grau de saturação nas faixas de `context/04` §5.

    Args:
        grau: Razão v/c.
        leve_ate: Teto da faixa `leve` (0,40 no context/04 §5).
        moderado_ate: Teto da faixa `moderado` (0,75).

    Returns:
        `"leve"`, `"moderado"` ou `"intenso"`.
    """
    if grau < leve_ate:
        return "leve"
    if grau <= moderado_ate:
        return "moderado"
    return "intenso"


def fluxo_para_grau(grau_alvo: float, capacidade_veic_h_: float) -> float:
    """Demanda que põe uma aproximação num grau de saturação dado.

    É como a demanda das transversais é definida (decisão de 2026-08-25): elas
    recebem o fluxo que as coloca **no mesmo grau de saturação da arterial**, e
    não um número escolhido à mão.

    Duas alternativas foram descartadas. Repetir o fluxo nominal da arterial
    (300/700/1200) numa via de uma faixa levaria o cenário `intenso` a v/c > 1,5:
    fila que não dissipa, gridlock e teleporte — execução inválida por
    `context/04` §12. Uma fração fixa declarada ("metade da arterial") seria
    exatamente o tipo de número sem lastro que o encaminhamento de P11 existe
    para eliminar.
    """
    return grau_alvo * capacidade_veic_h_


def montar_tabela(
    cenarios: Mapping[str, Mapping[str, Any]],
    arterial: Aproximacao,
    transversal: Aproximacao,
    programa: Programa,
    limiares: Mapping[str, float],
) -> list[LinhaCenario]:
    """Monta a tabela de calibração da metodologia.

    Args:
        cenarios: Cenários de `cenarios.yaml`, com `fluxo_arterial_veic_h`.
        arterial: Aproximação arterial, com o fluxo de saturação medido.
        transversal: Aproximação transversal, idem.
        programa: Programa semafórico do baseline.
        limiares: `leve_ate` e `moderado_ate`.

    Returns:
        Uma linha por cenário, na ordem em que aparecem na configuração.
    """
    capacidade_arterial = capacidade_veic_h(arterial, programa)
    capacidade_transversal = capacidade_veic_h(transversal, programa)

    linhas: list[LinhaCenario] = []
    for nome, definicao in cenarios.items():
        fluxo = float(definicao["fluxo_arterial_veic_h"])
        grau = grau_de_saturacao(fluxo, capacidade_arterial)
        linhas.append(
            LinhaCenario(
                cenario=nome,
                fluxo_arterial_veic_h=fluxo,
                capacidade_arterial_veic_h=capacidade_arterial,
                grau_saturacao=grau,
                classificacao=classificar(
                    grau, float(limiares["leve_ate"]), float(limiares["moderado_ate"])
                ),
                fluxo_transversal_veic_h=fluxo_para_grau(grau, capacidade_transversal),
                capacidade_transversal_veic_h=capacidade_transversal,
            )
        )
    return linhas


# ---------------------------------------------------------------------------
# Leitura da medição e da configuração
# ---------------------------------------------------------------------------


def carregar_configuracao(caminho: Path = CENARIOS_YAML) -> dict[str, Any]:
    """Lê `sim/config/cenarios.yaml`."""
    with caminho.open(encoding="utf-8") as arquivo:
        dados: dict[str, Any] = yaml.safe_load(arquivo)
    return dados


def carregar_medicao(caminho: Path = MEDICAO_CSV) -> dict[str, tuple[float, float]]:
    """Lê a medição do fluxo de saturação, agregando as faixas por aproximação.

    Returns:
        `{aproximacao: (fluxo_saturacao_medio_veic_h_faixa, tempo_perdido_medio_s)}`.

    Raises:
        FileNotFoundError: se a medição ainda não existir — a mensagem diz o que
            rodar, porque essa é a ordem obrigatória das duas etapas.
    """
    if not caminho.is_file():
        raise FileNotFoundError(
            f"{caminho} não existe. Rode antes:\n"
            "    python -m sim.calibracao.fluxo_saturacao\n"
            "O fluxo de saturação é MEDIDO na malha, não adotado da literatura (P11)."
        )

    por_aproximacao: dict[str, list[tuple[float, float]]] = {}
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        for registro in csv.DictReader(arquivo):
            por_aproximacao.setdefault(registro["aproximacao"], []).append(
                (
                    float(registro["fluxo_saturacao_veic_h_faixa"]),
                    float(registro["tempo_perdido_partida_s"]),
                )
            )

    return {
        nome: (
            sum(fluxo for fluxo, _ in medicoes) / len(medicoes),
            sum(perda for _, perda in medicoes) / len(medicoes),
        )
        for nome, medicoes in por_aproximacao.items()
    }


def aproximacoes_medidas(
    configuracao: Mapping[str, Any], medicao: Mapping[str, tuple[float, float]]
) -> tuple[Aproximacao, Aproximacao]:
    """Combina a geometria declarada com o fluxo de saturação medido."""
    geometria = configuracao["aproximacoes"]
    return tuple(  # type: ignore[return-value]
        Aproximacao(
            nome=nome,
            faixas=int(geometria[nome]["faixas"]),
            fluxo_saturacao_veic_h_faixa=medicao[nome][0],
            tempo_perdido_partida_s=medicao[nome][1],
        )
        for nome in ("arterial", "transversal")
    )


def programa_de(configuracao: Mapping[str, Any]) -> Programa:
    """Constrói o `Programa` a partir de `cenarios.yaml`."""
    dados = configuracao["programa"]
    return Programa(
        n_fases=int(dados["n_fases"]),
        verde_s=float(dados["verde_s"]),
        amarelo_s=float(dados["amarelo_s"]),
        all_red_s=float(dados["all_red_s"]),
    )


# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------


def gravar_csv(linhas: Sequence[LinhaCenario], destino: Path = SAIDA_CSV) -> Path:
    """Grava a tabela de calibração em `analysis/data/`."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(
            [
                "cenario",
                "fluxo_arterial_veic_h",
                "capacidade_arterial_veic_h",
                "grau_saturacao",
                "classificacao",
                "fluxo_transversal_veic_h",
                "capacidade_transversal_veic_h",
            ]
        )
        for linha in linhas:
            escritor.writerow(
                [
                    linha.cenario,
                    f"{linha.fluxo_arterial_veic_h:.0f}",
                    f"{linha.capacidade_arterial_veic_h:.0f}",
                    f"{linha.grau_saturacao:.3f}",
                    linha.classificacao,
                    f"{linha.fluxo_transversal_veic_h:.0f}",
                    f"{linha.capacidade_transversal_veic_h:.0f}",
                ]
            )
    return destino


def tabela_markdown(linhas: Sequence[LinhaCenario]) -> str:
    """Tabela pronta para colar na metodologia do TCC."""
    cabecalho = (
        "| Cenário | Fluxo arterial (veíc./h) | Capacidade (veíc./h) | v/c | "
        "Classificação | Fluxo transversal derivado (veíc./h) |\n"
        "|---|---|---|---|---|---|"
    )
    corpo = "\n".join(
        f"| `{linha.cenario}` | {linha.fluxo_arterial_veic_h:.0f} | "
        f"{linha.capacidade_arterial_veic_h:.0f} | {linha.grau_saturacao:.2f} | "
        f"{linha.classificacao} | {linha.fluxo_transversal_veic_h:.0f} |"
        for linha in linhas
    )
    return f"{cabecalho}\n{corpo}"


def conferir_plausibilidade(
    aproximacoes: Sequence[Aproximacao], faixa: Sequence[float]
) -> list[str]:
    """Confronta o fluxo de saturação medido com a faixa reportada na literatura.

    Não é validação do resultado — é guarda contra o modelo estar grosseiramente
    fora de esquadro. Valor muito longe do reportado para via urbana significa
    parâmetro errado em `veiculos.typ.xml` (`tau`, `minGap`, `length`, `accel`),
    e é isso que se corrige.

    Returns:
        Lista de avisos. Vazia significa que tudo caiu dentro da faixa.
    """
    minimo, maximo = float(faixa[0]), float(faixa[1])
    return [
        f"{aproximacao.nome}: fluxo de saturação medido "
        f"{aproximacao.fluxo_saturacao_veic_h_faixa:.0f} veíc./h/faixa fora da faixa "
        f"de plausibilidade [{minimo:.0f}, {maximo:.0f}] — revise veiculos.typ.xml"
        for aproximacao in aproximacoes
        if not minimo <= aproximacao.fluxo_saturacao_veic_h_faixa <= maximo
    ]


def calibrar() -> tuple[list[LinhaCenario], list[str]]:
    """Executa a calibração completa a partir dos arquivos do repositório.

    Returns:
        `(linhas_da_tabela, avisos_de_plausibilidade)`.
    """
    configuracao = carregar_configuracao()
    medicao = carregar_medicao()
    arterial, transversal = aproximacoes_medidas(configuracao, medicao)
    programa = programa_de(configuracao)

    linhas = montar_tabela(
        configuracao["cenarios"],
        arterial,
        transversal,
        programa,
        configuracao["limiares_saturacao"],
    )
    avisos = conferir_plausibilidade(
        (arterial, transversal), configuracao["faixa_plausivel_saturacao_veic_h_faixa"]
    )
    return linhas, avisos


def main(argumentos: list[str] | None = None) -> int:
    saida_utf8()
    analisador = argparse.ArgumentParser(
        description="Deriva o grau de saturação dos cenários (entrega 3.0, P11)."
    )
    analisador.add_argument(
        "--markdown", action="store_true", help="imprime só a tabela, para colar no texto"
    )
    opcoes = analisador.parse_args(argumentos)

    linhas, avisos = calibrar()

    if opcoes.markdown:
        print(tabela_markdown(linhas))
        return 0

    destino = gravar_csv(linhas)
    print(tabela_markdown(linhas))
    print(f"\ngravado em {destino}")
    for aviso in avisos:
        print(f"\nAVISO  {aviso}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
