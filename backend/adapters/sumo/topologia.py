"""Da rede SUMO para a topologia do motor — entrega 3.6.

O motor de decisão não conhece o SUMO: ele recebe uma `TopologiaMalha` de
`core/malha.py`, que é geometria e fases em abstrato (`context/01` §1). Este
módulo é a tradução, e mora em `adapters/` justamente porque lê arquivo — coisa
que `core/` não pode fazer.

A topologia é montada de **duas** fontes, com papéis distintos:

* `sim/rede/malha.net.xml` — a geometria: comprimento de cada via, em que
  cruzamento cada via desemboca, e quais movimentos existem de fato.
* `sim/config/mapa_fases.yaml` — as fases: quantas são, que aproximações cada
  uma serve, quanto duram e quais conflitam.

Duplicar qualquer um dos dois lados criaria uma segunda fonte da verdade, que
divergiria na primeira alteração de geometria. Por isso `mapa_fases.yaml` declara
**aproximações**, não movimentos: os movimentos são expandidos a partir das
conexões que a rede realmente tem.

`validar()` confere que os dois lados concordam, e é chamada na partida de toda
execução. Falhar aqui custa um segundo; falhar no meio de 600 execuções, não.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from core.excecoes import ConfiguracaoInvalidaError
from core.malha import Cruzamento, Fase, Movimento, TopologiaMalha
from core.modelos import Sinal

RAIZ = Path(__file__).resolve().parents[3]
REDE_PADRAO = RAIZ / "sim" / "rede" / "malha.net.xml"
MAPA_FASES_PADRAO = RAIZ / "sim" / "config" / "mapa_fases.yaml"

#: Sinal -> chave usada no bloco `programa` de `mapa_fases.yaml`.
CHAVE_DO_SINAL = {Sinal.VERDE: "verde", Sinal.AMARELO: "amarelo", Sinal.VERMELHO: "all_red"}


@dataclass(frozen=True)
class ProgramaSemaforico:
    """As *state strings* de um cruzamento, indexadas por (fase lógica, sinal).

    É o que permite ao adaptador dizer ao SUMO "fase 2 em amarelo" sem que o
    resto do sistema saiba que, do lado de lá, isso é a string
    `yyyrrrryyyrrrr`.

    Attributes:
        id_semaforo: Cruzamento.
        estados: Mapa `(fase, sinal) -> state string`.
        indices: Mapa `(fase, sinal) -> índice da fase no programa do SUMO`.
    """

    id_semaforo: str
    estados: Mapping[tuple[int, Sinal], str]
    indices: Mapping[tuple[int, Sinal], int]

    def estado(self, fase: int, sinal: Sinal) -> str:
        """State string de uma combinação (fase, sinal).

        Raises:
            ConfiguracaoInvalidaError: se a combinação não existir no programa.
        """
        try:
            return self.estados[(fase, sinal)]
        except KeyError as erro:
            raise ConfiguracaoInvalidaError(
                f"{self.id_semaforo} não tem estado para fase {fase} em {sinal}"
            ) from erro

    def fase_e_sinal(self, indice_no_programa: int) -> tuple[int, Sinal]:
        """Traduz um índice de fase do SUMO em (fase lógica, sinal).

        É o caminho inverso de `estado`, e serve ao modo `FIXO`: lá quem conduz
        a sinalização é o programa do próprio SUMO, e o adaptador só observa —
        precisa traduzir "o TLS está na fase 4 do programa" em "fase lógica 2,
        amarelo" para registrar a transição (decisão P5) e verificar I2/I3/I4.

        Raises:
            ConfiguracaoInvalidaError: se o índice não pertencer ao programa.
        """
        for chave, posicao in self.indices.items():
            if posicao == indice_no_programa:
                return chave
        raise ConfiguracaoInvalidaError(
            f"{self.id_semaforo}: índice de fase {indice_no_programa} não está no mapa de fases"
        )


@dataclass(frozen=True)
class MalhaSumo:
    """Tudo o que o adaptador precisa saber sobre a malha, já traduzido.

    Attributes:
        topologia: A topologia que vai para o motor.
        programas: State strings por cruzamento.
        acessos: Vias de entrada de cada cruzamento, por eixo.
        faixas_do_acesso: Faixas de cada via de entrada — usado para somar as
            filas dos detectores E2 por aproximação.
    """

    topologia: TopologiaMalha
    programas: Mapping[str, ProgramaSemaforico]
    acessos: Mapping[str, Mapping[str, tuple[str, ...]]]
    faixas_do_acesso: Mapping[str, tuple[str, ...]]

    @property
    def semaforos(self) -> tuple[str, ...]:
        """Cruzamentos semaforizados, em ordem."""
        return tuple(sorted(self.topologia.cruzamentos))


def _ler_mapa_de_fases(caminho: Path) -> dict[str, Any]:
    with caminho.open(encoding="utf-8") as arquivo:
        dados: dict[str, Any] = yaml.safe_load(arquivo)
    return dados


def _movimentos(rede: Any, acessos: Sequence[str]) -> frozenset[Movimento]:
    """Pares (entrada, saída) que a rede permite a partir destas aproximações."""
    pares: set[Movimento] = set()
    for entrada in acessos:
        for saida in rede.getEdge(entrada).getOutgoing():
            pares.add((entrada, saida.getID()))
    return frozenset(pares)


def _programa_de(tls: Any, fases: Sequence[Mapping[str, Any]]) -> ProgramaSemaforico:
    """Extrai as state strings do programa do SUMO, por (fase lógica, sinal)."""
    programas = tls.getPrograms()
    if not programas:
        raise ConfiguracaoInvalidaError(f"{tls.getID()} não tem programa semafórico")
    fases_sumo = next(iter(programas.values())).getPhases()

    estados: dict[tuple[int, Sinal], str] = {}
    indices: dict[tuple[int, Sinal], int] = {}
    for fase in fases:
        for sinal, chave in CHAVE_DO_SINAL.items():
            posicao = int(fase["programa"][chave])
            if posicao >= len(fases_sumo):
                raise ConfiguracaoInvalidaError(
                    f"{tls.getID()}: fase {fase['indice']} aponta para o índice {posicao}, "
                    f"mas o programa tem {len(fases_sumo)} fases"
                )
            estados[(int(fase["indice"]), sinal)] = fases_sumo[posicao].state
            indices[(int(fase["indice"]), sinal)] = posicao
    return ProgramaSemaforico(tls.getID(), estados, indices)


def carregar(rede_xml: Path = REDE_PADRAO, mapa_fases_yaml: Path = MAPA_FASES_PADRAO) -> MalhaSumo:
    """Monta a `MalhaSumo` a partir da rede e do mapa de fases.

    Args:
        rede_xml: Caminho de `malha.net.xml`.
        mapa_fases_yaml: Caminho de `mapa_fases.yaml`.

    Returns:
        A malha traduzida, pronta para o motor e para o adaptador.

    Raises:
        ConfiguracaoInvalidaError: se a rede não existir ou se os dois lados
            não fecharem.
    """
    if not rede_xml.is_file():
        raise ConfiguracaoInvalidaError(
            f"{rede_xml} não existe — rode `python -m sim.rede.construir`"
        )

    from sim.ambiente import registrar_ferramentas  # import local: evita ciclo de import

    registrar_ferramentas()
    import sumolib  # import local: depende de SUMO_HOME no sys.path

    rede = sumolib.net.readNet(str(rede_xml), withPrograms=True, withConnections=True)
    mapa = _ler_mapa_de_fases(mapa_fases_yaml)
    padrao = mapa["padrao"]
    conflitos = {
        int(fase): frozenset(int(outra) for outra in outras)
        for fase, outras in padrao["conflitos"].items()
    }

    cruzamentos: dict[str, Cruzamento] = {}
    acessos: dict[str, dict[str, tuple[str, ...]]] = {}
    faixas_do_acesso: dict[str, tuple[str, ...]] = {}
    programas: dict[str, ProgramaSemaforico] = {}

    for id_semaforo, eixos in mapa["semaforos"].items():
        fases: list[Fase] = []
        for definicao in padrao["fases"]:
            vias = tuple(eixos[definicao["eixo"]])
            fases.append(
                Fase(
                    indice=int(definicao["indice"]),
                    descricao=str(definicao["descricao"]),
                    movimentos=_movimentos(rede, vias),
                    duracao_base_s=float(definicao["duracao_base_s"]),
                    verde_min_s=float(definicao["verde_min_s"]),
                    verde_max_s=float(definicao["verde_max_s"]),
                )
            )
            for via in vias:
                faixas_do_acesso[via] = tuple(
                    faixa.getID() for faixa in rede.getEdge(via).getLanes()
                )

        cruzamentos[id_semaforo] = Cruzamento(
            id=id_semaforo, fases=tuple(fases), conflitos=conflitos
        )
        acessos[id_semaforo] = {
            str(eixo): tuple(vias)
            for eixo, vias in eixos.items()  # type: ignore[union-attr]
        }
        programas[id_semaforo] = _programa_de(rede.getTLS(id_semaforo), padrao["fases"])

    topologia = TopologiaMalha(
        cruzamentos=cruzamentos,
        comprimento_via_m={aresta.getID(): aresta.getLength() for aresta in rede.getEdges()},
        cruzamento_apos_via={
            aresta.getID(): aresta.getToNode().getID()
            for aresta in rede.getEdges()
            if aresta.getToNode().getType() == "traffic_light"
        },
        # E3 divide a fila do acesso pelas faixas para estimar a dissipação
        # (P16). O número vem da rede construída, não de configuração: duplicá-lo
        # num YAML criaria uma segunda fonte da verdade sobre a geometria.
        faixas_por_via={aresta.getID(): aresta.getLaneNumber() for aresta in rede.getEdges()},
    )
    topologia.validar()

    return MalhaSumo(
        topologia=topologia,
        programas=programas,
        acessos=acessos,
        faixas_do_acesso=faixas_do_acesso,
    )


def validar(malha: MalhaSumo, rede_xml: Path = REDE_PADRAO) -> list[str]:
    """Confere que o mapa de fases e a rede descrevem a mesma coisa.

    O que é verificado, e por quê:

    1. **Toda aproximação da rede é servida por alguma fase.** Uma aproximação
       esquecida no YAML ficaria eternamente no vermelho sob controle do motor —
       violação de I5 na cara, mas só descoberta rodando.
    2. **Nenhuma aproximação é servida por duas fases.** Seria conceder verde a
       movimentos conflitantes, violação de I1.
    3. **A fase declarada verde é verde de verdade no programa do SUMO.** É a
       mesma verificação que I1 faz no motor, aplicada à rede: se a state string
       da fase 1 desse verde a um link da transversal, o motor estaria correto e
       a rua, errada.

    Returns:
        Lista de problemas. Vazia significa que os dois lados fecham.
    """
    from sim.ambiente import registrar_ferramentas  # import local: evita ciclo de import

    registrar_ferramentas()
    import sumolib  # import local: depende de SUMO_HOME no sys.path

    rede = sumolib.net.readNet(str(rede_xml), withPrograms=True, withConnections=True)
    problemas: list[str] = []

    for id_semaforo, eixos in malha.acessos.items():
        no = rede.getNode(id_semaforo)
        na_rede = {aresta.getID() for aresta in no.getIncoming()}
        declaradas = [via for vias in eixos.values() for via in vias]

        if faltando := na_rede - set(declaradas):
            problemas.append(
                f"{id_semaforo}: aproximações da rede fora do mapa de fases: "
                f"{', '.join(sorted(faltando))}"
            )
        if sobrando := set(declaradas) - na_rede:
            problemas.append(
                f"{id_semaforo}: aproximações no mapa que a rede não tem: "
                f"{', '.join(sorted(sobrando))}"
            )
        if len(declaradas) != len(set(declaradas)):
            problemas.append(f"{id_semaforo}: aproximação declarada em mais de uma fase")

        problemas += _conferir_verdes(rede, malha, id_semaforo)

    return problemas


def _conferir_verdes(rede: Any, malha: MalhaSumo, id_semaforo: str) -> list[str]:
    """Confere que a state string de cada fase verde só abre a própria aproximação."""
    programa = malha.programas[id_semaforo]
    cruzamento = malha.topologia.cruzamento(id_semaforo)
    ligacoes = rede.getTLS(id_semaforo).getConnections()

    problemas: list[str] = []
    for fase in cruzamento.fases:
        estado = programa.estado(fase.indice, Sinal.VERDE)
        for entrada, _, indice in ligacoes:
            via = entrada.getEdge().getID()
            e_da_fase = via in fase.acessos
            esta_verde = estado[indice] in "Gg"
            if esta_verde and not e_da_fase:
                problemas.append(
                    f"{id_semaforo}: fase {fase.indice} dá verde ao link {indice} "
                    f"({via}), que não é aproximação dela"
                )
            elif e_da_fase and not esta_verde:
                problemas.append(
                    f"{id_semaforo}: fase {fase.indice} deixa o link {indice} "
                    f"({via}) no vermelho, embora a aproximação seja dela"
                )
    return problemas
