"""Tradução dos eventos do UNO em `log_prioridade` e `metrica_latencia` (Bloco 6).

Sem banco e sem rede: o tradutor é puro. As sequências seguem o que o dublê do
UNO publica (`adapters/hardware/simulado.py`, `context/05` §3.3 e §4.2). Em
particular, na interrupção o `PREEMP_INI` do novo sai **antes** do `FILA` do
interrompido, e o teto descarta a fila **sem** `DESCARTADO`.
"""

from __future__ import annotations

import itertools
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from app.models import StatusExecucao
from app.services.bancada import (
    AmostraBancada,
    EncerrarLog,
    EventoBancada,
    InserirLatencia,
    InserirLog,
    LeitorPonte,
    Operacao,
    TradutorBancada,
    estado_do_semaforo,
)
from app.services.difusao import Difusor

T0 = datetime(2026, 10, 5, 12, tzinfo=UTC)


def _t(segundos: float) -> datetime:
    return T0 + timedelta(seconds=segundos)


def _ev(tipo: str, s: float, rua: int | None = None, veiculo: str | None = None) -> EventoBancada:
    return EventoBancada(_t(s), int(s * 1000), tipo, rua, veiculo)


def _tradutor() -> TradutorBancada:
    contador = itertools.count(1)
    return TradutorBancada(novo_id=lambda: uuid.UUID(int=next(contador)))


def _rodar(tradutor: TradutorBancada, *eventos: EventoBancada) -> list[Operacao]:
    return [op for evento in eventos for op in tradutor.traduzir(evento)]


def test_episodio_simples_abre_no_preemp_ini_e_fecha_no_preemp_fim() -> None:
    tradutor = _tradutor()

    (inicio,) = tradutor.traduzir(_ev("PREEMP_INI", 0, 3, "AMBULANCIA"))
    (renovado,) = tradutor.traduzir(_ev("RENOVADO", 2, 3, "AMBULANCIA"))
    fim = tradutor.traduzir(_ev("PREEMP_FIM", 11, 3, "AMBULANCIA"))

    assert isinstance(inicio, InserirLog)
    assert (inicio.status, inicio.timestamp_inicio, inicio.timestamp_fim) == (
        StatusExecucao.SUCESSO,
        _t(0),
        None,
    )
    # A aproximação vai no motivo; fase_aplicada fica nula (decisão de 2026-10-05).
    assert "S3 (RUA3)" in inicio.motivo and "AMBULANCIA" in inicio.motivo
    assert isinstance(renovado, InserirLog) and "RENOVADO" in renovado.motivo
    assert fim == [EncerrarLog(inicio.chave, _t(11)), EncerrarLog(renovado.chave, _t(11))]


def test_cada_decisao_tem_o_proprio_id_de_correlacao() -> None:
    tradutor = _tradutor()
    operacoes = _rodar(
        tradutor, _ev("PREEMP_INI", 0, 3, "AMBULANCIA"), _ev("FILA", 1, 1, "BOMBEIRO")
    )
    ids = [op.id_correlacao for op in operacoes if isinstance(op, InserirLog)]
    assert len(set(ids)) == 2


def test_interrupcao_fecha_o_interrompido_e_a_fila_o_devolve() -> None:
    """Bombeiro atendido; ambulância chega; bombeiro vai para a fila e volta depois."""
    tradutor = _tradutor()
    (bombeiro,) = tradutor.traduzir(_ev("PREEMP_INI", 0, 1, "BOMBEIRO"))
    (ambulancia,) = tradutor.traduzir(_ev("PREEMP_INI", 1, 3, "AMBULANCIA"))
    interrompido, fila = tradutor.traduzir(_ev("FILA", 1, 1, "BOMBEIRO"))

    assert isinstance(bombeiro, InserirLog) and isinstance(ambulancia, InserirLog)
    assert interrompido == EncerrarLog(
        bombeiro.chave, _t(1), None, f"{bombeiro.motivo}; interrompido por VE de prioridade maior"
    )
    assert isinstance(fila, InserirLog) and fila.status is StatusExecucao.CONFLITO_ADIADO

    assert tradutor.traduzir(_ev("PREEMP_FIM", 10, 3, "AMBULANCIA")) == [
        EncerrarLog(ambulancia.chave, _t(10))
    ]
    saiu_da_fila, de_volta = tradutor.traduzir(_ev("PREEMP_INI", 10, 1, "BOMBEIRO"))
    assert saiu_da_fila == EncerrarLog(
        fila.chave, _t(10), None, f"{fila.motivo}; atendido ao sair da fila"
    )
    assert isinstance(de_volta, InserirLog) and de_volta.status is StatusExecucao.SUCESSO


def test_quem_perde_o_lugar_na_fila_fecha_a_linha_dela() -> None:
    tradutor = _tradutor()
    _rodar(tradutor, _ev("PREEMP_INI", 0, 3, "AMBULANCIA"))
    (policia,) = tradutor.traduzir(_ev("FILA", 1, 2, "POLICIA"))
    (bombeiro,) = tradutor.traduzir(_ev("FILA", 2, 1, "BOMBEIRO"))
    deslocado, descartado = tradutor.traduzir(_ev("DESCARTADO", 2, 2, "POLICIA"))

    assert isinstance(policia, InserirLog) and isinstance(bombeiro, InserirLog)
    assert deslocado == EncerrarLog(
        policia.chave, _t(2), None, f"{policia.motivo}; deslocado da fila"
    )
    assert isinstance(descartado, InserirLog)
    assert (descartado.status, descartado.timestamp_fim) == (StatusExecucao.FALHA, _t(2))
    assert "perdeu o lugar" in descartado.motivo


def test_descartado_na_chegada_nao_mexe_na_fila() -> None:
    tradutor = _tradutor()
    _rodar(tradutor, _ev("PREEMP_INI", 0, 3, "AMBULANCIA"), _ev("FILA", 1, 1, "BOMBEIRO"))

    (descartado,) = tradutor.traduzir(_ev("DESCARTADO", 2, 2, "POLICIA"))

    assert isinstance(descartado, InserirLog)
    assert "sem lugar na fila" in descartado.motivo


def test_teto_de_30_s_encerra_com_timeout_e_descarta_a_fila() -> None:
    tradutor = _tradutor()
    (ambulancia,) = tradutor.traduzir(_ev("PREEMP_INI", 0, 3, "AMBULANCIA"))
    (fila,) = tradutor.traduzir(_ev("FILA", 1, 1, "BOMBEIRO"))

    (fila_fechada,) = tradutor.traduzir(_ev("TIMEOUT", 30))
    (fim,) = tradutor.traduzir(_ev("PREEMP_FIM", 30, 3, "AMBULANCIA"))

    assert isinstance(ambulancia, InserirLog) and isinstance(fila, InserirLog)
    assert fila_fechada.chave == fila.chave and "teto" in (fila_fechada.motivo or "")
    assert isinstance(fim, EncerrarLog)
    assert (fim.chave, fim.status) == (ambulancia.chave, StatusExecucao.TIMEOUT)
    # O teto vale para aquele episódio só.
    (_,) = tradutor.traduzir(_ev("PREEMP_INI", 40, 2, "POLICIA"))
    (normal,) = tradutor.traduzir(_ev("PREEMP_FIM", 47, 2, "POLICIA"))
    assert isinstance(normal, EncerrarLog) and normal.status is None


def test_reinicio_do_uno_encerra_tudo_que_estava_aberto_como_falha() -> None:
    tradutor = _tradutor()
    _rodar(tradutor, _ev("PREEMP_INI", 0, 3, "AMBULANCIA"), _ev("FILA", 1, 1, "BOMBEIRO"))

    fechadas = tradutor.traduzir(_ev("BOOT", 5))

    assert len(fechadas) == 2
    assert all(isinstance(op, EncerrarLog) and op.status is StatusExecucao.FALHA for op in fechadas)
    assert tradutor.traduzir(_ev("PREEMP_FIM", 9, 3, "AMBULANCIA")) == []


def test_recusado_nao_vira_linha() -> None:
    assert _tradutor().traduzir(_ev("RECUSADO", 1)) == []


def test_sem_ocorrencia_vira_linha_de_falha_fechada() -> None:
    """P20 na bancada (2026-10-06): a detecção negada fica no log, como na API."""
    (linha,) = _tradutor().traduzir(_ev("SEM_OCORRENCIA", 2, 3, "AMBULANCIA"))
    assert isinstance(linha, InserirLog)
    assert (linha.status, linha.timestamp_inicio, linha.timestamp_fim) == (
        StatusExecucao.FALHA,
        _t(2),
        _t(2),
    )
    assert "sem ocorrência ativa na Central" in linha.motivo


# ---------------------------------------------------------------------------
# A lista da Central mantida no UNO (decisão de 2026-10-06)
# ---------------------------------------------------------------------------


@dataclass
class _CentralFixa:
    lista: dict[str, int]

    def autorizacoes(self) -> dict[str, int]:
        return dict(self.lista)


def _leitor_com_central(
    central: _CentralFixa | None,
) -> tuple[LeitorPonte, list[httpx.Request]]:
    pedidos: list[httpx.Request] = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        return httpx.Response(202, json={"linhas": [], "t_envio": T0.isoformat()})

    cliente = httpx.AsyncClient(transport=httpx.MockTransport(responder), base_url="http://ponte")
    leitor = LeitorPonte(cliente, Difusor(), central=central)  # type: ignore[arg-type]
    return leitor, pedidos


NEGA_TODOS = {"AMBULANCIA": 0, "BOMBEIRO": 0, "POLICIA": 0}


async def test_lista_diferente_da_st_e_enviada_a_ponte() -> None:
    leitor, pedidos = _leitor_com_central(_CentralFixa({**NEGA_TODOS, "AMBULANCIA": 1}))
    await leitor._sincronizar_central({"autorizacoes": NEGA_TODOS})

    (pedido,) = pedidos
    assert (pedido.method, pedido.url.path) == ("PUT", "/autorizacoes")
    assert json.loads(pedido.content) == {
        "autorizacoes": {"AMBULANCIA": 1, "BOMBEIRO": 0, "POLICIA": 0}
    }
    assert leitor.envios_de_autorizacao == 1


async def test_lista_igual_a_da_st_nao_e_reenviada() -> None:
    leitor, pedidos = _leitor_com_central(_CentralFixa(NEGA_TODOS))
    await leitor._sincronizar_central({"autorizacoes": NEGA_TODOS})
    assert pedidos == []


async def test_reenvio_espera_o_intervalo_enquanto_a_st_nao_confirma() -> None:
    leitor, pedidos = _leitor_com_central(_CentralFixa({**NEGA_TODOS, "POLICIA": 2}))
    for _ in range(5):  # cinco leituras a 5 Hz, e o UNO ainda sem a lista
        await leitor._sincronizar_central({"autorizacoes": NEGA_TODOS})
    assert len(pedidos) == 1


async def test_sem_banco_ninguem_sincroniza() -> None:
    leitor, pedidos = _leitor_com_central(None)
    await leitor._sincronizar_central({"autorizacoes": NEGA_TODOS})
    assert pedidos == []


def test_amostra_de_h3_liga_ao_preemp_ini_do_mesmo_carimbo() -> None:
    """`id_correlacao` vai da decisão até a métrica (`context/02` §7)."""
    tradutor = _tradutor()
    (inicio,) = tradutor.traduzir(_ev("PREEMP_INI", 3, 3, "AMBULANCIA"))
    assert isinstance(inicio, InserirLog)

    amostra = AmostraBancada(_t(2.955), _t(3), 45.0, 3, "AMBULANCIA")
    assert tradutor.amostra(amostra) == InserirLatencia(
        inicio.id_correlacao, inicio.chave, _t(2.955), _t(3)
    )


def test_amostra_sem_preemp_ini_conhecido_fica_sem_log() -> None:
    """Ex.: o backend subiu depois do PREEMP_INI. A amostra é gravada mesmo assim."""
    latencia = _tradutor().amostra(AmostraBancada(_t(0), _t(0.04), 40.0, 1, "AMBULANCIA"))
    assert latencia.chave_log is None


def _telemetria(cores: str, regime: str) -> dict[str, object]:
    return {
        "recebida_em": T0.isoformat(),
        "t_dispositivo_ms": 1,
        "cores": cores,
        "regime": regime,
        "rua_ativa": 3 if regime == "E" else None,
        "rua_fila": None,
        "autorizacoes": {"AMBULANCIA": 1, "BOMBEIRO": 0, "POLICIA": 0},
    }


def test_estado_do_semaforo_da_bancada_no_websocket() -> None:
    ciclo = estado_do_semaforo(_telemetria("GGRR", "C"))
    transversal = estado_do_semaforo(_telemetria("RRYY", "C"))
    all_red = estado_do_semaforo(_telemetria("RRRR", "C"))
    emergencia = estado_do_semaforo(_telemetria("RRGR", "E"))

    assert (ciclo["fase"], ciclo["estado"], ciclo["em_preempcao"]) == (1, "VERDE", False)
    assert (transversal["fase"], transversal["estado"]) == (2, "AMARELO")
    assert (all_red["fase"], all_red["estado"]) == (None, "VERMELHO")
    # O verde exclusivo não é fase do ciclo.
    assert (emergencia["fase"], emergencia["em_preempcao"], emergencia["aproximacoes"]) == (
        None,
        True,
        "RRGR",
    )
    # O que o UNO tem da Central vai junto, para o painel mostrar.
    assert emergencia["autorizacoes"] == {"AMBULANCIA": 1, "BOMBEIRO": 0, "POLICIA": 0}
