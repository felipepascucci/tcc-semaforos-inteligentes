"""Dublê do UNO — entrega 5.2, refeita para a arquitetura de 2026-10-05.

O dublê é o modelo de referência do firmware (`context/05` §8): se ele aceitar o
que o UNO recusaria, ou acender o que o UNO não acenderia, o roteiro de aceitação
validado contra ele aprovaria um firmware errado. Por isso os testes aqui
conferem `context/05` §3 e §4 ponto a ponto — inclusive I1 a I4 sob sequências
aleatórias de chegadas de VE.

As durações são conferidas no `millis()` que vem nas linhas, e o dublê processa
cada mudança no instante exato em que ela vence: as igualdades abaixo são exatas,
sem a folga de um passo de relógio.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from adapters.hardware.simulado import (
    ConfigBancada,
    Entrada,
    TransporteSimulado,
    UnoSimulado,
    config_da_bancada,
)
from bridge.protocolo import (
    EVENTOS_DE_DECISAO,
    Autorizacao,
    Cor,
    Deteccao,
    Evento,
    Regime,
    Resposta,
    Telemetria,
    TipoEvento,
    interpretar,
)
from bridge.transporte import ConexaoPerdidaError
from bridge.verificar import transicoes, violacoes
from core.excecoes import ConfiguracaoInvalidaError
from core.modelos import TipoVeiculo

AMB, BOMB, POL = TipoVeiculo.AMBULANCIA, TipoVeiculo.BOMBEIRO, TipoVeiculo.POLICIA
PASSO_S = 0.1
CONFIG = config_da_bancada()

# Perfil de bancada (parametros.hardware.yaml), em ms.
VERDE, AMARELO, ALL_RED = 3000, 2000, 1000
CICLO = 2 * (VERDE + AMARELO + ALL_RED)
PIOR_CASO = VERDE + AMARELO + ALL_RED
TETO = 30_000
VERDE_DO_TIPO = {AMB: 9000, BOMB: 8000, POL: 7000}

#: A Central com uma ocorrência de cada tipo, na ordem antiga dos tipos: com ela
#: as regras de antes de 2026-10-06 continuam valendo nos cenários.
TODOS = {AMB: 1, BOMB: 2, POL: 3}


class Bancada:
    """Dirige um `UnoSimulado` em passos de 0,1 s e guarda tudo o que ele disse.

    Args:
        autorizacoes: O que a ponte manda logo no boot, como faria ao ver a
            lista da Central. Vazio: o UNO fica negando todos.
    """

    def __init__(
        self, config: ConfigBancada = CONFIG, autorizacoes: dict[TipoVeiculo, int] | None = None
    ) -> None:
        self.uno = UnoSimulado(config, 0.0)
        self.t = 0.0
        self.mensagens: list[Resposta] = []
        self._registrar(self.uno.avancar(0.0))
        for tipo, criticidade in (TODOS if autorizacoes is None else autorizacoes).items():
            self.autorizar(tipo, criticidade)

    def autorizar(self, tipo: TipoVeiculo, criticidade: int) -> list[Resposta]:
        return self.linha(Autorizacao(tipo, criticidade).codificar())

    def _registrar(self, linhas: list[bytes]) -> list[Resposta]:
        mensagens = [interpretar(linha) for linha in linhas]
        self.mensagens += mensagens
        return mensagens

    def ir_ate(self, t_s: float) -> None:
        t_s = round(t_s, 6)
        while self.t < t_s:
            self.t = round(min(self.t + PASSO_S, t_s), 6)
            self._registrar(self.uno.avancar(self.t))

    def esperar(self, duracao_s: float) -> None:
        self.ir_ate(self.t + duracao_s)

    def chegar(self, rua: int, tipo: TipoVeiculo) -> list[Resposta]:
        """O receptor entrega uma detecção agora; devolve só a reação a ela."""
        linha = Deteccao(rua, tipo).codificar().replace(b"\n", b"\r\n")
        return self.linha(linha, Entrada.RECEPTOR)

    def linha(self, linha: bytes, entrada: Entrada = Entrada.USB) -> list[Resposta]:
        self._registrar(self.uno.avancar(self.t))
        return self._registrar(self.uno.receber(linha, self.t, entrada))

    # -- leitura ---------------------------------------------------------------

    def telemetrias(self) -> list[Telemetria]:
        return [m for m in self.mensagens if isinstance(m, Telemetria)]

    def sequencia(self) -> list[tuple[int, str]]:
        return [(st.t_dispositivo_ms, st.estado) for st in self.telemetrias()]

    def eventos(self, tipo: TipoEvento | None = None) -> list[Evento]:
        return [
            m for m in self.mensagens if isinstance(m, Evento) and (tipo is None or m.tipo is tipo)
        ]

    def evento(self, tipo: TipoEvento, depois_ms: int = 0, rua: int | None = None) -> Evento:
        for ev in self.eventos(tipo):
            if ev.t_dispositivo_ms >= depois_ms and (rua is None or ev.rua == rua):
                return ev
        raise AssertionError(f"nenhum {tipo} depois de {depois_ms} ms")

    def quando(self, estado: str, depois_ms: int = 0) -> int:
        """O `millis()` em que o estado de luzes apareceu pela primeira vez."""
        for ms, visto in transicoes(self.sequencia()):
            if ms >= depois_ms and visto == estado:
                return ms
        raise AssertionError(f"{estado} não apareceu depois de {depois_ms} ms")

    def estados_entre(self, inicio_ms: int, fim_ms: int) -> list[str]:
        return [e for ms, e in self.sequencia() if inicio_ms <= ms <= fim_ms]

    @property
    def ms(self) -> int:
        return self.uno.t_dispositivo_ms


@pytest.fixture
def bancada() -> Bancada:
    return Bancada()


def _exclusivo(rua: int) -> str:
    return "".join("G" if i == rua - 1 else "R" for i in range(4))


# ---------------------------------------------------------------------------
# Ciclo
# ---------------------------------------------------------------------------


def test_liga_em_all_red_e_abre_o_eixo_principal(bancada: Bancada) -> None:
    """Nenhum verde no reset; o eixo principal abre depois do all-red."""
    assert bancada.eventos()[0] == Evento(0, TipoEvento.BOOT)
    assert bancada.telemetrias()[0].estado == "RRRR"
    bancada.esperar(2.0)
    assert bancada.quando("GGRR") == ALL_RED


def test_ciclo_de_12_s_com_os_eixos_alternando(bancada: Bancada) -> None:
    bancada.esperar(30.0)
    assert [(ms, e) for ms, e in transicoes(bancada.sequencia()) if ms <= 13_000] == [
        (0, "RRRR"),
        (1000, "GGRR"),
        (4000, "YYRR"),
        (6000, "RRRR"),
        (7000, "RRGG"),
        (10_000, "RRYY"),
        (12_000, "RRRR"),
        (13_000, "GGRR"),
    ]
    assert bancada.quando("GGRR", 2000) - bancada.quando("GGRR") == CICLO


def test_telemetria_a_2_hz_e_a_cada_mudanca(bancada: Bancada) -> None:
    bancada.esperar(10.0)
    periodicas = {ms for ms, _ in bancada.sequencia() if ms % 500 == 0}
    assert periodicas >= set(range(0, 10_001, 500))
    # E toda mudança de luz tem a sua ST, no instante exato.
    assert {ms for ms, _ in transicoes(bancada.sequencia())} <= {
        ms for ms, _ in bancada.sequencia()
    }


def test_uma_st_por_instante() -> None:
    # Sem autorizar no boot: cada AUT muda a ST, e no instante 0 sairiam quatro.
    bancada = Bancada(autorizacoes={})
    bancada.esperar(20.0)
    instantes = [ms for ms, _ in bancada.sequencia()]
    assert len(instantes) == len(set(instantes))


# ---------------------------------------------------------------------------
# VE: transição, duração e volta ao ciclo
# ---------------------------------------------------------------------------


def test_exemplo_do_context_05(bancada: Bancada) -> None:
    """`context/05` §4.2: eixo principal verde há 1 s, ambulância chega pela Rua 3."""
    bancada.ir_ate(14.0)  # o principal abriu em 13 s

    reacao = bancada.chegar(3, AMB)
    assert reacao[0] == Evento(14_000, TipoEvento.PREEMP_INI, 3, AMB)

    bancada.esperar(20.0)
    assert [(ms, e) for ms, e in transicoes(bancada.sequencia()) if 13_000 <= ms <= 31_000] == [
        (13_000, "GGRR"),
        (16_000, "YYRR"),  # o principal cumpre o verde mínimo, depois amarelo
        (18_000, "RRRR"),  # all-red
        (19_000, "RRGR"),  # verde exclusivo da Rua 3
        (28_000, "RRYR"),  # 9 s depois, sai pelo amarelo
        (30_000, "RRRR"),
        (31_000, "GGRR"),  # e volta pelo eixo que esperou
    ]
    assert bancada.evento(TipoEvento.PREEMP_FIM).t_dispositivo_ms == 28_000


@settings(max_examples=80, deadline=None)
@given(
    t_chegada=st.floats(min_value=0.0, max_value=CICLO * 2 / 1000, allow_nan=False),
    rua=st.integers(min_value=1, max_value=4),
)
def test_verde_exclusivo_em_ate_6_s_em_qualquer_instante(t_chegada: float, rua: int) -> None:
    """A promessa de `context/05` §3.4 — chegando em verde, amarelo ou all-red."""
    bancada = Bancada()
    bancada.ir_ate(t_chegada)
    bancada.chegar(rua, AMB)
    chegada = bancada.ms
    bancada.esperar(7.0)

    assert bancada.quando(_exclusivo(rua), chegada) - chegada <= PIOR_CASO


@pytest.mark.parametrize("tipo", [AMB, BOMB, POL])
def test_verde_do_ve_dura_o_do_tipo_contado_do_verde_exclusivo(
    bancada: Bancada, tipo: TipoVeiculo
) -> None:
    bancada.ir_ate(2.0)
    bancada.chegar(3, tipo)
    bancada.esperar(20.0)

    verde = bancada.quando(_exclusivo(3))
    fim = bancada.evento(TipoEvento.PREEMP_FIM, rua=3).t_dispositivo_ms
    assert fim - verde == VERDE_DO_TIPO[tipo]


def test_ve_no_eixo_verde_nao_apaga_o_proprio_verde(bancada: Bancada) -> None:
    """`context/05` §3.4, item 4: só o S2 sai, pelo amarelo."""
    bancada.ir_ate(13.5)  # principal verde desde 13 s
    inicio = bancada.chegar(1, POL)[0].t_dispositivo_ms
    bancada.esperar(15.0)
    fim = bancada.evento(TipoEvento.PREEMP_FIM, rua=1).t_dispositivo_ms

    assert all(e[0] == "G" for e in bancada.estados_entre(inicio, fim - 1))
    assert bancada.quando("GYRR", inicio) == 16_000  # S2 cumpriu o mínimo desde 13 s
    assert bancada.quando("GRRR", inicio) == 18_000
    assert fim == 18_000 + VERDE_DO_TIPO[POL]


def test_ve_chegando_no_amarelo_nao_volta_ao_verde(bancada: Bancada) -> None:
    """Nunca amarelo -> verde: o S1 vai a vermelho, espera o all-red e reabre."""
    bancada.ir_ate(4.5)  # principal em amarelo desde 4 s
    bancada.chegar(1, AMB)
    bancada.esperar(10.0)

    assert bancada.quando("RRRR", 4500) == 6000
    assert bancada.quando("GRRR", 4500) == 7000
    assert "RRGG" not in bancada.estados_entre(4500, 7000)  # o transversal não abriu


@pytest.mark.parametrize(
    ("rua", "eixo_oposto"), [(1, "RRGG"), (2, "RRGG"), (3, "GGRR"), (4, "GGRR")]
)
def test_fim_da_emergencia_volta_pelo_eixo_oposto(rua: int, eixo_oposto: str) -> None:
    bancada = Bancada()
    bancada.ir_ate(2.0)
    bancada.chegar(rua, POL)
    bancada.esperar(20.0)
    fim = bancada.evento(TipoEvento.PREEMP_FIM).t_dispositivo_ms
    primeiro_verde = next(e for ms, e in bancada.sequencia() if ms > fim and "G" in e)
    assert primeiro_verde == eixo_oposto


# ---------------------------------------------------------------------------
# Decisão (context/05 §3.3)
# ---------------------------------------------------------------------------


def test_mesmo_ve_relendo_a_mesma_rua_renova(bancada: Bancada) -> None:
    bancada.ir_ate(2.0)
    bancada.chegar(3, AMB)
    bancada.esperar(6.0)  # verde exclusivo já estabelecido
    reacao = bancada.chegar(3, AMB)
    renovado_em = bancada.ms
    bancada.esperar(15.0)

    assert reacao[0] == Evento(renovado_em, TipoEvento.RENOVADO, 3, AMB)
    assert bancada.eventos(TipoEvento.PREEMP_INI) == [bancada.eventos(TipoEvento.PREEMP_INI)[0]]
    assert bancada.evento(TipoEvento.PREEMP_FIM).t_dispositivo_ms == renovado_em + 9000


def test_prioridade_maior_interrompe_e_o_interrompido_vai_para_a_fila(bancada: Bancada) -> None:
    bancada.ir_ate(2.0)
    bancada.chegar(1, BOMB)
    bancada.esperar(6.0)
    reacao = bancada.chegar(3, AMB)
    interrompido_em = bancada.ms

    assert [(ev.tipo, ev.rua) for ev in reacao if isinstance(ev, Evento)] == [
        (TipoEvento.PREEMP_INI, 3),
        (TipoEvento.FILA, 1),
    ]
    assert bancada.uno.telemetria().rua_fila == 1

    bancada.esperar(30.0)
    fim_amb = bancada.evento(TipoEvento.PREEMP_FIM, interrompido_em, rua=3).t_dispositivo_ms
    retomada = bancada.evento(TipoEvento.PREEMP_INI, fim_amb, rua=1)
    assert retomada.t_dispositivo_ms == fim_amb
    verde = bancada.quando("GRRR", fim_amb)
    assert bancada.evento(TipoEvento.PREEMP_FIM, verde, rua=1).t_dispositivo_ms == verde + 8000


def test_fila_de_um_lugar_e_descarte(bancada: Bancada) -> None:
    bancada.ir_ate(2.0)
    bancada.chegar(3, AMB)
    assert bancada.chegar(1, POL)[0].tipo is TipoEvento.FILA
    # Bombeiro é mais prioritário que a polícia da fila: toma o lugar dela.
    reacao = [m for m in bancada.chegar(2, BOMB) if isinstance(m, Evento)]
    assert [(ev.tipo, ev.veiculo) for ev in reacao] == [
        (TipoEvento.FILA, BOMB),
        (TipoEvento.DESCARTADO, POL),
    ]
    # Outro bombeiro não passa à frente do que já está na fila.
    assert bancada.chegar(4, BOMB)[0].tipo is TipoEvento.DESCARTADO
    # Nem uma polícia.
    assert bancada.chegar(4, POL)[0].tipo is TipoEvento.DESCARTADO


def test_interrompido_desloca_quem_estava_na_fila(bancada: Bancada) -> None:
    bancada.ir_ate(2.0)
    bancada.chegar(1, BOMB)
    bancada.chegar(2, POL)  # fila: polícia
    reacao = [m for m in bancada.chegar(3, AMB) if isinstance(m, Evento)]
    assert [(ev.tipo, ev.veiculo) for ev in reacao] == [
        (TipoEvento.PREEMP_INI, AMB),
        (TipoEvento.FILA, BOMB),
        (TipoEvento.DESCARTADO, POL),
    ]


def test_mesma_rua_tipo_mais_prioritario_assume_sem_transicao(bancada: Bancada) -> None:
    bancada.ir_ate(2.0)
    bancada.chegar(1, POL)
    bancada.esperar(6.0)
    estados_antes = len(transicoes(bancada.sequencia()))
    bancada.chegar(1, AMB)
    bancada.esperar(2.0)

    assert len(transicoes(bancada.sequencia())) == estados_antes  # S1 segue verde
    assert bancada.uno.telemetria().rua_fila == 1


def test_teto_de_30_s_com_renovacoes(bancada: Bancada) -> None:
    bancada.ir_ate(2.0)
    inicio = bancada.chegar(4, AMB)[0].t_dispositivo_ms
    for _ in range(7):  # renova até 30 s, sem passar do teto
        bancada.esperar(4.0)
        bancada.chegar(4, AMB)
    bancada.esperar(10.0)

    timeout = bancada.evento(TipoEvento.TIMEOUT)
    assert timeout.t_dispositivo_ms == inicio + TETO
    fim = bancada.evento(TipoEvento.PREEMP_FIM)
    assert fim.t_dispositivo_ms == timeout.t_dispositivo_ms
    assert bancada.mensagens.index(timeout) < bancada.mensagens.index(fim)
    assert bancada.quando("GGRR", timeout.t_dispositivo_ms) > timeout.t_dispositivo_ms


def test_teto_descarta_a_fila(bancada: Bancada) -> None:
    bancada.ir_ate(2.0)
    bancada.chegar(4, AMB)
    bancada.chegar(1, POL)
    for _ in range(7):
        bancada.esperar(4.0)
        bancada.chegar(4, AMB)
    bancada.esperar(5.0)

    assert bancada.eventos(TipoEvento.TIMEOUT)
    assert bancada.eventos(TipoEvento.PREEMP_INI) == [bancada.eventos(TipoEvento.PREEMP_INI)[0]]
    assert bancada.uno.regime is Regime.CICLO


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "linha", [b"RUA9,AMBULANCIA\r\n", b"RUA3,HELICOPTERO\n", b"RUA3,AMBULANCIA,X\n", b",\n"]
)
def test_linha_com_virgula_e_conteudo_invalido_e_recusada(bancada: Bancada, linha: bytes) -> None:
    bancada.ir_ate(2.0)
    reacao = bancada.linha(linha)

    assert [m for m in reacao if isinstance(m, Evento)] == [Evento(2000, TipoEvento.RECUSADO)]
    assert bancada.uno.regime is Regime.CICLO


def test_lixo_sem_virgula_e_ignorado(bancada: Bancada) -> None:
    """É o que o ESP8266 imprime no próprio boot, a 74880 baud."""
    bancada.ir_ate(2.0)
    assert bancada.linha(b"\x00\xfe ets Jan  8 2013 rst cause:2\n") == []


@pytest.mark.parametrize("linha", [b"3,BOMBEIRO\r\n", b" RUA3 , BOMBEIRO \r\n"])
def test_formatos_aceitos_pelo_sketch(bancada: Bancada, linha: bytes) -> None:
    bancada.ir_ate(2.0)
    assert bancada.linha(linha)[0] == Evento(2000, TipoEvento.PREEMP_INI, 3, BOMB)


@pytest.mark.parametrize("entrada", list(Entrada))
def test_linha_maior_que_o_buffer_da_entrada_e_recusada(bancada: Bancada, entrada: Entrada) -> None:
    """32 bytes no receptor, 72 no USB, como no firmware."""
    linha = b" " * 30 + b"RUA3,BOMBEIRO\r\n"  # 44 bytes antes do \n
    bancada.ir_ate(2.0)
    reacao = [m for m in bancada.linha(linha, entrada) if isinstance(m, Evento)]
    esperado = TipoEvento.RECUSADO if entrada is Entrada.RECEPTOR else TipoEvento.PREEMP_INI
    assert reacao[0].tipo is esperado


# ---------------------------------------------------------------------------
# A Central na bancada (decisão de 2026-10-06)
# ---------------------------------------------------------------------------


def test_liga_negando_todos() -> None:
    bancada = Bancada(autorizacoes={})
    assert bancada.telemetrias()[0].autorizacoes == (0, 0, 0)
    bancada.ir_ate(2.0)
    reacao = bancada.chegar(3, AMB)
    assert reacao[0] == Evento(2000, TipoEvento.SEM_OCORRENCIA, 3, AMB)
    assert bancada.uno.regime is Regime.CICLO


def test_autorizacao_muda_a_st_na_hora_sem_evento() -> None:
    bancada = Bancada(autorizacoes={})
    bancada.ir_ate(2.0)
    reacao = bancada.autorizar(BOMB, 2)
    assert reacao == [bancada.uno.telemetria()]
    assert bancada.uno.telemetria().autorizacoes == (0, 2, 0)
    assert bancada.uno.telemetria().criticidade(BOMB) == 2
    # Repetir a mesma lista não muda nada, e não sai ST.
    assert bancada.autorizar(BOMB, 2) == []


def test_ocorrencia_encerrada_vale_da_proxima_leitura(bancada: Bancada) -> None:
    """O VE já atendido termina o verde; a releitura seguinte é negada."""
    bancada.ir_ate(2.0)
    bancada.chegar(3, AMB)
    bancada.esperar(6.0)
    bancada.autorizar(AMB, 0)
    assert bancada.uno.regime is Regime.EMERGENCIA
    assert bancada.chegar(3, AMB)[0].tipo is TipoEvento.SEM_OCORRENCIA
    bancada.esperar(10.0)
    assert bancada.evento(TipoEvento.PREEMP_FIM).t_dispositivo_ms == bancada.quando("RRGR") + 9000


def test_criticidade_e_nao_o_tipo_decide_quem_interrompe() -> None:
    """Polícia com risco à vida interrompe ambulância com urgência."""
    bancada = Bancada(autorizacoes={AMB: 3, POL: 1})
    bancada.ir_ate(2.0)
    bancada.chegar(3, AMB)
    reacao = [m for m in bancada.chegar(1, POL) if isinstance(m, Evento)]
    assert [(ev.tipo, ev.veiculo) for ev in reacao] == [
        (TipoEvento.PREEMP_INI, POL),
        (TipoEvento.FILA, AMB),
    ]


def test_mesma_criticidade_nao_interrompe_nem_toma_a_fila() -> None:
    """A guarda de oscilação do motor (P20): no mesmo nível, fica quem chegou."""
    bancada = Bancada(autorizacoes={AMB: 1, BOMB: 1, POL: 1})
    bancada.ir_ate(2.0)
    bancada.chegar(1, BOMB)
    assert bancada.chegar(3, AMB)[0].tipo is TipoEvento.FILA
    assert bancada.chegar(2, POL)[0].tipo is TipoEvento.DESCARTADO


def test_criticidade_vai_com_o_ve_lido() -> None:
    """Mudar a Central depois não reordena quem já está atendido ou na fila."""
    bancada = Bancada(autorizacoes={AMB: 2, BOMB: 2})
    bancada.ir_ate(2.0)
    bancada.chegar(1, BOMB)
    bancada.autorizar(BOMB, 3)
    # O bombeiro foi lido com 2: a ambulância, também 2, não o interrompe.
    assert bancada.chegar(3, AMB)[0].tipo is TipoEvento.FILA


def test_aut_vindo_do_receptor_e_recusado() -> None:
    """Um VE não se autoriza pelo rádio."""
    bancada = Bancada(autorizacoes={})
    bancada.ir_ate(2.0)
    reacao = bancada.linha(Autorizacao(AMB, 1).codificar(), Entrada.RECEPTOR)
    assert [m for m in reacao if isinstance(m, Evento)] == [Evento(2000, TipoEvento.RECUSADO)]
    assert bancada.uno.autorizacoes == (0, 0, 0)


@pytest.mark.parametrize(
    "linha",
    [b"AUT,AMBULANCIA,4\n", b"AUT,HELICOPTERO,1\n", b"AUT,AMBULANCIA\n", b"AUT, AMBULANCIA,1\n"],
)
def test_autorizacao_invalida_e_recusada(linha: bytes) -> None:
    bancada = Bancada(autorizacoes={})
    bancada.ir_ate(2.0)
    reacao = bancada.linha(linha)
    assert [m for m in reacao if isinstance(m, Evento)] == [Evento(2000, TipoEvento.RECUSADO)]
    assert bancada.uno.autorizacoes == (0, 0, 0)


# ---------------------------------------------------------------------------
# Propriedades sob sequências aleatórias de chegadas
# ---------------------------------------------------------------------------

chegadas = st.lists(
    st.tuples(
        st.one_of(
            st.tuples(st.integers(1, 4), st.sampled_from(list(TipoVeiculo))),
            st.sampled_from([b"RUA9,AMBULANCIA\n", b"lixo\n"]),
            st.builds(
                lambda tipo, criticidade: Autorizacao(tipo, criticidade).codificar(),
                st.sampled_from(list(TipoVeiculo)),
                st.integers(0, 3),
            ),
        ),
        st.floats(min_value=0.0, max_value=8.0, allow_nan=False),
    ),
    max_size=20,
)


def _rodar(sequencia: list[tuple[tuple[int, TipoVeiculo] | bytes, float]]) -> Bancada:
    bancada = Bancada()
    for entrada, espera_s in sequencia:
        if isinstance(entrada, bytes):
            bancada.linha(entrada)
        else:
            reacao = bancada.chegar(*entrada)
            # Toda detecção válida recebe exatamente uma decisão sobre o VE
            # novo, antes de tudo. Depois dela podem vir a FILA do interrompido e
            # o DESCARTADO de quem perdeu o lugar.
            primeiro = reacao[0]
            assert isinstance(primeiro, Evento)
            assert primeiro.tipo in EVENTOS_DE_DECISAO
            assert (primeiro.rua, primeiro.veiculo) == entrada
            assert len([m for m in reacao if isinstance(m, Evento)]) <= 3
        bancada.esperar(espera_s)
    bancada.esperar(45.0)
    return bancada


@settings(max_examples=200, deadline=None)
@given(chegadas)
def test_i1_a_i4_valem_para_qualquer_sequencia_de_chegadas(
    sequencia: list[tuple[tuple[int, TipoVeiculo] | bytes, float]],
) -> None:
    bancada = _rodar(sequencia)
    assert violacoes(bancada.sequencia()) == []


@settings(max_examples=100, deadline=None)
@given(chegadas)
def test_emergencia_nunca_passa_do_teto_e_sempre_volta_ao_ciclo(
    sequencia: list[tuple[tuple[int, TipoVeiculo] | bytes, float]],
) -> None:
    bancada = _rodar(sequencia)
    inicio: int | None = None
    for telemetria in bancada.telemetrias():
        if telemetria.regime is Regime.EMERGENCIA and inicio is None:
            inicio = telemetria.t_dispositivo_ms
        elif telemetria.regime is Regime.CICLO:
            inicio = None
        if inicio is not None:
            assert telemetria.t_dispositivo_ms - inicio <= TETO
    assert bancada.uno.regime is Regime.CICLO  # 45 s depois da última chegada


@settings(max_examples=100, deadline=None)
@given(chegadas)
def test_nenhuma_aproximacao_passa_de_120_s_no_vermelho(
    sequencia: list[tuple[tuple[int, TipoVeiculo] | bytes, float]],
) -> None:
    """I5 na bancada, garantida pelo teto (`context/05` §3.4, item 7)."""
    bancada = _rodar(sequencia)
    vermelho_desde: dict[int, int] = {}
    for ms, estado in transicoes(bancada.sequencia()):
        for i, cor in enumerate(estado):
            if cor != Cor.VERMELHO.value:
                vermelho_desde.pop(i, None)
            else:
                assert ms - vermelho_desde.setdefault(i, ms) <= 120_000


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------


def test_config_da_bancada_vem_do_perfil_hardware() -> None:
    assert (CONFIG.verde_s, CONFIG.amarelo_s, CONFIG.all_red_s) == (3.0, 2.0, 1.0)
    assert CONFIG.teto_s == 30.0
    assert CONFIG.verde_por_tipo_s == {AMB: 9.0, BOMB: 8.0, POL: 7.0}


@pytest.mark.parametrize(
    ("alteracao", "trecho"),
    [
        ({"teto_s": 15.0}, "teto cortaria"),
        ({"verde_s": 2.0}, "verde_s abaixo"),
        ({"verde_por_tipo_s": {AMB: 9.0}}, "todos os tipos"),
        ({"verde_por_tipo_s": {AMB: 9.0, BOMB: 8.0, POL: 1.0}}, "verde de VE abaixo"),
        ({"amarelo_s": 0.0}, "precisam ser > 0"),
    ],
)
def test_config_incoerente_falha_cedo(alteracao: dict[str, object], trecho: str) -> None:
    with pytest.raises(ConfiguracaoInvalidaError, match=trecho):
        replace(CONFIG, **alteracao).validar()  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Transporte assíncrono
# ---------------------------------------------------------------------------


async def _ler_ate(transporte: TransporteSimulado, tipo: TipoEvento, limite_s: float = 2.0) -> None:
    async def _laco() -> None:
        while True:
            mensagem = interpretar((await transporte.ler_linha()).dados)
            if isinstance(mensagem, Evento) and mensagem.tipo is tipo:
                return

    await asyncio.wait_for(_laco(), limite_s)


async def test_transporte_decide_com_latencia() -> None:
    transporte = TransporteSimulado(latencia_s=0.05)
    await transporte.abrir()
    try:
        await transporte.escrever(Autorizacao(AMB, 1).codificar())
        loop = asyncio.get_running_loop()
        inicio = loop.time()
        await transporte.escrever(Deteccao(3, AMB).codificar())
        await _ler_ate(transporte, TipoEvento.PREEMP_INI)
        # Folga da resolução do relógio do Windows (~15,6 ms).
        assert loop.time() - inicio >= 0.05 - 0.02
    finally:
        await transporte.fechar()


async def test_transporte_entrega_boot_e_telemetria_sem_ser_pedido() -> None:
    transporte = TransporteSimulado()
    await transporte.abrir()
    try:
        primeiras = [interpretar((await asyncio.wait_for(transporte.ler_linha(), 2.0)).dados)]
        primeiras.append(interpretar((await asyncio.wait_for(transporte.ler_linha(), 2.0)).dados))
        assert primeiras[0] == Evento(0, TipoEvento.BOOT)
        assert isinstance(primeiras[1], Telemetria)
    finally:
        await transporte.fechar()


async def test_receptor_no_a0_e_ponte_no_usb_chegam_os_dois() -> None:
    """`context/05` §1, desde 2026-10-06: o RX é só do USB, e o receptor tem o A0."""
    transporte = TransporteSimulado(passo_s=0.01)
    await transporte.abrir()
    try:
        await transporte.escrever(Autorizacao(AMB, 1).codificar())
        transporte.simular_receptor(Deteccao(3, AMB))
        await _ler_ate(transporte, TipoEvento.PREEMP_INI)
        await transporte.escrever(Deteccao(1, AMB).codificar())
        await _ler_ate(transporte, TipoEvento.FILA)
    finally:
        await transporte.fechar()


async def test_reabrir_a_porta_perde_a_lista_da_central() -> None:
    """O DTR reinicia o UNO, e ele volta negando todos: a ponte reenvia."""
    transporte = TransporteSimulado(passo_s=0.01)
    await transporte.abrir()
    try:
        await transporte.escrever(Autorizacao(AMB, 1).codificar())
        await asyncio.sleep(0.05)
        assert transporte.uno is not None
        assert transporte.uno.autorizacoes == (1, 0, 0)
        transporte.puxar_cabo()
        await transporte.abrir()
        assert transporte.uno.autorizacoes == (0, 0, 0)
    finally:
        await transporte.fechar()


async def test_cabo_puxado_corta_a_ligacao_e_desliga_a_placa() -> None:
    transporte = TransporteSimulado(passo_s=0.01)
    await transporte.abrir()
    try:
        await asyncio.sleep(0.05)
        transporte.puxar_cabo()
        with pytest.raises(ConexaoPerdidaError):
            await transporte.ler_linha()
        with pytest.raises(ConexaoPerdidaError):
            await transporte.escrever(b"RUA3,AMBULANCIA\n")
    finally:
        await transporte.fechar()


async def test_abrir_de_novo_reinicia_a_placa() -> None:
    """O DTR do USB serial reseta o UNO toda vez que a porta é aberta."""
    transporte = TransporteSimulado(passo_s=0.01)
    await transporte.abrir()
    try:
        await asyncio.sleep(0.2)
        primeiro = transporte.uno
        transporte.puxar_cabo()
        await transporte.abrir()

        assert transporte.uno is not primeiro
        assert transporte.uno is not None
        assert transporte.uno.t_dispositivo_ms < 100
        await _ler_ate(transporte, TipoEvento.BOOT)
    finally:
        await transporte.fechar()


async def test_fechar_duas_vezes_nao_e_erro() -> None:
    transporte = TransporteSimulado()
    await transporte.abrir()
    await transporte.fechar()
    await transporte.fechar()
