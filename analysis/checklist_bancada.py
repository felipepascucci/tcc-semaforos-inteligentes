"""Checklist da bancada a partir da telemetria gravada — `context/06` §6.

    python -m analysis.checklist_bancada                  # a última sessão da ponte
    python -m analysis.checklist_bancada --sessao <iso>   # uma sessão (repetível)
    python -m analysis.checklist_bancada --todas
    python -m analysis.checklist_bancada --banco          # mais o item 9, no PostgreSQL

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
  lista da Central leva para voltar;
* **item 9**, com `--banco` — cada evento de decisão da sessão tem a sua linha em
  `log_prioridade`, com `id_correlacao`, e cada amostra de H3 em
  `metrica_latencia` tem o mesmo `id_correlacao` da linha do `PREEMP_INI`.

O resto do checklist (5, 6, 8, 13, e o que o LCD mostra em 5b e 10) é observação
de quem está na bancada e não sai daqui.

As durações são conferidas no `millis()` do UNO, com a folga de
`bridge.verificar` (60 ms, uma volta do `loop()`); os intervalos entre a ponte e
o UNO, no relógio do notebook.
"""

from __future__ import annotations

import argparse
import csv
import os
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

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


def item_15(linhas: Sequence[Linha], partes: Sequence[Trecho]) -> Resultado:
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
        if envio is None:
            resultado.detalhes.append(
                f"Arranque {n}: primeira lista {_lista(primeira)}; a ponte não escreveu a lista "
                "da Central na sessão (backend fora do ar?)"
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


# ---------------------------------------------------------------------------
# Relatório
# ---------------------------------------------------------------------------


def avaliar(linhas: Sequence[Linha], url_banco: str | None = None) -> list[Resultado]:
    """Todos os itens que o dado de uma sessão permite julgar."""
    partes = trechos(linhas)
    resultados = [
        item_1(partes),
        item_2(partes),
        item_3(partes),
        item_5b(partes),
        item_10(partes),
        item_11(partes),
        item_12(linhas, partes),
        item_14(partes),
        item_15(linhas, partes),
    ]
    if url_banco is not None:
        resultados.insert(4, item_9(linhas, url_banco))
    return resultados


def relatorio_da_sessao(sessao: str, linhas: Sequence[Linha], url_banco: str | None) -> list[str]:
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
    resultados = avaliar(linhas, url_banco)
    saida += [f"| {r.item} | {r.titulo} | {_veredito(r.ok)} |" for r in resultados]
    saida.append("")
    for r in resultados:
        saida += [f"### Item {r.item} — {_veredito(r.ok)}", ""]
        saida += [f"- {detalhe}" for detalhe in r.detalhes] or ["- Nada na sessão."]
        saida.append("")
    return saida


def gerar_relatorio(
    sessoes: dict[str, list[Linha]], escolhidas: Sequence[str], url_banco: str | None = None
) -> str:
    linhas = ["# Checklist da bancada — o que a telemetria gravada mostra", ""]
    if not escolhidas:
        linhas.append(
            "Nenhuma sessão encontrada. Grave com "
            "`python -m bridge.main --porta COM3 --telemetria`."
        )
        return "\n".join(linhas) + "\n"
    linhas += [
        "Itens 5, 6, 8 e 13, e o LCD de 5b e 10, são observação de quem está na bancada "
        "(`context/06` §6).",
        "",
    ]
    for sessao in escolhidas:
        if sessao not in sessoes:
            linhas += [f"## Sessão {sessao}", "", "Não está no arquivo.", ""]
            continue
        linhas += relatorio_da_sessao(sessao, sessoes[sessao], url_banco)
    return "\n".join(linhas).rstrip() + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada: `python -m analysis.checklist_bancada`."""
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument("--telemetria", type=Path, default=CSV_TELEMETRIA_PADRAO)
    grupo = analisador.add_mutually_exclusive_group()
    grupo.add_argument("--sessao", action="append", default=None, help="repetível")
    grupo.add_argument("--todas", action="store_true", help="todas as sessões do arquivo")
    analisador.add_argument(
        "--banco", action="store_true", help="confere o item 9 no PostgreSQL (DATABASE_URL do .env)"
    )
    analisador.add_argument("--saida", type=Path, default=None)
    opcoes = analisador.parse_args(argv)

    sessoes = ler_sessoes(opcoes.telemetria)
    if opcoes.todas:
        escolhidas = sorted(sessoes)
    elif opcoes.sessao:
        escolhidas = list(opcoes.sessao)
    else:
        escolhidas = [max(sessoes)] if sessoes else []

    relatorio = gerar_relatorio(sessoes, escolhidas, _url_do_banco() if opcoes.banco else None)
    if opcoes.saida is not None:
        opcoes.saida.parent.mkdir(parents=True, exist_ok=True)
        opcoes.saida.write_text(relatorio, encoding="utf-8")
    print(relatorio, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
