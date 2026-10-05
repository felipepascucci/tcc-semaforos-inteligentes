"""Desenho da malha SUMO para o mapa do dashboard (Bloco 7).

    python -m sim.rede.exportar_mapa          # regrava frontend/src/malha/malha.json

O dashboard desenha a malha do experimento, e não um mapa de rua: as
coordenadas dos cruzamentos são fictícias (`db/seeds/dados.yaml`), e um fundo do
OpenStreetMap só confundiria. Este script lê `malha.net.xml` e grava, em
latitude e longitude (`sim/rede/georreferencia.py`, a mesma conversão da posição
dos VEs):

* **vias** — cada faixa das vias normais, como polilinha. As faixas internas dos
  cruzamentos ficam de fora: o contorno do cruzamento as cobre;
* **cruzamentos** — o centro, o contorno e, por aproximação, a **linha de
  retenção** de cada faixa que chega e um **ponto de sinal** 30 m antes dela,
  com a fase que a serve. A fase vem do eixo da aproximação em
  `sim/config/mapa_fases.yaml`, e é com ela que o dashboard pinta a linha e o
  ponto com a cor do sinal transmitido.

O arquivo é versionado e derivado: `sim/tests/test_exportar_mapa.py` falha se a
rede ou o mapa de fases mudarem sem ele ser regravado.
"""

from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Final

import yaml

from sim.rede.georreferencia import REDE, Georreferencia
from sim.rede.georreferencia import carregar as carregar_georreferencia

RAIZ: Final = Path(__file__).resolve().parents[2]
MAPA_FASES: Final = RAIZ / "sim" / "config" / "mapa_fases.yaml"
DESTINO: Final = RAIZ / "frontend" / "src" / "malha" / "malha.json"

#: Metade da largura da linha de retenção, em metros (faixa de 3,2 m).
MEIA_LINHA_M: Final = 1.6
#: Onde fica o ponto de sinal de cada aproximação, antes da linha de retenção.
#: A linha tem ~1 pixel com a malha inteira na tela; o ponto, recuado para não
#: se sobrepor ao cruzamento, é o que deixa a cor legível nesse zoom.
RECUO_SINAL_M: Final = 30.0
CASAS: Final = 7

Ponto = tuple[float, float]


def _pontos(shape: str) -> list[Ponto]:
    return [(float(x), float(y)) for x, y in (par.split(",") for par in shape.split())]


def _linha_de_retencao(faixa: list[Ponto]) -> tuple[Ponto, Ponto]:
    """Segmento perpendicular ao fim da faixa, onde o veículo para no vermelho."""
    (x1, y1), (x2, y2) = faixa[-2], faixa[-1]
    comprimento = math.hypot(x2 - x1, y2 - y1) or 1.0
    nx, ny = -(y2 - y1) / comprimento, (x2 - x1) / comprimento
    return (
        (x2 - nx * MEIA_LINHA_M, y2 - ny * MEIA_LINHA_M),
        (x2 + nx * MEIA_LINHA_M, y2 + ny * MEIA_LINHA_M),
    )


def _recuar(faixa: list[Ponto], metros: float) -> Ponto:
    """O ponto da faixa a `metros` do fim, andando para trás pela polilinha."""
    restante = metros
    for (x1, y1), (x2, y2) in zip(reversed(faixa[:-1]), reversed(faixa[1:]), strict=True):
        trecho = math.hypot(x2 - x1, y2 - y1)
        if trecho >= restante:
            fracao = restante / trecho
            return (x2 + (x1 - x2) * fracao, y2 + (y1 - y2) * fracao)
        restante -= trecho
    return faixa[0]


def _ponto_de_sinal(faixas: list[list[Ponto]]) -> Ponto:
    """Recuado da linha de retenção, no meio das faixas da aproximação."""
    pontos = [_recuar(faixa, RECUO_SINAL_M) for faixa in faixas]
    return (sum(p[0] for p in pontos) / len(pontos), sum(p[1] for p in pontos) / len(pontos))


def _fase_por_via(mapa_fases: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Cruzamento → via de entrada → índice da fase que a serve."""
    fase_do_eixo = {fase["eixo"]: int(fase["indice"]) for fase in mapa_fases["padrao"]["fases"]}
    return {
        cruzamento: {via: fase_do_eixo[eixo] for eixo, vias in eixos.items() for via in vias}
        for cruzamento, eixos in mapa_fases["semaforos"].items()
    }


def exportar(rede: Path = REDE, mapa_fases: Path = MAPA_FASES) -> dict[str, Any]:
    """O desenho da malha, pronto para gravar."""
    geo: Georreferencia = carregar_georreferencia(rede)

    def ll(ponto: Ponto) -> list[float]:
        lat, lon = geo.para_lat_lon(*ponto)
        return [round(lat, CASAS), round(lon, CASAS)]

    with mapa_fases.open(encoding="utf-8") as arquivo:
        fases = _fase_por_via(yaml.safe_load(arquivo))

    raiz = ET.parse(rede).getroot()
    vias: list[dict[str, Any]] = []
    retencoes: dict[str, list[dict[str, Any]]] = {cruzamento: [] for cruzamento in fases}
    for aresta in raiz.iter("edge"):
        if aresta.get("function") is not None:
            continue  # faixa interna de cruzamento
        faixas = [_pontos(faixa.attrib["shape"]) for faixa in aresta.iter("lane")]
        vias.append({"id": aresta.attrib["id"], "faixas": [[ll(p) for p in f] for f in faixas]})
        destino = aresta.attrib["to"]
        if destino in fases:
            fase = fases[destino].get(aresta.attrib["id"])
            if fase is None:
                raise ValueError(f"{aresta.attrib['id']} chega a {destino} sem fase no mapa")
            retencoes[destino].append(
                {
                    "via": aresta.attrib["id"],
                    "fase": fase,
                    "linhas": [[ll(p) for p in _linha_de_retencao(f)] for f in faixas],
                    "sinal": ll(_ponto_de_sinal(faixas)),
                }
            )

    cruzamentos = []
    for juncao in raiz.iter("junction"):
        codigo = juncao.attrib["id"]
        if codigo not in fases:
            continue
        cruzamentos.append(
            {
                "id": codigo,
                "centro": ll((float(juncao.attrib["x"]), float(juncao.attrib["y"]))),
                "contorno": [ll(p) for p in _pontos(juncao.attrib["shape"])],
                "aproximacoes": sorted(retencoes[codigo], key=lambda a: a["via"]),
            }
        )

    todos = [p for via in vias for faixa in via["faixas"] for p in faixa]
    return {
        "_gerado_por": "python -m sim.rede.exportar_mapa, a partir de sim/rede/malha.net.xml",
        "limites": [
            [min(p[0] for p in todos), min(p[1] for p in todos)],
            [max(p[0] for p in todos), max(p[1] for p in todos)],
        ],
        "vias": sorted(vias, key=lambda v: v["id"]),
        "cruzamentos": sorted(cruzamentos, key=lambda c: c["id"]),
    }


def serializar(dados: dict[str, Any]) -> str:
    """JSON estável: a mesma rede dá sempre o mesmo texto, para o teste comparar."""
    return json.dumps(dados, ensure_ascii=False, indent=1) + "\n"


def main() -> int:
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    with DESTINO.open("w", encoding="utf-8", newline="\n") as arquivo:
        arquivo.write(serializar(exportar()))
    print(f"gravado {DESTINO.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
