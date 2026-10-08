"""RNF02 — o sistema opera 60 min contínuos sem vazamento de memória (`context/06` §2).

Uma execução inteira de 3.600 s simulados, com o laço completo do executor
(adaptador TraCI, motor, verificador de segurança, coletor), enquanto uma thread
lê o RSS do processo Python a cada `INTERVALO_AMOSTRA_S` de relógio. O SUMO roda
em outro processo e fica fora da conta: o que se mede é o controlador.

**Por que 60 min simulados, e não de relógio.** O que vaza memória é o número de
voltas do laço, e não o tempo de parede: 3.600 s a 0,1 s por passo são as
36.000 leituras de estado e decisões de 60 min de operação, que aqui rodam em
poucos minutos. A operação contínua no relógio de verdade foi medida na
bancada, onde o tempo de parede é o que importa (`06` §6, item 12, 30 min).

**Critério, declarado antes da primeira execução deste teste (2026-10-08).**
`06` §2 pede "RSS estável ± 10%". A referência é o RSS máximo do primeiro quinto
das amostras, quando o processo já carregou a rede, os módulos e o SUMO e passou
pelo aquecimento; a partir dela, todo o resto da execução fica entre 90% e 110%.
Crescimento legítimo existe — o coletor guarda uma latência por passo e as
transições —, e é da ordem de 1 MB, abaixo de 1% do processo.

Ponto: `moderado`, `PREEMPCAO_COMPENSADA` (o braço que passa por mais código:
preempção e compensação), seed 900, fora das faixas reservadas
(`cenarios.yaml`), a mesma das verificações do Bloco 7. Sem banco
(`persistir=False`): o teste não grava em `execucao_simulacao`, e a execução
não é dado experimental.
"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest

pytestmark = [pytest.mark.sumo, pytest.mark.lento]

CENARIO, MODO, SEED = "moderado", "PREEMPCAO_COMPENSADA", 900
DURACAO_S = 3600.0
INTERVALO_AMOSTRA_S = 0.5
FRACAO_REFERENCIA = 0.2
TOLERANCIA = 0.10


def rss_bytes() -> int:
    """RSS do processo atual: working set no Windows, `statm` no Linux."""
    if sys.platform == "win32":
        from ctypes import wintypes

        class Contadores(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        contadores = Contadores()
        contadores.cb = ctypes.sizeof(Contadores)
        psapi = ctypes.WinDLL("psapi")
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(Contadores),
            wintypes.DWORD,
        ]
        ok = psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(), ctypes.byref(contadores), contadores.cb
        )
        assert ok, "GetProcessMemoryInfo falhou"
        return int(contadores.WorkingSetSize)
    paginas = int(Path("/proc/self/statm").read_text(encoding="ascii").split()[1])
    return paginas * os.sysconf("SC_PAGE_SIZE")


def test_rss_e_um_numero_plausivel() -> None:
    """O medidor em si: um processo Python com o pytest carregado tem dezenas de MB."""
    assert 10 * 2**20 < rss_bytes() < 8 * 2**30


def test_uma_hora_de_operacao_sem_vazamento(
    tmp_path: Path, record_property: Callable[[str, object], None]
) -> None:
    from sim.controlador.executor import Opcoes, executar

    amostras: list[int] = []
    parar = threading.Event()

    def amostrar() -> None:
        while not parar.is_set():
            amostras.append(rss_bytes())
            time.sleep(INTERVALO_AMOSTRA_S)

    medidor = threading.Thread(target=amostrar, daemon=True)
    medidor.start()
    try:
        resultado = executar(
            Opcoes(
                cenario=CENARIO,
                modo=MODO,
                seed=SEED,
                duracao_s=DURACAO_S,
                persistir=False,
                diretorio_csv=tmp_path,
            )
        )
    finally:
        parar.set()
        medidor.join(timeout=5.0)

    # A execução foi até o fim, e foi uma execução válida.
    assert resultado.duracao_s == DURACAO_S
    assert resultado.colisoes == 0
    assert not resultado.violacoes
    assert len(resultado.latencias_ms) > 0

    assert len(amostras) >= 20, "execução curta demais para ver tendência"
    corte = max(1, int(len(amostras) * FRACAO_REFERENCIA))
    referencia = max(amostras[:corte])
    resto = amostras[corte:]
    mb = 2**20
    # Vão para o XML do JUnit, de onde o relatório de validação os lê.
    record_property("amostras_rss", len(amostras))
    record_property("rss_referencia_mb", round(referencia / mb, 1))
    record_property("rss_max_mb", round(max(resto) / mb, 1))
    record_property("rss_min_mb", round(min(resto) / mb, 1))
    record_property("decisoes", len(resultado.latencias_ms))
    assert max(resto) <= referencia * (1 + TOLERANCIA), (
        f"RSS subiu de {referencia / mb:.1f} MB para {max(resto) / mb:.1f} MB"
    )
    assert min(resto) >= referencia * (1 - TOLERANCIA), (
        f"RSS caiu de {referencia / mb:.1f} MB para {min(resto) / mb:.1f} MB"
    )
