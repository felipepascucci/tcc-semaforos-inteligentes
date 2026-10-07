"""O roteiro da demonstração (`bridge/demo.py`): narração, eixos e a Central.

O roteiro inteiro só roda com a ponte e o backend no ar; aqui ficam as partes
que decidem alguma coisa sem eles.
"""

from __future__ import annotations

from typing import Any

import pytest

from bridge.demo import (
    Demo,
    Opcoes,
    central_esperada,
    descrever,
    eixo_oposto,
    exclusivo,
)
from bridge.verificar import PRINCIPAL, TRANSVERSAL, Amostra, Ev

TIPOS = {1: "AMBULANCIA", 2: "BOMBEIRO", 3: "POLICIA"}


def test_descreve_o_ciclo() -> None:
    assert descrever("GGRR", "C") == "eixo principal verde (S1 e S2)"
    assert descrever("RRYY", "C") == "eixo transversal amarelo"
    assert descrever("RRRR", "C") == "all-red: todos vermelhos"


def test_descreve_o_verde_exclusivo_da_emergencia() -> None:
    assert descrever("RRGR", "E") == (
        "[emergência] verde exclusivo no S3 (Rua 3), os outros três vermelhos"
    )


def test_descreve_a_transicao_aproximacao_por_aproximacao() -> None:
    assert descrever("GYRR", "E") == "[emergência] S1 verde, S2 amarelo, S3 vermelho, S4 vermelho"


@pytest.mark.parametrize(("rua", "eixo"), [(1, TRANSVERSAL), (2, TRANSVERSAL), (3, PRINCIPAL)])
def test_o_ciclo_volta_pelo_eixo_que_esperou(rua: int, eixo: str) -> None:
    assert eixo_oposto(rua) == eixo


def test_exclusivo() -> None:
    assert exclusivo(1) == "GRRR"
    assert exclusivo(4) == "RRRG"


def test_central_sem_ocorrencia_nega_todos() -> None:
    assert central_esperada([], TIPOS) == {"AMBULANCIA": 0, "BOMBEIRO": 0, "POLICIA": 0}


def test_central_fica_com_a_criticidade_mais_alta_do_tipo() -> None:
    tipos = {**TIPOS, 4: "AMBULANCIA"}
    ocorrencias = [
        {"id_veiculo": 1, "criticidade": 3, "aberta": True},
        {"id_veiculo": 4, "criticidade": 2, "aberta": True},
        {"id_veiculo": 2, "criticidade": 1, "aberta": True},
    ]
    assert central_esperada(ocorrencias, tipos) == {"AMBULANCIA": 2, "BOMBEIRO": 1, "POLICIA": 0}


def test_central_ignora_veiculo_inativo() -> None:
    """O cadastro só traz os ativos; ocorrência de outro veículo não conta."""
    ocorrencias = [{"id_veiculo": 9, "criticidade": 1, "aberta": True}]
    assert central_esperada(ocorrencias, TIPOS)["AMBULANCIA"] == 0


# ---------------------------------------------------------------------------
# A Central pela API: encerra e reabre para trocar a criticidade
# ---------------------------------------------------------------------------


class BackendFalso:
    def __init__(self, abertas: list[dict[str, Any]]) -> None:
        self.abertas = abertas
        self.proximo = 100
        self.chamadas: list[tuple[str, int, int | None]] = []

    def veiculos(self) -> list[dict[str, Any]]:
        return [
            {"id_veiculo": i, "tipo": t, "placa": f"P{i}", "status_operacional": "ATIVO"}
            for i, t in TIPOS.items()
        ]

    def ocorrencias_ativas(self) -> list[dict[str, Any]]:
        return [dict(o) for o in self.abertas]

    def abrir(self, id_veiculo: int, criticidade: int, descricao: str) -> dict[str, Any]:
        self.proximo += 1
        nova = {
            "id_ocorrencia": self.proximo,
            "id_veiculo": id_veiculo,
            "criticidade": criticidade,
            "aberta": True,
        }
        self.abertas.append(nova)
        self.chamadas.append(("abrir", id_veiculo, criticidade))
        return nova

    def encerrar(self, id_ocorrencia: int) -> dict[str, Any]:
        self.abertas = [o for o in self.abertas if o["id_ocorrencia"] != id_ocorrencia]
        self.chamadas.append(("encerrar", id_ocorrencia, None))
        return {}


class ObservadorFalso:
    """A `ST` traz sempre a lista das ocorrências abertas: o backend sincronizou."""

    def __init__(self, backend: BackendFalso) -> None:
        self.backend = backend

    def copia(self) -> tuple[list[Amostra], list[Ev]]:
        lista = central_esperada(self.backend.abertas, TIPOS)
        return [Amostra(1000, "GGRR", "C", None, None, tuple(sorted(lista.items())))], []

    def agora_ms(self) -> int:
        return 1000


def _demo(backend: BackendFalso) -> Demo:
    demo = Demo(None, ObservadorFalso(backend), backend, Opcoes(pausa=False))  # type: ignore[arg-type]
    demo.carregar_cadastro()
    return demo


def test_trocar_a_criticidade_encerra_e_reabre() -> None:
    backend = BackendFalso(
        [{"id_ocorrencia": 7, "id_veiculo": 1, "criticidade": 1, "aberta": True}]
    )
    demo = _demo(backend)
    demo.definir_central({"AMBULANCIA": 2, "BOMBEIRO": 1})
    assert backend.chamadas == [("encerrar", 7, None), ("abrir", 1, 2), ("abrir", 2, 1)]
    assert demo.abertas_pelo_roteiro == {101, 102}


def test_criticidade_que_ja_esta_certa_fica() -> None:
    backend = BackendFalso(
        [{"id_ocorrencia": 7, "id_veiculo": 1, "criticidade": 2, "aberta": True}]
    )
    _demo(backend).definir_central({"AMBULANCIA": 2})
    assert backend.chamadas == []


def test_encerra_no_fim_so_as_que_o_roteiro_abriu() -> None:
    alheia = {"id_ocorrencia": 5, "id_veiculo": 3, "criticidade": 3, "aberta": True}
    backend = BackendFalso([alheia])
    demo = _demo(backend)
    demo.definir_central({"AMBULANCIA": 1})
    demo.encerrar_as_minhas()
    assert backend.abertas == [alheia]
