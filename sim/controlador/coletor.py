"""Coleta de métricas da execução — entrega 3.8 (`context/04` §9 e §10).

Divide o trabalho em dois tempos, e a divisão não é arbitrária:

* **Durante a execução** só se acumula em memória — latências, transições, fila
  máxima, colisões. Nada de banco e nada de arquivo dentro do loop. A regra vem
  de `context/03` §4.1, e a razão mais forte não é desempenho: um `INSERT`
  síncrono no meio do passo **contamina a medição de latência**, que é o dado
  que sustenta o RNF01. Latência de decisão medida junto com round-trip de banco
  não mede o motor, mede a rede.
* **Depois da execução** consolida-se tudo: o `tripinfo.xml` é lido, os
  percentis são calculados e os CSV de `analysis/data/` são escritos.

Sobre percentis: `context/04` §9.3 é explícito em pedir **p95 e p99, não só a
média**. Sistema crítico se avalia pela cauda — média de 68 ms com p99 de 400 ms
não atende ao requisito, e essa é exatamente a pergunta que a banca pode fazer.
"""

from __future__ import annotations

import csv
import math
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from core.modelos import EstadoMalha, Transicao
from core.seguranca import Violacao

RAIZ = Path(__file__).resolve().parents[2]
DADOS = RAIZ / "analysis" / "data"

ARQUIVO_EXECUCOES = "execucoes.csv"
ARQUIVO_VE = "ve_por_execucao.csv"
ARQUIVO_TRANSVERSAL = "transversal_por_execucao.csv"
ARQUIVO_LATENCIAS = "latencias.csv"

#: Prefixos de id que identificam veículo de fundo em via transversal. Os ids
#: são gerados por `sim/demanda/gerar_rotas.py` a partir do nome da corrente.
PREFIXOS_TRANSVERSAIS = ("T1_", "T2_", "T3_", "T4_")

#: `vType` dos veículos de emergência — os que compõem as métricas de H1.
VTYPES_EMERGENCIA = ("ambulancia", "bombeiro", "policia")


def percentil(valores: Sequence[float], p: float) -> float:
    """Percentil pelo método do posto mais próximo (*nearest-rank*).

    Sem interpolação de propósito: o valor devolvido é uma medição que de fato
    ocorreu, e não uma média entre duas. Para orçamento de latência é a leitura
    mais defensável — "95% das decisões levaram no máximo isto".

    Args:
        valores: Amostras, em qualquer ordem.
        p: Percentil pedido, entre 0 e 100.

    Returns:
        O valor do percentil, ou 0.0 se não houver amostra.
    """
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    posicao = max(1, math.ceil(p / 100.0 * len(ordenados)))
    return ordenados[min(posicao, len(ordenados)) - 1]


@dataclass(frozen=True)
class ViagemVE:
    """Uma viagem de veículo de emergência, do `tripinfo` (`context/04` §9.1)."""

    id_veiculo: str
    tipo: str
    tempo_viagem_s: float
    tempo_espera_s: float
    paradas: int
    velocidade_media_ms: float
    atraso_s: float


@dataclass(frozen=True)
class ResultadoExecucao:
    """Tudo o que uma execução produziu, já consolidado.

    Attributes:
        cenario: Cenário simulado.
        modo: Braço de comparação.
        seed: Seed do ponto experimental.
        duracao_s: Duração simulada, em segundos.
        viagens_ve: Uma entrada por VE que completou a rota.
        tempo_espera_medio_transversal_s: Evidência de H2.
        atraso_total_rede_s: Soma de `timeLoss` de todos os veículos.
        veiculos_completos: Veículos que chegaram ao destino.
        veiculos_planejados: Veículos declarados no arquivo de rotas.
        fila_maxima_por_acesso: Pico de fila em cada aproximação.
        latencias_ms: Latência de decisão de cada passo.
        colisoes: Colisões observadas — precisa ser zero.
        teleportes: Teleportes observados — precisa ser zero.
        violacoes: Invariantes de segurança violados — precisa ser vazio.
        transicoes: Transições de fase (decisão P5).
        avisos: Ocorrências não fatais registradas pelo adaptador.
    """

    cenario: str
    modo: str
    seed: int
    duracao_s: float
    viagens_ve: tuple[ViagemVE, ...] = ()
    tempo_espera_medio_transversal_s: float = 0.0
    atraso_total_rede_s: float = 0.0
    veiculos_completos: int = 0
    veiculos_planejados: int = 0
    fila_maxima_por_acesso: Mapping[str, int] = field(default_factory=dict)
    latencias_ms: tuple[float, ...] = ()
    colisoes: int = 0
    teleportes: int = 0
    violacoes: tuple[Violacao, ...] = ()
    transicoes: tuple[Transicao, ...] = ()
    avisos: tuple[str, ...] = ()

    # -- agregados de latência (RNF01 e H3) ---------------------------------

    @property
    def latencia_media_ms(self) -> float:
        """Média das latências de decisão, em milissegundos."""
        return sum(self.latencias_ms) / len(self.latencias_ms) if self.latencias_ms else 0.0

    @property
    def latencia_p95_ms(self) -> float:
        """p95 da latência de decisão — o número do RNF01."""
        return percentil(self.latencias_ms, 95)

    @property
    def latencia_p99_ms(self) -> float:
        """p99 da latência de decisão."""
        return percentil(self.latencias_ms, 99)

    @property
    def latencia_max_ms(self) -> float:
        """Pior latência de decisão observada."""
        return max(self.latencias_ms, default=0.0)

    # -- agregados do VE (H1) ------------------------------------------------

    @property
    def tempo_medio_travessia_ve_s(self) -> float:
        """Tempo médio de travessia dos VEs — a variável de resposta de H1."""
        if not self.viagens_ve:
            return 0.0
        return sum(viagem.tempo_viagem_s for viagem in self.viagens_ve) / len(self.viagens_ve)

    @property
    def paradas_medias_ve(self) -> float:
        """Paradas médias por VE — a evidência do RF03 (`waitingCount == 0`)."""
        if not self.viagens_ve:
            return 0.0
        return sum(viagem.paradas for viagem in self.viagens_ve) / len(self.viagens_ve)


@dataclass
class ColetorMetricas:
    """Acumula, sem tocar disco nem banco, o que a execução vai produzir.

    Attributes:
        cenario: Cenário simulado.
        modo: Braço de comparação.
        seed: Seed do ponto experimental.
    """

    cenario: str
    modo: str
    seed: int

    latencias_ms: list[float] = field(default_factory=list)
    transicoes: list[Transicao] = field(default_factory=list)
    violacoes: list[Violacao] = field(default_factory=list)
    fila_maxima_por_acesso: dict[str, int] = field(default_factory=dict)
    colisoes: int = 0
    teleportes: int = 0
    comandos_emitidos: int = 0
    preempcoes: int = 0

    def registrar_decisao(self, latencia_ms: float, n_comandos: int) -> None:
        """Anota a latência de uma chamada ao motor e quantos comandos saíram."""
        self.latencias_ms.append(latencia_ms)
        self.comandos_emitidos += n_comandos

    def registrar_transicoes(self, transicoes: Iterable[Transicao]) -> None:
        """Anota as transições de fase deste passo (decisão P5)."""
        for transicao in transicoes:
            self.transicoes.append(transicao)
            if transicao.em_preempcao:
                self.preempcoes += 1

    def registrar_violacoes(self, violacoes: Iterable[Violacao]) -> None:
        """Anota violações de invariante. O esperado é que nunca seja chamado."""
        self.violacoes.extend(violacoes)

    def registrar_estado(self, estado: EstadoMalha) -> None:
        """Atualiza o pico de fila de cada aproximação (`context/04` §9.2)."""
        for semaforo in estado.semaforos.values():
            for acesso, fila in semaforo.fila_por_acesso.items():
                if fila > self.fila_maxima_por_acesso.get(acesso, 0):
                    self.fila_maxima_por_acesso[acesso] = fila

    def registrar_incidentes(self, colisoes: int, teleportes: int) -> None:
        """Soma colisões e teleportes do passo."""
        self.colisoes += colisoes
        self.teleportes += teleportes

    def consolidar(
        self, tripinfo: Path, duracao_s: float, veiculos_planejados: int, avisos: Sequence[str] = ()
    ) -> ResultadoExecucao:
        """Fecha a execução, lendo o `tripinfo.xml` produzido pelo SUMO.

        Args:
            tripinfo: Caminho do `tripinfo.xml`.
            duracao_s: Duração simulada, em segundos.
            veiculos_planejados: Veículos declarados no arquivo de rotas.
            avisos: Avisos acumulados pelo adaptador.

        Returns:
            O resultado consolidado.
        """
        viagens, espera_transversal, atraso_total, completos = _ler_tripinfo(tripinfo)
        return ResultadoExecucao(
            cenario=self.cenario,
            modo=self.modo,
            seed=self.seed,
            duracao_s=duracao_s,
            viagens_ve=viagens,
            tempo_espera_medio_transversal_s=espera_transversal,
            atraso_total_rede_s=atraso_total,
            veiculos_completos=completos,
            veiculos_planejados=veiculos_planejados,
            fila_maxima_por_acesso=dict(self.fila_maxima_por_acesso),
            latencias_ms=tuple(self.latencias_ms),
            colisoes=self.colisoes,
            teleportes=self.teleportes,
            violacoes=tuple(self.violacoes),
            transicoes=tuple(self.transicoes),
            avisos=tuple(avisos),
        )


def _ler_tripinfo(caminho: Path) -> tuple[tuple[ViagemVE, ...], float, float, int]:
    """Extrai de `tripinfo.xml` as métricas de `context/04` §9.1 e §9.2.

    Os veículos de fundo em via transversal são identificados pelo prefixo do id,
    que `sim/demanda/gerar_rotas.py` monta a partir do nome da corrente. O
    `tripinfo` não carrega o id da rota, e reabrir a rede só para descobrir isso
    custaria mais do que a convenção de nome — que está declarada nos dois lados.
    """
    if not caminho.is_file():
        return (), 0.0, 0.0, 0

    viagens: list[ViagemVE] = []
    esperas_transversais: list[float] = []
    atraso_total = 0.0
    completos = 0

    for elemento in ET.parse(caminho).getroot().iter("tripinfo"):
        completos += 1
        identificador = str(elemento.get("id"))
        vtype = str(elemento.get("vType", ""))
        duracao = float(elemento.get("duration", 0.0))
        atraso_total += float(elemento.get("timeLoss", 0.0))

        if vtype in VTYPES_EMERGENCIA:
            comprimento = float(elemento.get("routeLength", 0.0))
            viagens.append(
                ViagemVE(
                    id_veiculo=identificador,
                    tipo=vtype,
                    tempo_viagem_s=duracao,
                    tempo_espera_s=float(elemento.get("waitingTime", 0.0)),
                    paradas=int(elemento.get("waitingCount", 0)),
                    velocidade_media_ms=comprimento / duracao if duracao > 0 else 0.0,
                    atraso_s=float(elemento.get("timeLoss", 0.0)),
                )
            )
        elif identificador.startswith(PREFIXOS_TRANSVERSAIS):
            esperas_transversais.append(float(elemento.get("waitingTime", 0.0)))

    media_transversal = (
        sum(esperas_transversais) / len(esperas_transversais) if esperas_transversais else 0.0
    )
    return tuple(viagens), media_transversal, atraso_total, completos


# ---------------------------------------------------------------------------
# Escrita dos CSV — context/04 §10
# ---------------------------------------------------------------------------


def _anexar(destino: Path, cabecalho: Sequence[str], linhas: Sequence[Sequence[object]]) -> None:
    """Acrescenta linhas a um CSV, criando o cabeçalho se o arquivo for novo."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    novo = not destino.is_file()
    with destino.open("a", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo)
        if novo:
            escritor.writerow(cabecalho)
        escritor.writerows(linhas)


def gravar_csv(
    resultado: ResultadoExecucao,
    *,
    id_execucao: int | None = None,
    versao_codigo: str = "",
    detalhar_latencias: bool = False,
    diretorio: Path = DADOS,
) -> None:
    """Escreve os CSV de `context/04` §10.

    `latencias.csv` só recebe uma linha por decisão quando `detalhar_latencias`
    está ligado — o que na prática significa execução **exemplar**. São 36.000
    decisões por execução: nas 600 do Bloco 8 isso daria mais de 20 milhões de
    linhas, e a mesma razão que levou a decisão P5 a persistir só transições de
    execuções exemplares vale aqui. Os percentis, que são o que RNF01 e H3
    exigem, vão em `execucoes.csv` de toda execução.
    """
    identificador = id_execucao if id_execucao is not None else -1
    ponto = (identificador, resultado.cenario, resultado.modo, resultado.seed)

    _anexar(
        diretorio / ARQUIVO_EXECUCOES,
        (
            "id_execucao",
            "cenario",
            "modo",
            "seed",
            "versao_codigo",
            "duracao_s",
            "veiculos_planejados",
            "veiculos_completos",
            "ves_completos",
            "tempo_medio_travessia_ve_s",
            "paradas_medias_ve",
            "tempo_espera_medio_transversal_s",
            "atraso_total_rede_s",
            "latencia_media_ms",
            "latencia_p95_ms",
            "latencia_p99_ms",
            "latencia_max_ms",
            "colisoes",
            "teleportes",
            "violacoes",
            "transicoes",
        ),
        [
            [
                *ponto,
                versao_codigo,
                f"{resultado.duracao_s:.0f}",
                resultado.veiculos_planejados,
                resultado.veiculos_completos,
                len(resultado.viagens_ve),
                f"{resultado.tempo_medio_travessia_ve_s:.2f}",
                f"{resultado.paradas_medias_ve:.2f}",
                f"{resultado.tempo_espera_medio_transversal_s:.2f}",
                f"{resultado.atraso_total_rede_s:.2f}",
                f"{resultado.latencia_media_ms:.4f}",
                f"{resultado.latencia_p95_ms:.4f}",
                f"{resultado.latencia_p99_ms:.4f}",
                f"{resultado.latencia_max_ms:.4f}",
                resultado.colisoes,
                resultado.teleportes,
                len(resultado.violacoes),
                len(resultado.transicoes),
            ]
        ],
    )

    _anexar(
        diretorio / ARQUIVO_VE,
        (
            "id_execucao",
            "cenario",
            "modo",
            "seed",
            "id_veiculo",
            "tipo",
            "tempo_viagem_s",
            "tempo_espera_s",
            "paradas",
            "velocidade_media_ms",
            "atraso_s",
        ),
        [
            [
                *ponto,
                viagem.id_veiculo,
                viagem.tipo,
                f"{viagem.tempo_viagem_s:.2f}",
                f"{viagem.tempo_espera_s:.2f}",
                viagem.paradas,
                f"{viagem.velocidade_media_ms:.2f}",
                f"{viagem.atraso_s:.2f}",
            ]
            for viagem in resultado.viagens_ve
        ],
    )

    _anexar(
        diretorio / ARQUIVO_TRANSVERSAL,
        ("id_execucao", "cenario", "modo", "seed", "acesso", "fila_maxima"),
        [
            [*ponto, acesso, fila]
            for acesso, fila in sorted(resultado.fila_maxima_por_acesso.items())
        ],
    )

    if detalhar_latencias:
        _anexar(
            diretorio / ARQUIVO_LATENCIAS,
            ("id_execucao", "cenario", "modo", "seed", "indice", "latencia_ms"),
            [
                [*ponto, indice, f"{latencia:.4f}"]
                for indice, latencia in enumerate(resultado.latencias_ms)
            ],
        )
