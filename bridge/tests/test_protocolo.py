"""Protocolo serial ponte <-> UNO — contrato §6, `context/05` §4.

Tudo aqui roda sem hardware: é a condição que o `context/05` §6 impõe ao
`protocolo.py`, e é o que permite ao trio trabalhar com a bancada fora da mesa.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from bridge import protocolo
from bridge.protocolo import (
    Ack,
    ComandoInvalidoError,
    ComandoSerial,
    Cor,
    Evento,
    LinhaInvalidaError,
    MotivoNak,
    Nak,
    NomeComando,
    Telemetria,
    TipoEvento,
    acionamento_direto,
    configurar,
    consultar,
    interpretar,
    interpretar_comando,
    liberar,
    modo_teste,
    parada_segura,
    ping,
    preempcao,
    traduzir,
)
from core.comandos import Comando, TipoComando, fallback_seguro

CRUZ = "PROTO_CRUZ_TESTE"
R, Y, G, A = Cor.VERMELHO, Cor.AMARELO, Cor.VERDE, Cor.APAGADO


# ---------------------------------------------------------------------------
# Host -> UNO: os comandos da tabela do contrato §6, byte a byte
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("comando", "linha"),
    [
        (ping(), b"PING\n"),
        (preempcao(3, 20), b"PRE,3,20\n"),
        (liberar(), b"CLR\n"),
        (configurar(3, 2, 1), b"CFG,3,2,1\n"),
        (consultar(), b"ST?\n"),
        (parada_segura(), b"SAFE\n"),
        (modo_teste(True), b"TESTMODE,1\n"),
        (modo_teste(False), b"TESTMODE,0\n"),
        (acionamento_direto("RYG-"), b"TEST,RYG-\n"),
    ],
    ids=lambda v: v.decode().strip() if isinstance(v, bytes) else "",
)
def test_comando_codifica_exatamente_a_linha_do_contrato(
    comando: ComandoSerial, linha: bytes
) -> None:
    assert comando.codificar() == linha


def test_duracao_arredonda_para_cima() -> None:
    """Arredondar para baixo fecharia o verde antes de o VE passar."""
    assert preempcao(1, 9.2).codificar() == b"PRE,1,10\n"
    assert preempcao(1, 0.1).codificar() == b"PRE,1,1\n"


def test_ruido_de_ponto_flutuante_nao_ganha_um_segundo() -> None:
    assert preempcao(1, 0.1 * 3 * 100 / 3 * 2).codificar() == b"PRE,1,20\n"


@pytest.mark.parametrize("duracao_s", [0.0, -1.0, math.nan, math.inf])
def test_duracao_invalida_e_recusada(duracao_s: float) -> None:
    with pytest.raises(ComandoInvalidoError, match="duracao_s"):
        preempcao(1, duracao_s)


@pytest.mark.parametrize("fase", [0, -1, True])
def test_fase_que_nao_e_inteiro_positivo_e_recusada(fase: int) -> None:
    with pytest.raises(ComandoInvalidoError, match="fase"):
        preempcao(fase, 20)


def test_fase_fora_da_bancada_passa_porque_quem_valida_e_o_uno() -> None:
    """`NAK,PRE,FASE_INVALIDA` é do firmware; a ponte não é uma terceira guarda."""
    assert preempcao(5, 20).codificar() == b"PRE,5,20\n"


def test_cfg_recusa_tempo_fracionario_em_vez_de_arredondar() -> None:
    """Arredondar `amarelo_s = 2.5` para 2 encurtaria o amarelo em silêncio (I2)."""
    with pytest.raises(ComandoInvalidoError, match="amarelo_s"):
        configurar(3, 2.5, 1)


@pytest.mark.parametrize("tempos", [(0, 2, 1), (3, -2, 1), (3, 2, math.nan)])
def test_cfg_recusa_tempo_nao_positivo(tempos: tuple[float, float, float]) -> None:
    with pytest.raises(ComandoInvalidoError):
        configurar(*tempos)


def test_cfg_aceita_float_inteiro_como_vem_do_yaml() -> None:
    """`parametros.hardware.yaml` traz `verde_s: 3.0`, não `3`."""
    assert configurar(3.0, 2.0, 1.0).codificar() == b"CFG,3,2,1\n"


def test_test_com_dois_verdes_sai_para_o_uno_recusar() -> None:
    """É o comando que demonstra `NAK,TEST,CONFLITO` (contrato §6, regra 3)."""
    assert acionamento_direto("GG--").codificar() == b"TEST,GG--\n"


@pytest.mark.parametrize("cores", ["RRR", "RRRRR", "RRRX", "rrrr"])
def test_test_com_cores_malformadas_e_recusado(cores: str) -> None:
    with pytest.raises(ComandoInvalidoError, match="cores"):
        acionamento_direto(cores)


# ---------------------------------------------------------------------------
# Comando abstrato -> linha
# ---------------------------------------------------------------------------


def _comando(tipo: TipoComando, **campos: object) -> Comando:
    return Comando(tipo=tipo, id_semaforo=CRUZ, motivo="teste", **campos)  # type: ignore[arg-type]


def test_ir_para_fase_vira_pre() -> None:
    comando = _comando(TipoComando.IR_PARA_FASE, fase_alvo=3, duracao_s=20.0, id_veiculo="VE_1")
    assert traduzir(comando) == preempcao(3, 20)


def test_estender_verde_de_um_ve_vira_pre_para_a_mesma_fase() -> None:
    comando = _comando(TipoComando.ESTENDER_VERDE, fase_alvo=1, duracao_s=8.4, id_veiculo="VE_1")
    assert traduzir(comando) == preempcao(1, 9)


def test_estender_verde_de_compensacao_nao_vira_pre() -> None:
    """`PRE` marcaria preempção, e o motor omite o VE justamente para não marcar."""
    comando = _comando(TipoComando.ESTENDER_VERDE, fase_alvo=2, duracao_s=2.0)
    assert traduzir(comando) is None


@pytest.mark.parametrize(
    "comando",
    [
        _comando(TipoComando.LIBERAR, id_veiculo="VE_1"),
        _comando(TipoComando.COMPENSAR, id_veiculo="VE_1", duracao_s=12.0),
        fallback_seguro(CRUZ, "invariante violado"),
    ],
    ids=lambda c: c.tipo.value,
)
def test_fim_de_preempcao_vira_clr(comando: Comando) -> None:
    """`COMPENSAR` substitui `LIBERAR`; sem o `CLR` o UNO ficaria preso até o timeout."""
    assert traduzir(comando) == liberar()


def test_fallback_seguro_volta_ao_ciclo_fixo_e_nao_apaga_o_cruzamento() -> None:
    """O fail-safe de `context/01` §6 é o ciclo fixo; `SAFE` é parada de operador."""
    assert traduzir(fallback_seguro(CRUZ, "teste")) != parada_segura()


@pytest.mark.parametrize(
    "campos",
    [{"duracao_s": 20.0}, {"fase_alvo": 3}],
    ids=["sem_fase", "sem_duracao"],
)
def test_preempcao_incompleta_e_recusada(campos: dict[str, object]) -> None:
    comando = _comando(TipoComando.IR_PARA_FASE, id_veiculo="VE_1", **campos)
    with pytest.raises(ComandoInvalidoError):
        traduzir(comando)


@pytest.mark.parametrize("tipo", list(TipoComando))
def test_todo_tipo_de_comando_tem_traducao_definida(tipo: TipoComando) -> None:
    """Um `TipoComando` novo sem tradução precisa falhar aqui, não na bancada."""
    comando = _comando(tipo, fase_alvo=1, duracao_s=5.0, id_veiculo="VE_1")
    assert isinstance(traduzir(comando), ComandoSerial)


# ---------------------------------------------------------------------------
# UNO -> host
# ---------------------------------------------------------------------------


def test_sessao_de_exemplo_do_contrato() -> None:
    """A sessão de `context/05` §4 e contrato §6, linha a linha."""
    sessao = [
        b"ACK,PRE\n",
        b"EV,142350,PREEMP_INI\n",
        b"ST,142350,1,YRRR,0,0\n",
        b"ST,142850,1,RRRR,0,0\n",
        b"ST,143350,3,RRGR,1,0\n",
        b"ACK,CLR\n",
        b"EV,156100,PREEMP_FIM\n",
    ]

    respostas = [interpretar(linha) for linha in sessao]

    assert respostas == [
        Ack(NomeComando.PRE),
        Evento(142350, TipoEvento.PREEMP_INI),
        Telemetria(142350, 1, (Y, R, R, R), em_preempcao=False),
        Telemetria(142850, 1, (R, R, R, R), em_preempcao=False),
        Telemetria(143350, 3, (R, R, G, R), em_preempcao=True),
        Ack(NomeComando.CLR),
        Evento(156100, TipoEvento.PREEMP_FIM),
    ]
    assert not any(r.viola_i1 for r in respostas if isinstance(r, Telemetria))


def test_nak_traz_comando_e_motivo() -> None:
    assert interpretar(b"NAK,TEST,CONFLITO\n") == Nak(NomeComando.TEST, MotivoNak.CONFLITO)


def test_ack_da_consulta() -> None:
    assert interpretar(b"ACK,ST?\n") == Ack(NomeComando.CONSULTA)


def test_aceita_o_terminador_do_serial_println() -> None:
    r"""`Serial.println` termina em `\r\n`, não em `\n`."""
    assert interpretar(b"ACK,PRE\r\n") == Ack(NomeComando.PRE)


def test_aceita_linha_sem_terminador() -> None:
    assert interpretar(b"ACK,PRE") == Ack(NomeComando.PRE)


def test_telemetria_de_firmware_anterior_a_p13_nao_quebra() -> None:
    """Sem o campo `<teste>`: o parser tolera a ausência (contrato §6)."""
    telemetria = interpretar(b"ST,1000,2,RGRR,1\n")

    assert telemetria == Telemetria(1000, 2, (R, G, R, R), em_preempcao=True, em_teste=False)


def test_telemetria_de_modo_de_teste_com_modulo_apagado() -> None:
    assert interpretar(b"ST,500,1,G-R-,0,1\n") == Telemetria(
        500, 1, (G, A, R, A), em_preempcao=False, em_teste=True
    )


def test_telemetria_com_dois_verdes_e_lida_e_denuncia_i1() -> None:
    """A evidência de violação não pode sumir como "linha malformada"."""
    telemetria = interpretar(b"ST,1000,1,GRGR,0,0\n")

    assert isinstance(telemetria, Telemetria)
    assert telemetria.verdes == 2
    assert telemetria.viola_i1


@pytest.mark.parametrize(
    "linha",
    [
        b"",
        b"\r\n",
        b"\xff\xfe ruido de boot\n",
        b"OLA\n",
        b"ACK\n",
        b"ACK,PRE,extra\n",
        b"ACK,XYZ\n",
        b"NAK,PRE\n",
        b"NAK,PRE,SEI_LA\n",
        b"EV,100\n",
        b"EV,100,DESCONHECIDO\n",
        b"EV,-1,WATCHDOG\n",
        b"ST,100,1,RRRR\n",
        b"ST,100,1,RRRR,0,0,0\n",
        b"ST,100,1,RRR,0,0\n",
        b"ST,100,1,RRRX,0,0\n",
        b"ST,100,0,RRRR,0,0\n",
        b"ST,+100,1,RRRR,0,0\n",
        b"ST, 100,1,RRRR,0,0\n",
        b"ST,100,1,RRRR,2,0\n",
        b"ST,100,1,RRRR,0,sim\n",
        b"ack,PRE\n",
    ],
)
def test_linha_fora_do_protocolo_e_recusada(linha: bytes) -> None:
    with pytest.raises(LinhaInvalidaError):
        interpretar(linha)


# ---------------------------------------------------------------------------
# O lado do UNO — interpretar o que o host envia (usado pelo dublê)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "linha",
    [
        b"PRE,3\n",
        b"PRE,3,0\n",
        b"PRE,0,20\n",
        b"PRE,3,2.5\n",
        b"PING,1\n",
        b"CFG,3,2\n",
        b"TESTMODE,2\n",
        b"TEST,GGGGG\n",
        b"PRE;3;20\n",
        b"\n",
    ],
)
def test_comando_fora_do_protocolo_e_recusado_do_lado_do_uno(linha: bytes) -> None:
    with pytest.raises(LinhaInvalidaError):
        interpretar_comando(linha)


# ---------------------------------------------------------------------------
# Ida e volta: o que um lado escreve, o outro lê igual
# ---------------------------------------------------------------------------

_SEGUNDOS = st.integers(min_value=1, max_value=999)
_MS = st.integers(min_value=0, max_value=2**32 - 1)  # unsigned long do millis()

comandos_seriais = st.one_of(
    st.just(ping()),
    st.builds(preempcao, st.integers(min_value=1, max_value=9), _SEGUNDOS),
    st.just(liberar()),
    st.builds(configurar, _SEGUNDOS, _SEGUNDOS, _SEGUNDOS),
    st.just(consultar()),
    st.just(parada_segura()),
    st.builds(modo_teste, st.booleans()),
    st.builds(acionamento_direto, st.text(alphabet="RYG-", min_size=4, max_size=4)),
)

_COR = st.sampled_from(Cor)
respostas = st.one_of(
    st.builds(Ack, st.sampled_from(NomeComando)),
    st.builds(Nak, st.sampled_from(NomeComando), st.sampled_from(MotivoNak)),
    st.builds(
        Telemetria,
        _MS,
        st.integers(min_value=1, max_value=9),
        st.tuples(_COR, _COR, _COR, _COR),
        st.booleans(),
        st.booleans(),
    ),
    st.builds(Evento, _MS, st.sampled_from(TipoEvento)),
)


@given(comandos_seriais)
def test_ida_e_volta_host_para_uno(comando: ComandoSerial) -> None:
    linha = comando.codificar()

    assert linha.endswith(b"\n")
    assert linha.count(b"\n") == 1
    assert interpretar_comando(linha) == comando


@given(respostas)
def test_ida_e_volta_uno_para_host(resposta: protocolo.Resposta) -> None:
    assert interpretar(resposta.codificar()) == resposta


# ---------------------------------------------------------------------------
# Pureza
# ---------------------------------------------------------------------------


def test_protocolo_nao_faz_io() -> None:
    """`context/05` §6: 100% testável sem hardware — nada de porta, rede ou relógio."""
    arvore = ast.parse(Path(protocolo.__file__).read_text(encoding="utf-8"))
    importados = {
        nome.split(".")[0]
        for no in ast.walk(arvore)
        if isinstance(no, ast.Import | ast.ImportFrom)
        for nome in (
            [alias.name for alias in no.names] if isinstance(no, ast.Import) else [no.module or ""]
        )
    }

    assert not importados & {"serial", "asyncio", "socket", "time", "threading", "httpx"}
