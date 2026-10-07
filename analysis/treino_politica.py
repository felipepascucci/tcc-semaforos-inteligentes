"""Treino offline da política de desempate de P19 — entrega 10.5 do Bloco 10.

    python -m analysis.treino_politica

Lê os rótulos da bifurcação (10.4), ajusta a regressão logística par a par e
grava os pesos em `backend/config/politica_desempate.yaml`, de onde a inferência
da 10.6 os lê. As tabelas da seleção da regularização e da avaliação vão para
`analysis/data/bloco10_treino/`.

**O modelo.** `score = w · (x_A - x_B)`, escolhe A se `score > 0`, senão B, com
`x = (eta_s, velocidade_ms, fila_por_faixa, cruzamentos_restantes)`. **Sem
intercepto**: é o que garante `score(B, A) = -score(A, B)` por construção.

**As decisões da equipe, de 2026-10-06** (registradas em `context/09`, P19):

- **Fila por faixa**, e não somada: é a fila que o VE tem à frente, e a mesma que
  E3 usa (P16).
- **Cada exemplo pesa a margem do minimax**, `|minimax_se_A - minimax_se_B|`, em
  segundos. Errar uma disputa em que a escolha vale 60 s custa mais do que errar
  uma em que vale 1 s, e é em segundos do pior VE que H4 é medida. O
  desequilíbrio A/B (A, o VE do corredor, vence em 73% do treino) **não** é
  tratado: é sinal do minimax, não defeito da amostra. Espelhar os exemplos não
  mudaria nada — sem intercepto, a perda do exemplo espelhado é idêntica à do
  original, e há teste que mostra isso.
- **L2 com λ escolhido na validação**, pela menor perda logística ponderada,
  numa grade declarada antes do treino (`GRADE_LAMBDA`); empate fica com o maior
  λ. O modelo final é ajustado **só no treino**, e a validação continua sendo um
  número fora da amostra.
- Os atributos são **divididos pelo RMS do treino, sem centralizar** —
  subtrair a média criaria um intercepto escondido. A penalidade incide sobre os
  pesos escalados, para que λ não dependa das unidades. O arquivo guarda os pesos
  já nas unidades originais, e a inferência é só um produto escalar.
- numpy e scipy, que já estão na stack de análise (`context/02` §2): não há
  dependência nova.

**Isto não é resultado de H4.** O acerto e o custo daqui descrevem o modelo nas
seeds de treino e validação, pela régua do rótulo. H4 é testada no Bloco 8, com o
braço `PREEMPCAO_ML` rodando de verdade nas seeds 1..50 do cenário de avaliação.
"""

from __future__ import annotations

import argparse
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from numpy.typing import NDArray
from scipy.optimize import minimize
from scipy.special import expit

from analysis.resumo_rotulos import ARQUIVO_ROTULOS, TREINAVEIS, divisao_de_seeds

RAIZ = Path(__file__).resolve().parents[1]
DADOS = RAIZ / "analysis" / "data" / "bloco10_rotulos"
SAIDA_DADOS = RAIZ / "analysis" / "data" / "bloco10_treino"
ARQUIVO_PESOS = RAIZ / "backend" / "config" / "politica_desempate.yaml"
PARAMETROS = RAIZ / "backend" / "config" / "parametros.yaml"

#: Ordem dos atributos no vetor — os nomes são os campos de `AtributosVE`.
ATRIBUTOS = ("eta_s", "velocidade_ms", "fila_por_faixa", "cruzamentos_restantes")

#: Colunas de `rotulos.csv` de cada atributo, para o VE A e o VE B.
COLUNAS = {
    "eta_s": ("eta_a_s", "eta_b_s"),
    "velocidade_ms": ("velocidade_a_ms", "velocidade_b_ms"),
    "fila_por_faixa": ("fila_faixa_a", "fila_faixa_b"),
    "cruzamentos_restantes": ("cruzamentos_restantes_a", "cruzamentos_restantes_b"),
}

#: Grade de regularização, declarada antes do treino. λ multiplica `‖w‖² / 2`,
#: com `w` sobre os atributos escalados e a perda como média ponderada.
GRADE_LAMBDA = (0.0, 1e-4, 1e-3, 1e-2, 1e-1, 1.0)

Vetor = NDArray[np.float64]
Matriz = NDArray[np.float64]


@dataclass(frozen=True)
class Conjunto:
    """Os exemplos de uma divisão, prontos para o ajuste.

    Attributes:
        x: Diferenças `x_A - x_B`, uma linha por exemplo, nas unidades originais.
        y: `+1` se o rótulo é A, `-1` se é B.
        custo_s: Margem do minimax entre as escolhas — o peso do exemplo e o
            quanto se perde, em segundos, escolhendo errado.
        escolha_e8: A escolha do E8 determinístico, `+1` (A) ou `-1` (B).
        id_semaforo: Cruzamento da disputa.
    """

    x: Matriz
    y: Vetor
    custo_s: Vetor
    escolha_e8: Vetor
    id_semaforo: NDArray[np.str_]

    def __len__(self) -> int:
        return int(self.y.shape[0])

    def filtrar(self, mascara: NDArray[np.bool_]) -> Conjunto:
        """O subconjunto marcado pela máscara."""
        return Conjunto(
            self.x[mascara],
            self.y[mascara],
            self.custo_s[mascara],
            self.escolha_e8[mascara],
            self.id_semaforo[mascara],
        )


@dataclass(frozen=True)
class Ajuste:
    """Um modelo ajustado.

    Attributes:
        pesos: Pesos nas unidades originais dos atributos, na ordem de
            `ATRIBUTOS`. É o que vai para o arquivo.
        pesos_escalados: Os mesmos pesos sobre os atributos divididos pelo RMS.
        escala: RMS de cada atributo no treino.
        lambda_: Regularização usada.
    """

    pesos: Vetor
    pesos_escalados: Vetor
    escala: Vetor
    lambda_: float


def ler_conjuntos(caminho: Path, divisao: dict[str, tuple[int, int]]) -> dict[str, Conjunto]:
    """Lê `rotulos.csv` e separa os exemplos treináveis por divisão de seed.

    Empates e descartes ficam de fora: não há escolha melhor a aprender.
    """
    tabela = pd.read_csv(caminho, dtype={"rotulo": str, "escolha_e8": str})
    tabela = tabela[tabela["rotulo"].isin(TREINAVEIS)]
    conjuntos = {}
    for nome, (inicio, fim) in divisao.items():
        parte = tabela[tabela["seed"].between(inicio, fim)]
        x = np.column_stack(
            [
                parte[COLUNAS[nome_atributo][0]].to_numpy(float)
                - parte[COLUNAS[nome_atributo][1]].to_numpy(float)
                for nome_atributo in ATRIBUTOS
            ]
        )
        conjuntos[nome] = Conjunto(
            x=x,
            y=np.where(parte["rotulo"] == "A", 1.0, -1.0),
            # Mesmo arredondamento de `Rotulo.margem_s`: a régua do resumo da 10.4.
            custo_s=(parte["minimax_se_a_s"] - parte["minimax_se_b_s"]).abs().round(1).to_numpy(),
            escolha_e8=np.where(parte["escolha_e8"] == "A", 1.0, -1.0),
            id_semaforo=parte["id_semaforo"].to_numpy(str),
        )
    return conjuntos


def perda(w: Vetor, x: Matriz, y: Vetor, custo: Vetor, lambda_: float) -> tuple[float, Vetor]:
    """Perda logística ponderada pela margem, mais L2, e o gradiente.

    `Σ c·log(1 + e^(-y·w·x)) / Σ c + λ‖w‖²/2`. Média ponderada, e não soma,
    para que λ tenha o mesmo significado com qualquer número de exemplos.
    """
    margem = y * (x @ w)
    total = float(custo.sum())
    valor = float(custo @ np.logaddexp(0.0, -margem)) / total + 0.5 * lambda_ * float(w @ w)
    gradiente = -(x.T @ (custo * y * expit(-margem))) / total + lambda_ * w
    return valor, gradiente


def ajustar(conjunto: Conjunto, lambda_: float) -> Ajuste:
    """Ajusta os pesos por L-BFGS, partindo de zero (determinístico)."""
    escala = np.sqrt(np.mean(conjunto.x**2, axis=0))
    escala = np.where(escala > 0.0, escala, 1.0)
    x = conjunto.x / escala
    resultado = minimize(
        perda,
        np.zeros(x.shape[1]),
        args=(x, conjunto.y, conjunto.custo_s, lambda_),
        jac=True,
        method="L-BFGS-B",
        options={"gtol": 1e-10, "ftol": 1e-15, "maxiter": 10_000},
    )
    if not resultado.success:
        raise RuntimeError(f"o ajuste não convergiu (λ = {lambda_}): {resultado.message}")
    pesos_escalados = np.asarray(resultado.x, dtype=float)
    return Ajuste(pesos_escalados / escala, pesos_escalados, escala, lambda_)


def perda_sem_penalidade(pesos: Vetor, conjunto: Conjunto) -> float:
    """A perda logística ponderada de um modelo num conjunto, sem o termo L2."""
    return perda(pesos, conjunto.x, conjunto.y, conjunto.custo_s, 0.0)[0]


def escolhas(pesos: Vetor, x: Matriz) -> Vetor:
    """`+1` (A) se o score é positivo, senão `-1` (B) — a regra de P19."""
    return np.where(x @ pesos > 0.0, 1.0, -1.0)


def escolher_lambda(perdas_validacao: Sequence[tuple[float, float]]) -> float:
    """O λ de menor perda na validação; no empate, o maior (o modelo mais simples)."""
    menor = min(valor for _, valor in perdas_validacao)
    return max(
        lambda_
        for lambda_, valor in perdas_validacao
        if np.isclose(valor, menor, rtol=1e-12, atol=0.0)
    )


@dataclass(frozen=True)
class Desempenho:
    """Uma política num conjunto, pela régua do rótulo."""

    exemplos: int
    acertos: int
    custo_medio_s: float
    custo_total_s: float


def desempenho(escolha: Vetor, conjunto: Conjunto) -> Desempenho:
    """Acerto e custo de uma sequência de escolhas: o custo do erro é a margem."""
    erro = escolha != conjunto.y
    custo = conjunto.custo_s * erro
    return Desempenho(
        exemplos=len(conjunto),
        acertos=int((~erro).sum()),
        custo_medio_s=float(custo.mean()) if len(conjunto) else 0.0,
        custo_total_s=float(custo.sum()),
    )


def selecionar(conjuntos: dict[str, Conjunto]) -> tuple[Ajuste, pd.DataFrame]:
    """Ajusta no treino para cada λ da grade, escolhe na validação, devolve o final."""
    treino, validacao = conjuntos["treino"], conjuntos["validacao"]
    linhas = []
    ajustes = {}
    for lambda_ in GRADE_LAMBDA:
        ajuste = ajustar(treino, lambda_)
        ajustes[lambda_] = ajuste
        linha: dict[str, Any] = {"lambda": lambda_}
        for nome, conjunto in (("treino", treino), ("validacao", validacao)):
            avaliado = desempenho(escolhas(ajuste.pesos, conjunto.x), conjunto)
            linha[f"perda_{nome}"] = perda_sem_penalidade(ajuste.pesos, conjunto)
            linha[f"acerto_{nome}"] = avaliado.acertos / avaliado.exemplos
            linha[f"custo_medio_{nome}_s"] = avaliado.custo_medio_s
        linhas.append(linha)
    tabela = pd.DataFrame(linhas)
    escolhido = escolher_lambda(list(zip(tabela["lambda"], tabela["perda_validacao"], strict=True)))
    tabela["escolhido"] = (tabela["lambda"] == escolhido).astype(int)
    return ajustes[escolhido], tabela


def avaliar(ajuste: Ajuste, conjuntos: dict[str, Conjunto]) -> pd.DataFrame:
    """O modelo contra três referências, por divisão e por cruzamento.

    - `e8`: a escolha que o E8 fez na trajetória principal. **No cenário de
      treino os dois VEs do par são de tipos diferentes** (10.2), então o E8
      decidiu por `prioridade_tipo`, e não por ETA.
    - `menor_eta`: o critério que o E8 aplica quando os dois VEs são do mesmo
      tipo, que é o caso de todo par do cenário de avaliação
      (`multiplas_emergencias`). É a referência mais próxima do E8 contra o qual
      H4 vai ser testada.
    - `sempre_a`: A é sempre o VE do corredor; mostra quanto os atributos
      acrescentam além de saber quem é o corredor.
    """
    linhas = []
    for nome, conjunto in conjuntos.items():
        recortes = [("todos", conjunto)] + [
            (cruzamento, conjunto.filtrar(conjunto.id_semaforo == cruzamento))
            for cruzamento in sorted(set(conjunto.id_semaforo))
        ]
        for recorte, parte in recortes:
            politicas = {
                # O próprio rótulo: a linha existe para mostrar quantos B há.
                "rotulo": parte.y,
                "modelo": escolhas(ajuste.pesos, parte.x),
                "e8": parte.escolha_e8,
                "menor_eta": np.where(parte.x[:, ATRIBUTOS.index("eta_s")] < 0.0, 1.0, -1.0),
                "sempre_a": np.ones(len(parte)),
            }
            for politica, escolha in politicas.items():
                avaliado = desempenho(escolha, parte)
                linhas.append(
                    {
                        "divisao": nome,
                        "cruzamento": recorte,
                        "politica": politica,
                        "exemplos": avaliado.exemplos,
                        "escolhe_b": int((escolha < 0).sum()),
                        "acertos": avaliado.acertos,
                        "acerto": avaliado.acertos / avaliado.exemplos,
                        "custo_medio_s": avaliado.custo_medio_s,
                        "custo_total_s": avaliado.custo_total_s,
                    }
                )
    return pd.DataFrame(linhas)


def sha256(caminho: Path) -> str:
    """Impressão digital do arquivo de rótulos que produziu os pesos."""
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def conteudo_pesos(
    ajuste: Ajuste,
    conjuntos: dict[str, Conjunto],
    divisao: dict[str, tuple[int, int]],
    caminho_rotulos: Path,
) -> dict[str, Any]:
    """O que vai para `politica_desempate.yaml`."""
    try:
        origem = caminho_rotulos.resolve().relative_to(RAIZ).as_posix()
    except ValueError:
        origem = caminho_rotulos.as_posix()
    return {
        "modelo": "regressao_logistica_par_a_par",
        "regra": "escolhe A se soma(pesos[a] * (x_A[a] - x_B[a])) > 0, senao B",
        "atributos": list(ATRIBUTOS),
        "pesos": {
            atributo: float(peso) for atributo, peso in zip(ATRIBUTOS, ajuste.pesos, strict=True)
        },
        "treino": {
            "rotulos": origem,
            "sha256_rotulos": sha256(caminho_rotulos),
            "seeds_treino": list(divisao["treino"]),
            "seeds_validacao": list(divisao["validacao"]),
            "exemplos_treino": len(conjuntos["treino"]),
            "exemplos_validacao": len(conjuntos["validacao"]),
            "ponderacao": "margem do minimax entre as escolhas, em s",
            "grade_lambda": list(GRADE_LAMBDA),
            "lambda": ajuste.lambda_,
            "escala_rms": {
                atributo: float(valor)
                for atributo, valor in zip(ATRIBUTOS, ajuste.escala, strict=True)
            },
        },
    }


CABECALHO_PESOS = """\
# Política de desempate de P19 (E8, entre VEs de mesmo nível de criticidade).
# GERADO por `python -m analysis.treino_politica` — não editar à mão. O teste
# analysis/tests/test_treino_politica.py refaz o treino a partir dos rótulos
# versionados e confere estes pesos.
#
# score = soma(pesos[a] * (x_A[a] - x_B[a])); escolhe A se score > 0, senão B.
# Pesos nas unidades originais (s, m/s, veículos por faixa, cruzamentos).
"""


def gravar_pesos(conteudo: dict[str, Any], caminho: Path) -> None:
    """Grava o arquivo de pesos, em LF, na ordem das chaves."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    texto = CABECALHO_PESOS + yaml.safe_dump(conteudo, sort_keys=False, allow_unicode=True)
    with caminho.open("w", encoding="utf-8", newline="\n") as arquivo:
        arquivo.write(texto)


def prioridade_tipo(caminho: Path = PARAMETROS) -> list[str]:
    """A ordem de tipos do E8, de `parametros.yaml`."""
    with caminho.open(encoding="utf-8") as arquivo:
        return [str(tipo) for tipo in yaml.safe_load(arquivo)["prioridade_tipo"]]


def descrever_treino(
    caminho: Path, divisao: dict[str, tuple[int, int]], ordem_tipo: Sequence[str]
) -> list[str]:
    """O que o conjunto de treino mostra antes do ajuste, em linhas de relatório.

    Só as seeds de treino: a validação fica para escolher λ e para o número fora
    da amostra.
    """
    tabela = pd.read_csv(caminho, dtype={"rotulo": str, "escolha_e8": str})
    inicio, fim = divisao["treino"]
    treino = tabela[tabela["rotulo"].isin(TREINAVEIS) & tabela["seed"].between(inicio, fim)]
    vencedor = treino["rotulo"].str.lower()
    travessia_a = [
        treino.at[indice, f"travessia_a_se_{ramo}_s"] for indice, ramo in vencedor.items()
    ]
    travessia_b = [
        treino.at[indice, f"travessia_b_se_{ramo}_s"] for indice, ramo in vencedor.items()
    ]
    pior_e_a = int(sum(a >= b for a, b in zip(travessia_a, travessia_b, strict=True)))
    restantes = treino["cruzamentos_restantes_a"] - treino["cruzamentos_restantes_b"]
    fila = treino["fila_faixa_a"] - treino["fila_faixa_b"]
    posicao = {tipo: indice for indice, tipo in enumerate(ordem_tipo)}
    pela_ordem = np.where(treino["tipo_a"].map(posicao) < treino["tipo_b"].map(posicao), "A", "B")
    return [
        f"Exemplos de treino: {len(treino)}",
        f"VE mais prejudicado no ramo vencedor é o A (corredor): {pior_e_a} de {len(treino)}",
        "Diferença de cruzamentos_restantes (A - B): "
        f"mín {restantes.min()}, máx {restantes.max()}, positiva em {int((restantes > 0).sum())}",
        f"Diferença de fila_por_faixa igual a zero: {int((fila == 0).sum())}",
        f"Pares de tipos diferentes: {int((treino['tipo_a'] != treino['tipo_b']).sum())}; "
        "E8 seguiu a ordem de tipo em "
        f"{int((pela_ordem == treino['escolha_e8']).sum())} de {len(treino)}",
    ]


def gerar_relatorio(
    ajuste: Ajuste,
    selecao: pd.DataFrame,
    avaliacao: pd.DataFrame,
    descricao: Sequence[str] = (),
) -> str:
    """Relatório de texto do treino."""
    linhas = ["# Treino da política de desempate — entrega 10.5", ""]
    if descricao:
        linhas += ["## O conjunto de treino, antes do ajuste", ""]
        linhas += [f"- {linha}" for linha in descricao]
        linhas.append("")
    linhas += [
        "## Seleção da regularização (ajuste no treino, escolha na validação)",
        "",
        "| λ | perda treino | perda validação | acerto validação | custo médio validação (s) |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, linha in selecao.iterrows():
        marca = " **←**" if linha["escolhido"] else ""
        linhas.append(
            f"| {linha['lambda']:g}{marca} | {linha['perda_treino']:.4f} | "
            f"{linha['perda_validacao']:.4f} | {100 * linha['acerto_validacao']:.1f}% | "
            f"{linha['custo_medio_validacao_s']:.2f} |"
        )
    linhas += ["", f"λ escolhido: {ajuste.lambda_:g}", "", "## Pesos (unidades originais)", ""]
    linhas += [
        f"- `{atributo}`: {peso:+.6g}  (escalado: {escalado:+.4f})"
        for atributo, peso, escalado in zip(
            ATRIBUTOS, ajuste.pesos, ajuste.pesos_escalados, strict=True
        )
    ]
    linhas += [
        "",
        "## Avaliação pela régua do rótulo",
        "",
        "| divisão | cruzamento | política | exemplos | escolhe B | acerto | custo médio (s) |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for _, linha in avaliacao.iterrows():
        linhas.append(
            f"| {linha['divisao']} | {linha['cruzamento']} | {linha['politica']} | "
            f"{linha['exemplos']} | {linha['escolhe_b']} | {100 * linha['acerto']:.1f}% | "
            f"{linha['custo_medio_s']:.2f} |"
        )
    linhas += [
        "",
        "## O que isto não é",
        "",
        "Não é resultado de H4. É o modelo descrito nas seeds de treino e validação, pela "
        "régua do rótulo; H4 é testada no Bloco 8, com o braço PREEMPCAO_ML nas seeds 1..50 "
        "do cenário de avaliação.",
    ]
    return "\n".join(linhas)


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada: `python -m analysis.treino_politica`."""
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument("--dados", type=Path, default=DADOS)
    analisador.add_argument("--saida-dados", type=Path, default=SAIDA_DADOS)
    analisador.add_argument("--pesos", type=Path, default=ARQUIVO_PESOS)
    analisador.add_argument("--relatorio", type=Path, default=None)
    opcoes = analisador.parse_args(argv)

    divisao = divisao_de_seeds()
    caminho_rotulos = opcoes.dados / ARQUIVO_ROTULOS
    conjuntos = ler_conjuntos(caminho_rotulos, divisao)
    ajuste, selecao = selecionar(conjuntos)
    avaliacao = avaliar(ajuste, conjuntos)

    opcoes.saida_dados.mkdir(parents=True, exist_ok=True)
    # LF explícito: o pandas usaria o separador do sistema, e o arquivo mudaria
    # conforme a máquina que o gerou.
    selecao.to_csv(opcoes.saida_dados / "selecao_lambda.csv", index=False, lineterminator="\n")
    avaliacao.to_csv(opcoes.saida_dados / "avaliacao.csv", index=False, lineterminator="\n")
    gravar_pesos(conteudo_pesos(ajuste, conjuntos, divisao, caminho_rotulos), opcoes.pesos)

    descricao = descrever_treino(caminho_rotulos, divisao, prioridade_tipo())
    relatorio = gerar_relatorio(ajuste, selecao, avaliacao, descricao)
    if opcoes.relatorio is not None:
        opcoes.relatorio.parent.mkdir(parents=True, exist_ok=True)
        opcoes.relatorio.write_text(relatorio + "\n", encoding="utf-8", newline="\n")
    print(relatorio)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
