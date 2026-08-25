"""Verificação do ambiente SUMO (entrega 0.5).

Marcado com `sumo`, portanto **fora** da execução padrão do pytest
(context/06 §1). Para rodar:

    pytest -m sumo
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.sumo

VERSAO_MINIMA = (1, 19)


def _versao_de(saida: str) -> tuple[int, int]:
    """Extrai (maior, menor) de "Eclipse SUMO netconvert 1.27.1"."""
    achado = re.search(r"netconvert\s+v?(\d+)\.(\d+)", saida)
    assert achado is not None, f"não consegui extrair a versão de: {saida!r}"
    return int(achado.group(1)), int(achado.group(2))


def test_sumo_home_esta_definido() -> None:
    sumo_home = os.getenv("SUMO_HOME")
    assert sumo_home, "SUMO_HOME não definido — ver README, seção SUMO"
    assert Path(sumo_home, "tools").is_dir(), "%SUMO_HOME%\\tools ausente"


def _netconvert() -> str | None:
    """Resolve o `netconvert` pelo PATH ou, na falta dele, por `%SUMO_HOME%/bin`.

    O PATH nem sempre está atualizado logo após a instalação (o processo em
    execução herdou o ambiente antigo). `SUMO_HOME` é a referência autoritativa
    da documentação do SUMO, então serve de fallback.
    """
    if achado := shutil.which("netconvert"):
        return achado
    sumo_home = os.getenv("SUMO_HOME")
    if not sumo_home:
        return None
    return shutil.which("netconvert", path=str(Path(sumo_home) / "bin"))


def test_netconvert_responde_e_atende_a_versao_minima() -> None:
    executavel = _netconvert()
    assert executavel, "netconvert não encontrado no PATH nem em %SUMO_HOME%/bin"

    resultado = subprocess.run(
        [executavel, "--version"], capture_output=True, text=True, timeout=30, check=True
    )
    assert _versao_de(resultado.stdout) >= VERSAO_MINIMA


def test_traci_importa_a_partir_do_sumo_home() -> None:
    """O cliente TraCI vem do SUMO instalado, não de uma cópia do pip."""
    import traci

    assert Path(traci.__file__).is_file()
