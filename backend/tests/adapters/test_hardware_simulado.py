"""Dublê do UNO — entrega 5.2 (`context/05` §8).

O dublê só serve se se comportar como o firmware que o contrato descreve: se ele
aceitar o que o UNO recusaria, ou acender o que o UNO não acenderia, a ponte
desenvolvida contra ele quebra na bancada. Por isso os testes aqui conferem o
contrato §6 e §7 — inclusive I1 a I4 sob sequências aleatórias de comandos.
"""

from __future__ import annotations

import asyncio
from itertools import pairwise

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from adapters.hardware.simulado import (
    Regime,
    TransporteSimulado,
    UnoSimulado,
    uno_da_bancada,
)
from bridge.protocolo import (
    Ack,
    Cor,
    Evento,
    MotivoNak,
    Nak,
    NomeComando,
    Resposta,
    Telemetria,
    TipoEvento,
    interpretar,
)
from bridge.transporte import ConexaoPerdidaError

PASSO_S = 0.1
G, Y, R = Cor.VERDE, Cor.AMARELO, Cor.VERMELHO

# Perfil de bancada (parametros.hardware.yaml): verde 3, amarelo 2, all-red 1.
VERDE_S, AMARELO_S, ALL_RED_S = 3.0, 2.0, 1.0
CICLO_S = 4 * (VERDE_S + AMARELO_S + ALL_RED_S)
PIOR_CASO_S = VERDE_S + AMARELO_S + ALL_RED_S  # contrato §7: 6 s


class Bancada:
    """Dirige um `UnoSimulado` em passos de 0,1 s e guarda tudo o que ele disse."""

    def __init__(self, ping_a_cada_s: float | None = 1.0) -> None:
        # O host vivo, como a ponte real: PING a cada 1 s. `None` simula silêncio.
        self.ping_a_cada_s = ping_a_cada_s
        self.uno: UnoSimulado = uno_da_bancada(0.0)
        self.t = 0.0
        self._ultimo_ping = 0.0
        self.respostas: list[tuple[float, Resposta]] = []
        self.amostras: list[tuple[float, tuple[Cor, ...], Regime]] = [
            (0.0, self.uno.cores(), self.uno.regime)
        ]

    def _registrar(self, linhas: list[bytes]) -> list[Resposta]:
        respostas = [interpretar(linha) for linha in linhas]
        self.respostas += [(self.t, r) for r in respostas]
        self.amostras.append((self.t, self.uno.cores(), self.uno.regime))
        return respostas

    def enviar(self, texto: str) -> list[Resposta]:
        """Envia uma linha agora; devolve só a resposta ao comando, sem telemetria."""
        respostas = self._registrar(self.uno.receber(texto.encode("ascii") + b"\n", self.t))
        return [r for r in respostas if not isinstance(r, Telemetria) or texto == "ST?"]

    def ir_ate(self, t_s: float) -> None:
        # Arredonda o alvo na mesma resolução do passo; senão um alvo como
        # 3.0000001 nunca é alcançado e o laço não termina.
        t_s = round(t_s, 6)
        while self.t < t_s:
            self.t = round(min(self.t + PASSO_S, t_s), 6)
            if (
                self.ping_a_cada_s is not None
                and self.t - self._ultimo_ping >= self.ping_a_cada_s - 1e-9
            ):
                self.enviar("PING")
            else:
                self._registrar(self.uno.avancar(self.t))

    def esperar(self, duracao_s: float) -> None:
        self.ir_ate(self.t + duracao_s)

    def ate_verde(self, fase: int, limite_s: float = 60.0) -> float:
        """Avança até a fase acender verde; devolve o instante."""
        fim = self.t + limite_s
        while self.uno.cores()[fase - 1] is not G:
            assert self.t < fim, f"fase {fase} não abriu em {limite_s} s"
            self.esperar(PASSO_S)
        return self.t

    def eventos(self, tipo: TipoEvento) -> list[float]:
        return [t for t, r in self.respostas if isinstance(r, Evento) and r.tipo is tipo]

    def telemetrias(self) -> list[Telemetria]:
        return [r for _, r in self.respostas if isinstance(r, Telemetria)]


@pytest.fixture
def bancada() -> Bancada:
    return Bancada()


# ---------------------------------------------------------------------------
# Ciclo fixo
# ---------------------------------------------------------------------------


def test_liga_em_all_red_e_abre_a_fase_1(bancada: Bancada) -> None:
    """Nenhum verde acende no reset."""
    assert bancada.uno.cores() == (R, R, R, R)
    assert bancada.ate_verde(1) == pytest.approx(ALL_RED_S)
    assert bancada.uno.cores() == (G, R, R, R)


def test_ciclo_fixo_de_24_s_uma_fase_por_vez(bancada: Bancada) -> None:
    inicios = [bancada.ate_verde(fase) for fase in (1, 2, 3, 4, 1)]

    assert inicios[-1] - inicios[0] == pytest.approx(CICLO_S, abs=PASSO_S)
    assert [b - a for a, b in pairwise(inicios)] == pytest.approx([CICLO_S / 4] * 4, abs=PASSO_S)


def test_telemetria_a_2_hz(bancada: Bancada) -> None:
    bancada.esperar(10.0)
    assert len(bancada.telemetrias()) == pytest.approx(20, abs=1)


def test_ciclo_fixo_nao_depende_da_serial() -> None:
    """Sem preempção, silêncio na serial não dispara o watchdog."""
    bancada = Bancada(ping_a_cada_s=None)
    bancada.esperar(30.0)
    assert bancada.eventos(TipoEvento.WATCHDOG) == []


# ---------------------------------------------------------------------------
# Preempção
# ---------------------------------------------------------------------------


def test_transicao_do_exemplo_do_contrato(bancada: Bancada) -> None:
    """Contrato §7: fase 1 verde há 1 s, chega PRE,3,20 — S3 abre 5 s depois."""
    bancada.ate_verde(1)
    bancada.esperar(1.0)
    t_pre = bancada.t

    assert bancada.enviar("PRE,3,20") == [
        Ack(NomeComando.PRE),
        Evento(bancada.uno.t_dispositivo_ms, TipoEvento.PREEMP_INI),
    ]
    assert bancada.ate_verde(3) - t_pre == pytest.approx(5.0, abs=PASSO_S)
    assert bancada.uno.cores() == (R, R, G, R)
    assert bancada.uno.telemetria().em_preempcao


@settings(max_examples=60, deadline=None)
@given(
    t_pre=st.floats(min_value=0.0, max_value=CICLO_S, allow_nan=False),
    fase=st.integers(min_value=1, max_value=4),
)
def test_pior_caso_da_transicao_e_6_s_em_qualquer_instante(t_pre: float, fase: int) -> None:
    """A promessa do contrato §7 — vale também com PRE chegando em amarelo ou all-red."""
    bancada = Bancada()
    bancada.ir_ate(t_pre)
    bancada.enviar(f"PRE,{fase},20")

    assert bancada.ate_verde(fase, limite_s=10.0) - t_pre <= PIOR_CASO_S + PASSO_S


def test_pre_em_amarelo_vai_direto_ao_alvo_sem_abrir_outra_fase(bancada: Bancada) -> None:
    bancada.ate_verde(1)
    bancada.esperar(VERDE_S)  # S1 em amarelo
    assert bancada.uno.cores()[0] is Y

    bancada.enviar("PRE,3,20")
    bancada.ate_verde(3)

    assert not any(cores[1] is G for _, cores, _ in bancada.amostras)


def test_pre_para_a_fase_ja_verde_estende(bancada: Bancada) -> None:
    """Primeiro ramo de E5: não recomeça a transição."""
    t_verde = bancada.ate_verde(1)
    bancada.enviar("PRE,1,10")
    bancada.esperar(5.0)

    assert bancada.uno.cores() == (G, R, R, R)
    assert bancada.t - t_verde > VERDE_S


def test_preempcao_acaba_quando_dur_s_esgota(bancada: Bancada) -> None:
    """`dur_s` conta do recebimento: 6 s de transição + 6 s de verde = 12 s."""
    bancada.ate_verde(1)
    bancada.enviar("PRE,3,12")
    t_pre = bancada.t
    bancada.ate_verde(3)
    bancada.esperar(10.0)

    (fim,) = bancada.eventos(TipoEvento.PREEMP_FIM)
    assert fim - t_pre == pytest.approx(12.0, abs=PASSO_S)
    assert not bancada.uno.em_preempcao
    assert bancada.ate_verde(4) > fim  # o ciclo segue da fase seguinte à preemptada


def test_dur_s_curto_nao_trunca_o_verde_minimo(bancada: Bancada) -> None:
    """I4 vence `dur_s`: o verde alvo dura pelo menos o mínimo, mesmo com pedido curto."""
    bancada.ate_verde(1)
    bancada.enviar("PRE,3,1")
    t_verde = bancada.ate_verde(3)
    bancada.esperar(10.0)

    (fim,) = bancada.eventos(TipoEvento.PREEMP_FIM)
    assert fim - t_verde == pytest.approx(VERDE_S, abs=PASSO_S)


def test_clr_encerra_pelo_amarelo(bancada: Bancada) -> None:
    bancada.enviar("PRE,2,20")
    bancada.ate_verde(2)
    bancada.esperar(VERDE_S)

    respostas = bancada.enviar("CLR")
    bancada.esperar(0.5)

    assert respostas[0] == Ack(NomeComando.CLR)
    assert isinstance(respostas[1], Evento)
    assert respostas[1].tipo is TipoEvento.PREEMP_FIM
    assert bancada.uno.cores()[1] is Y


def test_clr_sem_preempcao_e_recusado(bancada: Bancada) -> None:
    assert bancada.enviar("CLR") == [Nak(NomeComando.CLR, MotivoNak.MODO)]


def test_preempcao_nunca_passa_de_30_s(bancada: Bancada) -> None:
    """Contrato §7, requisito 5: mesmo com o host vivo e sem CLR."""
    bancada.enviar("PRE,3,60")
    t_pre = bancada.t
    bancada.esperar(35.0)

    (timeout,) = bancada.eventos(TipoEvento.TIMEOUT)
    assert timeout - t_pre == pytest.approx(30.0, abs=PASSO_S)
    assert bancada.eventos(TipoEvento.PREEMP_FIM) == [timeout]


def test_fase_fora_da_bancada_e_recusada(bancada: Bancada) -> None:
    assert bancada.enviar("PRE,5,20") == [Nak(NomeComando.PRE, MotivoNak.FASE_INVALIDA)]
    assert not bancada.uno.em_preempcao


# ---------------------------------------------------------------------------
# Watchdog (I6)
# ---------------------------------------------------------------------------


def test_watchdog_derruba_a_preempcao_em_3_s_de_silencio() -> None:
    """O passo 6 da demonstração: cabo puxado no meio da preempção."""
    bancada = Bancada(ping_a_cada_s=None)
    bancada.enviar("PRE,3,20")
    t_pre = bancada.t
    bancada.esperar(5.0)

    (watchdog,) = bancada.eventos(TipoEvento.WATCHDOG)
    assert watchdog - t_pre == pytest.approx(3.0, abs=PASSO_S)
    assert bancada.eventos(TipoEvento.PREEMP_FIM) == [watchdog]
    assert not bancada.uno.em_preempcao


def test_ping_a_cada_1_s_segura_o_watchdog(bancada: Bancada) -> None:
    bancada.enviar("PRE,3,20")
    bancada.esperar(10.0)
    assert bancada.eventos(TipoEvento.WATCHDOG) == []


def test_linha_malformada_nao_alimenta_o_watchdog() -> None:
    bancada = Bancada(ping_a_cada_s=None)
    bancada.enviar("PRE,3,20")
    for _ in range(5):
        bancada.esperar(1.0)
        bancada.enviar("PRE,3")
    assert len(bancada.eventos(TipoEvento.WATCHDOG)) == 1


# ---------------------------------------------------------------------------
# Modo de teste
# ---------------------------------------------------------------------------


def test_test_fora_do_modo_de_teste_e_recusado(bancada: Bancada) -> None:
    assert bancada.enviar("TEST,GRRR") == [Nak(NomeComando.TEST, MotivoNak.MODO)]


def test_modo_de_teste_acende_o_que_se_pede_e_recusa_dois_verdes(bancada: Bancada) -> None:
    bancada.ate_verde(1)
    entrada = bancada.enviar("TESTMODE,1")
    assert entrada[0] == Ack(NomeComando.TESTMODE)
    assert bancada.uno.cores() == (R, R, R, R)
    assert bancada.enviar("ST?")[0] == bancada.uno.telemetria()
    assert bancada.uno.telemetria().em_teste

    assert bancada.enviar("TEST,RYG-") == [Ack(NomeComando.TEST)]
    recusa = bancada.enviar("TEST,GG--")

    assert recusa[0] == Nak(NomeComando.TEST, MotivoNak.CONFLITO)
    assert isinstance(recusa[1], Evento)
    assert recusa[1].tipo is TipoEvento.CONFLITO_RECUSADO
    assert bancada.uno.cores() == (R, Y, G, Cor.APAGADO)


def test_regimes_de_teste_e_preempcao_nunca_coexistem(bancada: Bancada) -> None:
    bancada.enviar("TESTMODE,1")
    assert bancada.enviar("PRE,1,20") == [Nak(NomeComando.PRE, MotivoNak.MODO)]
    bancada.enviar("TESTMODE,0")

    bancada.enviar("PRE,1,20")
    assert bancada.enviar("TESTMODE,1") == [Nak(NomeComando.TESTMODE, MotivoNak.MODO)]


def test_saida_do_teste_volta_pelo_all_red(bancada: Bancada) -> None:
    bancada.enviar("TESTMODE,1")
    bancada.enviar("TEST,--G-")
    bancada.enviar("TESTMODE,0")

    assert bancada.uno.cores() == (R, R, R, R)
    assert bancada.uno.regime is Regime.NORMAL


def test_watchdog_tira_do_modo_de_teste() -> None:
    bancada = Bancada(ping_a_cada_s=None)
    bancada.enviar("TESTMODE,1")
    bancada.esperar(4.0)

    assert bancada.eventos(TipoEvento.WATCHDOG)
    assert bancada.eventos(TipoEvento.TESTE_FIM)
    assert bancada.uno.regime is Regime.NORMAL


# ---------------------------------------------------------------------------
# SAFE e CFG
# ---------------------------------------------------------------------------


def test_safe_fecha_pelo_amarelo_e_segura_o_all_red(bancada: Bancada) -> None:
    bancada.ate_verde(1)
    assert bancada.enviar("SAFE") == [Ack(NomeComando.SAFE)]
    bancada.esperar(10.0)

    assert bancada.uno.cores() == (R, R, R, R)
    assert bancada.uno.regime is Regime.PARADA
    assert any(cores[0] is Y for _, cores, _ in bancada.amostras)

    bancada.enviar("CLR")
    assert bancada.uno.regime is Regime.NORMAL
    bancada.ate_verde(2, limite_s=5.0)


def test_watchdog_tira_da_parada() -> None:
    bancada = Bancada(ping_a_cada_s=None)
    bancada.enviar("SAFE")
    bancada.esperar(4.0)
    assert bancada.uno.regime is Regime.NORMAL


def test_cfg_muda_o_verde_do_ciclo(bancada: Bancada) -> None:
    assert bancada.enviar("CFG,5,2,1") == [Ack(NomeComando.CFG)]
    inicio = bancada.ate_verde(1)
    fim = bancada.ate_verde(2) - AMARELO_S - ALL_RED_S
    assert fim - inicio == pytest.approx(5.0, abs=PASSO_S)


def test_cfg_abaixo_do_verde_minimo_e_recusado(bancada: Bancada) -> None:
    assert bancada.enviar("CFG,2,2,1") == [Nak(NomeComando.CFG, MotivoNak.VERDE_MIN)]


def test_cfg_durante_preempcao_e_recusado(bancada: Bancada) -> None:
    bancada.enviar("PRE,1,20")
    assert bancada.enviar("CFG,4,2,1") == [Nak(NomeComando.CFG, MotivoNak.MODO)]


# ---------------------------------------------------------------------------
# Linhas sem sentido
# ---------------------------------------------------------------------------


def test_ping_e_consulta(bancada: Bancada) -> None:
    assert bancada.enviar("PING") == [Ack(NomeComando.PING)]
    (telemetria,) = bancada.enviar("ST?")
    assert telemetria == bancada.uno.telemetria()


def test_comando_conhecido_malformado_recebe_nak_formato(bancada: Bancada) -> None:
    assert bancada.enviar("PRE,3") == [Nak(NomeComando.PRE, MotivoNak.FORMATO)]


def test_lixo_sem_nome_de_comando_e_ignorado(bancada: Bancada) -> None:
    assert bancada.enviar("\x00\x13lixo") == []


# ---------------------------------------------------------------------------
# Invariantes sob sequências aleatórias de linhas
# ---------------------------------------------------------------------------

# Agrupadas e sorteadas por grupo, não por linha: com as 24 variações de PRE no
# mesmo saco, a sequência TESTMODE,1 -> TEST,GG-- quase nunca saía, e uma guarda de
# I1 sabotada no modo de teste passava despercebida (verificado por mutação).
LINHAS_DE_PREEMPCAO = [f"PRE,{fase},{dur}" for fase in range(0, 6) for dur in (1, 5, 20, 60)]
LINHAS_DE_REGIME = ["CLR", "SAFE", "TESTMODE,1", "TESTMODE,0"]
LINHAS_DE_TESTE = ["TEST,G---", "TEST,RYGR", "TEST,GG--", "TEST,-G-G"]
LINHAS_DIVERSAS = ["PING", "ST?", "CFG,3,2,1", "CFG,4,2,1", "PRE,3", "lixo"]

linhas = st.one_of(
    st.sampled_from(LINHAS_DE_PREEMPCAO),
    st.sampled_from(LINHAS_DE_REGIME),
    st.sampled_from(LINHAS_DE_TESTE),
    st.sampled_from(LINHAS_DIVERSAS),
)


@settings(max_examples=150, deadline=None)
@given(
    st.lists(
        st.tuples(linhas, st.floats(min_value=0.0, max_value=8.0)),
        max_size=25,
    )
)
def test_i1_a_i4_valem_para_qualquer_sequencia_de_linhas(
    sequencia: list[tuple[str, float]],
) -> None:
    bancada = Bancada()
    for linha, espera_s in sequencia:
        bancada.enviar(linha)
        bancada.esperar(espera_s)
    bancada.esperar(10.0)

    inicio_do_verde: dict[int, float] = {}
    for (_, antes, regime_antes), (t, depois, regime_depois) in pairwise(bancada.amostras):
        # I1 vale em todo regime, inclusive no de teste.
        assert depois.count(G) <= 1, f"dois verdes em t={t}: {depois}"

        if Regime.TESTE in (regime_antes, regime_depois):
            inicio_do_verde.clear()  # o teste não promete I2 a I4
            continue
        for modulo, (a, d) in enumerate(zip(antes, depois, strict=True)):
            assert not (a is G and d is R), f"I2: S{modulo + 1} verde -> vermelho em t={t}"
            if d is G and a is not G:
                assert all(c is R for c in antes), f"I3: S{modulo + 1} abriu sem all-red em t={t}"
                inicio_do_verde[modulo] = t
            if a is G and d is Y and modulo in inicio_do_verde:
                duracao = t - inicio_do_verde.pop(modulo)
                assert duracao >= VERDE_S - PASSO_S - 1e-9, f"I4: verde de {duracao:.1f} s"


# ---------------------------------------------------------------------------
# Transporte assíncrono
# ---------------------------------------------------------------------------


async def _ler_ate(transporte: TransporteSimulado, alvo: Resposta, limite_s: float = 2.0) -> None:
    async def _laco() -> None:
        while interpretar(await transporte.ler_linha()) != alvo:
            pass

    await asyncio.wait_for(_laco(), limite_s)


async def test_transporte_responde_com_latencia() -> None:
    transporte = TransporteSimulado(latencia_s=0.05)
    await transporte.abrir()
    try:
        loop = asyncio.get_running_loop()
        inicio = loop.time()
        await transporte.escrever(b"PING\n")
        await _ler_ate(transporte, Ack(NomeComando.PING))
        # Folga da resolução do relógio do Windows (~15,6 ms).
        assert loop.time() - inicio >= 0.05 - 0.02
    finally:
        await transporte.fechar()


async def test_transporte_entrega_telemetria_sem_ser_pedido() -> None:
    transporte = TransporteSimulado()
    await transporte.abrir()
    try:
        linha = await asyncio.wait_for(transporte.ler_linha(), 2.0)
        assert isinstance(interpretar(linha), Telemetria)
    finally:
        await transporte.fechar()


async def test_cabo_puxado_corta_a_ligacao_mas_o_uno_segue_rodando() -> None:
    transporte = TransporteSimulado(passo_s=0.01)
    await transporte.abrir()
    try:
        transporte.puxar_cabo()
        with pytest.raises(ConexaoPerdidaError):
            await transporte.ler_linha()
        with pytest.raises(ConexaoPerdidaError):
            await transporte.escrever(b"PING\n")

        assert transporte.uno is not None
        antes = transporte.uno.t_dispositivo_ms
        await asyncio.sleep(0.1)
        assert transporte.uno.t_dispositivo_ms > antes
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
        await transporte.escrever(b"PING\n")
        await _ler_ate(transporte, Ack(NomeComando.PING))
    finally:
        await transporte.fechar()


async def test_fechar_duas_vezes_nao_e_erro() -> None:
    transporte = TransporteSimulado()
    await transporte.abrir()
    await transporte.fechar()
    await transporte.fechar()
