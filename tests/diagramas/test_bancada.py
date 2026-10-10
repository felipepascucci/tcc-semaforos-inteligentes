"""Os diagramas da bancada acompanham o firmware e a ponte (`context/05`).

`maquina_estados_firmware.puml` desenha o que `controlador.cpp` faz, e
`sequencia_bancada.puml` o caminho da preempção na bancada. Os nomes de evento e
os tempos são lidos do código, não copiados: um evento novo no firmware, ou um
tempo trocado em `controlador.h`, quebra o teste até o diagrama ser revisto
(`context/08` §5: "um diagrama que diverge do sistema é passivo").
"""

from __future__ import annotations

import re
from pathlib import Path

from bridge.protocolo import EVENTOS_DE_DECISAO

RAIZ = Path(__file__).resolve().parents[2]
DIAGRAMAS = RAIZ / "docs" / "diagramas"
FIRMWARE = RAIZ / "firmware" / "uno" / "semaforo"


def _texto(nome: str) -> str:
    return (DIAGRAMAS / nome).read_text(encoding="utf-8")


def _eventos_do_firmware() -> set[str]:
    """Os tipos de evento que o UNO escreve: `evento(FIXO("…"), …)`."""
    codigo = (FIRMWARE / "controlador.cpp").read_text(encoding="utf-8")
    return set(re.findall(r'evento\(FIXO\("([A-Z_]+)"\)', codigo))


def _constante_ms(nome: str) -> int:
    cabecalho = (FIRMWARE / "controlador.h").read_text(encoding="utf-8")
    achado = re.search(rf"const uint32_t {nome} = (\d+);", cabecalho)
    assert achado, f"{nome} sumiu de controlador.h"
    return int(achado.group(1))


def _segundos(ms: int) -> str:
    assert ms % 1000 == 0
    return f"{ms // 1000} s"


def test_o_leitor_de_eventos_acha_os_do_firmware() -> None:
    assert {"BOOT", "PREEMP_INI", "PREEMP_FIM", "TIMEOUT", "RECUSADO"} <= _eventos_do_firmware()


def test_todo_evento_do_firmware_esta_na_maquina_de_estados() -> None:
    """O UNO ganhou um evento? Ele entra em `maquina_estados_firmware.puml`."""
    texto = _texto("maquina_estados_firmware.puml")
    assert {e for e in _eventos_do_firmware() if e not in texto} == set()


def test_tempos_do_firmware_estao_na_maquina_de_estados() -> None:
    texto = _texto("maquina_estados_firmware.puml")
    for nome in ("VERDE_MS", "VERDE_MIN_MS", "AMARELO_MS", "ALL_RED_MS", "TETO_MS"):
        assert _segundos(_constante_ms(nome)) in texto, nome


def test_verde_por_tipo_esta_na_maquina_de_estados() -> None:
    codigo = (FIRMWARE / "controlador.cpp").read_text(encoding="utf-8")
    achado = re.search(r"VERDE_DO_TIPO_MS\[4\] = \{0, (\d+), (\d+), (\d+)\}", codigo)
    assert achado, "VERDE_DO_TIPO_MS mudou de forma em controlador.cpp"
    ambulancia, bombeiro, policia = (_segundos(int(v)) for v in achado.groups())
    texto = _texto("maquina_estados_firmware.puml")
    assert f"{ambulancia} (ambulância)" in texto
    assert f"{bombeiro} (bombeiro)" in texto
    assert f"{policia} (polícia)" in texto


def test_toda_decisao_do_uno_esta_na_sequencia() -> None:
    """Os eventos de decisão da ponte, e o fim da emergência, estão no diagrama."""
    texto = _texto("sequencia_bancada.puml")
    esperados = {str(e) for e in EVENTOS_DE_DECISAO} | {"PREEMP_FIM", "TIMEOUT"}
    assert {e for e in esperados if f"EV,...,{e}" not in texto} == set()


def test_a_maquina_do_motor_aponta_para_a_do_firmware() -> None:
    """Desde 2026-10-05 o firmware não reimplementa a máquina do motor."""
    texto = _texto("maquina_estados.puml")
    assert "maquina_estados_firmware.puml" in texto
    assert "reimplementa em C++" not in texto
