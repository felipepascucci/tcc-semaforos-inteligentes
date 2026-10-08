"""Traço das figuras F3, F4 e F6 (`sim/controlador/traco.py`), sem SUMO."""

from __future__ import annotations

import gzip
from pathlib import Path

from core.modelos import EstadoMalha, EstadoSemaforo, Sinal, Transicao
from sim.controlador.traco import (
    ARQUIVO_FILA,
    ARQUIVO_SINAL,
    ARQUIVO_VE,
    Traco,
    deve_amostrar,
    filas_transversais,
    gravar,
)


def test_amostra_uma_vez_por_segundo_no_passo_de_um_decimo() -> None:
    instantes = [round(0.1 * i, 1) for i in range(1, 31)]
    amostrados = [t for t in instantes if deve_amostrar(t, 0.1)]

    assert amostrados == [1.0, 2.0, 3.0]


def test_filas_so_dos_acessos_transversais() -> None:
    estado = EstadoMalha(
        t=1.0,
        semaforos={
            "SEMAFORO_TESTE": EstadoSemaforo(
                id="SEMAFORO_TESTE",
                fase_atual=1,
                tempo_na_fase=0.0,
                fila_por_acesso={"A1_L0": 9, "T1_S0": 3, "T1_N1": 0},
            )
        },
    )

    assert filas_transversais(estado) == [
        ("SEMAFORO_TESTE", "T1_N1", 0),
        ("SEMAFORO_TESTE", "T1_S0", 3),
    ]


def test_gravar_escreve_os_quatro_arquivos(tmp_path: Path) -> None:
    traco = Traco(
        modo="PREEMPCAO",
        ve=[(1.0, "VE_TESTE_00", 10.0, 10.0, "A1_L0")],
        fila=[(1.0, "SEMAFORO_TESTE", "T1_S0", 3)],
        sinal=[Transicao("SEMAFORO_TESTE", 30.0, 1, Sinal.AMARELO, em_preempcao=True)],
        viagens=[("VE_TESTE_00", 300.0)],
    )

    gravar([traco], "intenso", 1, tmp_path)

    assert "VE_TESTE_00" in (tmp_path / ARQUIVO_VE).read_text(encoding="utf-8")
    assert "AMARELO,1" in (tmp_path / ARQUIVO_SINAL).read_text(encoding="utf-8")
    with gzip.open(tmp_path / ARQUIVO_FILA, "rt", encoding="utf-8") as arquivo:
        assert "SEMAFORO_TESTE,T1_S0,3" in arquivo.read()
