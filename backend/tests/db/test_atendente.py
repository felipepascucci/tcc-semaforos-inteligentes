"""Atendente de pedidos de simulação (`sim/controlador/atendente.py`, Bloco 6).

Fica entre os testes de banco porque precisa do Postgres efêmero. O SUMO é
trocado por um executor falso: o que se prova é o ciclo do pedido, as guardas
de `analysis/data/` e das seeds reservadas, e o vínculo com `execucao_simulacao`.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.models import ExecucaoSimulacao, ModoControle, PedidoSimulacao
from app.services.simulacoes import RegrasSimulacao
from sim.controlador import atendente, executor
from sim.controlador.coletor import DADOS, ResultadoExecucao, ViagemVE

pytestmark = pytest.mark.banco

REGRAS = RegrasSimulacao(frozenset({"leve", "moderado"}), ((1, 50), (101, 105)))


def _pedido(sessao: Session, seed: int = 1001, cenario: str = "moderado") -> int:
    pedido = PedidoSimulacao(nome_cenario=cenario, modo=ModoControle.PREEMPCAO, seed=seed)
    sessao.add(pedido)
    sessao.commit()
    return pedido.id_pedido


def _resultado(opcoes: executor.Opcoes) -> ResultadoExecucao:
    return ResultadoExecucao(
        cenario=opcoes.cenario,
        modo=opcoes.modo,
        seed=opcoes.seed,
        duracao_s=600.0,
        viagens_ve=(ViagemVE("ve_amb_0", "AMBULANCIA", 300.0, 2.0, 1, 15.0, 20.0),),
        latencias_ms=(0.1, 0.2),
    )


def test_pedido_concluido_grava_resumo_e_aponta_a_execucao(
    sessao: Session, fabrica_sessao: sessionmaker[Session]
) -> None:
    id_pedido = _pedido(sessao)
    recebidas: list[executor.Opcoes] = []

    def executar(opcoes: executor.Opcoes) -> ResultadoExecucao:
        recebidas.append(opcoes)
        # O executor de verdade abre a linha em execucao_simulacao.
        with fabrica_sessao() as outra:
            outra.add(
                ExecucaoSimulacao(
                    nome_cenario=opcoes.cenario,
                    modo=ModoControle(opcoes.modo),
                    seed=opcoes.seed,
                    duracao_s=600,
                    arquivo_rede="sim/rede/malha.net.xml",
                    parametros={},
                )
            )
            outra.commit()
        return _resultado(opcoes)

    atendidos = atendente.atender_pendentes(
        fabrica_sessao, url_backend="http://backend", regras=REGRAS, executar=executar
    )

    assert atendidos == 1
    (opcoes,) = recebidas
    assert opcoes.diretorio_csv != DADOS, "demonstração nunca escreve em analysis/data/"
    assert opcoes.diretorio_csv == executor.pasta_de_saida("moderado", "PREEMPCAO", 1001)
    assert (opcoes.transmitir, opcoes.id_pedido, opcoes.persistir) == (
        "http://backend",
        id_pedido,
        True,
    )
    sessao.expire_all()
    pedido = sessao.get(PedidoSimulacao, id_pedido)
    assert pedido is not None
    assert pedido.status == "CONCLUIDA"
    assert pedido.fk_execucao is not None
    assert pedido.resumo is not None and pedido.resumo["viagens_ve"] == 1
    assert pedido.iniciado_em is not None and pedido.finalizado_em is not None


def test_repetir_um_ponto_nao_grava_execucao_de_novo(
    sessao: Session, fabrica_sessao: sessionmaker[Session]
) -> None:
    sessao.add(
        ExecucaoSimulacao(
            nome_cenario="moderado",
            modo=ModoControle.PREEMPCAO,
            seed=1001,
            duracao_s=600,
            arquivo_rede="sim/rede/malha.net.xml",
            parametros={},
        )
    )
    sessao.commit()
    _pedido(sessao)
    recebidas: list[executor.Opcoes] = []

    def executar(opcoes: executor.Opcoes) -> ResultadoExecucao:
        recebidas.append(opcoes)
        return _resultado(opcoes)

    atendente.atender_pendentes(fabrica_sessao, url_backend=None, regras=REGRAS, executar=executar)

    assert recebidas[0].persistir is False


def test_seed_reservada_falha_sem_rodar(
    sessao: Session, fabrica_sessao: sessionmaker[Session]
) -> None:
    """Defesa em profundidade: um pedido que entrou sem passar pela API."""
    id_pedido = _pedido(sessao, seed=7)

    def executar(_: executor.Opcoes) -> ResultadoExecucao:
        raise AssertionError("não devia rodar")

    atendente.atender_pendentes(fabrica_sessao, url_backend=None, regras=REGRAS, executar=executar)

    sessao.expire_all()
    pedido = sessao.get(PedidoSimulacao, id_pedido)
    assert pedido is not None
    assert pedido.status == "FALHA"
    assert "seed 7" in (pedido.mensagem or "")


def test_erro_do_executor_vira_falha_com_mensagem(
    sessao: Session, fabrica_sessao: sessionmaker[Session]
) -> None:
    primeiro, segundo = _pedido(sessao, seed=1001), _pedido(sessao, seed=1002)

    def executar(opcoes: executor.Opcoes) -> ResultadoExecucao:
        if opcoes.seed == 1001:
            raise RuntimeError("SUMO não abriu")
        return _resultado(opcoes)

    atendidos = atendente.atender_pendentes(
        fabrica_sessao, url_backend=None, regras=REGRAS, executar=executar
    )

    sessao.expire_all()
    assert atendidos == 2
    assert sessao.get(PedidoSimulacao, primeiro).status == "FALHA"  # type: ignore[union-attr]
    assert "SUMO não abriu" in (sessao.get(PedidoSimulacao, primeiro).mensagem or "")  # type: ignore[union-attr]
    # Um pedido que falha não trava a fila.
    assert sessao.get(PedidoSimulacao, segundo).status == "CONCLUIDA"  # type: ignore[union-attr]


def test_sem_pendentes_nada_acontece(
    fabrica_sessao: sessionmaker[Session], sessao: Session
) -> None:
    def executar(_: executor.Opcoes) -> ResultadoExecucao:
        raise AssertionError("não devia rodar")

    assert (
        atendente.atender_pendentes(
            fabrica_sessao, url_backend=None, regras=REGRAS, executar=executar
        )
        == 0
    )
