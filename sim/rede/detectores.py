"""Detectores E1, E2 e E3 — entrega 3.2 (`context/04` §11).

Sem detectores, **H2 fica sem evidência**: não há como medir fila, throughput nem
tempo de viagem nas transversais, que é justamente o custo que a compensação
promete mitigar. Daí este módulo não ser opcional.

    E2 (laneAreaDetector)  em cada faixa de aproximação, 100 m antes da linha
                           de retenção   -> fila e ocupação
    E1 (inductionLoop)     logo após cada cruzamento, em cada faixa de saída
                           -> throughput
    E3 (entryExitDetector) em cada trecho interno da arterial, por sentido
                           -> tempo de viagem por trecho

O arquivo é **gerado a partir da rede**, não escrito à mão: os ids de faixa saem
do `.net.xml`, e mantê-los a mão significaria reescrever 100 linhas a cada
mudança de geometria — com a garantia de esquecer uma. Rodar
`python -m sim.rede.construir` regenera.

Os detectores E2 servem a dois consumidores diferentes, e é bom saber qual é
qual: em tempo real o adaptador TraCI lê `getLastStepHaltingNumber` para montar
`EstadoSemaforo.fila_por_acesso` (entrada do motor); em lote, os arquivos de
saída agregados alimentam `metrica_via_transversal`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.sax.saxutils import quoteattr

from sim.ambiente import registrar_ferramentas

#: Comprimento da área de detecção de fila, em metros (context/04 §11).
COMPRIMENTO_E2_M = 100.0

#: Distância após a linha de retenção onde o laço de indução é instalado, em
#: metros. Longe o bastante do cruzamento para não contar veículo que ainda está
#: manobrando, perto o bastante para não perder quem converte na saída.
POSICAO_E1_M = 5.0

#: Período de agregação da saída dos detectores, em segundos.
PERIODO_S = 300

ARQUIVO_E1 = "detectores_e1.xml"
ARQUIVO_E2 = "detectores_e2.xml"
ARQUIVO_E3 = "detectores_e3.xml"

CABECALHO = """<?xml version="1.0" encoding="UTF-8"?>
<!--
  ARQUIVO GERADO por `python -m sim.rede.construir` a partir de {rede}.
  Não edite à mão: a próxima construção da rede sobrescreve.

  Detectores E1 / E2 / E3 de context/04 §11. Ver sim/rede/detectores.py.

  Os arquivos de saída têm nome relativo de propósito: o SUMO os resolve
  relativo a ESTE arquivo, e o executor copia esta cópia para dentro da pasta da
  execução — é assim que cada execução fica com sua própria saída de detectores.
-->
<additional xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/additional_file.xsd">
"""


def _atributos(**campos: Any) -> str:
    return " ".join(f"{nome}={quoteattr(str(valor))}" for nome, valor in campos.items())


def _e_arterial(aresta: Any) -> bool:
    """Diz se a via é da arterial, pelo id (`A1_L2`) e não pelo número de faixas."""
    return str(aresta.getID()).startswith("A")


def _trechos_internos_da_arterial(rede: Any) -> list[Any]:
    """Vias arteriais entre dois cruzamentos semaforizados.

    Os trechos de fronteira ficam de fora: neles o tempo de viagem depende de
    quando o veículo foi inserido, não do controle semafórico.
    """
    semaforizados = {no.getID() for no in rede.getNodes() if no.getType() == "traffic_light"}
    return [
        aresta
        for aresta in sorted(rede.getEdges(), key=lambda a: str(a.getID()))
        if _e_arterial(aresta)
        and aresta.getFromNode().getID() in semaforizados
        and aresta.getToNode().getID() in semaforizados
    ]


def gerar_detectores(
    rede_xml: Path,
    destino: Path,
    *,
    periodo_s: int = PERIODO_S,
    comprimento_e2_m: float = COMPRIMENTO_E2_M,
) -> Path:
    """Escreve o `.add.xml` com os detectores E1, E2 e E3 da rede.

    Args:
        rede_xml: Caminho de `malha.net.xml`.
        destino: Caminho do arquivo a escrever.
        periodo_s: Período de agregação da saída, em segundos.
        comprimento_e2_m: Comprimento da área de detecção de fila, em metros.

    Returns:
        O caminho do arquivo escrito.
    """
    registrar_ferramentas()
    import sumolib  # import local: depende de SUMO_HOME estar no sys.path

    rede = sumolib.net.readNet(str(rede_xml), withConnections=True)
    linhas: list[str] = [CABECALHO.format(rede=rede_xml.name)]

    semaforizados = sorted(
        (no for no in rede.getNodes() if no.getType() == "traffic_light"),
        key=lambda no: str(no.getID()),
    )

    # --- E2: fila por faixa de aproximação ---------------------------------
    linhas.append("\n    <!-- E2 — fila e ocupação, 100 m antes da linha de retenção -->")
    for no in semaforizados:
        for aresta in sorted(no.getIncoming(), key=lambda a: str(a.getID())):
            for faixa in aresta.getLanes():
                linhas.append(
                    "    <laneAreaDetector "
                    + _atributos(
                        id=f"E2_{faixa.getID()}",
                        lane=faixa.getID(),
                        pos=f"{-comprimento_e2_m:.2f}",
                        endPos="-0.10",
                        period=periodo_s,
                        file=ARQUIVO_E2,
                        friendlyPos="true",
                    )
                    + "/>"
                )

    # --- E1: throughput na saída -------------------------------------------
    linhas.append("\n    <!-- E1 — throughput, logo após cada cruzamento -->")
    for no in semaforizados:
        for aresta in sorted(no.getOutgoing(), key=lambda a: str(a.getID())):
            for faixa in aresta.getLanes():
                linhas.append(
                    "    <inductionLoop "
                    + _atributos(
                        id=f"E1_{faixa.getID()}",
                        lane=faixa.getID(),
                        pos=f"{POSICAO_E1_M:.2f}",
                        period=periodo_s,
                        file=ARQUIVO_E1,
                        friendlyPos="true",
                    )
                    + "/>"
                )

    # --- E3: tempo de viagem por trecho da arterial ------------------------
    linhas.append("\n    <!-- E3 — tempo de viagem por trecho interno da arterial -->")
    for aresta in _trechos_internos_da_arterial(rede):
        linhas.append(
            "    <entryExitDetector "
            + _atributos(
                id=f"E3_{aresta.getID()}",
                period=periodo_s,
                file=ARQUIVO_E3,
                openEntry="true",
                timeThreshold="1.00",
            )
            + ">"
        )
        for faixa in aresta.getLanes():
            linhas.append(f'        <detEntry lane={quoteattr(faixa.getID())} pos="0.10"/>')
        for faixa in aresta.getLanes():
            linhas.append(f'        <detExit lane={quoteattr(faixa.getID())} pos="-0.10"/>')
        linhas.append("    </entryExitDetector>")

    linhas.append("\n</additional>")
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return destino
