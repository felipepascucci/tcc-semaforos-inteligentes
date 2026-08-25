"""Invariantes I1 a I5 (`context/01` §6, `context/06` §3).

São os testes mais importantes do projeto. Falha aqui é falha crítica, não bug.
"""

from __future__ import annotations

import pytest

from core.comandos import Comando, TipoComando
from core.malha import Cruzamento, Fase
from core.modelos import Sinal, Transicao
from core.parametros import Parametros
from core.priorizacao.fases import EstadoControlador, estado_inicial
from core.seguranca import (
    VerificadorSeguranca,
    comandos_criam_conflito,
    verificar_i1,
    verificar_i5,
    verificar_par_de_transicoes,
    verificar_sequencia,
    verificar_transicao,
)
from tests.core.conftest import FASE_ARTERIAL, FASE_TRANSVERSAL

CRUZ = "CRUZ_TESTE_1"


def _transicao(
    t: float,
    fase: int,
    sinal: Sinal,
    fase_anterior: int | None = None,
    duracao: float | None = None,
) -> Transicao:
    return Transicao(
        id_semaforo=CRUZ,
        t=t,
        fase=fase,
        sinal=sinal,
        fase_anterior=fase_anterior,
        duracao_fase_anterior_s=duracao,
    )


# ---------------------------------------------------------------------------
# I1 — dois verdes conflitantes
# ---------------------------------------------------------------------------


def test_i1_aprova_estado_com_um_verde(cruzamento: Cruzamento) -> None:
    estado = estado_inicial(CRUZ, cruzamento)
    assert verificar_i1(estado, cruzamento, t=0.0) == ()


def test_i1_aprova_all_red(cruzamento: Cruzamento) -> None:
    estado = EstadoControlador(CRUZ, FASE_ARTERIAL, sinal=Sinal.VERMELHO)
    assert estado.fases_verdes(cruzamento) == frozenset()
    assert verificar_i1(estado, cruzamento, t=0.0) == ()


def test_matriz_de_conflito_padrao_e_conservadora() -> None:
    """Omitir a matriz precisa significar *split phasing*, não "tudo liberado".

    Uma matriz permissiva por omissão deixaria de acusar conflito num cruzamento
    mal configurado, e o erro só apareceria como dois verdes simultâneos na rua.
    """
    cruzamento = Cruzamento(
        id="SEM_MATRIZ",
        fases=tuple(
            Fase(i, f"F{i}", frozenset({(f"IN{i}", f"OUT{i}")}), 10.0, 5.0, 30.0) for i in (1, 2, 3)
        ),
    )
    assert cruzamento.conflitam(1, 2)
    assert cruzamento.conflitam(2, 3)
    assert not cruzamento.conflitam(1, 1)


def test_comando_que_acenderia_verde_conflitante_e_sinalizado(
    cruzamento: Cruzamento,
) -> None:
    """A metade do motor na defesa em profundidade da decisão P13."""
    estado = estado_inicial(CRUZ, cruzamento)  # fase 1 em verde
    salto = Comando(
        TipoComando.IR_PARA_FASE, CRUZ, fase_alvo=FASE_TRANSVERSAL, duracao_s=0, motivo="t"
    )

    assert comandos_criam_conflito([salto], estado, cruzamento) == (salto,)


def test_transicao_normal_nao_e_sinalizada_como_conflito(cruzamento: Cruzamento) -> None:
    estado = estado_inicial(CRUZ, cruzamento)
    normal = Comando(TipoComando.IR_PARA_FASE, CRUZ, fase_alvo=FASE_TRANSVERSAL, motivo="t")
    assert comandos_criam_conflito([normal], estado, cruzamento) == ()


# ---------------------------------------------------------------------------
# I2 — verde nunca vai direto a vermelho
# ---------------------------------------------------------------------------


def test_i2_acusa_verde_seguido_de_vermelho(cruzamento: Cruzamento) -> None:
    anterior = _transicao(0.0, FASE_ARTERIAL, Sinal.VERDE)
    atual = _transicao(10.0, FASE_ARTERIAL, Sinal.VERMELHO, duracao=10.0)

    violacoes = verificar_par_de_transicoes(anterior, atual, cruzamento)
    assert [v.invariante for v in violacoes] == ["I2"]


def test_i2_aprova_verde_amarelo_vermelho(cruzamento: Cruzamento) -> None:
    sequencia = [
        _transicao(0.0, FASE_ARTERIAL, Sinal.VERDE),
        _transicao(10.0, FASE_ARTERIAL, Sinal.AMARELO, FASE_ARTERIAL, 10.0),
        _transicao(13.0, FASE_ARTERIAL, Sinal.VERMELHO, FASE_ARTERIAL, 3.0),
    ]
    assert verificar_sequencia(sequencia, cruzamento) == ()


# ---------------------------------------------------------------------------
# I3 — all-red entre fases
# ---------------------------------------------------------------------------


def test_i3_acusa_troca_de_fase_sem_all_red(cruzamento: Cruzamento) -> None:
    anterior = _transicao(10.0, FASE_ARTERIAL, Sinal.AMARELO, FASE_ARTERIAL, 10.0)
    atual = _transicao(13.0, FASE_TRANSVERSAL, Sinal.VERDE, FASE_ARTERIAL, 3.0)

    violacoes = verificar_par_de_transicoes(anterior, atual, cruzamento)
    assert [v.invariante for v in violacoes] == ["I3"]


def test_i3_aprova_troca_precedida_de_all_red(cruzamento: Cruzamento) -> None:
    anterior = _transicao(13.0, FASE_ARTERIAL, Sinal.VERMELHO, FASE_ARTERIAL, 3.0)
    atual = _transicao(15.0, FASE_TRANSVERSAL, Sinal.VERDE, FASE_ARTERIAL, 2.0)

    assert verificar_par_de_transicoes(anterior, atual, cruzamento) == ()


# ---------------------------------------------------------------------------
# I4 — verde mínimo
# ---------------------------------------------------------------------------


def test_i4_acusa_verde_truncado(cruzamento: Cruzamento) -> None:
    truncado = _transicao(2.0, FASE_ARTERIAL, Sinal.AMARELO, FASE_ARTERIAL, duracao=2.0)
    violacoes = verificar_transicao(truncado, cruzamento)

    assert [v.invariante for v in violacoes] == ["I4"]
    assert "abaixo do mínimo" in violacoes[0].detalhe


def test_i4_aprova_verde_no_limite(cruzamento: Cruzamento) -> None:
    """Exatamente `verde_min_s` é permitido — o invariante é "não menos que"."""
    no_limite = _transicao(7.0, FASE_ARTERIAL, Sinal.AMARELO, FASE_ARTERIAL, duracao=7.0)
    assert verificar_transicao(no_limite, cruzamento) == ()


def test_i4_e_verificado_na_primeira_transicao_da_execucao(cruzamento: Cruzamento) -> None:
    """Regressão: I4 escapava quando não havia transição anterior.

    Encontrado por teste de mutação — o verde mínimo foi sabotado e a violação
    não era acusada, porque a checagem só rodava sobre pares consecutivos. A
    primeira transição de cada execução é justamente a mais exposta a um comando
    prematuro, logo depois da partida do controlador.
    """
    primeira = _transicao(1.5, FASE_ARTERIAL, Sinal.AMARELO, FASE_ARTERIAL, duracao=1.5)

    verificador = VerificadorSeguranca(parametros=_parametros_padrao())
    estado = estado_inicial(CRUZ, cruzamento)
    violacoes = verificador.verificar(estado, cruzamento, t=1.5, transicoes=[primeira])

    assert [v.invariante for v in violacoes] == ["I4"]


def _parametros_padrao() -> Parametros:
    from tests.core.conftest import construir_parametros

    return construir_parametros()


# ---------------------------------------------------------------------------
# I5 — starvation
# ---------------------------------------------------------------------------


def test_i5_acusa_fase_sem_verde_ha_tempo_demais(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    estado = EstadoControlador(
        CRUZ,
        fase_corrente=FASE_ARTERIAL,
        sinal=Sinal.VERDE,
        t_ultimo_verde={FASE_ARTERIAL: 200.0, FASE_TRANSVERSAL: 50.0},
    )

    violacoes = verificar_i5(estado, cruzamento, parametros, t=200.0)

    assert [v.invariante for v in violacoes] == ["I5"]
    assert f"fase {FASE_TRANSVERSAL}" in violacoes[0].detalhe


def test_i5_aprova_dentro_do_limite(cruzamento: Cruzamento, parametros: Parametros) -> None:
    estado = EstadoControlador(
        CRUZ,
        fase_corrente=FASE_ARTERIAL,
        sinal=Sinal.VERDE,
        t_ultimo_verde={FASE_ARTERIAL: 100.0, FASE_TRANSVERSAL: 30.0},
    )
    assert verificar_i5(estado, cruzamento, parametros, t=100.0) == ()


def test_i5_ignora_a_fase_que_esta_verde_agora(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    """Quem está com o verde não pode estar em starvation por definição."""
    estado = EstadoControlador(
        CRUZ,
        fase_corrente=FASE_ARTERIAL,
        sinal=Sinal.VERDE,
        t_ultimo_verde={FASE_ARTERIAL: 0.0, FASE_TRANSVERSAL: 199.0},
    )
    assert verificar_i5(estado, cruzamento, parametros, t=200.0) == ()


# ---------------------------------------------------------------------------
# Verificador acumulativo
# ---------------------------------------------------------------------------


def test_verificador_soma_violacoes_e_resume(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    """O resumo alimenta a tabela §5 do relatório de validação."""
    verificador = VerificadorSeguranca(parametros=parametros)
    estado = estado_inicial(CRUZ, cruzamento)

    verificador.verificar(
        estado,
        cruzamento,
        t=2.0,
        transicoes=[_transicao(2.0, FASE_ARTERIAL, Sinal.AMARELO, FASE_ARTERIAL, duracao=2.0)],
    )

    assert verificador.seguro is False
    assert verificador.resumo()["I4"] == 1
    assert verificador.resumo()["I1"] == 0


def test_verificador_de_execucao_limpa_reporta_zero(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    """O resultado esperado de toda execução válida (`context/06` §4)."""
    verificador = VerificadorSeguranca(parametros=parametros)
    estado = estado_inicial(CRUZ, cruzamento)

    verificador.verificar(estado, cruzamento, t=0.0)

    assert verificador.seguro is True
    assert set(verificador.resumo().values()) == {0}


def test_violacao_tem_texto_legivel(cruzamento: Cruzamento) -> None:
    """É o que vai para o log de incidente e para o relatório."""
    violacao = verificar_transicao(
        _transicao(2.0, FASE_ARTERIAL, Sinal.AMARELO, FASE_ARTERIAL, duracao=2.0), cruzamento
    )[0]

    texto = str(violacao)
    assert "[I4]" in texto
    assert CRUZ in texto
    assert pytest.approx(2.0) == violacao.t
