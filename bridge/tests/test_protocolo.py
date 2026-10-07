"""Protocolo serial da bancada — entrega 5.1, refeita para `context/05` §4."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from bridge.protocolo import (
    EVENTOS_DE_DECISAO,
    EVENTOS_DE_VEICULO,
    Autorizacao,
    Cor,
    Deteccao,
    Evento,
    LeituraVeiculo,
    LinhaInvalidaError,
    ProtocoloError,
    Regime,
    Telemetria,
    TipoEvento,
    interpretar,
    interpretar_autorizacao,
    interpretar_deteccao,
    interpretar_leitura_veiculo,
    parece_autorizacao,
    parece_deteccao,
)
from core.modelos import TipoVeiculo

G, Y, R = Cor.VERDE, Cor.AMARELO, Cor.VERMELHO
AMB = TipoVeiculo.AMBULANCIA

# ---------------------------------------------------------------------------
# NodeMCU receptor -> UNO
# ---------------------------------------------------------------------------


def test_deteccao_codifica_como_o_receptor() -> None:
    assert Deteccao(3, AMB).codificar() == b"RUA3,AMBULANCIA\n"


@pytest.mark.parametrize(
    "linha",
    [b"RUA3,AMBULANCIA\n", b"RUA3,AMBULANCIA\r\n", b"3,AMBULANCIA\n", b" RUA3 , AMBULANCIA \n"],
)
def test_deteccao_aceita_os_formatos_do_sketch(linha: bytes) -> None:
    assert interpretar_deteccao(linha) == Deteccao(3, AMB)


@pytest.mark.parametrize(
    "linha",
    [
        b"RUA0,AMBULANCIA\n",
        b"RUA5,AMBULANCIA\n",
        b"RUA,AMBULANCIA\n",
        b"RUA3,HELICOPTERO\n",
        b"RUA3,ambulancia\n",
        b"RUA3,AMBULANCIA,X\n",
        b"\xff,\xfe\n",
    ],
)
def test_deteccao_invalida(linha: bytes) -> None:
    with pytest.raises(LinhaInvalidaError):
        interpretar_deteccao(linha)


def test_lixo_sem_virgula_nao_parece_deteccao() -> None:
    assert parece_deteccao(b"RUA3,AMBULANCIA\n")
    assert not parece_deteccao(b"ets Jan  8 2013 rst cause:2\n")


@pytest.mark.parametrize("rua", [0, 5, True])
def test_deteccao_fora_de_1_a_4_nao_e_construida(rua: int) -> None:
    with pytest.raises(ProtocoloError):
        Deteccao(rua, AMB)


@given(st.integers(1, 4), st.sampled_from(list(TipoVeiculo)))
def test_deteccao_ida_e_volta(rua: int, veiculo: TipoVeiculo) -> None:
    deteccao = Deteccao(rua, veiculo)
    assert interpretar_deteccao(deteccao.codificar()) == deteccao


# ---------------------------------------------------------------------------
# UNO -> notebook
# ---------------------------------------------------------------------------


def test_telemetria_do_exemplo_do_context_05() -> None:
    linha = b"ST,147350,RRGR,E,3,0,123\r\n"
    telemetria = interpretar(linha)

    assert telemetria == Telemetria(147350, (R, R, G, R), Regime.EMERGENCIA, 3, None, (1, 2, 3))
    assert telemetria.codificar() == linha.replace(b"\r", b"")


@pytest.mark.parametrize(
    ("estado", "viola"),
    [("GGRR", False), ("RRGG", False), ("GRRR", False), ("GRGR", True), ("RGRG", True)],
)
def test_viola_i1_e_verde_nos_dois_eixos(estado: str, viola: bool) -> None:
    """Dois verdes no mesmo eixo é o ciclo; em eixos diferentes, conflito."""
    telemetria = interpretar(f"ST,0,{estado},C,0,0,000\n".encode())
    assert isinstance(telemetria, Telemetria)
    assert telemetria.viola_i1 is viola


def test_eventos_com_e_sem_ve() -> None:
    assert interpretar(b"EV,10,BOOT\n") == Evento(10, TipoEvento.BOOT)
    assert interpretar(b"EV,20,FILA,1,BOMBEIRO\n") == Evento(
        20, TipoEvento.FILA, 1, TipoVeiculo.BOMBEIRO
    )
    assert Evento(30, TipoEvento.TIMEOUT).codificar() == b"EV,30,TIMEOUT\n"


def test_decisoes_sao_eventos_de_veiculo() -> None:
    assert EVENTOS_DE_DECISAO < EVENTOS_DE_VEICULO
    assert TipoEvento.PREEMP_FIM in EVENTOS_DE_VEICULO - EVENTOS_DE_DECISAO
    assert TipoEvento.SEM_OCORRENCIA in EVENTOS_DE_DECISAO


# ---------------------------------------------------------------------------
# Notebook -> UNO: a lista da Central (decisão de 2026-10-06)
# ---------------------------------------------------------------------------


@given(st.sampled_from(list(TipoVeiculo)), st.integers(0, 3))
def test_autorizacao_ida_e_volta(veiculo: TipoVeiculo, criticidade: int) -> None:
    autorizacao = Autorizacao(veiculo, criticidade)
    linha = autorizacao.codificar()
    assert parece_autorizacao(linha)
    assert interpretar_autorizacao(linha) == autorizacao
    assert interpretar_autorizacao(linha.replace(b"\n", b"\r\n")) == autorizacao


def test_autorizacao_na_linha() -> None:
    assert Autorizacao(TipoVeiculo.BOMBEIRO, 2).codificar() == b"AUT,BOMBEIRO,2\n"


@pytest.mark.parametrize("criticidade", [-1, 4, True])
def test_autorizacao_fora_da_faixa(criticidade: int) -> None:
    with pytest.raises(ProtocoloError):
        Autorizacao(TipoVeiculo.AMBULANCIA, criticidade)


@pytest.mark.parametrize(
    "linha",
    [
        b"AUT,AMBULANCIA\n",
        b"AUT,AMBULANCIA,1,2\n",
        b"AUT,AMBULANCIA,4\n",
        b"AUT,AMBULANCIA,01\n",
        b"AUT, AMBULANCIA,1\n",
        b"AUT,AMBULANCIA, 1\n",
        b"AUT,HELICOPTERO,1\n",
        b"AUT,,1\n",
    ],
)
def test_autorizacao_invalida(linha: bytes) -> None:
    with pytest.raises(LinhaInvalidaError):
        interpretar_autorizacao(linha)


def test_telemetria_sabe_a_criticidade_de_cada_tipo() -> None:
    telemetria = Telemetria(0, (R, R, R, R), Regime.CICLO, autorizacoes=(0, 2, 3))
    assert telemetria.criticidade(TipoVeiculo.AMBULANCIA) == 0
    assert telemetria.criticidade(TipoVeiculo.POLICIA) == 3
    assert Telemetria(0, (R, R, R, R), Regime.CICLO).autorizacoes == (0, 0, 0)


@pytest.mark.parametrize(
    "linha",
    [
        b"ST,1,GGRR,C,0,0\n",  # sem as autorizações (antes de 2026-10-06)
        b"ST,1,GGRR,C,0,0,00\n",  # dois tipos
        b"ST,1,GGRR,C,0,0,104\n",  # criticidade fora de 0..3
        b"ST,1,GGRR,C,0,0,1a0\n",
        b"ST,1,GGR,C,0,0,000\n",  # três cores
        b"ST,1,GGRX,C,0,0,000\n",  # cor desconhecida
        b"ST,1,GGRR,X,0,0,000\n",  # regime desconhecido
        b"ST,1,GGRR,C,5,0,000\n",  # rua fora de 0..4
        b"ST,-1,GGRR,C,0,0,000\n",  # ms com sinal
        b"EV,1,PREEMP_INI\n",  # evento de VE sem o VE
        b"EV,1,BOOT,3,AMBULANCIA\n",  # evento sem VE com VE
        b"EV,1,FILA,0,AMBULANCIA\n",  # rua zero
        b"EV,1,FILA,3,HELICOPTERO\n",
        b"EV,1,DESCONHECIDO\n",
        b"ACK,PRE\n",  # protocolo anterior a 2026-10-05
        b"\n",
        b"\xff\xfe\n",
    ],
)
def test_linha_invalida_do_uno(linha: bytes) -> None:
    with pytest.raises(LinhaInvalidaError):
        interpretar(linha)


@given(
    st.integers(0, 2**32 - 1),
    st.tuples(*[st.sampled_from(list(Cor))] * 4),
    st.sampled_from(list(Regime)),
    st.one_of(st.none(), st.integers(1, 4)),
    st.one_of(st.none(), st.integers(1, 4)),
    st.tuples(*[st.integers(0, 3)] * 3),
)
def test_telemetria_ida_e_volta(
    ms: int,
    cores: tuple[Cor, Cor, Cor, Cor],
    regime: Regime,
    ativa: int | None,
    fila: int | None,
    autorizacoes: tuple[int, int, int],
) -> None:
    telemetria = Telemetria(ms, cores, regime, ativa, fila, autorizacoes)
    assert interpretar(telemetria.codificar()) == telemetria


@given(
    st.integers(0, 2**32 - 1),
    st.sampled_from(sorted(EVENTOS_DE_VEICULO)),
    st.integers(1, 4),
    st.sampled_from(list(TipoVeiculo)),
)
def test_evento_ida_e_volta(ms: int, tipo: TipoEvento, rua: int, veiculo: TipoVeiculo) -> None:
    evento = Evento(ms, tipo, rua, veiculo)
    assert interpretar(evento.codificar()) == evento


# ---------------------------------------------------------------------------
# NodeMCU emissor -> notebook
# ---------------------------------------------------------------------------


def test_linha_do_emissor_como_o_sketch_imprime() -> None:
    """`docs/hardware/veiculo_ambulancia.ino`: `"Tag " + uid + " lida -> Enviando " + rua`."""
    linha = b"Tag B7EF8FA0 lida -> Enviando RUA3\r\n"
    leitura = interpretar_leitura_veiculo(linha)

    assert leitura == LeituraVeiculo("B7EF8FA0", 3)
    assert leitura.codificar() == linha.replace(b"\r", b"")


@pytest.mark.parametrize(
    "linha", [b"ets Jan  8 2013\n", b"Tag B7EF8FA0 lida -> Enviando RUA9\n", b"\n"]
)
def test_outras_linhas_do_emissor_nao_sao_envio(linha: bytes) -> None:
    with pytest.raises(LinhaInvalidaError):
        interpretar_leitura_veiculo(linha)
