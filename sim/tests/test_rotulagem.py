"""Rotulagem por bifurcação — entrega 10.4 (P19).

As regras do rótulo, da escolha forçada e da fidelidade da reexecução são puras
e testadas sem SUMO. O teste de ponta a ponta, que reexecuta uma seed de verdade,
fica no fim, marcado `sumo`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.modelos import Criticidade, EstadoMalha, TipoVeiculo
from core.priorizacao.atributos import AtributosVE
from core.priorizacao.conflito import Disputa, EventoConflito
from core.priorizacao.deteccao import DeteccaoVE
from sim.controlador.coletor import CabecalhoDivergenteError, ColetorMetricas, EpisodioConflito
from sim.controlador.rotulagem import (
    ARQUIVO_ROTULOS,
    COLUNAS,
    DESCARTADA,
    EMPATE,
    A,
    B,
    EscolhaForcada,
    ResultadoRamo,
    consolidar_rotulos,
    decidir_rotulo,
    elegivel,
    minimax,
    replay_fiel,
)


def _disputa(id_veiculo: str, eta_s: float = 10.0, fase: int = 1) -> Disputa:
    return Disputa(
        deteccao=DeteccaoVE(
            id_veiculo=id_veiculo,
            tipo=TipoVeiculo.AMBULANCIA,
            criticidade=Criticidade.RISCO_VIDA,
            id_semaforo="CRUZ_TESTE",
            distancia_m=eta_s * 10.0,
            eta_s=eta_s,
            movimento=("E0", "E1"),
        ),
        fase_desejada=fase,
    )


def _episodio(
    ids: tuple[str, ...] = ("VE_A", "VE_B"),
    criticidades: tuple[int, ...] = (1, 1),
    decidivel: bool = True,
    etas: tuple[float, ...] = (10.0, 20.0),
) -> EpisodioConflito:
    return EpisodioConflito(
        id_semaforo="CRUZ_TESTE",
        t_inicio_s=100.0,
        t_fim_s=120.0,
        passos=200,
        ids_veiculos=ids,
        tipos=tuple("AMBULANCIA" for _ in ids),
        criticidades=criticidades,
        etas_s=etas,
        fases_desejadas=tuple(range(1, len(ids) + 1)),
        decidivel=decidivel,
        decidivel_em_algum_passo=decidivel,
    )


# ---------------------------------------------------------------------------
# Escolha forçada
# ---------------------------------------------------------------------------


def test_escolha_forcada_vale_so_na_disputa_bifurcada() -> None:
    politica = EscolhaForcada("CRUZ_TESTE", vencedor="VE_B", outro="VE_A")
    a, b = _disputa("VE_A", fase=1), _disputa("VE_B", fase=2)
    estado = EstadoMalha(t=0.0, semaforos={})

    assert politica.escolher("CRUZ_TESTE", [a, b], estado) == b
    assert politica.escolher("OUTRO_CRUZ", [a, b], estado) is None
    assert politica.escolher("CRUZ_TESTE", [b, _disputa("VE_C")], estado) is None


# ---------------------------------------------------------------------------
# Rótulo minimax
# ---------------------------------------------------------------------------


def test_minimax_e_o_tempo_do_mais_prejudicado() -> None:
    assert minimax([200.0, 250.5]) == 250.5
    assert minimax([200.0, None]) is None


@pytest.mark.parametrize(
    ("se_a", "se_b", "esperado"),
    [
        (250.0, 260.0, A),
        (260.0, 250.0, B),
        (250.0, 250.0, EMPATE),
        # resíduo de ponto flutuante não desfaz um empate no passo de 0,1 s
        (312.30000000000001, 312.29999999999995, EMPATE),
        (250.0, None, DESCARTADA),
        (None, 250.0, DESCARTADA),
    ],
)
def test_rotulo_e_a_escolha_de_melhor_minimax(
    se_a: float | None, se_b: float | None, esperado: str
) -> None:
    assert decidir_rotulo(se_a, se_b) == esperado


# ---------------------------------------------------------------------------
# Quem é bifurcado
# ---------------------------------------------------------------------------


def test_so_disputa_de_dois_ves_de_mesmo_nivel_e_decidivel_e_bifurcada() -> None:
    assert elegivel(_episodio())
    assert not elegivel(_episodio(criticidades=(1, 2)))  # a regra de criticidade decide
    assert not elegivel(_episodio(decidivel=False))  # a guarda de oscilação decide
    assert not elegivel(_episodio(ids=("A", "B", "C"), criticidades=(1, 1, 1)))


# ---------------------------------------------------------------------------
# Fidelidade da reexecução
# ---------------------------------------------------------------------------


def _ramo(etas: tuple[float, float] | None, fila: int = 0) -> ResultadoRamo:
    if etas is None:
        return ResultadoRamo(evento=None)
    evento = EventoConflito(
        t=100.0,
        id_semaforo="CRUZ_TESTE",
        disputas=(_disputa("VE_B", etas[1], fase=2), _disputa("VE_A", etas[0], fase=1)),
    )
    atributos = {
        identificador: AtributosVE(eta, 10.0, fila, float(fila), 3)
        for identificador, eta in zip(("VE_A", "VE_B"), etas, strict=True)
    }
    return ResultadoRamo(evento=evento, atributos=atributos)


def test_reexecucao_fiel_reencontra_a_disputa_com_os_mesmos_etas() -> None:
    episodio = _episodio(etas=(10.0, 20.0))

    assert replay_fiel(episodio, [_ramo((10.0, 20.0)), _ramo((10.0, 20.0))])


def test_qualquer_diferenca_na_reexecucao_e_infidelidade() -> None:
    """Sem tolerância: com reexecução determinística, diferença é defeito."""
    episodio = _episodio(etas=(10.0, 20.0))

    assert not replay_fiel(episodio, [_ramo((10.0, 20.0)), _ramo(None)])
    assert not replay_fiel(episodio, [_ramo((10.0, 20.000001)), _ramo((10.0, 20.0))])
    assert not replay_fiel(episodio, [_ramo((10.0, 20.0)), _ramo((10.0, 20.0), fila=1)])


# ---------------------------------------------------------------------------
# Consolidação
# ---------------------------------------------------------------------------


def _parcial(pasta: Path, seeds: list[int], colunas: tuple[str, ...] = COLUNAS) -> Path:
    pasta.mkdir(parents=True)
    linhas = [",".join(colunas)] + [
        ",".join(str(seed) if coluna == "seed" else "" for coluna in colunas) for seed in seeds
    ]
    (pasta / ARQUIVO_ROTULOS).write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return pasta


def test_consolidacao_preserva_a_ordem_das_seeds(tmp_path: Path) -> None:
    pastas = [_parcial(tmp_path / "s2", [202, 202]), _parcial(tmp_path / "s1", [201])]

    linhas = consolidar_rotulos(pastas, tmp_path / "destino")

    conteudo = (tmp_path / "destino" / ARQUIVO_ROTULOS).read_text(encoding="utf-8").splitlines()
    assert linhas == 3
    seed = list(COLUNAS).index("seed")
    assert [linha.split(",")[seed] for linha in conteudo[1:]] == ["202", "202", "201"]


def test_consolidacao_recusa_destino_com_rotulos(tmp_path: Path) -> None:
    """Acrescentar a um arquivo antigo duplicaria disputas: peso dobrado no treino."""
    pastas = [_parcial(tmp_path / "s1", [201])]
    consolidar_rotulos(pastas, tmp_path / "destino")

    with pytest.raises(FileExistsError):
        consolidar_rotulos(pastas, tmp_path / "destino")


def test_consolidacao_recusa_parcial_com_outras_colunas(tmp_path: Path) -> None:
    pastas = [_parcial(tmp_path / "s1", [201], colunas=(*COLUNAS, "extra"))]

    with pytest.raises(CabecalhoDivergenteError):
        consolidar_rotulos(pastas, tmp_path / "destino")


# ---------------------------------------------------------------------------
# Abertura de episódio — a mesma regra da contagem da 10.1
# ---------------------------------------------------------------------------


def test_abriria_episodio_segue_a_folga_da_contagem() -> None:
    coletor = ColetorMetricas(cenario="teste", modo="PREEMPCAO", seed=1, passo_s=0.1)
    evento = EventoConflito(
        t=10.0, id_semaforo="CRUZ_TESTE", disputas=(_disputa("VE_A"), _disputa("VE_B", fase=2))
    )

    assert coletor.abriria_episodio(evento)
    coletor.registrar_conflitos([evento])
    seguinte = EventoConflito(t=10.1, id_semaforo="CRUZ_TESTE", disputas=evento.disputas)
    depois = EventoConflito(t=11.0, id_semaforo="CRUZ_TESTE", disputas=evento.disputas)
    assert not coletor.abriria_episodio(seguinte)
    assert coletor.abriria_episodio(depois)


# ---------------------------------------------------------------------------
# Ponta a ponta, com SUMO
# ---------------------------------------------------------------------------


@pytest.mark.sumo
def test_reexecucao_reencontra_a_disputa_e_o_ramo_do_e8_reproduz_a_principal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A garantia que sustenta o rótulo, medida numa seed de verdade.

    Os dois ramos reencontram a primeira disputa igual à da principal, e o ramo
    que força a mesma escolha do E8 chega com os dois VEs no mesmo instante da
    principal (a travessia do ramo fica 0,1 s acima do `tripinfo`, pela
    convenção do instante de chegada).

    Seed 900 do cenário de treino, fora das reservadas. A primeira disputa
    elegível abre em CRUZ_02 aos 334,7 s, e o E8 não troca de vencedor no meio
    dela; 700 s bastam para os dois VEs chegarem na principal.
    """
    from adapters.configuracao import carregar as carregar_parametros
    from adapters.sumo import topologia as topologia_sumo
    from sim.controlador import executor, rotulagem
    from sim.demanda import gerar_rotas

    monkeypatch.setattr(executor, "SAIDA", tmp_path / "saida")
    principal = executor.executar(
        executor.Opcoes(
            cenario="treino_multiplas",
            modo="PREEMPCAO",
            seed=900,
            duracao_s=700.0,
            persistir=False,
            diretorio_csv=tmp_path / "csv",
        )
    )
    episodio = next(e for e in principal.conflitos if rotulagem.elegivel(e))
    (tmp_path / "ramo").mkdir()
    contexto = rotulagem.Contexto(
        cenario="treino_multiplas",
        seed=900,
        malha=topologia_sumo.carregar(),
        parametros=executor.parametros_do_modo("PREEMPCAO", carregar_parametros("simulacao")),
        rotas=gerar_rotas.garantir("treino_multiplas", 900),
        pasta_ramo=tmp_path / "ramo",
        passo_s=0.1,
        horizonte_s=rotulagem.HORIZONTE_S,
    )

    linha = rotulagem.rotular_disputa(contexto, episodio, "teste")

    assert linha["replay_fiel"] == 1
    assert linha["rotulo"] in (A, B, EMPATE)
    lado = str(linha["escolha_e8"]).lower()
    na_principal = {v.id_veiculo: v.tempo_viagem_s for v in principal.viagens_ve}
    for letra, identificador in (("a", episodio.ids_veiculos[0]), ("b", episodio.ids_veiculos[1])):
        no_ramo = float(str(linha[f"travessia_{letra}_se_{lado}_s"]))
        assert no_ramo == pytest.approx(na_principal[identificador] + 0.1, abs=1e-6)
