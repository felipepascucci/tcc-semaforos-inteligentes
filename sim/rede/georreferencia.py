"""Coordenadas da rede SUMO → latitude/longitude do mapa do dashboard (RF06).

A rede não tem projeção geográfica (`projParameter="!"` em `malha.net.xml`): é
uma grade em metros. As coordenadas geográficas dos cruzamentos vêm dos seeds,
que as **derivam** de uma origem e do espaçamento (`db/seeds/dados.yaml`). Este
módulo aplica a mesma conversão a qualquer ponto da rede, ancorada em `CRUZ_01`,
que é a origem dos seeds.

A âncora é lida do `.net.xml`, e não do `.nod.xml`: o adaptador entrega a posição
do VE em coordenadas da rede, já com o `netOffset` aplicado.
`sim/tests/test_georreferencia.py` confere que os oito cruzamentos da rede caem
exatamente onde os seeds os põem, senão o marcador do VE andaria fora das ruas.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from db.seeds.carregar import METROS_POR_GRAU_LAT, carregar_dados, metros_por_grau_lon

RAIZ: Final = Path(__file__).resolve().parents[2]
REDE: Final = RAIZ / "sim" / "rede" / "malha.net.xml"

#: O cruzamento que os seeds põem na origem.
ANCORA: Final = "CRUZ_01"


@dataclass(frozen=True)
class Georreferencia:
    """Transformação afim: metros na rede → graus, em torno da âncora."""

    x0: float
    y0: float
    lat0: float
    lon0: float

    def para_lat_lon(self, x: float, y: float) -> tuple[float, float]:
        """Latitude e longitude de um ponto da rede (y cresce para o norte)."""
        latitude = self.lat0 + (y - self.y0) / METROS_POR_GRAU_LAT
        longitude = self.lon0 + (x - self.x0) / metros_por_grau_lon(self.lat0)
        return latitude, longitude


def posicao_da_juncao(rede: Path, id_juncao: str) -> tuple[float, float]:
    """`x`, `y` de uma junção no `.net.xml`.

    Raises:
        LookupError: se a junção não existe.
    """
    for _, elemento in ET.iterparse(rede, events=("end",)):
        if elemento.tag == "junction" and elemento.get("id") == id_juncao:
            return float(elemento.attrib["x"]), float(elemento.attrib["y"])
        elemento.clear()
    raise LookupError(f"junção {id_juncao} não está em {rede}")


def carregar(rede: Path = REDE) -> Georreferencia:
    """A georreferência da malha do experimento."""
    origem = carregar_dados()["malha_sumo"]["origem"]
    x0, y0 = posicao_da_juncao(rede, ANCORA)
    return Georreferencia(x0, y0, float(origem["latitude"]), float(origem["longitude"]))
