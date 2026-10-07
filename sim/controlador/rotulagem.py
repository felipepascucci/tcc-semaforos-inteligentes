r"""Rotulagem por bifurcação da simulação — entrega 10.4 (P19).

    python -m sim.controlador.rotulagem --seeds 201..250 --paralelo 6 \
        --saida analysis/data/bloco10_rotulos

Para cada disputa entre dois VEs de **mesmo nível** de criticidade, decidível
(sem preempção em curso), a simulação é bifurcada no instante em que a disputa
abre, e cada escolha é rodada até os dois VEs saírem da malha. O rótulo é a
escolha com o melhor **minimax**: o menor tempo de travessia do VE mais
prejudicado (P19, decidido em 2026-09-10).

COMO A BIFURCAÇÃO É FEITA, E POR QUÊ

Primeiro roda a trajetória principal: o braço `PREEMPCAO` de sempre, pelo
executor, com o E8 determinístico. Os episódios de conflito que ela registra
dizem onde e quando cada disputa abriu.

Para cada disputa elegível saem dois ramos, **A** (o primeiro VE, em ordem de id,
vence) e **B** (o segundo vence). Cada ramo sobe um SUMO novo com a mesma seed e
**reexecuta do zero**, com o mesmo código da principal, até o passo em que a
disputa abre; só ali a escolha é instalada. Como a simulação é determinística
(mesma seed, mesmo resultado — `CLAUDE.md`), o ramo chega à disputa no mesmo
estado em que a principal chegou, e a única diferença entre A e B é a escolha.

A reexecução substituiu o `saveState`/`loadState` previsto em P19 (decisão da
equipe, 2026-10-05). Medido no mesmo dia: o SUMO grava o estado do modelo de
troca de faixa arredondado, e a trajetória carregada do arquivo desviou até
0,3 s da original. A reexecução é exata por construção, e cada rótulo carrega a
prova: `replay_fiel` diz se os dois ramos encontraram a disputa no mesmo passo e
com os mesmos ETAs da principal.

O QUE O RAMO FORÇA, E O QUE NÃO

O ramo força **só a disputa bifurcada**: enquanto os dois VEs disputarem aquele
cruzamento, vence o escolhido. Daí em diante, inclusive num segundo encontro
adiante, decide o E8 determinístico (decisão da equipe, 2026-10-05). O rótulo
responde, portanto, "qual escolha é melhor agora, se o resto seguir a regra
atual" — que é a pergunta de H4: substituir o E8 numa decisão.

Empate no minimax fica fora do treino e é contado (`EMPATE`). Ramo que bate no
teto de `HORIZONTE_S` sem os dois VEs chegarem, que registra colisão, teleporte
ou violação de invariante, ou cuja reexecução não reencontra a disputa, descarta
a disputa (`DESCARTADA`), com o motivo.

A travessia é `chegada - partida`, com a chegada no passo em que o SUMO tira o
VE da malha. Fica 0,1 s acima da duração do `tripinfo`, igual em todos os ramos.
"""

from __future__ import annotations

import argparse
import csv
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from adapters.configuracao import carregar as carregar_parametros
from adapters.sumo import topologia as topologia_sumo
from adapters.sumo.adaptador import AdaptadorSumo
from adapters.sumo.cliente import abrir_cliente
from adapters.sumo.topologia import MalhaSumo
from adapters.terminal import saida_utf8
from core.modelos import EstadoMalha
from core.parametros import Parametros
from core.priorizacao.atributos import AtributosVE, atributos_do_ve
from core.priorizacao.conflito import Disputa, EventoConflito, resolver
from core.priorizacao.motor import MotorDecisao
from core.seguranca import VerificadorSeguranca
from sim.calibracao import cenarios as calibracao
from sim.controlador import executor, lote
from sim.controlador.coletor import (
    ColetorMetricas,
    EpisodioConflito,
    cabecalho_do_csv,
    exigir_mesmo_cabecalho,
)
from sim.demanda import gerar_rotas
from sim.validacao.execucao import validar_execucao

#: A trajetória principal é o baseline de H4: o E8 determinístico.
MODO = "PREEMPCAO"

CENARIO_PADRAO = "treino_multiplas"

#: Teto de tempo simulado de um ramo, contado da abertura da disputa. O corredor
#: inteiro leva ~250 s; 900 s só é atingido se algo travar (decisão de 2026-10-05).
HORIZONTE_S = 900.0

ARQUIVO_ROTULOS = "rotulos.csv"

#: Onde cada seed roda. Uma pasta por seed, porque os processos são paralelos.
SAIDA = executor.SAIDA / "rotulagem"

#: Valores da coluna `rotulo`. A e B são os VEs em ordem de id.
A = "A"
B = "B"
EMPATE = "EMPATE"
DESCARTADA = "DESCARTADA"

COLUNAS = (
    "cenario",
    "seed",
    "versao_codigo",
    "t_s",
    "id_semaforo",
    "ve_a",
    "ve_b",
    "tipo_a",
    "tipo_b",
    "criticidade",
    "partida_a_s",
    "partida_b_s",
    "eta_a_s",
    "eta_b_s",
    "velocidade_a_ms",
    "velocidade_b_ms",
    "fila_acesso_a",
    "fila_acesso_b",
    "fila_faixa_a",
    "fila_faixa_b",
    "cruzamentos_restantes_a",
    "cruzamentos_restantes_b",
    "escolha_e8",
    "travessia_a_se_a_s",
    "travessia_b_se_a_s",
    "travessia_a_se_b_s",
    "travessia_b_se_b_s",
    "minimax_se_a_s",
    "minimax_se_b_s",
    "replay_fiel",
    "rotulo",
    "motivo_descarte",
)


# ---------------------------------------------------------------------------
# A escolha forçada e o rótulo — puros, testáveis sem SUMO
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EscolhaForcada:
    """`PoliticaDesempate` de um ramo: `vencedor` ganha de `outro` em `id_semaforo`.

    Vale enquanto os dois disputarem aquele cruzamento. Em qualquer outra
    disputa devolve `None`, e decide o E8.
    """

    id_semaforo: str
    vencedor: str
    outro: str

    def escolher(
        self, id_semaforo: str, disputas: Sequence[Disputa], estado: EstadoMalha
    ) -> Disputa | None:
        """O pedido de `vencedor`, se a disputa for a forçada."""
        del estado
        if id_semaforo != self.id_semaforo:
            return None
        por_id = {disputa.deteccao.id_veiculo: disputa for disputa in disputas}
        if self.vencedor in por_id and self.outro in por_id:
            return por_id[self.vencedor]
        return None


def minimax(travessias: Sequence[float | None]) -> float | None:
    """O tempo do VE mais prejudicado, ou `None` se algum não chegou."""
    if any(travessia is None for travessia in travessias):
        return None
    return max(travessia for travessia in travessias if travessia is not None)


def decidir_rotulo(minimax_se_a: float | None, minimax_se_b: float | None) -> str:
    """Qual escolha dá o melhor minimax.

    Os instantes vêm em passos de 0,1 s; a comparação arredonda ao passo para
    que um resíduo de ponto flutuante não desfaça um empate.
    """
    if minimax_se_a is None or minimax_se_b is None:
        return DESCARTADA
    se_a, se_b = round(minimax_se_a, 1), round(minimax_se_b, 1)
    if se_a < se_b:
        return A
    if se_b < se_a:
        return B
    return EMPATE


def elegivel(episodio: EpisodioConflito) -> bool:
    """Se a disputa é do domínio do modelo: dois VEs, mesmo nível, decidível (P19, P20)."""
    return (
        episodio.decidivel
        and len(episodio.ids_veiculos) == 2
        and len(set(episodio.criticidades)) == 1
    )


# ---------------------------------------------------------------------------
# Um ramo
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Contexto:
    """O que não muda entre os ramos de uma seed."""

    cenario: str
    seed: int
    malha: MalhaSumo
    parametros: Parametros
    rotas: Path
    pasta_ramo: Path
    passo_s: float
    horizonte_s: float


@dataclass(frozen=True)
class ResultadoRamo:
    """O que um ramo da bifurcação mediu.

    Attributes:
        evento: A disputa como o ramo a reencontrou, ou `None` se a reexecução
            não a reencontrou no passo esperado.
        atributos: Os atributos de cada VE nesse instante.
        partidas_s: Instante de partida de cada VE da disputa.
        chegadas_s: Instante de chegada de cada VE da disputa que chegou.
        colisoes: Colisões no ramo.
        teleportes: Teleportes no ramo.
        violacoes: Violações de invariante no ramo.
    """

    evento: EventoConflito | None
    atributos: Mapping[str, AtributosVE] = field(default_factory=dict)
    partidas_s: Mapping[str, float] = field(default_factory=dict)
    chegadas_s: Mapping[str, float] = field(default_factory=dict)
    colisoes: int = 0
    teleportes: int = 0
    violacoes: int = 0

    @property
    def incidente(self) -> str | None:
        """Descrição do primeiro incidente que invalida o ramo, se houver."""
        if self.colisoes:
            return f"{self.colisoes} colisão(ões)"
        if self.teleportes:
            return f"{self.teleportes} teleporte(s)"
        if self.violacoes:
            return f"{self.violacoes} violação(ões) de invariante"
        return None


def _mesmo_passo(t: float, alvo: float, passo_s: float) -> bool:
    return abs(t - alvo) < passo_s / 2


def _reencontrar(
    coletor: ColetorMetricas, eventos: Sequence[EventoConflito], episodio: EpisodioConflito
) -> EventoConflito | None:
    """A disputa do episódio entre os conflitos deste passo, se ela abre aqui."""
    for evento in eventos:
        if (
            evento.id_semaforo == episodio.id_semaforo
            and evento.ids_veiculos == episodio.ids_veiculos
            and evento.decidivel
            and coletor.abriria_episodio(evento)
        ):
            return evento
    return None


def rodar_ramo(contexto: Contexto, episodio: EpisodioConflito, forcado: str) -> ResultadoRamo:
    """Reexecuta a seed do zero e força `forcado` na disputa do episódio.

    Até o passo em que a disputa abre, o ramo é a trajetória principal
    reexecutada, com o mesmo código. Nesse passo, antes de o motor decidir, ele
    confere que a disputa está lá, lê os atributos e instala a escolha forçada.
    Daí roda até os dois VEs chegarem ou o teto de `horizonte_s` estourar.

    Args:
        contexto: O que não muda entre ramos.
        episodio: A disputa, como a principal a registrou.
        forcado: Quem vence a disputa neste ramo.

    Returns:
        O que o ramo mediu. `evento` fica `None` se a reexecução não reencontrou
        a disputa no passo esperado — o ramo não serve, e a disputa é descartada.
    """
    ids = episodio.ids_veiculos
    outro = ids[1] if forcado == ids[0] else ids[0]
    t0 = episodio.t_inicio_s
    limite = t0 + contexto.horizonte_s
    conflitos: list[EventoConflito] = []
    motor = MotorDecisao(
        parametros=contexto.parametros,
        topologia=contexto.malha.topologia,
        observador_conflito=conflitos.append,
    )
    verificador = VerificadorSeguranca(parametros=contexto.parametros)
    coletor = ColetorMetricas(
        cenario=contexto.cenario, modo=MODO, seed=contexto.seed, passo_s=contexto.passo_s
    )
    adaptador = AdaptadorSumo(
        cliente=abrir_cliente(), malha=contexto.malha, parametros=contexto.parametros
    )
    opcoes = executor.Opcoes(cenario=contexto.cenario, modo=MODO, seed=contexto.seed)
    adaptador.iniciar(
        executor.comando_sumo(opcoes, contexto.rotas, contexto.pasta_ramo, limite + 1.0)
    )

    evento: EventoConflito | None = None
    atributos: dict[str, AtributosVE] = {}
    partidas: dict[str, float] = {}
    chegadas: dict[str, float] = {}
    try:
        while adaptador.cliente.tempo() < limite - 1e-9:
            t = adaptador.passo()
            if evento is not None:
                for identificador in adaptador.cliente.simulacao.getArrivedIDList():
                    if identificador in ids:
                        chegadas[identificador] = t
                if len(chegadas) == len(ids):
                    break
            estado = adaptador.ler_estado(t)
            if evento is None and _mesmo_passo(t, t0, contexto.passo_s):
                evento = _reencontrar(coletor, motor.conflitos_em(estado), episodio)
                if evento is None:
                    break
                atributos = {
                    disputa.deteccao.id_veiculo: atributos_do_ve(
                        disputa, estado, contexto.malha.topologia
                    )
                    for disputa in evento.disputas
                }
                partidas = {
                    identificador: float(adaptador.cliente.veiculo.getDeparture(identificador))
                    for identificador in ids
                }
                motor.politica = EscolhaForcada(episodio.id_semaforo, forcado, outro)
            executor.decidir_e_aplicar(
                adaptador, motor, verificador, coletor, estado, True, conflitos
            )
    finally:
        adaptador.fechar()

    return ResultadoRamo(
        evento=evento,
        atributos=atributos,
        partidas_s=partidas,
        chegadas_s=chegadas,
        colisoes=coletor.colisoes,
        teleportes=coletor.teleportes,
        violacoes=len(coletor.violacoes),
    )


# ---------------------------------------------------------------------------
# Uma disputa
# ---------------------------------------------------------------------------


def _travessia(ramo: ResultadoRamo, identificador: str) -> float | None:
    chegada = ramo.chegadas_s.get(identificador)
    partida = ramo.partidas_s.get(identificador)
    if chegada is None or partida is None:
        return None
    return round(chegada - partida, 1)


def _vazio_se_none(valor: float | None) -> object:
    return "" if valor is None else valor


def replay_fiel(episodio: EpisodioConflito, ramos: Sequence[ResultadoRamo]) -> bool:
    """Se todos os ramos reencontraram a disputa igual à da principal.

    Igual quer dizer: no mesmo passo, com os mesmos VEs e **os mesmos ETAs**, sem
    tolerância. Com a reexecução determinística, qualquer diferença é defeito.
    """
    for ramo in ramos:
        if ramo.evento is None:
            return False
        por_id = {d.deteccao.id_veiculo: d.deteccao.eta_s for d in ramo.evento.disputas}
        if tuple(por_id[i] for i in episodio.ids_veiculos) != episodio.etas_s:
            return False
    return all(ramo.atributos == ramos[0].atributos for ramo in ramos)


def rotular_disputa(
    contexto: Contexto, episodio: EpisodioConflito, versao_codigo: str
) -> dict[str, object]:
    """Roda os dois ramos de uma disputa e monta a linha do rótulo."""
    ids = episodio.ids_veiculos
    ramo_a = rodar_ramo(contexto, episodio, ids[0])
    ramo_b = rodar_ramo(contexto, episodio, ids[1])
    fiel = replay_fiel(episodio, (ramo_a, ramo_b))

    travessias = {
        (nome, identificador): _travessia(ramo, identificador)
        for nome, ramo in ((A, ramo_a), (B, ramo_b))
        for identificador in ids
    }
    minimax_se_a = minimax([travessias[(A, identificador)] for identificador in ids])
    minimax_se_b = minimax([travessias[(B, identificador)] for identificador in ids])
    rotulo = decidir_rotulo(minimax_se_a, minimax_se_b)
    motivo = ""
    incidentes = [(nome, ramo.incidente) for nome, ramo in ((A, ramo_a), (B, ramo_b))]
    if not fiel:
        rotulo, motivo = DESCARTADA, "reexecução não reencontrou a disputa igual à principal"
    elif rotulo == DESCARTADA:
        motivo = f"VE sem chegar em {contexto.horizonte_s:.0f} s"
    elif any(incidente for _, incidente in incidentes):
        nome, incidente = next((n, i) for n, i in incidentes if i)
        rotulo, motivo = DESCARTADA, f"ramo {nome}: {incidente}"

    valores: dict[str, object] = {
        "cenario": contexto.cenario,
        "seed": contexto.seed,
        "versao_codigo": versao_codigo,
        "t_s": round(episodio.t_inicio_s, 1),
        "id_semaforo": episodio.id_semaforo,
        "ve_a": ids[0],
        "ve_b": ids[1],
        "tipo_a": episodio.tipos[0],
        "tipo_b": episodio.tipos[1],
        "criticidade": episodio.criticidades[0],
        "replay_fiel": int(fiel),
        "rotulo": rotulo,
        "motivo_descarte": motivo,
    }
    for coluna in COLUNAS:
        valores.setdefault(coluna, "")
    if ramo_a.evento is None:
        return valores

    resolucao = resolver(
        episodio.id_semaforo,
        list(ramo_a.evento.disputas),
        contexto.malha.topologia.cruzamento(episodio.id_semaforo),
        contexto.parametros,
    )
    vencedor_e8 = resolucao.vencedor.deteccao.id_veiculo if resolucao is not None else ""
    a, b = ramo_a.atributos[ids[0]], ramo_a.atributos[ids[1]]
    valores.update(
        {
            "partida_a_s": round(ramo_a.partidas_s[ids[0]], 2),
            "partida_b_s": round(ramo_a.partidas_s[ids[1]], 2),
            "eta_a_s": round(a.eta_s, 4),
            "eta_b_s": round(b.eta_s, 4),
            "velocidade_a_ms": round(a.velocidade_ms, 4),
            "velocidade_b_ms": round(b.velocidade_ms, 4),
            "fila_acesso_a": a.fila_no_acesso,
            "fila_acesso_b": b.fila_no_acesso,
            "fila_faixa_a": round(a.fila_por_faixa, 4),
            "fila_faixa_b": round(b.fila_por_faixa, 4),
            "cruzamentos_restantes_a": a.cruzamentos_restantes,
            "cruzamentos_restantes_b": b.cruzamentos_restantes,
            "escolha_e8": A if vencedor_e8 == ids[0] else B,
            "travessia_a_se_a_s": _vazio_se_none(travessias[(A, ids[0])]),
            "travessia_b_se_a_s": _vazio_se_none(travessias[(A, ids[1])]),
            "travessia_a_se_b_s": _vazio_se_none(travessias[(B, ids[0])]),
            "travessia_b_se_b_s": _vazio_se_none(travessias[(B, ids[1])]),
            "minimax_se_a_s": _vazio_se_none(minimax_se_a),
            "minimax_se_b_s": _vazio_se_none(minimax_se_b),
        }
    )
    return valores


# ---------------------------------------------------------------------------
# Uma seed
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultadoSeed:
    """O que o processo pai recebe de cada seed."""

    cenario: str
    seed: int
    segundos: float
    pasta: Path
    rotulos: Mapping[str, int] = field(default_factory=dict)
    problemas: tuple[str, ...] = ()
    erro: str | None = None

    @property
    def valida(self) -> bool:
        """Se a trajetória principal passou na validação e nada quebrou."""
        return self.erro is None and not self.problemas


def pasta_da_seed(cenario: str, seed: int) -> Path:
    """Pasta de trabalho de uma seed."""
    return SAIDA / f"{cenario}_{seed}"


def rotular_seed(
    cenario: str, seed: int, horizonte_s: float = HORIZONTE_S, duracao_s: float | None = None
) -> ResultadoSeed:
    """Roda a trajetória principal de uma seed e rotula as disputas elegíveis.

    Grava, na pasta da seed, `rotulos.csv` e os CSV de sempre da trajetória
    principal, que são os de um lote `PREEMPCAO` comum da mesma seed.

    Nunca levanta: uma seed que quebra volta com `erro` e não derruba as outras.
    """
    inicio = time.perf_counter()
    pasta = pasta_da_seed(cenario, seed)
    try:
        linhas, problemas = _rotular_seed(cenario, seed, pasta, horizonte_s, duracao_s)
    except Exception as erro:  # a seed entra como falha; as outras seguem
        return ResultadoSeed(
            cenario=cenario,
            seed=seed,
            segundos=time.perf_counter() - inicio,
            pasta=pasta,
            erro=f"{erro.__class__.__name__}: {erro}",
        )
    return ResultadoSeed(
        cenario=cenario,
        seed=seed,
        segundos=time.perf_counter() - inicio,
        pasta=pasta,
        rotulos=Counter(str(linha["rotulo"]) for linha in linhas),
        problemas=tuple(problemas),
    )


def _rotular_seed(
    cenario: str, seed: int, pasta: Path, horizonte_s: float, duracao_s: float | None
) -> tuple[list[dict[str, object]], list[str]]:
    configuracao = calibracao.carregar_configuracao()
    parametros = executor.parametros_do_modo(MODO, carregar_parametros("simulacao"))
    versao = executor.versao_do_codigo()

    for nome in (*lote.ARQUIVOS_CSV, ARQUIVO_ROTULOS):
        (pasta / nome).unlink(missing_ok=True)
    pasta_ramo = pasta / "ramo"
    pasta_ramo.mkdir(parents=True, exist_ok=True)

    principal = executor.executar(
        executor.Opcoes(
            cenario=cenario,
            modo=MODO,
            seed=seed,
            duracao_s=duracao_s,
            persistir=False,
            diretorio_csv=pasta,
        )
    )
    problemas = validar_execucao(principal, parametros, completa=duracao_s is None)

    contexto = Contexto(
        cenario=cenario,
        seed=seed,
        malha=topologia_sumo.carregar(),
        parametros=parametros,
        rotas=gerar_rotas.garantir(cenario, seed),
        pasta_ramo=pasta_ramo,
        passo_s=float(configuracao["execucao"]["passo_s"]),
        horizonte_s=horizonte_s,
    )
    linhas = [
        rotular_disputa(contexto, episodio, versao)
        for episodio in principal.conflitos
        if elegivel(episodio)
    ]
    with (pasta / ARQUIVO_ROTULOS).open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS)
        escritor.writeheader()
        escritor.writerows(linhas)
    return linhas, problemas


# ---------------------------------------------------------------------------
# O lote de seeds
# ---------------------------------------------------------------------------


def consolidar_rotulos(pastas: Sequence[Path], destino: Path) -> int:
    """Junta os `rotulos.csv` das seeds, na ordem dada, num só arquivo.

    Recusa destino que já exista: rótulos acrescentados a um arquivo antigo
    duplicariam disputas em silêncio, e no treino isso é peso dobrado.

    Raises:
        FileExistsError: se `destino/rotulos.csv` já existir.
        CabecalhoDivergenteError: se uma seed trouxer outras colunas.
    """
    alvo = destino / ARQUIVO_ROTULOS
    if alvo.exists():
        raise FileExistsError(f"{alvo} já existe; grave numa pasta nova")
    destino.mkdir(parents=True, exist_ok=True)
    parciais = [pasta / ARQUIVO_ROTULOS for pasta in pastas]
    for parcial in parciais:
        exigir_mesmo_cabecalho(parcial, list(COLUNAS))
    linhas = 0
    with alvo.open("w", encoding="utf-8", newline="") as saida:
        escritor = csv.writer(saida)
        escritor.writerow(COLUNAS)
        for parcial in parciais:
            with parcial.open(encoding="utf-8", newline="") as entrada:
                leitor = csv.reader(entrada)
                next(leitor)
                for linha in leitor:
                    escritor.writerow(linha)
                    linhas += 1
    return linhas


def rodar(
    cenario: str,
    seeds: Sequence[int],
    saida: Path,
    paralelo: int = 1,
    horizonte_s: float = HORIZONTE_S,
    duracao_s: float | None = None,
) -> list[ResultadoSeed]:
    """Rotula as seeds em paralelo e consolida em `saida`.

    As rotas são geradas em série antes de qualquer processo subir, pela mesma
    razão do lote: dois processos escrevendo o mesmo arquivo de rotas o
    truncariam.

    Raises:
        FileExistsError: se `saida` já tiver rótulos ou CSV de execução.
    """
    if (saida / ARQUIVO_ROTULOS).exists() or cabecalho_do_csv(saida / lote.ARQUIVOS_CSV[0]):
        raise FileExistsError(f"{saida} já tem dados; grave numa pasta nova")
    for seed in seeds:
        gerar_rotas.garantir(cenario, seed)

    resultados: dict[int, ResultadoSeed] = {}
    inicio = time.perf_counter()
    with ProcessPoolExecutor(max_workers=max(1, paralelo)) as piscina:
        futuros = [
            piscina.submit(rotular_seed, cenario, seed, horizonte_s, duracao_s) for seed in seeds
        ]
        for indice, futuro in enumerate(as_completed(futuros), start=1):
            resultado = futuro.result()
            resultados[resultado.seed] = resultado
            situacao = "ok" if resultado.valida else "FALHOU"
            print(
                f"  [{indice:3d}/{len(seeds)}] {cenario}/seed={resultado.seed:<5d} "
                f"{situacao:<7} {resultado.segundos / 60:5.1f} min · {dict(resultado.rotulos)}",
                flush=True,
            )

    ordenados = [resultados[seed] for seed in sorted(resultados)]
    validos = [resultado for resultado in ordenados if resultado.valida]
    pastas = [resultado.pasta for resultado in validos]
    if pastas:
        lote.consolidar(pastas, saida)
        consolidar_rotulos(pastas, saida)
    total = sum((Counter(resultado.rotulos) for resultado in validos), Counter())
    minutos = (time.perf_counter() - inicio) / 60
    print(f"\n=== rotulagem: {len(seeds)} seeds em {minutos:.1f} min ===")
    print(f"  válidas {len(validos)} · inválidas {len(ordenados) - len(validos)}")
    print(f"  rótulos {dict(total)}")
    for resultado in ordenados:
        if not resultado.valida:
            print(f"  seed {resultado.seed}: {resultado.erro or '; '.join(resultado.problemas)}")
    return ordenados


def main(argumentos: Sequence[str] | None = None) -> int:
    saida_utf8()
    analisador = argparse.ArgumentParser(
        description="Rotulagem por bifurcação da simulação (entrega 10.4, P19)."
    )
    analisador.add_argument("--cenario", default=CENARIO_PADRAO)
    analisador.add_argument("--seeds", required=True, help="ex.: 201..250")
    analisador.add_argument("--paralelo", type=int, default=1)
    analisador.add_argument("--saida", type=Path, required=True)
    analisador.add_argument("--horizonte", type=float, default=HORIZONTE_S)
    analisador.add_argument(
        "--duracao", type=float, default=None, help="duração da trajetória principal (teste)"
    )
    opcoes = analisador.parse_args(argumentos)
    resultados = rodar(
        opcoes.cenario,
        lote.analisar_seeds(opcoes.seeds),
        opcoes.saida,
        opcoes.paralelo,
        opcoes.horizonte,
        opcoes.duracao,
    )
    return 0 if all(resultado.valida for resultado in resultados) else 1


if __name__ == "__main__":
    raise SystemExit(main())
