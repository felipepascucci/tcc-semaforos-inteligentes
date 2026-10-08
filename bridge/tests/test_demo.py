"""O roteiro da demonstração (`bridge/demo.py`): narração, eixos e a Central.

O roteiro inteiro só roda com a ponte e o backend no ar; aqui ficam as partes
que decidem alguma coisa sem eles.
"""

from __future__ import annotations

from typing import Any

import pytest

from bridge import demo as demo_modulo
from bridge.demo import (
    DISPUTAS,
    Demo,
    DemoInterrompidaError,
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


# ---------------------------------------------------------------------------
# Passo 5 com os carrinhos (2026-10-08): a chegada e a disputa
# ---------------------------------------------------------------------------

AMB, BOMB, POL = "AMBULANCIA", "BOMBEIRO", "POLICIA"


class ObservadorRoteiro(ObservadorFalso):
    """Telemetria e eventos de uma disputa inteira, já chegados."""

    def __init__(
        self, backend: BackendFalso, luzes: list[tuple[int, str, str]], eventos: list[Ev]
    ) -> None:
        super().__init__(backend)
        self.luzes = luzes
        self.eventos = eventos

    def copia(self) -> tuple[list[Amostra], list[Ev]]:
        lista = tuple(sorted(central_esperada(self.backend.abertas, TIPOS).items()))
        amostras = [
            Amostra(ms, cores, regime, None, None, lista) for ms, cores, regime in self.luzes
        ]
        return amostras, list(self.eventos)

    def primeira(self, condicao: Any, desde_ms: int) -> Amostra | None:
        return next((a for a in self.copia()[0] if a.ms >= desde_ms and condicao(a)), None)

    def entre(self, inicio_ms: int, fim_ms: int) -> list[Amostra]:
        return [a for a in self.copia()[0] if inicio_ms <= a.ms <= fim_ms]


class PonteFalsa:
    def __init__(self) -> None:
        self.injecoes: list[tuple[int, str]] = []

    def injetar(self, rua: int, veiculo: str) -> tuple[int, dict[str, Any]]:
        self.injecoes.append((rua, veiculo))
        return 200, {"decisao_t_dispositivo_ms": 2000, "decisao": "PREEMP_INI"}


def _demo_roteiro(
    eventos: list[Ev], luzes: list[tuple[int, str, str]] | None = None, **opcoes: Any
) -> tuple[Demo, PonteFalsa]:
    backend = BackendFalso([])
    ponte = PonteFalsa()
    observador = ObservadorRoteiro(backend, luzes or [(1000, "GGRR", "C")], eventos)
    demo = Demo(ponte, observador, backend, Opcoes(pausa=False, **opcoes))  # type: ignore[arg-type]
    demo.carregar_cadastro()
    return demo, ponte


def test_a_chegada_e_a_decisao_do_tipo_do_carrinho() -> None:
    """A releitura do outro carrinho no meio não é tomada pela chegada."""
    demo, _ = _demo_roteiro([Ev(2000, "RENOVADO", 3, AMB), Ev(2100, "PREEMP_INI", 1, BOMB)])
    assert demo.chegada(BOMB, 1, 1500) == Ev(2100, "PREEMP_INI", 1, BOMB)


def test_a_chegada_segue_a_rua_que_o_carrinho_leu() -> None:
    demo, _ = _demo_roteiro([Ev(2000, "PREEMP_INI", 2, POL)])
    assert demo.chegada(POL, 1, 1500).rua == 2


def test_sem_carrinho_a_chegada_e_injetada() -> None:
    demo, ponte = _demo_roteiro([], sem_carrinho=True)
    assert demo.chegada(BOMB, 1, 1000) == Ev(2000, "PREEMP_INI", 1, BOMB)
    assert ponte.injecoes == [(1, BOMB)]


def test_o_cadastro_precisa_dos_tres_tipos() -> None:
    backend = BackendFalso([])
    backend.veiculos = lambda: [  # type: ignore[method-assign]
        {"id_veiculo": 1, "tipo": AMB, "placa": "P1", "status_operacional": "ATIVO"},
        {"id_veiculo": 2, "tipo": BOMB, "placa": "P2", "status_operacional": "ATIVO"},
    ]
    demo = Demo(None, ObservadorFalso(backend), backend, Opcoes(pausa=False))  # type: ignore[arg-type]
    with pytest.raises(DemoInterrompidaError, match="POLICIA"):
        demo.carregar_cadastro()


@pytest.fixture
def sem_intervalo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(demo_modulo, "INTERVALO_SEGUNDO_VE_S", 0.0)


#: Ambulância na Rua 3; bombeiro na Rua 1 3 s depois, mais crítico.
_INTERROMPE = [
    Ev(2000, "PREEMP_INI", 3, AMB),
    Ev(5000, "PREEMP_INI", 1, BOMB),
    Ev(5000, "FILA", 3, AMB),
    Ev(16000, "PREEMP_FIM", 1, BOMB),
    Ev(16000, "PREEMP_INI", 3, AMB),
    Ev(28000, "PREEMP_FIM", 3, AMB),
]
_LUZES = [
    (1000, "GGRR", "C"),
    (8000, "GRRR", "E"),
    (19000, "RRGR", "E"),
    (28000, "RRYR", "C"),
    (31000, "GGRR", "C"),
]


@pytest.mark.usefixtures("sem_intervalo")
def test_disputa_com_os_carrinhos_o_mais_critico_interrompe() -> None:
    demo, ponte = _demo_roteiro(_INTERROMPE, _LUZES)
    demo._disputa(AMB, BOMB, {AMB: 2, BOMB: 1, POL: 0})
    assert ponte.injecoes == []
    assert [r.nome for r in demo.resultados if not r.ok] == []
    assert any("interrompe" in r.nome for r in demo.resultados)
    assert any("AMBULANCIA sai da fila" in r.nome for r in demo.resultados)


@pytest.mark.usefixtures("sem_intervalo")
def test_disputa_com_os_carrinhos_o_menos_critico_espera() -> None:
    eventos = [
        Ev(2000, "PREEMP_INI", 3, AMB),
        Ev(5000, "FILA", 1, POL),
        Ev(14000, "PREEMP_FIM", 3, AMB),
        Ev(14000, "PREEMP_INI", 1, POL),
        Ev(24000, "PREEMP_FIM", 1, POL),
    ]
    luzes = [
        (1000, "GGRR", "C"),
        (5000, "RRGR", "E"),
        (17000, "GRRR", "E"),
        (24000, "YRRR", "C"),
        (27000, "RRGG", "C"),
    ]
    demo, _ = _demo_roteiro(eventos, luzes)
    demo._disputa(AMB, POL, {AMB: 1, BOMB: 0, POL: 2})
    assert [r.nome for r in demo.resultados if not r.ok] == []
    assert any("espera na fila" in r.nome for r in demo.resultados)
    assert any("POLICIA sai da fila" in r.nome for r in demo.resultados)


@pytest.mark.usefixtures("sem_intervalo")
def test_segundo_carrinho_atrasado_nao_e_disputa() -> None:
    """Passou depois do fim do verde do primeiro: o roteiro diz isso, e não 'sem FILA'."""
    eventos = [
        Ev(2000, "PREEMP_INI", 3, AMB),
        Ev(14000, "PREEMP_FIM", 3, AMB),
        Ev(20000, "PREEMP_INI", 1, BOMB),
    ]
    demo, _ = _demo_roteiro(eventos)
    demo._disputa(AMB, BOMB, {AMB: 2, BOMB: 1, POL: 0})
    [falha] = [r for r in demo.resultados if not r.ok]
    assert "não houve disputa" in falha.detalhe


def test_as_disputas_mostram_os_tres_carrinhos_e_os_dois_desfechos() -> None:
    assert {tipo for primeiro, segundo, _ in DISPUTAS for tipo in (primeiro, segundo)} == {
        AMB,
        BOMB,
        POL,
    }
    desfechos = {central[segundo] < central[primeiro] for primeiro, segundo, central in DISPUTAS}
    assert desfechos == {True, False}
