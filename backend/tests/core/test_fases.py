"""E4, E5 e a máquina de estados do controlador."""

from __future__ import annotations

import pytest

from core.comandos import Comando, TipoComando
from core.excecoes import FaseInexistenteError
from core.malha import Cruzamento
from core.modelos import Sinal
from core.parametros import Parametros
from core.priorizacao.fases import (
    EstadoControlador,
    avancar,
    duracao_da_transicao_s,
    estado_inicial,
    selecionar_fase,
)
from tests.core.conftest import FASE_ARTERIAL, FASE_TRANSVERSAL, construir_parametros

PASSO_S = 0.1  # o mesmo `--step-length` do loop de simulação (context/01 §3)


def _rodar(
    estado: EstadoControlador,
    cruzamento: Cruzamento,
    parametros: Parametros,
    ate_t: float,
    comandos_em: dict[float, tuple[Comando, ...]] | None = None,
    t_inicial: float = 0.0,
) -> tuple[EstadoControlador, list]:
    """Avança a máquina passo a passo, aplicando comandos em instantes dados."""
    comandos_em = comandos_em or {}
    transicoes: list = []
    t = t_inicial
    while t < ate_t:
        t = round(t + PASSO_S, 4)
        comandos = comandos_em.get(round(t, 1), ())
        avanco = avancar(estado, t, cruzamento, parametros, comandos)
        estado = avanco.estado
        transicoes.extend(avanco.transicoes)
    return estado, transicoes


# ---------------------------------------------------------------------------
# E4 — seleção da fase
# ---------------------------------------------------------------------------


def test_e4_escolhe_a_fase_que_serve_o_movimento(cruzamento: Cruzamento) -> None:
    assert selecionar_fase(cruzamento, ("E0", "E1")) == FASE_ARTERIAL
    assert selecionar_fase(cruzamento, ("T1_IN", "T1_OUT")) == FASE_TRANSVERSAL


def test_e4_recusa_movimento_sem_fase(cruzamento: Cruzamento) -> None:
    """Mapa de fases incompleto é erro de configuração, não de operação."""
    with pytest.raises(FaseInexistenteError, match="serve o movimento"):
        selecionar_fase(cruzamento, ("VIA_INEXISTENTE", "OUTRA"))


# ---------------------------------------------------------------------------
# E5 — transição segura
# ---------------------------------------------------------------------------


def test_transicao_segue_verde_amarelo_allred_alvo(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    """A sequência obrigatória de `context/01` §5.2, sem atalho."""
    estado = estado_inicial("CRUZ_TESTE_1", cruzamento)
    ir = Comando(
        tipo=TipoComando.IR_PARA_FASE,
        id_semaforo="CRUZ_TESTE_1",
        fase_alvo=FASE_TRANSVERSAL,
        motivo="teste",
    )

    # Comando aos 10 s: verde mínimo (7 s) já cumprido.
    estado, transicoes = _rodar(
        estado, cruzamento, parametros, ate_t=20.0, comandos_em={10.0: (ir,)}
    )

    sequencia = [(round(t.t, 1), t.sinal, t.fase) for t in transicoes]
    assert sequencia == [
        (10.0, Sinal.AMARELO, FASE_ARTERIAL),  # I2
        (13.0, Sinal.VERMELHO, FASE_ARTERIAL),  # I3 — all-red
        (15.0, Sinal.VERDE, FASE_TRANSVERSAL),
    ]
    assert estado.fase_corrente == FASE_TRANSVERSAL
    assert estado.sinal is Sinal.VERDE


def test_verde_nao_e_truncado_antes_do_minimo(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    """I4 — o comando chega aos 2 s, mas o amarelo só acende aos 7 s."""
    estado = estado_inicial("CRUZ_TESTE_1", cruzamento)
    ir = Comando(
        tipo=TipoComando.IR_PARA_FASE,
        id_semaforo="CRUZ_TESTE_1",
        fase_alvo=FASE_TRANSVERSAL,
        motivo="teste",
    )

    _, transicoes = _rodar(estado, cruzamento, parametros, ate_t=10.0, comandos_em={2.0: (ir,)})

    primeira = transicoes[0]
    assert primeira.sinal is Sinal.AMARELO
    assert primeira.t == pytest.approx(7.0, abs=0.11)  # verde_min_s
    assert primeira.duracao_fase_anterior_s >= parametros.verde_min_s - 1e-9


def test_fase_alvo_igual_a_corrente_nao_gera_transicao(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    """`se fase_atual == fase_alvo: estender` — não recomeçar a transição."""
    estado = estado_inicial("CRUZ_TESTE_1", cruzamento)
    estender = Comando(
        tipo=TipoComando.ESTENDER_VERDE,
        id_semaforo="CRUZ_TESTE_1",
        fase_alvo=FASE_ARTERIAL,
        duracao_s=45.0,
        motivo="teste",
    )

    estado, transicoes = _rodar(
        estado, cruzamento, parametros, ate_t=35.0, comandos_em={5.0: (estender,)}
    )

    # Sem a extensão o verde acabaria aos 30 s (duracao_base_s).
    assert transicoes == []
    assert estado.fase_corrente == FASE_ARTERIAL
    assert estado.sinal is Sinal.VERDE


def test_extensao_respeita_o_teto_de_verde_max(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    """Estender sem teto seria starvation por construção nas demais fases (I5).

    Com `preempcao_timeout_s` folgado, o teto que sobra é `verde_max_s`.
    """
    frouxo = construir_parametros(preempcao_timeout_s=300.0)
    estado = estado_inicial("CRUZ_TESTE_1", cruzamento)
    exagero = Comando(
        tipo=TipoComando.ESTENDER_VERDE,
        id_semaforo="CRUZ_TESTE_1",
        duracao_s=9999.0,
        motivo="teste",
    )

    _, transicoes = _rodar(estado, cruzamento, frouxo, ate_t=80.0, comandos_em={1.0: (exagero,)})

    amarelo = next(t for t in transicoes if t.sinal is Sinal.AMARELO)
    assert amarelo.t == pytest.approx(frouxo.verde_max_s, abs=0.11)


def test_timeout_de_preempcao_limita_antes_de_verde_max(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    """Dois tetos protegem a transversal, e vale o menor.

    No perfil de simulação `preempcao_timeout_s` (45 s) é mais apertado que
    `verde_max_s` (60 s), então é ele quem encerra a extensão. Vale registrar:
    quem for calibrar `verde_max_s` para cima precisa mexer nos dois, senão o
    segundo valor não tem efeito nenhum.
    """
    assert parametros.preempcao_timeout_s < parametros.verde_max_s

    estado = estado_inicial("CRUZ_TESTE_1", cruzamento)
    exagero = Comando(TipoComando.ESTENDER_VERDE, "CRUZ_TESTE_1", duracao_s=9999.0, motivo="teste")
    _, transicoes = _rodar(
        estado, cruzamento, parametros, ate_t=80.0, comandos_em={1.0: (exagero,)}
    )

    amarelo = next(t for t in transicoes if t.sinal is Sinal.AMARELO)
    # Preempção começa em t=1,0 e expira 45 s depois.
    assert amarelo.t == pytest.approx(1.0 + parametros.preempcao_timeout_s, abs=0.11)


def test_ciclo_fixo_gira_sozinho_sem_comando(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    """Sem intervenção, o controlador é autônomo — o baseline `FIXO`."""
    estado = estado_inicial("CRUZ_TESTE_1", cruzamento)
    estado, transicoes = _rodar(estado, cruzamento, parametros, ate_t=80.0)

    verdes = [t.fase for t in transicoes if t.sinal is Sinal.VERDE]
    assert verdes[:2] == [FASE_TRANSVERSAL, FASE_ARTERIAL]  # alterna


def test_duracao_da_transicao_soma_verde_minimo_residual(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    """É o número que E3 usa para decidir *quando* preemptar."""
    estado = estado_inicial("CRUZ_TESTE_1", cruzamento, t=0.0)

    # Aos 2 s: faltam 5 s de verde mínimo, mais 3 de amarelo e 2 de all-red.
    assert duracao_da_transicao_s(
        estado, cruzamento, FASE_TRANSVERSAL, parametros, t=2.0
    ) == pytest.approx(10.0)

    # Aos 10 s o verde mínimo já foi cumprido: só amarelo + all-red.
    assert duracao_da_transicao_s(
        estado, cruzamento, FASE_TRANSVERSAL, parametros, t=10.0
    ) == pytest.approx(5.0)

    # Fase alvo já está em verde: nada a fazer.
    assert duracao_da_transicao_s(estado, cruzamento, FASE_ARTERIAL, parametros, t=10.0) == 0.0


# ---------------------------------------------------------------------------
# Recusas — a metade do firmware na defesa em profundidade (P13)
# ---------------------------------------------------------------------------


def test_fase_inexistente_e_recusada(cruzamento: Cruzamento, parametros: Parametros) -> None:
    estado = estado_inicial("CRUZ_TESTE_1", cruzamento)
    avanco = avancar(
        estado,
        1.0,
        cruzamento,
        parametros,
        (Comando(TipoComando.IR_PARA_FASE, "CRUZ_TESTE_1", fase_alvo=99, motivo="teste"),),
    )

    assert [r.motivo for r in avanco.recusas] == ["FASE_INVALIDA"]
    assert avanco.estado.fase_alvo is None


def test_troca_de_alvo_no_meio_da_transicao_e_recusada(
    cruzamento: Cruzamento, parametros: Parametros
) -> None:
    """Redirecionar a transição no meio do caminho é recusado.

    O amarelo em curso pertence à transição antiga; trocar o destino ali
    deixaria o cruzamento em estado inconsistente.
    """
    estado = estado_inicial("CRUZ_TESTE_1", cruzamento)
    ir = Comando(TipoComando.IR_PARA_FASE, "CRUZ_TESTE_1", fase_alvo=FASE_TRANSVERSAL, motivo="t")
    estado, _ = _rodar(estado, cruzamento, parametros, ate_t=11.0, comandos_em={10.0: (ir,)})
    assert estado.sinal is Sinal.AMARELO

    avanco = avancar(
        estado,
        11.1,
        cruzamento,
        parametros,
        (Comando(TipoComando.IR_PARA_FASE, "CRUZ_TESTE_1", fase_alvo=FASE_ARTERIAL, motivo="t"),),
    )
    assert [r.motivo for r in avanco.recusas] == ["MODO"]


def test_estender_fora_do_verde_e_recusado(cruzamento: Cruzamento, parametros: Parametros) -> None:
    estado = estado_inicial("CRUZ_TESTE_1", cruzamento)
    ir = Comando(TipoComando.IR_PARA_FASE, "CRUZ_TESTE_1", fase_alvo=FASE_TRANSVERSAL, motivo="t")
    estado, _ = _rodar(estado, cruzamento, parametros, ate_t=11.0, comandos_em={10.0: (ir,)})

    avanco = avancar(
        estado,
        11.1,
        cruzamento,
        parametros,
        (Comando(TipoComando.ESTENDER_VERDE, "CRUZ_TESTE_1", duracao_s=10.0, motivo="t"),),
    )
    assert [r.motivo for r in avanco.recusas] == ["MODO"]


def test_liberar_sem_preempcao_e_recusado(cruzamento: Cruzamento, parametros: Parametros) -> None:
    estado = estado_inicial("CRUZ_TESTE_1", cruzamento)
    avanco = avancar(
        estado,
        1.0,
        cruzamento,
        parametros,
        (Comando(TipoComando.LIBERAR, "CRUZ_TESTE_1", motivo="t"),),
    )
    assert [r.motivo for r in avanco.recusas] == ["MODO"]


def test_fallback_seguro_nunca_e_recusado(cruzamento: Cruzamento, parametros: Parametros) -> None:
    """Fail-safe não pede licença: é a resposta a estado já inseguro."""
    estado = estado_inicial("CRUZ_TESTE_1", cruzamento)
    ir = Comando(TipoComando.IR_PARA_FASE, "CRUZ_TESTE_1", fase_alvo=FASE_TRANSVERSAL, motivo="t")
    estado, _ = _rodar(estado, cruzamento, parametros, ate_t=11.0, comandos_em={10.0: (ir,)})

    avanco = avancar(
        estado,
        11.1,
        cruzamento,
        parametros,
        (Comando(TipoComando.FALLBACK_SEGURO, "CRUZ_TESTE_1", motivo="invariante violado"),),
    )
    assert avanco.recusas == ()
    assert avanco.estado.em_preempcao is False


def test_preempcao_expira_no_timeout(cruzamento: Cruzamento, parametros: Parametros) -> None:
    """E6 — backend travado não bloqueia a transversal para sempre."""
    estado = estado_inicial("CRUZ_TESTE_1", cruzamento)
    estender = Comando(TipoComando.ESTENDER_VERDE, "CRUZ_TESTE_1", duracao_s=9999.0, motivo="t")
    estado, _ = _rodar(estado, cruzamento, parametros, ate_t=10.0, comandos_em={1.0: (estender,)})
    assert estado.em_preempcao is True

    estado, _ = _rodar(estado, cruzamento, parametros, ate_t=50.0, t_inicial=10.0)
    assert estado.em_preempcao is False
