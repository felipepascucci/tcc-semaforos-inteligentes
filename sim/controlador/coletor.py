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
from core.parametros import Parametros
from core.priorizacao.conflito import EventoConflito
from core.priorizacao.politica import ConsultaModelo
from core.seguranca import Violacao

RAIZ = Path(__file__).resolve().parents[2]
DADOS = RAIZ / "analysis" / "data"

ARQUIVO_EXECUCOES = "execucoes.csv"
ARQUIVO_VE = "ve_por_execucao.csv"
ARQUIVO_TRANSVERSAL = "transversal_por_execucao.csv"
ARQUIVO_LATENCIAS = "latencias.csv"
ARQUIVO_CONFLITOS = "conflitos_por_execucao.csv"

#: Quantos passos de folga separam dois episódios de conflito. Um conflito
#: reaparece a cada passo enquanto os dois VEs se aproximam; um buraco maior que
#: isto significa que a disputa se desfez e outra começou depois.
FOLGA_ENTRE_EPISODIOS_EM_PASSOS = 1.5

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
class EpisodioConflito:
    """Uma disputa entre VEs, agregada ao longo dos passos em que durou.

    A unidade da contagem da entrega 10.1 é o **episódio**, não o passo. Com
    passo de 0,1 s, um único conflito de dez segundos apareceria como cem
    "eventos" — número grande e sem significado, porque há **uma** escolha a
    fazer ali, e é ela que a política aprendida de P19 vai decidir.

    Os atributos dos VEs são os da **abertura** do episódio: é o instante em que
    a escolha se apresenta pela primeira vez, e portanto o instante que a
    rotulagem por bifurcação (10.4) vai usar. As tuplas seguem a ordem dos ids,
    então a i-ésima posição de `tipos`, `criticidades`, `etas_s` e
    `fases_desejadas` descreve o i-ésimo id.

    Attributes:
        id_semaforo: Cruzamento disputado.
        t_inicio_s: Instante do primeiro passo do episódio.
        t_fim_s: Instante do último passo observado.
        passos: Quantos passos o episódio durou.
        ids_veiculos: Ids dos VEs em disputa, ordenados.
        tipos: Tipo de cada VE.
        criticidades: Criticidade da ocorrência de cada VE (P20).
        etas_s: ETA de cada VE ao cruzamento, na abertura.
        fases_desejadas: Fase que cada VE demanda.
        decidivel: Se, na abertura, não havia preempção em curso — ou seja, se a
            escolha estava em aberto em vez de suspensa pela guarda de oscilação.
        decidivel_em_algum_passo: Se em algum passo do episódio a escolha esteve
            em aberto. Distingue o conflito que nasceu sob preempção alheia e se
            libertou daquele que passou inteiro suspenso.
        preempcao_em_curso: VE que detinha a preempção na abertura, ou `None`.
        decidida_pelo_modelo: Se o modelo de P19 decidiu a disputa em algum
            passo do episódio (entrega 10.7). Só pode ser verdade no braço
            `PREEMPCAO_ML`; nos outros não há modelo a consultar.
        modelo_divergiu_do_e8: Se, em algum desses passos, o modelo escolheu
            diferente do que o E8 determinístico escolheria. Episódio em que é
            falso decorreu igual nos dois braços **no que dependeu do modelo**:
            é o n em que a política aprendida pode ter mudado alguma coisa
            (`context/07` §3.3.1).
    """

    id_semaforo: str
    t_inicio_s: float
    t_fim_s: float
    passos: int
    ids_veiculos: tuple[str, ...]
    tipos: tuple[str, ...]
    criticidades: tuple[int, ...]
    etas_s: tuple[float, ...]
    fases_desejadas: tuple[int, ...]
    decidivel: bool
    decidivel_em_algum_passo: bool
    preempcao_em_curso: str | None = None
    decidida_pelo_modelo: bool = False
    modelo_divergiu_do_e8: bool = False

    @property
    def n_ves(self) -> int:
        """Quantos VEs disputaram o cruzamento."""
        return len(self.ids_veiculos)

    @property
    def mesmo_nivel(self) -> bool:
        """Se todos os VEs da disputa têm a mesma criticidade (P20).

        Só essas disputas são decididas pelo modelo de P19: entre níveis
        diferentes, a regra de criticidade decide nos dois braços. É por esta
        propriedade que a análise de H4 se estratifica (`context/07` §3.3.1).
        """
        return len(set(self.criticidades)) <= 1

    @property
    def duracao_s(self) -> float:
        """Quanto tempo a disputa durou, em segundos."""
        return self.t_fim_s - self.t_inicio_s


@dataclass(frozen=True)
class ResultadoExecucao:
    """Tudo o que uma execução produziu, já consolidado.

    Attributes:
        cenario: Cenário simulado.
        modo: Braço de comparação.
        seed: Seed do ponto experimental.
        duracao_s: Duração simulada, em segundos.
        aquecimento_s: Transiente descartado das médias, em segundos.
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
        conflitos: Episódios de disputa entre VEs (entrega 10.1).
    """

    cenario: str
    modo: str
    seed: int
    duracao_s: float
    aquecimento_s: float = 0.0
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
    conflitos: tuple[EpisodioConflito, ...] = ()

    # -- agregados de conflito entre VEs (entrega 10.1) ----------------------

    @property
    def eventos_conflito(self) -> int:
        """Episódios de disputa entre VEs na execução."""
        return len(self.conflitos)

    @property
    def eventos_conflito_decidiveis(self) -> int:
        """Quantos deles apresentaram uma escolha em aberto, e não suspensa."""
        return sum(1 for episodio in self.conflitos if episodio.decidivel)

    @property
    def passos_em_conflito(self) -> int:
        """Passos de simulação com alguma disputa em curso.

        Serve de contraste com `eventos_conflito`: é o número que se obteria
        contando por passo, e a diferença entre os dois mostra por que a unidade
        é o episódio.
        """
        return sum(episodio.passos for episodio in self.conflitos)

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
class _EpisodioAberto:
    """Episódio de conflito ainda em curso, enquanto os passos se acumulam."""

    abertura: EventoConflito
    t_fim_s: float
    passos: int
    decidivel_em_algum_passo: bool
    decidida_pelo_modelo: bool = False
    modelo_divergiu_do_e8: bool = False

    def fechar(self) -> EpisodioConflito:
        """Congela o episódio no formato que vai para o CSV."""
        ordenadas = sorted(self.abertura.disputas, key=lambda d: d.deteccao.id_veiculo)
        return EpisodioConflito(
            id_semaforo=self.abertura.id_semaforo,
            t_inicio_s=self.abertura.t,
            t_fim_s=self.t_fim_s,
            passos=self.passos,
            ids_veiculos=tuple(disputa.deteccao.id_veiculo for disputa in ordenadas),
            tipos=tuple(str(disputa.deteccao.tipo) for disputa in ordenadas),
            criticidades=tuple(int(disputa.deteccao.criticidade) for disputa in ordenadas),
            etas_s=tuple(disputa.deteccao.eta_s for disputa in ordenadas),
            fases_desejadas=tuple(disputa.fase_desejada for disputa in ordenadas),
            decidivel=self.abertura.decidivel,
            decidivel_em_algum_passo=self.decidivel_em_algum_passo,
            preempcao_em_curso=self.abertura.preempcao_em_curso,
            decidida_pelo_modelo=self.decidida_pelo_modelo,
            modelo_divergiu_do_e8=self.modelo_divergiu_do_e8,
        )


@dataclass
class ColetorMetricas:
    """Acumula, sem tocar disco nem banco, o que a execução vai produzir.

    Attributes:
        cenario: Cenário simulado.
        modo: Braço de comparação.
        seed: Seed do ponto experimental.
        passo_s: Passo da simulação, em segundos. Define a folga que separa dois
            episódios de conflito.
    """

    cenario: str
    modo: str
    seed: int
    passo_s: float = 0.1

    latencias_ms: list[float] = field(default_factory=list)
    transicoes: list[Transicao] = field(default_factory=list)
    violacoes: list[Violacao] = field(default_factory=list)
    fila_maxima_por_acesso: dict[str, int] = field(default_factory=dict)
    colisoes: int = 0
    teleportes: int = 0
    comandos_emitidos: int = 0
    preempcoes: int = 0
    conflitos: list[EpisodioConflito] = field(default_factory=list)
    _abertos: dict[tuple[str, tuple[str, ...]], _EpisodioAberto] = field(
        default_factory=dict, repr=False
    )

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

    def abriria_episodio(self, evento: EventoConflito) -> bool:
        """Se `registrar_conflitos` abriria um episódio novo com este evento.

        Consulta pura, para a rotulagem (10.4) bifurcar exatamente nas aberturas
        de episódio que a 10.1 conta, e não em cada passo da disputa.
        """
        aberto = self._abertos.get((evento.id_semaforo, evento.ids_veiculos))
        folga = FOLGA_ENTRE_EPISODIOS_EM_PASSOS * self.passo_s
        return aberto is None or evento.t - aberto.t_fim_s > folga

    def registrar_conflitos(self, eventos: Iterable[EventoConflito]) -> None:
        """Agrega os conflitos observados neste passo em episódios (10.1).

        Chamado **fora** do trecho cronometrado do executor, de propósito: o
        número que sustenta o RNF01 é a latência do motor, e não pode incluir a
        contabilidade da instrumentação.

        Um episódio é identificado pelo par (cruzamento, conjunto de VEs). O
        mesmo par reaparecendo no passo seguinte prolonga o episódio; reaparecer
        depois de um intervalo maior que a folga abre um episódio novo, porque
        entre um e outro a disputa deixou de existir.

        Args:
            eventos: Conflitos publicados pelo motor neste passo.
        """
        for evento in eventos:
            chave = (evento.id_semaforo, evento.ids_veiculos)
            aberto = self._abertos.get(chave)
            folga = FOLGA_ENTRE_EPISODIOS_EM_PASSOS * self.passo_s

            if aberto is not None and evento.t - aberto.t_fim_s <= folga:
                aberto.t_fim_s = evento.t
                aberto.passos += 1
                aberto.decidivel_em_algum_passo |= evento.decidivel
                continue

            if aberto is not None:
                self.conflitos.append(aberto.fechar())
            self._abertos[chave] = _EpisodioAberto(
                abertura=evento,
                t_fim_s=evento.t,
                passos=1,
                decidivel_em_algum_passo=evento.decidivel,
            )

    def registrar_consultas(
        self, consultas: Iterable[ConsultaModelo], parametros: Parametros
    ) -> None:
        """Marca os episódios em que o modelo decidiu, e se divergiu do E8 (10.7).

        Chamado depois de `registrar_conflitos` do **mesmo passo**, e fora do
        trecho cronometrado: comparar a escolha do modelo com a do E8 é
        contabilidade, e não entra na latência do RNF01.

        Toda consulta tem um episódio aberto: o modelo só decide entre pedidos
        por fases distintas, e esses pedidos são justamente um conflito que o
        motor publicou no mesmo passo e no mesmo cruzamento. O episódio é o
        daquele cruzamento cujo último passo é o da consulta.

        Args:
            consultas: As consultas ao modelo publicadas neste passo.
            parametros: Os parâmetros do motor, para a chave do E8.

        Raises:
            ValueError: se uma consulta não tiver episódio no mesmo passo. É
                defeito, e não dado: a contagem de H4 não pode perder consulta
                em silêncio.
        """
        folga = 0.5 * self.passo_s
        for consulta in consultas:
            ids = {disputa.deteccao.id_veiculo for disputa in consulta.candidatos}
            episodio = next(
                (
                    aberto
                    for (id_semaforo, ids_episodio), aberto in self._abertos.items()
                    if id_semaforo == consulta.id_semaforo
                    and abs(aberto.t_fim_s - consulta.t) <= folga
                    and ids <= set(ids_episodio)
                ),
                None,
            )
            if episodio is None:
                raise ValueError(
                    f"consulta ao modelo sem conflito no mesmo passo: {consulta.id_semaforo} "
                    f"em t={consulta.t:.1f}s, VEs {sorted(ids)}"
                )
            episodio.decidida_pelo_modelo = True
            episodio.modelo_divergiu_do_e8 |= consulta.divergiu_do_e8(parametros)

    def _fechar_conflitos(self) -> tuple[EpisodioConflito, ...]:
        """Fecha os episódios ainda abertos e devolve todos, em ordem de início."""
        for aberto in self._abertos.values():
            self.conflitos.append(aberto.fechar())
        self._abertos.clear()
        return tuple(
            sorted(self.conflitos, key=lambda e: (e.t_inicio_s, e.id_semaforo, e.ids_veiculos))
        )

    def consolidar(
        self,
        tripinfo: Path,
        duracao_s: float,
        veiculos_planejados: int,
        avisos: Sequence[str] = (),
        aquecimento_s: float = 0.0,
    ) -> ResultadoExecucao:
        """Fecha a execução, lendo o `tripinfo.xml` produzido pelo SUMO.

        Args:
            tripinfo: Caminho do `tripinfo.xml`.
            duracao_s: Duração simulada, em segundos.
            veiculos_planejados: Veículos declarados no arquivo de rotas.
            avisos: Avisos acumulados pelo adaptador.
            aquecimento_s: Veículos que partiram antes disso ficam **fora** das
                médias. Ver `_ler_tripinfo`.

        Returns:
            O resultado consolidado.
        """
        viagens, espera_transversal, atraso_total, completos = _ler_tripinfo(
            tripinfo, aquecimento_s
        )
        return ResultadoExecucao(
            cenario=self.cenario,
            modo=self.modo,
            seed=self.seed,
            duracao_s=duracao_s,
            aquecimento_s=aquecimento_s,
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
            conflitos=self._fechar_conflitos(),
        )


def _ler_tripinfo(
    caminho: Path, aquecimento_s: float = 0.0
) -> tuple[tuple[ViagemVE, ...], float, float, int]:
    """Extrai de `tripinfo.xml` as métricas de `context/04` §9.1 e §9.2.

    **O aquecimento é descartado das médias.** A malha começa vazia: quem parte
    nos primeiros minutos trafega numa via mais livre do que a que o cenário
    descreve, e entra na conta puxando a espera para baixo. Como a métrica
    transversal é justamente a evidência de H2, incluir o transiente de
    enchimento subestimaria o custo que a compensação existe para mitigar — e
    subestimaria igualmente nos três braços, o que esconde o efeito em vez de
    medi-lo.

    A janela é a mesma que `sim/validacao/malha.py` usa para medir o v/c, e o
    mesmo `aquecimento_s` que `gerar_rotas.py` usa para decidir quando o primeiro
    VE entra. Os VEs, portanto, nunca caem no descarte.

    `veiculos_completos` continua contando **todos** os que chegaram ao destino:
    ele não é métrica de desempenho, é conferência de que a execução escoou o que
    prometeu (`context/06` §4).

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
        if float(elemento.get("depart", 0.0)) < aquecimento_s:
            continue

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


class CabecalhoDivergenteError(ValueError):
    """Um CSV existente tem cabeçalho diferente das linhas que se quer acrescentar."""


def cabecalho_do_csv(caminho: Path) -> list[str] | None:
    """Colunas da primeira linha de um CSV, ou `None` se o arquivo não existir."""
    if not caminho.is_file():
        return None
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return next(csv.reader(arquivo), [])


def exigir_mesmo_cabecalho(destino: Path, cabecalho: Sequence[str]) -> None:
    """Recusa acrescentar linhas a um CSV cujo cabeçalho é outro.

    Sem esta guarda, linhas com colunas a mais entram num arquivo antigo em
    silêncio, cada valor debaixo da coluna errada — e o consumidor lê números
    plausíveis do lugar errado. É o risco que P19 registrou quando
    `execucoes.csv` ganhou três colunas, e que a P20 repetiria em
    `conflitos_por_execucao.csv`.

    Raises:
        CabecalhoDivergenteError: se o arquivo existe e o cabeçalho difere.
    """
    existente = cabecalho_do_csv(destino)
    if existente is not None and existente != list(cabecalho):
        faltam = [coluna for coluna in cabecalho if coluna not in existente]
        sobram = [coluna for coluna in existente if coluna not in cabecalho]
        raise CabecalhoDivergenteError(
            f"{destino}: o cabeçalho existente difere do novo "
            f"(novas: {faltam or '-'}; só no existente: {sobram or '-'}). "
            "Grave numa pasta nova (--saida) em vez de misturar os formatos."
        )


def _anexar(destino: Path, cabecalho: Sequence[str], linhas: Sequence[Sequence[object]]) -> None:
    """Acrescenta linhas a um CSV, criando o cabeçalho se o arquivo for novo.

    Raises:
        CabecalhoDivergenteError: se o arquivo existe com outro cabeçalho.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    exigir_mesmo_cabecalho(destino, cabecalho)
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
            "aquecimento_s",
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
            "eventos_conflito",
            "eventos_conflito_decidiveis",
            "passos_em_conflito",
        ),
        [
            [
                *ponto,
                versao_codigo,
                f"{resultado.duracao_s:.0f}",
                f"{resultado.aquecimento_s:.0f}",
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
                resultado.eventos_conflito,
                resultado.eventos_conflito_decidiveis,
                resultado.passos_em_conflito,
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

    _anexar(
        diretorio / ARQUIVO_CONFLITOS,
        (
            "id_execucao",
            "cenario",
            "modo",
            "seed",
            "t_inicio_s",
            "t_fim_s",
            "duracao_s",
            "passos",
            "id_semaforo",
            "n_ves",
            "ids_veiculos",
            "tipos",
            "criticidades",
            "etas_s",
            "fases_desejadas",
            "mesmo_nivel",
            "decidivel",
            "decidivel_em_algum_passo",
            "preempcao_em_curso",
            "decidida_pelo_modelo",
            "modelo_divergiu_do_e8",
        ),
        [
            [
                *ponto,
                f"{episodio.t_inicio_s:.1f}",
                f"{episodio.t_fim_s:.1f}",
                f"{episodio.duracao_s:.1f}",
                episodio.passos,
                episodio.id_semaforo,
                episodio.n_ves,
                "|".join(episodio.ids_veiculos),
                "|".join(episodio.tipos),
                "|".join(str(nivel) for nivel in episodio.criticidades),
                "|".join(f"{eta:.1f}" for eta in episodio.etas_s),
                "|".join(str(fase) for fase in episodio.fases_desejadas),
                int(episodio.mesmo_nivel),
                int(episodio.decidivel),
                int(episodio.decidivel_em_algum_passo),
                episodio.preempcao_em_curso or "",
                int(episodio.decidida_pelo_modelo),
                int(episodio.modelo_divergiu_do_e8),
            ]
            for episodio in resultado.conflitos
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
