"""Geração dos arquivos de fluxo — entrega 3.3.

Escreve `sim/demanda/fluxo_{leve,moderado,intenso}.rou.xml` a partir da tabela de
calibração. São arquivos **gerados e depois versionados**, como
`sim/rede/malha.con.xml` e `db/schema.sql`: ficam no Git porque são a demanda que
o experimento de fato usou, e regenerá-los é um ato explícito.

    python -m sim.demanda.gerar_fluxos

Por que congelar em vez de calcular a cada execução: o fluxo transversal é
derivado da medição do fluxo de saturação. Se alguém remedir a saturação no meio
do lote de 600 execuções, metade rodaria com uma demanda e metade com outra — e
o `git diff` destes arquivos é o que torna essa mudança visível em vez de
silenciosa.

Cada corrente vira duas linhas de `<flow>`, uma por tipo de veículo, em vez de
uma só com distribuição: assim a proporção de ônibus fica explícita no arquivo e
o total por corrente pode ser conferido a olho.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from adapters.terminal import saida_utf8
from sim.calibracao import cenarios as calibracao
from sim.demanda.fluxos import CorrenteDeTrafego, correntes_do_cenario

DIRETORIO = Path(__file__).resolve().parent

#: Cenários que ganham arquivo próprio. `multiplas_emergencias` reutiliza o de
#: `moderado` — mesma demanda de fundo (context/04 §5), muda só a emergência.
CENARIOS_COM_ARQUIVO = ("leve", "moderado", "intenso")

CABECALHO = """<?xml version="1.0" encoding="UTF-8"?>
<!--
  Demanda de fundo do cenário `{cenario}` — context/04 §5.

  ARQUIVO GERADO por `python -m sim.demanda.gerar_fluxos`, versionado de
  propósito. Não edite à mão.

  {classificacao}

  fluxo arterial     {fluxo_arterial:>7.0f} veíc./h por aproximação (do pré-projeto)
  capacidade         {capacidade_arterial:>7.0f} veíc./h  (2 faixas)
  grau de saturação  {grau:>7.2f}  ->  {classe}

  fluxo transversal  {fluxo_transversal:>7.0f} veíc./h por aproximação (DERIVADO)
  capacidade         {capacidade_transversal:>7.0f} veíc./h  (1 faixa)

  O fluxo transversal não é escolhido: é o que põe a transversal no MESMO grau
  de saturação da arterial, a partir do fluxo de saturação medido na própria
  malha (`analysis/data/fluxo_saturacao.csv`). Ver sim/calibracao/cenarios.py.

  Tráfego passante, sem conversões — simplificação declarada em
  sim/demanda/fluxos.py. Os veículos concretos, com instantes de partida por
  seed, saem de `python -m sim.demanda.gerar_rotas`.
-->
<routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/routes_file.xsd">
"""


def _linhas_de_fluxo(
    correntes: Sequence[CorrenteDeTrafego], proporcao_onibus: float, duracao_s: float
) -> list[str]:
    linhas: list[str] = []
    for corrente in correntes:
        linhas.append("")
        linhas.append(f'    <route id="{corrente.nome}" edges="{" ".join(corrente.vias)}"/>')
        por_tipo = (
            ("carro", corrente.fluxo_veic_h * (1 - proporcao_onibus)),
            ("onibus", corrente.fluxo_veic_h * proporcao_onibus),
        )
        linhas += [
            f'    <flow id="{corrente.nome}_{tipo}" type="{tipo}" route="{corrente.nome}" '
            f'begin="0.00" end="{duracao_s:.2f}" vehsPerHour="{fluxo:.2f}"/>'
            for tipo, fluxo in por_tipo
        ]
    return linhas


def gerar(nome_cenario: str, destino: Path | None = None) -> Path:
    """Escreve o arquivo de fluxo de um cenário.

    Args:
        nome_cenario: `"leve"`, `"moderado"` ou `"intenso"`.
        destino: Caminho de saída. Padrão: `sim/demanda/fluxo_<cenario>.rou.xml`.

    Returns:
        O caminho escrito.
    """
    configuracao = calibracao.carregar_configuracao()
    linhas_calibradas, _ = calibracao.calibrar()
    calibrada = next(linha for linha in linhas_calibradas if linha.cenario == nome_cenario)

    correntes = correntes_do_cenario(nome_cenario, linhas_calibradas)
    duracao_s = float(configuracao["execucao"]["duracao_s"])
    proporcao_onibus = float(configuracao["composicao"]["proporcao_onibus"])

    conteudo = [
        CABECALHO.format(
            cenario=nome_cenario,
            classificacao=str(configuracao["cenarios"][nome_cenario]["objetivo"]),
            fluxo_arterial=calibrada.fluxo_arterial_veic_h,
            capacidade_arterial=calibrada.capacidade_arterial_veic_h,
            grau=calibrada.grau_saturacao,
            classe=calibrada.classificacao,
            fluxo_transversal=calibrada.fluxo_transversal_veic_h,
            capacidade_transversal=calibrada.capacidade_transversal_veic_h,
        ),
        *_linhas_de_fluxo(correntes, proporcao_onibus, duracao_s),
        "",
        "</routes>",
    ]

    destino = destino or DIRETORIO / f"fluxo_{nome_cenario}.rou.xml"
    destino.write_text("\n".join(conteudo) + "\n", encoding="utf-8")
    return destino


def main(argumentos: list[str] | None = None) -> int:
    saida_utf8()
    analisador = argparse.ArgumentParser(description="Gera os arquivos de fluxo (entrega 3.3).")
    analisador.add_argument("--cenario", choices=CENARIOS_COM_ARQUIVO, default=None)
    opcoes = analisador.parse_args(argumentos)

    alvos = [opcoes.cenario] if opcoes.cenario else list(CENARIOS_COM_ARQUIVO)
    for nome in alvos:
        print(f"gerado: {gerar(nome)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
