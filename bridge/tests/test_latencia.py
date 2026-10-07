"""Casamento detecção → decisão e gravação de H3 — `bridge/latencia.py`.

Os instantes daqui são fixos e escritos à mão: testam o casamento, não medem
nada. Amostra de H3 só sai da bancada (`context/05` §4.3).
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from bridge.latencia import (
    COLUNAS,
    COLUNAS_DESFECHOS,
    JANELA_S,
    AmostraH3,
    CasadorH3,
    DecisaoCarimbada,
    Desfecho,
    GravadorCsv,
    GravadorDesfechos,
    LeituraCarimbada,
)
from bridge.protocolo import EVENTOS_DE_DECISAO, Evento, LeituraVeiculo, TipoEvento
from core.modelos import TipoVeiculo

T0 = datetime(2026, 10, 5, 14, 0, tzinfo=UTC)
AMB = TipoVeiculo.AMBULANCIA
UID_DA_RUA = {1: "F39BD606", 2: "1BD2308E", 3: "B7EF8FA0", 4: "97ABAFA0"}


def _t(ms: float) -> datetime:
    return T0 + timedelta(milliseconds=ms)


def _tag(ms: float, rua: int) -> LeituraCarimbada:
    return LeituraCarimbada(_t(ms), LeituraVeiculo(UID_DA_RUA[rua], rua))


def _ev(ms: float, tipo: TipoEvento, rua: int, uno_ms: int = 0) -> DecisaoCarimbada:
    return DecisaoCarimbada(_t(ms), Evento(uno_ms, tipo, rua, AMB))


def _latencias(desfechos: list[Desfecho]) -> list[float]:
    return [round(a.latencia_total_ms, 6) for d in desfechos if (a := d.amostra) is not None]


# ---------------------------------------------------------------------------
# Casos
# ---------------------------------------------------------------------------


def test_deteccao_seguida_de_preemp_ini_e_amostra() -> None:
    casador = CasadorH3()
    assert casador.deteccao(_tag(0, 3)) == []
    desfechos = casador.evento(_ev(45, TipoEvento.PREEMP_INI, 3))

    assert [d.tipo for d in desfechos] == ["PREEMP_INI"]
    assert _latencias(desfechos) == [45.0]
    assert casador.pendentes == 0


def test_decisao_processada_antes_da_deteccao_casa_pelos_carimbos() -> None:
    """A linha do emissor é mais longa e pode terminar de chegar depois."""
    casador = CasadorH3()
    assert casador.evento(_ev(30, TipoEvento.PREEMP_INI, 3)) == []
    desfechos = casador.deteccao(_tag(0, 3))

    assert _latencias(desfechos) == [30.0]


def test_decisao_anterior_a_deteccao_nao_e_dela() -> None:
    casador = CasadorH3()
    casador.evento(_ev(0, TipoEvento.PREEMP_INI, 3))  # injeção, ou outra passagem
    assert casador.deteccao(_tag(10, 3)) == []
    assert casador.pendentes == 1


def test_outra_rua_nao_casa() -> None:
    casador = CasadorH3()
    casador.deteccao(_tag(0, 3))
    assert casador.evento(_ev(40, TipoEvento.PREEMP_INI, 1)) == []
    assert _latencias(casador.evento(_ev(50, TipoEvento.PREEMP_INI, 3))) == [50.0]


def test_eventos_que_nao_sao_de_decisao_sao_ignorados() -> None:
    casador = CasadorH3()
    casador.deteccao(_tag(0, 3))
    assert casador.evento(_ev(20, TipoEvento.PREEMP_FIM, 3)) == []
    assert casador.evento(DecisaoCarimbada(_t(25), Evento(0, TipoEvento.TIMEOUT))) == []
    assert casador.pendentes == 1


def test_deteccao_que_vira_fila_nao_e_amostra_nem_casa_com_a_saida_da_fila() -> None:
    """Casar com "o próximo PREEMP_INI" mediria a espera na fila como latência."""
    casador = CasadorH3()
    casador.deteccao(_tag(0, 3))
    desfechos = casador.evento(_ev(40, TipoEvento.FILA, 3))
    assert [d.tipo for d in desfechos] == ["FILA"]
    assert desfechos[0].amostra is None

    # A saída da fila, segundos depois, não é decisão de detecção nenhuma.
    assert casador.evento(_ev(9_000, TipoEvento.PREEMP_INI, 3)) == []


def test_renovado_e_descartado_nao_sao_amostra() -> None:
    casador = CasadorH3()
    casador.deteccao(_tag(0, 2))
    casador.deteccao(_tag(5_000, 4))
    renovado = casador.evento(_ev(40, TipoEvento.RENOVADO, 2))
    descartado = casador.evento(_ev(5_040, TipoEvento.DESCARTADO, 4))

    assert [d.tipo for d in renovado + descartado] == ["RENOVADO", "DESCARTADO"]
    assert all(d.amostra is None for d in renovado + descartado)


def test_deteccao_sem_decisao_expira_na_janela_e_nao_antes() -> None:
    casador = CasadorH3()
    casador.deteccao(_tag(0, 3))

    assert casador.expirar(_t(JANELA_S * 1000 - 1)) == []
    vencidas = casador.expirar(_t(JANELA_S * 1000 + 1))
    assert [d.tipo for d in vencidas] == ["SEM_DECISAO"]
    assert vencidas[0].amostra is None
    assert casador.pendentes == 0


def test_amostra_lenta_dentro_da_janela_e_gravada_como_veio() -> None:
    """A janela é folgada de propósito: não pode cortar justamente as lentas."""
    casador = CasadorH3()
    casador.deteccao(_tag(0, 1))
    casador.expirar(_t(2_500))
    assert _latencias(casador.evento(_ev(2_600, TipoEvento.PREEMP_INI, 1))) == [2_600.0]


def test_decisao_sem_deteccao_some_depois_da_janela() -> None:
    casador = CasadorH3()
    casador.evento(_ev(0, TipoEvento.PREEMP_INI, 3))
    casador.expirar(_t(JANELA_S * 1000 + 1))
    # Uma detecção antiga processada muito tarde não casa mais com ela.
    assert casador.deteccao(_tag(-10, 3)) == []


# ---------------------------------------------------------------------------
# Propriedade: a ordem entre as duas portas não muda o resultado
# ---------------------------------------------------------------------------


@st.composite
def _passagens(draw: st.DrawFn) -> list[tuple[float, int, TipoEvento, float]]:
    """Passagens espaçadas como na bancada: (t_tag, rua, decisão, latência)."""
    n = draw(st.integers(1, 8))
    t = 0.0
    passagens = []
    for _ in range(n):
        t += draw(st.floats(300, 20_000))
        rua = draw(st.integers(1, 4))
        tipo = draw(st.sampled_from(sorted(EVENTOS_DE_DECISAO)))
        latencia = draw(st.floats(0.5, 250))
        passagens.append((t, rua, tipo, latencia))
    return passagens


@settings(max_examples=200, deadline=None)
@given(passagens=_passagens(), data=st.data())
def test_casamento_independe_da_ordem_de_processamento_das_portas(
    passagens: list[tuple[float, int, TipoEvento, float]], data: st.DataObject
) -> None:
    tags = [_tag(t, rua) for t, rua, _, _ in passagens]
    decisoes = [_ev(t + lat, tipo, rua) for t, rua, tipo, lat in passagens]

    # Cada porta em ordem; entre elas, qualquer intercalação.
    ordem = data.draw(st.permutations([0] * len(tags) + [1] * len(decisoes)))
    casador = CasadorH3()
    desfechos: list[Desfecho] = []
    fila_tags, fila_decisoes = list(tags), list(decisoes)
    for porta in ordem:
        if porta == 0:
            desfechos += casador.deteccao(fila_tags.pop(0))
        else:
            desfechos += casador.evento(fila_decisoes.pop(0))

    esperado = {
        (tag.t, decisao.t): decisao.evento.tipo for tag, decisao in zip(tags, decisoes, strict=True)
    }
    obtido = {(d.deteccao.t, d.decisao.t): d.decisao.evento.tipo for d in desfechos if d.decisao}
    assert obtido == esperado
    assert casador.pendentes == 0


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def _amostra(lat_ms: float, rua: int = 3) -> AmostraH3:
    return AmostraH3(
        LeituraCarimbada(_t(0), LeituraVeiculo(UID_DA_RUA[rua], rua), bytes_em_espera=0),
        DecisaoCarimbada(_t(lat_ms), Evento(142_350, TipoEvento.PREEMP_INI, rua, AMB), 2),
    )


def test_gravador_escreve_o_cabecalho_uma_vez_e_acrescenta(tmp_path: Path) -> None:
    caminho = tmp_path / "data" / "latencia_bancada.csv"
    primeira = GravadorCsv(caminho, sessao=T0, versao_codigo="abc1234")
    primeira.gravar(_amostra(45.25))
    segunda = GravadorCsv(caminho, sessao=_t(60_000), versao_codigo="abc1234")
    segunda.gravar(_amostra(51.0, rua=1))

    with caminho.open(encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.reader(arquivo))
    assert tuple(linhas[0]) == COLUNAS
    assert len(linhas) == 3
    registro = dict(zip(COLUNAS, linhas[1], strict=True))
    assert registro == {
        "sessao": T0.isoformat(),
        "t_deteccao": T0.isoformat(),
        "t_atuacao": _t(45.25).isoformat(),
        "latencia_total_ms": "45.250",
        "rua": "3",
        "uid": "B7EF8FA0",
        "veiculo": "AMBULANCIA",
        "uno_ms": "142350",
        "bytes_em_espera_deteccao": "0",
        "bytes_em_espera_atuacao": "2",
        "versao_codigo": "abc1234",
    }
    assert linhas[2][COLUNAS.index("sessao")] != linhas[1][COLUNAS.index("sessao")]


def test_gravador_de_desfechos_grava_a_decisao_e_a_falta_dela(tmp_path: Path) -> None:
    """Cada leitura do emissor vira uma linha, atendida ou não: o dado do RNF05."""
    caminho = tmp_path / "deteccoes_bancada.csv"
    gravador = GravadorDesfechos(caminho, sessao=T0, versao_codigo="abc1234")
    gravador.gravar(Desfecho(_tag(0, 3), _ev(30.5, TipoEvento.RENOVADO, 3, uno_ms=900)))
    gravador.gravar(Desfecho(_tag(20_000, 1), None))

    with caminho.open(encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.reader(arquivo))
    assert tuple(linhas[0]) == COLUNAS_DESFECHOS
    atendida, perdida = (dict(zip(COLUNAS_DESFECHOS, linha, strict=True)) for linha in linhas[1:])
    assert atendida == {
        "sessao": T0.isoformat(),
        "t_deteccao": T0.isoformat(),
        "rua": "3",
        "uid": "B7EF8FA0",
        "desfecho": "RENOVADO",
        "t_decisao": _t(30.5).isoformat(),
        "latencia_ms": "30.500",
        "veiculo": "AMBULANCIA",
        "uno_ms": "900",
        "versao_codigo": "abc1234",
    }
    assert (perdida["rua"], perdida["desfecho"]) == ("1", "SEM_DECISAO")
    assert perdida["t_decisao"] == perdida["latencia_ms"] == perdida["uno_ms"] == ""
