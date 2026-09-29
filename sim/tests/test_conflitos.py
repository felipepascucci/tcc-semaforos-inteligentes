"""Agregação dos conflitos entre VEs em episódios — entrega 10.1.

O motor publica um evento por passo enquanto a disputa existir. Com passo de
0,1 s, um conflito de dez segundos rende cem eventos e **uma** escolha. O que a
entrega 10.1 precisa contar é a escolha, porque é ela que a política aprendida
de P19 vai decidir — por isso a unidade é o episódio, e por isso ela tem teste
próprio.
"""

from __future__ import annotations

import csv
from pathlib import Path

from core.modelos import TipoVeiculo
from core.priorizacao.conflito import Disputa, EventoConflito
from core.priorizacao.deteccao import DeteccaoVE
from sim.controlador.coletor import (
    ARQUIVO_CONFLITOS,
    ARQUIVO_EXECUCOES,
    ColetorMetricas,
    gravar_csv,
)

PASSO_S = 0.1


def _disputa(
    id_veiculo: str,
    tipo: TipoVeiculo = TipoVeiculo.AMBULANCIA,
    fase: int = 1,
    eta_s: float = 12.0,
) -> Disputa:
    """Um pedido de preempção artificial, com valores redondos."""
    return Disputa(
        deteccao=DeteccaoVE(
            id_veiculo=id_veiculo,
            tipo=tipo,
            id_semaforo="CRUZ_TESTE_1",
            distancia_m=120.0,
            eta_s=eta_s,
            movimento=("E0", "E1"),
        ),
        fase_desejada=fase,
    )


def _evento(
    t: float,
    id_semaforo: str = "CRUZ_TESTE_1",
    ids: tuple[str, ...] = ("AMB", "BMB"),
    preempcao_em_curso: str | None = None,
) -> EventoConflito:
    """Um conflito entre os VEs dados, no instante dado."""
    return EventoConflito(
        t=t,
        id_semaforo=id_semaforo,
        disputas=tuple(
            _disputa(identificador, fase=indice + 1) for indice, identificador in enumerate(ids)
        ),
        preempcao_em_curso=preempcao_em_curso,
    )


def _coletor() -> ColetorMetricas:
    return ColetorMetricas(cenario="teste", modo="PREEMPCAO", seed=999, passo_s=PASSO_S)


def _consolidar(coletor: ColetorMetricas) -> tuple[object, ...]:
    resultado = coletor.consolidar(
        tripinfo=Path("tripinfo_que_nao_existe.xml"), duracao_s=60.0, veiculos_planejados=0
    )
    return resultado.conflitos


# ---------------------------------------------------------------------------
# Onde um episódio começa e termina
# ---------------------------------------------------------------------------


def test_passos_consecutivos_formam_um_unico_episodio() -> None:
    """Cem eventos, uma escolha: o número que vale é 1."""
    coletor = _coletor()

    for passo in range(100):
        coletor.registrar_conflitos([_evento(t=round(passo * PASSO_S, 1))])

    resultado = coletor.consolidar(
        tripinfo=Path("nao_existe.xml"), duracao_s=60.0, veiculos_planejados=0
    )
    assert resultado.eventos_conflito == 1
    assert resultado.passos_em_conflito == 100
    episodio = resultado.conflitos[0]
    assert episodio.t_inicio_s == 0.0
    assert episodio.duracao_s == 9.9


def test_intervalo_maior_que_a_folga_abre_episodio_novo() -> None:
    """A disputa se desfez e outra começou depois — são duas escolhas."""
    coletor = _coletor()

    coletor.registrar_conflitos([_evento(t=1.0), _evento(t=1.1)])
    coletor.registrar_conflitos([_evento(t=40.0)])

    episodios = _consolidar(coletor)
    assert len(episodios) == 2
    assert [episodio.t_inicio_s for episodio in episodios] == [1.0, 40.0]


def test_cruzamentos_diferentes_sao_episodios_diferentes() -> None:
    """Os mesmos dois VEs disputam de novo no cruzamento seguinte da rota."""
    coletor = _coletor()

    coletor.registrar_conflitos(
        [_evento(t=5.0, id_semaforo="CRUZ_TESTE_1"), _evento(t=5.0, id_semaforo="CRUZ_TESTE_2")]
    )

    episodios = _consolidar(coletor)
    assert {episodio.id_semaforo for episodio in episodios} == {
        "CRUZ_TESTE_1",
        "CRUZ_TESTE_2",
    }


def test_mudar_o_conjunto_de_ves_abre_episodio_novo() -> None:
    """Um terceiro VE entrando na disputa é outra escolha, não a mesma."""
    coletor = _coletor()

    coletor.registrar_conflitos([_evento(t=2.0, ids=("AMB", "BMB"))])
    coletor.registrar_conflitos([_evento(t=2.1, ids=("AMB", "BMB", "POL"))])

    episodios = _consolidar(coletor)
    assert len(episodios) == 2
    assert [episodio.n_ves for episodio in episodios] == [2, 3]


# ---------------------------------------------------------------------------
# O que o episódio guarda
# ---------------------------------------------------------------------------


def test_atributos_sao_os_da_abertura_e_nao_os_do_ultimo_passo() -> None:
    """A escolha se apresenta na abertura, e é lá que a 10.4 vai bifurcar."""
    coletor = _coletor()

    coletor.registrar_conflitos(
        [
            EventoConflito(
                t=3.0,
                id_semaforo="CRUZ_TESTE_1",
                disputas=(
                    _disputa("BMB", TipoVeiculo.BOMBEIRO, fase=2, eta_s=20.0),
                    _disputa("AMB", TipoVeiculo.AMBULANCIA, fase=1, eta_s=8.0),
                ),
            )
        ]
    )
    coletor.registrar_conflitos(
        [
            EventoConflito(
                t=3.1,
                id_semaforo="CRUZ_TESTE_1",
                disputas=(
                    _disputa("BMB", TipoVeiculo.BOMBEIRO, fase=2, eta_s=19.9),
                    _disputa("AMB", TipoVeiculo.AMBULANCIA, fase=1, eta_s=7.9),
                ),
            )
        ]
    )

    episodio = _consolidar(coletor)[0]
    assert episodio.ids_veiculos == ("AMB", "BMB")
    assert episodio.tipos == ("AMBULANCIA", "BOMBEIRO")
    assert episodio.etas_s == (8.0, 20.0)
    assert episodio.fases_desejadas == (1, 2)


def test_episodio_suspenso_que_se_liberta_fica_marcado() -> None:
    """Nasceu sob preempção alheia e virou escolha em aberto no passo seguinte."""
    coletor = _coletor()

    coletor.registrar_conflitos([_evento(t=4.0, preempcao_em_curso="AMB")])
    coletor.registrar_conflitos([_evento(t=4.1)])

    episodio = _consolidar(coletor)[0]
    assert not episodio.decidivel
    assert episodio.decidivel_em_algum_passo
    assert episodio.preempcao_em_curso == "AMB"


def test_agregados_separam_decidivel_de_suspenso() -> None:
    """`eventos_conflito_decidiveis` é o que sobra para treinar."""
    coletor = _coletor()

    coletor.registrar_conflitos([_evento(t=1.0)])
    coletor.registrar_conflitos([_evento(t=30.0, preempcao_em_curso="AMB")])

    resultado = coletor.consolidar(
        tripinfo=Path("nao_existe.xml"), duracao_s=60.0, veiculos_planejados=0
    )
    assert resultado.eventos_conflito == 2
    assert resultado.eventos_conflito_decidiveis == 1


def test_execucao_sem_conflito_zera_os_agregados() -> None:
    """O caso comum dos cenários de um VE só, e um resultado possível da 10.1."""
    resultado = _coletor().consolidar(
        tripinfo=Path("nao_existe.xml"), duracao_s=60.0, veiculos_planejados=0
    )
    assert resultado.conflitos == ()
    assert resultado.eventos_conflito == 0
    assert resultado.passos_em_conflito == 0


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def test_csv_de_conflitos_traz_uma_linha_por_episodio(tmp_path: Path) -> None:
    """Uma linha por escolha, com os VEs no mesmo lugar em todas as colunas."""
    coletor = _coletor()
    coletor.registrar_conflitos([_evento(t=1.0), _evento(t=1.0, id_semaforo="CRUZ_TESTE_2")])
    resultado = coletor.consolidar(
        tripinfo=Path("nao_existe.xml"), duracao_s=60.0, veiculos_planejados=0
    )

    gravar_csv(resultado, diretorio=tmp_path)

    with (tmp_path / ARQUIVO_CONFLITOS).open(encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    assert len(linhas) == 2
    primeira = linhas[0]
    assert primeira["cenario"] == "teste"
    assert primeira["ids_veiculos"] == "AMB|BMB"
    assert primeira["fases_desejadas"] == "1|2"
    assert primeira["decidivel"] == "1"
    assert primeira["preempcao_em_curso"] == ""


def test_execucoes_csv_ganha_as_tres_colunas_da_contagem(tmp_path: Path) -> None:
    """É o agregado que o resumo lê, e o denominador inclui execução sem conflito."""
    coletor = _coletor()
    coletor.registrar_conflitos([_evento(t=1.0), _evento(t=1.1)])
    resultado = coletor.consolidar(
        tripinfo=Path("nao_existe.xml"), duracao_s=60.0, veiculos_planejados=0
    )

    gravar_csv(resultado, diretorio=tmp_path)

    with (tmp_path / ARQUIVO_EXECUCOES).open(encoding="utf-8", newline="") as arquivo:
        linha = next(iter(csv.DictReader(arquivo)))
    assert linha["eventos_conflito"] == "1"
    assert linha["eventos_conflito_decidiveis"] == "1"
    assert linha["passos_em_conflito"] == "2"
