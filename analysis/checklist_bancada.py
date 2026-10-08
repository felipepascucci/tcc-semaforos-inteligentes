"""Checklist da bancada a partir da telemetria gravada — `context/06` §6.

    python -m analysis.checklist_bancada                  # a última sessão da ponte
    python -m analysis.checklist_bancada --sessao <iso>   # uma sessão (repetível)
    python -m analysis.checklist_bancada --todas
    python -m analysis.checklist_bancada --banco          # mais o item 9, no PostgreSQL
    python -m analysis.checklist_bancada --item5          # mais o item 5 (tag fora do mapa)

Lê `analysis/data/telemetria_bancada.csv`, que a ponte grava com `--telemetria`
(`bridge/registro.py`): cada linha do USB do UNO, crua e carimbada no relógio do
notebook. Como a `ST` sai a cada mudança de estado, a sequência de `ST` de uma
sessão é a sequência completa das luzes, com o `millis()` de cada transição
(`context/05` §4.2). Daí saem, por sessão:

* **item 1** — o boot em all-red e os ciclos de 12 s, com o trecho mais longo de
  ciclo puro (precisa de 5 min);
* **item 2** — nenhuma `ST` com verde nos dois eixos, e em emergência nenhum verde
  novo fora da aproximação do VE, que chega ao verde exclusivo;
* **item 3** — I2, I3 e I4 em toda transição (`bridge.verificar.violacoes`), com a
  contagem das entradas e saídas de emergência cobertas;
* **item 5b** — cada `SEM_OCORRENCIA` deixou o semáforo como estava, e a primeira
  decisão do mesmo tipo depois de a Central abrir a ocorrência foi `PREEMP_INI`;
* **item 10** — cada interrupção (`PREEMP_INI` de um VE e `FILA` do atendido no
  mesmo instante): a criticidade de quem interrompeu é maior, e o interrompido é
  atendido depois;
* **item 11** — cada `TIMEOUT`: 30 s desde o `PREEMP_INI` que abriu a emergência,
  as renovações no meio, e a volta pelo eixo oposto;
* **item 12** — duração da sessão, reinícios do UNO no meio, e o maior silêncio
  entre duas `ST`;
* **item 14** — se a sessão terminou com o UNO em emergência (a ponte foi
  encerrada no meio de uma);
* **item 15** — a cada abertura da porta, o UNO volta negando todos, e quanto a
  lista da Central leva para voltar; com `--banco`, também qual era a lista da
  Central no BOOT, para separar "nada a reenviar" de "não voltou";
* **item 9**, com `--banco` — cada evento de decisão da sessão tem a sua linha em
  `log_prioridade`, com `id_correlacao`, e cada amostra de H3 em
  `metrica_latencia` tem o mesmo `id_correlacao` da linha do `PREEMP_INI`;
* **item 5**, com `--item5` — na sessão em que a tag fora do mapa passou, com o
  emissor no USB (`--porta-veiculo`): da ambulância autorizada até a passagem de
  controle numa tag do mapa, o emissor não imprimiu nada, o UNO não publicou
  evento e o ciclo seguiu puro; e o controle preemptou. Lê também
  `analysis/data/deteccoes_bancada.csv`.

O resto do checklist (6, 8, 13, quantas vezes a tag do item 5 passou, e o que o
LCD mostra em 5b e 10) é observação de quem está na bancada e não sai daqui.

As durações são conferidas no `millis()` do UNO, com a folga de
`bridge.verificar` (60 ms, uma volta do `loop()`); os intervalos entre a ponte e
o UNO, no relógio do notebook.
"""

from __future__ import annotations

import argparse
import csv
import os
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Any, Final

from adapters.terminal import saida_utf8
from bridge.latencia import CSV_DESFECHOS_PADRAO
from bridge.ponte import SILENCIO_MAXIMO_S
from bridge.protocolo import (
    EIXO_DE,
    EVENTOS_DE_DECISAO,
    NENHUMA_AUTORIZACAO,
    TIPOS_DA_BANCADA,
    Evento,
    LinhaInvalidaError,
    Regime,
    Telemetria,
    TipoEvento,
    interpretar,
)
from bridge.registro import CSV_TELEMETRIA_PADRAO, Direcao
from bridge.verificar import (
    ALL_RED_MS,
    CICLO_MS,
    FOLGA_MS,
    PRINCIPAL,
    TETO_MS,
    transicoes,
    violacoes,
)
from core.modelos import TipoVeiculo

#: Item 1: o ciclo roda sem travar por 5 min.
CICLO_CONTINUO_MS = 5 * 60 * 1000

#: Item 12: operação contínua de 30 min.
SESSAO_CONTINUA_S = 30 * 60

#: Item 15: a lista da Central volta em "até ~1 s" (`context/06` §6). O backend
#: lê a ponte a 5 Hz, mas, enquanto ela esteve fora, tenta só a cada 1 s, e
#: reenvia a lista no máximo uma vez por segundo (`app/services/bancada.py`). O
#: critério declarado antes da medição é este (`context/06` §6, 2026-10-07).
LISTA_VOLTA_MAX_S = 2.0

#: Item 5: as tags do mapa, como no cabeçalho de `veiculo_ambulancia.ino`. O
#: emissor só imprime (e só envia) estas; qualquer outro UID no CSV de
#: detecções seria a tag fora do mapa gerando envio.
UIDS_DO_MAPA: Final = {"F39BD606": 1, "1BD2308E": 2, "B7EF8FA0": 3, "97ABAFA0": 4}


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Linha:
    """Uma linha de `telemetria_bancada.csv`, já interpretada quando é do UNO."""

    t: datetime
    direcao: Direcao
    texto: str
    versao_codigo: str
    resposta: Telemetria | Evento | None = None

    @property
    def st(self) -> Telemetria | None:
        return self.resposta if isinstance(self.resposta, Telemetria) else None

    @property
    def ev(self) -> Evento | None:
        return self.resposta if isinstance(self.resposta, Evento) else None


def _interpretar(direcao: Direcao, texto: str) -> Telemetria | Evento | None:
    if direcao is not Direcao.UNO:
        return None
    try:
        return interpretar(texto.encode("ascii"))
    except (LinhaInvalidaError, UnicodeEncodeError):
        return None


def ler_sessoes(caminho: Path) -> dict[str, list[Linha]]:
    """As linhas de cada sessão, na ordem em que a ponte as gravou."""
    sessoes: dict[str, list[Linha]] = {}
    if not caminho.is_file():
        return sessoes
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        for registro in csv.DictReader(arquivo):
            direcao = Direcao(registro["direcao"])
            sessoes.setdefault(registro["sessao"], []).append(
                Linha(
                    t=datetime.fromisoformat(registro["t"]),
                    direcao=direcao,
                    texto=registro["linha"],
                    versao_codigo=registro["versao_codigo"],
                    resposta=_interpretar(direcao, registro["linha"]),
                )
            )
    return sessoes


@dataclass(frozen=True)
class LeituraEmissor:
    """Uma linha de `deteccoes_bancada.csv`: uma leitura que o emissor imprimiu."""

    t: datetime
    rua: int
    uid: str
    desfecho: str


def ler_leituras(caminho: Path) -> dict[str, list[LeituraEmissor]]:
    """As leituras do emissor de cada sessão; vazio se o arquivo não existir."""
    sessoes: dict[str, list[LeituraEmissor]] = {}
    if not caminho.is_file():
        return sessoes
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        for registro in csv.DictReader(arquivo):
            sessoes.setdefault(registro["sessao"], []).append(
                LeituraEmissor(
                    t=datetime.fromisoformat(registro["t_deteccao"]),
                    rua=int(registro["rua"]),
                    uid=registro["uid"],
                    desfecho=registro["desfecho"],
                )
            )
    return sessoes


# ---------------------------------------------------------------------------
# Trechos: um por arranque do UNO
# ---------------------------------------------------------------------------


@dataclass
class Trecho:
    """As linhas válidas do UNO entre um arranque e o seguinte.

    Dentro de um trecho o `millis()` só cresce. Um trecho começa num `BOOT`, ou
    no começo da sessão, ou quando o `millis()` volta para trás sem `BOOT`
    visto (reinício cuja primeira linha se perdeu).
    """

    comeca_no_boot: bool
    linhas: list[Linha] = field(default_factory=list)

    @property
    def sts(self) -> list[Telemetria]:
        return [linha.st for linha in self.linhas if linha.st is not None]

    def eventos(self, *tipos: TipoEvento) -> list[tuple[int, Evento]]:
        """`(índice em linhas, evento)`, só dos tipos pedidos (todos, sem tipos)."""
        return [
            (i, linha.ev)
            for i, linha in enumerate(self.linhas)
            if linha.ev is not None and (not tipos or linha.ev.tipo in tipos)
        ]

    def st_antes(self, indice: int) -> Telemetria | None:
        """A última `ST` antes da linha `indice`: o estado em que o evento chegou."""
        return next(
            (linha.st for linha in reversed(self.linhas[:indice]) if linha.st is not None), None
        )

    def st_depois(self, indice: int) -> Telemetria | None:
        return next((linha.st for linha in self.linhas[indice + 1 :] if linha.st is not None), None)


def _ms(linha: Linha) -> int:
    assert linha.resposta is not None
    return linha.resposta.t_dispositivo_ms


def trechos(linhas: Sequence[Linha]) -> list[Trecho]:
    """Separa as linhas válidas do UNO em trechos, um por arranque."""
    saida: list[Trecho] = []
    for linha in linhas:
        if linha.resposta is None:
            continue
        boot = linha.ev is not None and linha.ev.tipo is TipoEvento.BOOT
        voltou = bool(saida) and bool(saida[-1].linhas) and _ms(linha) < _ms(saida[-1].linhas[-1])
        if not saida or boot or voltou:
            saida.append(Trecho(comeca_no_boot=boot))
        saida[-1].linhas.append(linha)
    return saida


# ---------------------------------------------------------------------------
# Resultado de um item
# ---------------------------------------------------------------------------


@dataclass
class Resultado:
    """O que o dado diz de um item: `ok` é `None` quando não há como julgar."""

    item: str
    titulo: str
    ok: bool | None
    detalhes: list[str] = field(default_factory=list)


def _veredito(ok: bool | None) -> str:
    return {True: "**atende**", False: "**não atende**", None: "sem veredito"}[ok]


def _exclusivo(rua: int) -> str:
    return "".join("G" if i == rua - 1 else "R" for i in range(len(EIXO_DE)))


def _perto(valor: int, esperado: int) -> bool:
    return abs(valor - esperado) <= FOLGA_MS


def _aberturas(sts: Sequence[Telemetria], estado: str) -> list[int]:
    """Índices das `ST` em que `estado` acende (não conta a primeira `ST`)."""
    return [i for i in range(1, len(sts)) if sts[i].estado == estado != sts[i - 1].estado]


def _ciclos(sts: Sequence[Telemetria]) -> list[tuple[int, int, int]]:
    """`(i_inicio, i_fim, período ms)` entre aberturas seguidas do eixo principal.

    Só os ciclos puros: toda `ST` entre as duas aberturas em regime de ciclo.
    """
    saida = []
    for a, b in pairwise(_aberturas(sts, PRINCIPAL)):
        if all(st.regime is Regime.CICLO for st in sts[a : b + 1]):
            saida.append((a, b, sts[b].t_dispositivo_ms - sts[a].t_dispositivo_ms))
    return saida


def _maior_trecho_de_ciclo(ciclos: Sequence[tuple[int, int, int]]) -> int:
    """Soma dos períodos da maior sequência de ciclos puros, emendados e no tempo."""
    melhor = atual = 0
    fim_anterior: int | None = None
    for inicio, fim, periodo in ciclos:
        if not _perto(periodo, CICLO_MS):
            atual, fim_anterior = 0, None
            continue
        atual = atual + periodo if inicio == fim_anterior else periodo
        fim_anterior = fim
        melhor = max(melhor, atual)
    return melhor


# ---------------------------------------------------------------------------
# Itens
# ---------------------------------------------------------------------------


def item_1(partes: Sequence[Trecho]) -> Resultado:
    resultado = Resultado("1", "Ciclo de 12 s, sem travar por 5 min; liga em all-red", None)
    oks: list[bool] = []
    for n, trecho in enumerate(partes, 1):
        sts = trecho.sts
        if not trecho.comeca_no_boot or not sts:
            continue
        abertura = next((st for st in sts if "G" in st.estado), None)
        boot_ok = (
            sts[0].estado == "RRRR"
            and abertura is not None
            and abertura.estado == PRINCIPAL
            and abertura.t_dispositivo_ms >= ALL_RED_MS - FOLGA_MS
        )
        oks.append(boot_ok)
        resultado.detalhes.append(
            f"Arranque {n}: primeira ST {sts[0].estado}; primeiro verde "
            + (
                "—"
                if abertura is None
                else f"{abertura.estado} em {abertura.t_dispositivo_ms} ms do millis()"
            )
            + f" — {'ok' if boot_ok else 'FALHA'}"
        )
    ciclos = [c for trecho in partes for c in _ciclos(trecho.sts)]
    periodos = [periodo for _, _, periodo in ciclos]
    fora = [p for p in periodos if not _perto(p, CICLO_MS)]
    maior = max((_maior_trecho_de_ciclo(_ciclos(trecho.sts)) for trecho in partes), default=0)
    if periodos:
        resultado.detalhes.append(
            f"Ciclos puros: {len(periodos)}; período mín {min(periodos)} ms, "
            f"máx {max(periodos)} ms (esperado {CICLO_MS} ± {FOLGA_MS} ms); "
            f"fora da tolerância: {len(fora)}"
        )
    resultado.detalhes.append(
        f"Maior trecho contínuo de ciclo dentro da tolerância: {maior / 1000:.1f} s "
        f"(precisa de {CICLO_CONTINUO_MS / 1000:.0f} s)"
    )
    if fora or not all(oks):
        resultado.ok = False
    elif maior >= CICLO_CONTINUO_MS:
        resultado.ok = True
    elif periodos:
        # Nenhuma falha, mas a sessão não teve ciclo bastante para julgar.
        resultado.detalhes.append("Sessão sem 5 min de ciclo puro: nada a julgar no trecho.")
    return resultado


def item_2(partes: Sequence[Trecho]) -> Resultado:
    resultado = Resultado(
        "2", "Nunca verde nos dois eixos; em emergência só a aproximação do VE abre", None
    )
    total = sum(len(trecho.sts) for trecho in partes)
    if not total:
        return resultado
    i1 = sum(1 for trecho in partes for st in trecho.sts if st.viola_i1)
    verdes_fora: list[str] = []
    episodios = interrompidos = sem_exclusivo = 0
    for trecho in partes:
        sts = trecho.sts
        for antes, depois in pairwise(sts):
            if depois.regime is not Regime.EMERGENCIA:
                continue
            for i, (a, d) in enumerate(zip(antes.estado, depois.estado, strict=True)):
                if d == "G" != a and depois.rua_ativa != i + 1:
                    verdes_fora.append(
                        f"S{i + 1} abriu em {depois.t_dispositivo_ms} ms com a rua ativa "
                        f"{depois.rua_ativa}"
                    )
        for indice, evento in trecho.eventos(TipoEvento.PREEMP_INI):
            fim = _fim_do_episodio(trecho, indice, evento)
            fim_ms = None if fim is None else fim[1].t_dispositivo_ms
            if fim is not None and fim[1].tipo is TipoEvento.FILA:
                interrompidos += 1
                continue
            episodios += 1
            assert evento.rua is not None
            alvo = _exclusivo(evento.rua)
            if not any(
                linha.st is not None
                and linha.st.estado == alvo
                and (fim_ms is None or linha.st.t_dispositivo_ms <= fim_ms)
                for linha in trecho.linhas[indice:]
            ):
                sem_exclusivo += 1
    resultado.detalhes += [
        f"ST na sessão: {total}; com verde nos dois eixos (I1): {i1}",
        f"Verdes novos em emergência fora da aproximação do VE: {len(verdes_fora)}"
        + ("" if not verdes_fora else " — " + "; ".join(verdes_fora[:3])),
        f"Emergências atendidas até o fim: {episodios}; sem verde exclusivo: {sem_exclusivo}"
        + (
            f" (mais {interrompidos} interrompida(s) por VE mais crítico, que volta(m) pela fila)"
            if interrompidos
            else ""
        ),
    ]
    resultado.ok = i1 == 0 and not verdes_fora and sem_exclusivo == 0
    return resultado


def _fim_do_episodio(trecho: Trecho, indice: int, inicio: Evento) -> tuple[int, Evento] | None:
    """O `PREEMP_FIM` ou o `FILA` do mesmo VE que encerra o atendimento dele."""
    ve = (inicio.rua, inicio.veiculo)
    for j, evento in trecho.eventos(TipoEvento.PREEMP_FIM, TipoEvento.FILA):
        if j > indice and (evento.rua, evento.veiculo) == ve:
            return j, evento
    return None


def item_3(partes: Sequence[Trecho]) -> Resultado:
    resultado = Resultado(
        "3",
        "Verde → amarelo → vermelho, e all-red antes de todo verde, inclusive na emergência",
        None,
    )
    achados: list[str] = []
    n_transicoes = entradas = saidas = 0
    contagem: Counter[str] = Counter()
    for trecho in partes:
        sts = trecho.sts
        sequencia = [(st.t_dispositivo_ms, st.estado) for st in sts]
        achados += violacoes(sequencia, folga_ms=FOLGA_MS)
        passos = transicoes(sequencia)
        n_transicoes += len(passos) - 1 if passos else 0
        for (_, luz_antes), (_, luz_depois) in pairwise(passos):
            for a, d in zip(luz_antes, luz_depois, strict=True):
                if a != d:
                    contagem[f"{a}→{d}"] += 1
        for antes, depois in pairwise(sts):
            if antes.regime is Regime.CICLO and depois.regime is Regime.EMERGENCIA:
                entradas += 1
            if antes.regime is Regime.EMERGENCIA and depois.regime is Regime.CICLO:
                saidas += 1
    if not n_transicoes:
        return resultado
    resultado.detalhes += [
        f"Mudanças de luz conferidas: {n_transicoes} "
        f"({', '.join(f'{k} {v}' for k, v in sorted(contagem.items()))})",
        f"Entradas em emergência: {entradas}; saídas: {saidas}",
        f"Violações de I2, I3 ou I4: {len(achados)}"
        + ("" if not achados else " — " + "; ".join(achados[:5])),
    ]
    resultado.ok = not achados if entradas and saidas else None
    if not (entradas and saidas):
        resultado.detalhes.append(
            "Sem entrada e saída de emergência na sessão: falta metade do item."
        )
    return resultado


def item_5(partes: Sequence[Trecho], leituras: Sequence[LeituraEmissor]) -> Resultado:
    """Tag fora do mapa: da ambulância autorizada à passagem de controle, nada.

    A tag fora do mapa não deixa rastro por construção (o emissor não imprime nem
    envia), então o que o dado mostra é o silêncio na janela em que ela passou. A
    passagem de controle no fim, numa tag do mapa, prova que a cadeia estava viva
    e que um envio teria preemptado. Quantas vezes a tag passou é observação.
    """
    resultado = Resultado("5", "Tag fora das 4 ruas: sem envio e sem mexer no semáforo", None)
    fora_do_mapa = [leitura for leitura in leituras if leitura.uid not in UIDS_DO_MAPA]
    if fora_do_mapa:
        resultado.ok = False
        resultado.detalhes.append(
            "O emissor imprimiu UID fora do mapa: "
            + "; ".join(f"{leitura.uid} ({leitura.t.isoformat()})" for leitura in fora_do_mapa)
        )
        return resultado
    validas = [linha for trecho in partes for linha in trecho.linhas]
    amb = TipoVeiculo.AMBULANCIA
    i0 = next(
        (
            i
            for i, linha in enumerate(validas)
            if linha.st is not None and linha.st.criticidade(amb)
        ),
        None,
    )
    if i0 is None:
        resultado.detalhes.append(
            "A ambulância não teve ocorrência na sessão: um envio não mexeria no semáforo."
        )
        return resultado
    t0 = validas[i0].t
    controle = next((leitura for leitura in leituras if leitura.t >= t0), None)
    if controle is None:
        resultado.detalhes.append(
            "Sem passagem de controle numa tag do mapa depois de a ambulância ter ocorrência."
        )
        return resultado
    janela = [linha for linha in validas[i0:] if linha.t < controle.t]
    sts = [linha.st for linha in janela if linha.st is not None]
    eventos = [linha for linha in janela if linha.ev is not None]
    fora_do_ciclo = sum(1 for st in sts if st.regime is not Regime.CICLO)
    sem_ocorrencia = sum(1 for st in sts if not st.criticidade(amb))
    periodos = [periodo for _, _, periodo in _ciclos(sts)]
    fora_da_tolerancia = [p for p in periodos if not _perto(p, CICLO_MS)]
    controle_ok = controle.desfecho == TipoEvento.PREEMP_INI.value
    duracao_s = (controle.t - t0).total_seconds()
    resultado.detalhes += [
        f"Janela: da primeira ST com a ambulância em ocorrência ({t0.isoformat()}) até a "
        f"passagem de controle ({controle.t.isoformat()}): {duracao_s:.1f} s",
        "Leituras do emissor na janela: 0 (a primeira depois da ocorrência é o controle)",
        f"Eventos do UNO na janela: {len(eventos)}"
        + ("" if not eventos else " — " + "; ".join(linha.texto for linha in eventos[:5])),
        f"ST na janela: {len(sts)}; fora do regime de ciclo: {fora_do_ciclo}; "
        f"com a ambulância sem ocorrência: {sem_ocorrencia}",
        f"Ciclos puros inteiros na janela: {len(periodos)}"
        + (
            f"; período mín {min(periodos)} ms, máx {max(periodos)} ms "
            f"(esperado {CICLO_MS} ± {FOLGA_MS} ms)"
            if periodos
            else ""
        ),
        f"Controle: {controle.uid} (RUA{controle.rua}) → {controle.desfecho} — "
        f"{'ok' if controle_ok else 'FALHA'}",
        "Quantas vezes a tag fora do mapa passou na janela é observação de quem está na bancada.",
    ]
    if eventos or fora_do_ciclo or fora_da_tolerancia:
        resultado.ok = False
    elif sem_ocorrencia or not periodos:
        # Sem falha, mas a janela não serve: um envio não preemptaria, ou ela não
        # cobre um ciclo inteiro para medir.
        resultado.detalhes.append(
            "Janela sem ocorrência o tempo todo ou sem um ciclo inteiro: nada a julgar."
        )
    else:
        resultado.ok = controle_ok
    return resultado


def item_5b(partes: Sequence[Trecho]) -> Resultado:
    resultado = Resultado("5b", "Tag sem ocorrência: SEM_OCORRENCIA, sem mexer no semáforo", None)
    oks: list[bool] = []
    preemptou_depois: list[bool] = []
    for trecho in partes:
        sts = trecho.sts
        aberturas = _aberturas(sts, PRINCIPAL)
        for indice, evento in trecho.eventos(TipoEvento.SEM_OCORRENCIA):
            assert evento.veiculo is not None
            antes, depois = trecho.st_antes(indice), trecho.st_depois(indice)
            if antes is None or depois is None:
                continue
            igual = (antes.regime, antes.rua_ativa, antes.rua_fila) == (
                depois.regime,
                depois.rua_ativa,
                depois.rua_fila,
            )
            sem_ocorrencia = antes.criticidade(evento.veiculo) == 0
            ciclo = "durante emergência"
            ciclo_ok = True
            if antes.regime is Regime.CICLO:
                ms = evento.t_dispositivo_ms
                volta = next(
                    (
                        (a, b)
                        for a, b in pairwise(aberturas)
                        if sts[a].t_dispositivo_ms <= ms < sts[b].t_dispositivo_ms
                    ),
                    None,
                )
                if volta is None:
                    ciclo, ciclo_ok = "ciclo incompleto na sessão", True
                else:
                    a, b = volta
                    periodo = sts[b].t_dispositivo_ms - sts[a].t_dispositivo_ms
                    puro = all(st.regime is Regime.CICLO for st in sts[a : b + 1])
                    ciclo_ok = puro and _perto(periodo, CICLO_MS)
                    ciclo = (
                        f"o ciclo que a contém durou {periodo} ms, "
                        f"{'só' if puro else 'nem só'} em ciclo"
                    )
            ok = igual and sem_ocorrencia and ciclo_ok
            oks.append(ok)
            seguinte = _decisao_depois_da_abertura(trecho, indice, evento.veiculo)
            if seguinte is not None:
                preemptou_depois.append(seguinte.tipo is TipoEvento.PREEMP_INI)
            resultado.detalhes.append(
                f"{evento.veiculo.value} na RUA{evento.rua} em {evento.t_dispositivo_ms} ms: "
                f"criticidade na ST {antes.criticidade(evento.veiculo)}; estado antes/depois "
                f"{'igual' if igual else 'DIFERENTE'}; {ciclo}; decisão seguinte depois de a "
                f"Central abrir a ocorrência: {'—' if seguinte is None else seguinte.tipo.value}"
                f" — {'ok' if ok else 'FALHA'}"
            )
    if oks:
        resultado.ok = all(oks) and any(preemptou_depois)
        if not preemptou_depois:
            resultado.detalhes.append(
                "Falta a passagem depois de abrir a ocorrência (a segunda metade do item)."
            )
    return resultado


def _decisao_depois_da_abertura(trecho: Trecho, indice: int, veiculo: TipoVeiculo) -> Evento | None:
    """A primeira decisão do tipo depois de a lista do UNO lhe dar ocorrência."""
    abriu = next(
        (
            j
            for j in range(indice + 1, len(trecho.linhas))
            if (st := trecho.linhas[j].st) is not None and st.criticidade(veiculo) > 0
        ),
        None,
    )
    if abriu is None:
        return None
    return next(
        (
            evento
            for j, evento in trecho.eventos(*EVENTOS_DE_DECISAO)
            if j > abriu and evento.veiculo is veiculo
        ),
        None,
    )


def item_10(partes: Sequence[Trecho]) -> Resultado:
    resultado = Resultado(
        "10",
        "Prioridade pela criticidade: o mais crítico interrompe, o outro vai para a fila",
        None,
    )
    oks: list[bool] = []
    for trecho in partes:
        inicios = trecho.eventos(TipoEvento.PREEMP_INI)
        for indice, fila in trecho.eventos(TipoEvento.FILA):
            novo = next(
                (
                    (j, ev)
                    for j, ev in inicios
                    if _perto(ev.t_dispositivo_ms, fila.t_dispositivo_ms)
                    and j < indice
                    and (ev.rua, ev.veiculo) != (fila.rua, fila.veiculo)
                ),
                None,
            )
            if novo is None:
                continue  # FILA sem interrupção: o VE chegou durante outra emergência
            j_novo, ev_novo = novo
            assert ev_novo.veiculo is not None and fila.veiculo is not None
            # A criticidade vai com o VE lido: a do interrompido é a do seu PREEMP_INI.
            j_antigo = next(
                (
                    j
                    for j, ev in reversed(inicios)
                    if j < j_novo and (ev.rua, ev.veiculo) == (fila.rua, fila.veiculo)
                ),
                None,
            )
            st_novo = trecho.st_antes(j_novo)
            st_antigo = None if j_antigo is None else trecho.st_antes(j_antigo)
            c_novo = None if st_novo is None else st_novo.criticidade(ev_novo.veiculo)
            c_antigo = None if st_antigo is None else st_antigo.criticidade(fila.veiculo)
            fim_novo = _fim_do_episodio(trecho, j_novo, ev_novo)
            retomada = None
            if fim_novo is not None and fim_novo[1].tipo is TipoEvento.PREEMP_FIM:
                retomada = next(
                    (
                        ev
                        for j, ev in inicios
                        if j > fim_novo[0] and (ev.rua, ev.veiculo) == (fila.rua, fila.veiculo)
                    ),
                    None,
                )
            ok = (
                c_novo is not None
                and c_antigo is not None
                and 0 < c_novo < c_antigo
                and retomada is not None
                and fim_novo is not None
                and _perto(retomada.t_dispositivo_ms, fim_novo[1].t_dispositivo_ms)
            )
            oks.append(ok)
            resultado.detalhes.append(
                f"{ev_novo.veiculo.value} (criticidade {c_novo}) na RUA{ev_novo.rua} interrompeu "
                f"{fila.veiculo.value} (criticidade {c_antigo}) na RUA{fila.rua} em "
                f"{fila.t_dispositivo_ms} ms; o interrompido "
                + (
                    "não foi retomado"
                    if retomada is None or fim_novo is None
                    else f"foi atendido no PREEMP_FIM do outro, "
                    f"{(retomada.t_dispositivo_ms - fila.t_dispositivo_ms) / 1000:.1f} s depois"
                )
                + f" — {'ok' if ok else 'FALHA'}"
            )
    if oks:
        resultado.ok = all(oks)
        resultado.detalhes.append(
            "O amarelo e o all-red da interrupção estão no item 3; o `Fila:…` do LCD é observação."
        )
    return resultado


def item_11(partes: Sequence[Trecho]) -> Resultado:
    resultado = Resultado("11", "Teto de 30 s (EV,TIMEOUT) e volta pelo eixo oposto", None)
    oks: list[bool] = []
    for trecho in partes:
        linhas = trecho.linhas
        for indice, timeout in trecho.eventos(TipoEvento.TIMEOUT):
            ultimo_ciclo = next(
                (
                    j
                    for j in range(indice - 1, -1, -1)
                    if (st := linhas[j].st) is not None and st.regime is Regime.CICLO
                ),
                -1,
            )
            inicio = next(
                (
                    ev
                    for j, ev in trecho.eventos(TipoEvento.PREEMP_INI)
                    if ultimo_ciclo < j < indice
                ),
                None,
            )
            renovacoes = sum(
                1 for j, _ in trecho.eventos(TipoEvento.RENOVADO) if ultimo_ciclo < j < indice
            )
            fim = next(
                ((j, ev) for j, ev in trecho.eventos(TipoEvento.PREEMP_FIM) if j > indice), None
            )
            volta = None
            if fim is not None:
                sts = [linha.st for linha in linhas[fim[0] :] if linha.st is not None]
                volta = next(
                    (
                        depois
                        for antes, depois in pairwise(sts)
                        if any(
                            d == "G" != a for a, d in zip(antes.estado, depois.estado, strict=True)
                        )
                    ),
                    None,
                )
            duracao = None if inicio is None else timeout.t_dispositivo_ms - inicio.t_dispositivo_ms
            oposto = None
            if fim is not None and fim[1].rua is not None:
                eixo_oposto = 1 - EIXO_DE[fim[1].rua - 1]
                oposto = (
                    volta is not None
                    and volta.regime is Regime.CICLO
                    and {EIXO_DE[i] for i, c in enumerate(volta.estado) if c == "G"}
                    == {eixo_oposto}
                )
            ok = duracao is not None and _perto(duracao, TETO_MS) and bool(oposto)
            oks.append(ok)
            resultado.detalhes.append(
                f"TIMEOUT em {timeout.t_dispositivo_ms} ms: "
                f"{'—' if duracao is None else f'{duracao} ms'} depois do PREEMP_INI "
                f"(esperado {TETO_MS} ± {FOLGA_MS}), {renovacoes} renovações no meio; "
                f"PREEMP_FIM {'—' if fim is None else f'na RUA{fim[1].rua}'}; depois abriu "
                f"{'—' if volta is None else volta.estado} — {'ok' if ok else 'FALHA'}"
            )
    if oks:
        resultado.ok = all(oks)
    return resultado


def item_12(linhas: Sequence[Linha], partes: Sequence[Trecho]) -> Resultado:
    resultado = Resultado("12", "Operação contínua de 30 min sem travamento ou reboot", None)
    chegadas = [linha.t for linha in linhas if linha.st is not None]
    if len(chegadas) < 2:
        return resultado
    duracao_s = (chegadas[-1] - chegadas[0]).total_seconds()
    silencio_s = max((b - a).total_seconds() for a, b in pairwise(chegadas))
    reinicios = len(partes) - 1
    sem_boot = sum(1 for trecho in partes[1:] if not trecho.comeca_no_boot)
    millis = [
        (trecho.sts[-1].t_dispositivo_ms - trecho.sts[0].t_dispositivo_ms) / 1000
        for trecho in partes
        if trecho.sts
    ]
    resultado.detalhes += [
        f"Da primeira à última ST: {duracao_s / 60:.1f} min "
        f"(precisa de {SESSAO_CONTINUA_S / 60:.0f})",
        f"Reinícios do UNO no meio da sessão: {reinicios}"
        + (f" ({sem_boot} sem BOOT visto)" if sem_boot else ""),
        f"Maior intervalo entre duas ST, no relógio do notebook: {silencio_s:.2f} s "
        f"(a ponte dá o UNO por calado a partir de {SILENCIO_MAXIMO_S:.0f} s)",
        f"Tempo pelo millis() do UNO: {sum(millis) / 60:.1f} min",
    ]
    if reinicios or silencio_s > SILENCIO_MAXIMO_S:
        resultado.ok = False
    elif duracao_s >= SESSAO_CONTINUA_S:
        resultado.ok = True
    else:
        # Sessão encerrada antes dos 30 min, sem falha: não é um soak.
        resultado.detalhes.append("Sessão mais curta que 30 min, sem falha: não é o soak.")
    return resultado


def item_14(partes: Sequence[Trecho]) -> Resultado:
    resultado = Resultado("14", "Ponte encerrada no meio de uma emergência", None)
    ultima = next((st for trecho in reversed(partes) for st in reversed(trecho.sts)), None)
    if ultima is None:
        return resultado
    em_emergencia = ultima.regime is Regime.EMERGENCIA
    resultado.detalhes.append(
        f"Última ST da sessão: {ultima.estado}, regime {ultima.regime.value}, rua ativa "
        f"{ultima.rua_ativa or '—'}, lista {''.join(map(str, ultima.autorizacoes))}"
        + (
            " — a ponte foi encerrada no meio de uma emergência."
            if em_emergencia
            else " — a sessão não terminou em emergência."
        )
    )
    resultado.detalhes.append(
        "O que o UNO fez com a ponte fechada não passa pelo notebook: é observação."
    )
    return resultado


#: A lista da Central num instante, por tipo da bancada (`TIPOS_DA_BANCADA`).
ListaDaCentral = Callable[[datetime], tuple[int, ...]]


def item_15(
    linhas: Sequence[Linha],
    partes: Sequence[Trecho],
    central_no_boot: ListaDaCentral | None = None,
) -> Resultado:
    """O UNO volta negando todos, e a lista da Central volta em até 2 s do BOOT.

    Sem envio da lista em 2 s do BOOT, há dois casos que a telemetria não separa:
    a Central não tinha ocorrência no BOOT (a lista já era `000`, e não havia nada
    a reenviar) ou havia, e o backend falhou. Com `central_no_boot` (o banco, na
    linha de comando com `--banco`), o primeiro sai "sem veredito" e o segundo
    "não atende"; sem ele, os dois saem "sem veredito", com o motivo. Ajuste de
    2026-10-08, depois da rodada, sem mudar o limite (`context/09`).
    """
    resultado = Resultado(
        "15", "Ponte reiniciada: o UNO volta negando todos, e a lista volta", None
    )
    oks: list[bool] = []
    for n, trecho in enumerate(partes, 1):
        if not trecho.comeca_no_boot:
            continue
        t_boot = trecho.linhas[0].t
        sts = [linha for linha in trecho.linhas if linha.st is not None]
        if not sts:
            continue
        primeira = sts[0].st
        assert primeira is not None
        negando = primeira.autorizacoes == NENHUMA_AUTORIZACAO
        envio = _primeira_lista_escrita(linhas, t_boot)
        if envio is None or (envio[0] - t_boot).total_seconds() > LISTA_VOLTA_MAX_S:
            detalhe, ok_sem_envio = _sem_envio_logo_apos_o_boot(t_boot, envio, central_no_boot)
            if not negando:
                ok_sem_envio = False
            if ok_sem_envio is not None:
                oks.append(ok_sem_envio)
            resultado.detalhes.append(
                f"Arranque {n}: primeira lista {_lista(primeira)}; {detalhe}"
                + ("" if ok_sem_envio is None else f" — {'ok' if ok_sem_envio else 'FALHA'}")
            )
            continue
        t_envio, desejada = envio
        volta = next(
            (linha for linha in sts if linha.st is not None and linha.st.autorizacoes == desejada),
            None,
        )
        espera_s = None if volta is None else (volta.t - t_boot).total_seconds()
        ok = negando and espera_s is not None and espera_s <= LISTA_VOLTA_MAX_S
        oks.append(ok)
        resultado.detalhes.append(
            f"Arranque {n}: primeira lista {_lista(primeira)}; a ponte escreveu "
            f"{''.join(map(str, desejada))} {(t_envio - t_boot).total_seconds():.2f} s depois do "
            "BOOT, e a ST a trouxe inteira "
            + ("— nunca" if espera_s is None else f"{espera_s:.2f} s depois do BOOT")
            + f"; critério ≤ {LISTA_VOLTA_MAX_S:.0f} s — {'ok' if ok else 'FALHA'}"
        )
    if oks:
        resultado.ok = all(oks)
    return resultado


def _lista(st: Telemetria) -> str:
    return "".join(map(str, st.autorizacoes))


def _sem_envio_logo_apos_o_boot(
    t_boot: datetime,
    envio: tuple[datetime, tuple[int, ...]] | None,
    central_no_boot: ListaDaCentral | None,
) -> tuple[str, bool | None]:
    """O que dizer do item 15 quando a ponte não reenviou a lista em 2 s do BOOT."""
    if envio is None:
        quando = "a ponte não escreveu a lista da Central na sessão"
    else:
        atraso_s = (envio[0] - t_boot).total_seconds()
        quando = f"a primeira lista que a ponte escreveu saiu {atraso_s:.2f} s depois do BOOT"
    if central_no_boot is None:
        return (
            f"{quando}; sem o banco, não dá para saber se a Central tinha ocorrência no BOOT "
            "(rode com --banco). Sem veredito.",
            None,
        )
    lista = central_no_boot(t_boot)
    texto = "".join(map(str, lista))
    if lista == NENHUMA_AUTORIZACAO:
        return (
            f"{quando}; a lista da Central no BOOT era {texto}, a mesma da ST, e não havia "
            "nada a reenviar. Sem veredito.",
            None,
        )
    return (
        f"{quando}; a lista da Central no BOOT era {texto}, e não voltou em "
        f"{LISTA_VOLTA_MAX_S:.0f} s",
        False,
    )


def lista_da_central(url: str) -> ListaDaCentral:
    """A lista da Central num instante, tirada das ocorrências gravadas no banco.

    A mesma regra de `app.repositories.ocorrencia.criticidade_por_tipo`, num
    instante do passado: por tipo, a criticidade mais alta entre as ocorrências
    abertas naquele instante, de veículos ativos. O status do veículo é o de
    hoje, porque o banco não guarda a história dele. Ocorrência posta na ponte à
    mão (`PUT /autorizacoes`, com o compose parado) não está no banco: para o
    banco, a Central não tinha nenhuma.
    """
    import psycopg

    def no_instante(instante: datetime) -> tuple[int, ...]:
        with psycopg.connect(url) as conexao:
            linhas = conexao.execute(
                "SELECT v.tipo::text, min(o.criticidade) FROM ocorrencia o "
                "JOIN veiculo_emergencia v ON v.id_veiculo = o.fk_veiculo "
                "WHERE o.aberta_em <= %s AND (o.encerrada_em IS NULL OR o.encerrada_em > %s) "
                "AND v.status_operacional = 'ATIVO' GROUP BY v.tipo",
                (instante, instante),
            ).fetchall()
        ativas = {str(tipo): int(criticidade) for tipo, criticidade in linhas}
        return tuple(ativas.get(tipo.value, 0) for tipo in TIPOS_DA_BANCADA)

    return no_instante


#: As linhas `AUT` de um mesmo envio saem juntas: o backend escreve as três em
#: ~2 ms (`PUT /autorizacoes`).
JANELA_DO_ENVIO_S = 0.1


def _primeira_lista_escrita(
    linhas: Sequence[Linha], t_boot: datetime
) -> tuple[datetime, tuple[int, ...]] | None:
    """O primeiro envio da lista da Central depois do BOOT, e a lista que ele deixa no UNO.

    A lista começa em `000` no boot e cada `AUT` do envio troca um tipo, como no
    UNO (`context/05` §3.2.1).
    """
    escritas = [
        linha
        for linha in linhas
        if linha.direcao is Direcao.PONTE and linha.texto.startswith("AUT,") and linha.t >= t_boot
    ]
    if not escritas:
        return None
    t_envio = escritas[0].t
    lista = list(NENHUMA_AUTORIZACAO)
    for linha in escritas:
        if (linha.t - t_envio).total_seconds() > JANELA_DO_ENVIO_S:
            break
        _, tipo, criticidade = linha.texto.split(",")
        lista[TIPOS_DA_BANCADA.index(TipoVeiculo(tipo))] = int(criticidade)
    return t_envio, tuple(lista)


# ---------------------------------------------------------------------------
# Item 9, no PostgreSQL
# ---------------------------------------------------------------------------


def _url_do_banco() -> str:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        from dotenv import load_dotenv

        load_dotenv()
        url = os.getenv("DATABASE_URL", "")
    # O backend usa o dialeto do SQLAlchemy; o psycopg quer a URL do libpq.
    return url.replace("postgresql+psycopg://", "postgresql://")


def item_9(linhas: Sequence[Linha], url: str) -> Resultado:
    """Cada decisão do UNO na sessão tem a sua linha em `log_prioridade`.

    O backend grava como `timestamp_inicio` o `recebido_em` do evento, que é o
    mesmo carimbo da linha no CSV; o casamento é exato.
    """
    import psycopg

    resultado = Resultado("9", "Log no PostgreSQL com id_correlacao completo", None)
    decisoes = [
        linha for linha in linhas if linha.ev is not None and linha.ev.tipo in EVENTOS_DE_DECISAO
    ]
    if not decisoes:
        return resultado
    inicio, fim = linhas[0].t, linhas[-1].t
    with psycopg.connect(url) as conexao:
        logs = conexao.execute(
            "SELECT id_log, id_correlacao, timestamp_inicio, timestamp_fim, motivo "
            "FROM log_prioridade WHERE fk_execucao IS NULL "
            "AND timestamp_inicio BETWEEN %s AND %s",
            (inicio, fim),
        ).fetchall()
        latencias = conexao.execute(
            "SELECT m.id_correlacao, l.id_correlacao FROM metrica_latencia m "
            "LEFT JOIN log_prioridade l ON l.id_log = m.fk_log "
            "WHERE m.ambiente = 'HARDWARE' AND m.t_atuacao BETWEEN %s AND %s",
            (inicio, fim),
        ).fetchall()
    if not logs and not latencias:
        return _sem_nada_gravado(resultado, linhas, len(decisoes), lista_da_central(url))
    por_instante: dict[datetime, list[Any]] = {}
    for registro in logs:
        por_instante.setdefault(registro[2], []).append(registro)
    sem_log = [linha for linha in decisoes if len(por_instante.get(linha.t, [])) != 1]
    preemp = [linha for linha in decisoes if linha.ev and linha.ev.tipo is TipoEvento.PREEMP_INI]
    abertos = [
        linha
        for linha in preemp
        if len(por_instante.get(linha.t, [])) == 1 and por_instante[linha.t][0][3] is None
    ]
    sem_id = sum(1 for registro in logs if registro[1] is None)
    ligadas = [par for par in latencias if par[1] is not None]
    iguais = sum(1 for a, b in ligadas if a == b)
    resultado.detalhes += [
        f"Eventos de decisão na sessão: {len(decisoes)}; com exatamente uma linha em "
        f"log_prioridade no mesmo instante: {len(decisoes) - len(sem_log)}",
        f"Linhas de log_prioridade na janela: {len(logs)}; sem id_correlacao: {sem_id}",
        f"PREEMP_INI sem timestamp_fim (atendimento não fechado): {len(abertos)} de {len(preemp)}",
        f"Amostras de H3 em metrica_latencia na janela: {len(latencias)}; ligadas a um log: "
        f"{len(ligadas)}; com o mesmo id_correlacao do log: {iguais}",
    ]
    if sem_log:
        resultado.detalhes.append(
            "Sem log: "
            + "; ".join(f"{linha.texto} ({linha.t.isoformat()})" for linha in sem_log[:5])
        )
    resultado.ok = not sem_log and sem_id == 0 and iguais == len(ligadas) == len(latencias)
    return resultado


def _sem_nada_gravado(
    resultado: Resultado, linhas: Sequence[Linha], decisoes: int, central: ListaDaCentral
) -> Resultado:
    """Item 9 quando o backend não gravou nada na sessão.

    Há dois casos que o banco sozinho não separa: o backend estava fora do ar
    (as sessões do item 5 rodaram com o compose parado e a lista posta à mão por
    `PUT /autorizacoes`) ou estava no ar e falhou em gravar. A lista que a `ST`
    traz separa os dois: com o backend no caminho, ela é a da Central do banco.
    Lista diferente da do banco: veio de fora do backend, "sem veredito". Igual
    e não nula: o backend estava no caminho e não gravou, "não atende". Nunca
    diferente de `000`: o dado não separa, "sem veredito". Mesmo tratamento do
    item 15 (ajuste de 2026-10-08, depois da rodada, `context/09`).
    """
    resultado.detalhes.append(
        f"Eventos de decisão na sessão: {decisoes}; nenhuma linha de log_prioridade nem de "
        "metrica_latencia na janela"
    )
    primeira = next(
        (
            linha
            for linha in linhas
            if linha.st is not None and linha.st.autorizacoes != NENHUMA_AUTORIZACAO
        ),
        None,
    )
    if primeira is None or primeira.st is None:
        resultado.detalhes.append(
            "A lista do UNO ficou em 000 a sessão inteira: não dá para saber se o backend "
            "estava no ar. Sem veredito."
        )
        return resultado
    no_uno = primeira.st.autorizacoes
    no_banco = central(primeira.t)
    texto = "".join(map(str, no_uno))
    if no_uno != no_banco:
        resultado.detalhes.append(
            f"A lista {texto} chegou ao UNO em {primeira.t.isoformat()}, e a Central do banco "
            f"tinha {''.join(map(str, no_banco))}: a lista veio de fora do backend "
            "(PUT /autorizacoes à mão), que não estava no caminho. Sem veredito."
        )
        return resultado
    resultado.detalhes.append(
        f"A lista {texto} do UNO é a da Central do banco: o backend estava no caminho e não "
        "gravou nenhum evento — FALHA"
    )
    resultado.ok = False
    return resultado


# ---------------------------------------------------------------------------
# Relatório
# ---------------------------------------------------------------------------


def avaliar(
    linhas: Sequence[Linha],
    url_banco: str | None = None,
    leituras: Sequence[LeituraEmissor] | None = None,
) -> list[Resultado]:
    """Todos os itens que o dado de uma sessão permite julgar.

    O item 5 só entra com `leituras`: é julgado na sessão declarada para ele.
    """
    partes = trechos(linhas)
    return [
        item_1(partes),
        item_2(partes),
        item_3(partes),
        *([] if leituras is None else [item_5(partes, leituras)]),
        item_5b(partes),
        *([] if url_banco is None else [item_9(linhas, url_banco)]),
        item_10(partes),
        item_11(partes),
        item_12(linhas, partes),
        item_14(partes),
        item_15(linhas, partes, None if url_banco is None else lista_da_central(url_banco)),
    ]


def relatorio_da_sessao(
    sessao: str,
    linhas: Sequence[Linha],
    url_banco: str | None,
    leituras: Sequence[LeituraEmissor] | None = None,
) -> list[str]:
    do_uno = [linha for linha in linhas if linha.direcao is Direcao.UNO]
    invalidas = sum(1 for linha in do_uno if linha.resposta is None)
    eventos = Counter(linha.ev.tipo.value for linha in do_uno if linha.ev is not None)
    versoes = sorted({linha.versao_codigo for linha in linhas})
    saida = [
        f"## Sessão {sessao}",
        "",
        f"De {linhas[0].t.isoformat()} a {linhas[-1].t.isoformat()} (relógio do notebook, UTC)",
        f"Versão do código: {', '.join(versoes)}",
        f"Linhas do UNO: {len(do_uno)} ({invalidas} ilegíveis); escritas da ponte: "
        f"{len(linhas) - len(do_uno)}",
        "Eventos: " + (", ".join(f"{k} {v}" for k, v in sorted(eventos.items())) or "—"),
        "",
        "| Item | Verificação | Pelo dado |",
        "|---|---|---|",
    ]
    resultados = avaliar(linhas, url_banco, leituras)
    saida += [f"| {r.item} | {r.titulo} | {_veredito(r.ok)} |" for r in resultados]
    saida.append("")
    for r in resultados:
        saida += [f"### Item {r.item} — {_veredito(r.ok)}", ""]
        saida += [f"- {detalhe}" for detalhe in r.detalhes] or ["- Nada na sessão."]
        saida.append("")
    return saida


def gerar_relatorio(
    sessoes: dict[str, list[Linha]],
    escolhidas: Sequence[str],
    url_banco: str | None = None,
    leituras: dict[str, list[LeituraEmissor]] | None = None,
) -> str:
    """O relatório das sessões escolhidas; com `leituras`, cada uma julga também o item 5."""
    linhas = ["# Checklist da bancada — o que a telemetria gravada mostra", ""]
    if not escolhidas:
        linhas.append(
            "Nenhuma sessão encontrada. Grave com "
            "`python -m bridge.main --porta COM3 --telemetria`."
        )
        return "\n".join(linhas) + "\n"
    linhas += [
        "Itens 6, 8 e 13, quantas vezes a tag do item 5 passou, e o LCD de 5b e 10, são "
        "observação de quem está na bancada (`context/06` §6).",
        "",
    ]
    for sessao in escolhidas:
        if sessao not in sessoes:
            linhas += [f"## Sessão {sessao}", "", "Não está no arquivo.", ""]
            continue
        da_sessao = None if leituras is None else leituras.get(sessao, [])
        linhas += relatorio_da_sessao(sessao, sessoes[sessao], url_banco, da_sessao)
    return "\n".join(linhas).rstrip() + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada: `python -m analysis.checklist_bancada`."""
    saida_utf8()
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument("--telemetria", type=Path, default=CSV_TELEMETRIA_PADRAO)
    grupo = analisador.add_mutually_exclusive_group()
    grupo.add_argument("--sessao", action="append", default=None, help="repetível")
    grupo.add_argument("--todas", action="store_true", help="todas as sessões do arquivo")
    analisador.add_argument(
        "--banco",
        action="store_true",
        help="confere no PostgreSQL (DATABASE_URL do .env) o item 9 e a lista da Central "
        "no BOOT do item 15",
    )
    analisador.add_argument(
        "--item5",
        action="store_true",
        help="julga também o item 5 (tag fora do mapa) nas sessões escolhidas",
    )
    analisador.add_argument("--deteccoes", type=Path, default=CSV_DESFECHOS_PADRAO)
    analisador.add_argument("--saida", type=Path, default=None)
    opcoes = analisador.parse_args(argv)

    sessoes = ler_sessoes(opcoes.telemetria)
    if opcoes.todas:
        escolhidas = sorted(sessoes)
    elif opcoes.sessao:
        escolhidas = list(opcoes.sessao)
    else:
        escolhidas = [max(sessoes)] if sessoes else []

    relatorio = gerar_relatorio(
        sessoes,
        escolhidas,
        _url_do_banco() if opcoes.banco else None,
        ler_leituras(opcoes.deteccoes) if opcoes.item5 else None,
    )
    if opcoes.saida is not None:
        opcoes.saida.parent.mkdir(parents=True, exist_ok=True)
        opcoes.saida.write_text(relatorio, encoding="utf-8")
    print(relatorio, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
