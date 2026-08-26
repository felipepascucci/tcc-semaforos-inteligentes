"""Localização do SUMO instalado — a fronteira entre o repositório e a máquina.

Todo módulo de `sim/` que precisa de um binário (`netconvert`, `sumo`,
`sumo-gui`) ou do cliente Python (`traci`, `libsumo`, `sumolib`) passa por aqui.
Concentrar isso num lugar só evita a proliferação de `shutil.which` espalhados e
dá uma mensagem de erro única e útil quando o SUMO não está instalado.

Duas regras que valem a pena repetir:

1. **O cliente Python vem de `%SUMO_HOME%/tools`, nunca do pip.** Uma segunda
   cópia instalada por `pip install traci` pode ficar em versão diferente do
   binário, e a divergência não falha alto: aparece como comportamento
   sutilmente diferente do TraCI. Decisão registrada em `context/09`.
2. **`PATH` não é confiável logo após a instalação.** O processo em execução
   herdou o ambiente antigo, então `SUMO_HOME` é o fallback autoritativo.
"""

from __future__ import annotations

import os
import shutil
import sys
from functools import cache
from pathlib import Path


class SumoIndisponivelError(RuntimeError):
    """O SUMO não está instalado, ou `SUMO_HOME` não aponta para ele."""


def sumo_home() -> Path:
    """Diretório da instalação do SUMO.

    Returns:
        Caminho de `%SUMO_HOME%`.

    Raises:
        SumoIndisponivelError: se a variável não estiver definida ou o caminho
            não existir.
    """
    bruto = os.getenv("SUMO_HOME")
    if not bruto:
        raise SumoIndisponivelError(
            "SUMO_HOME não definido. Instale o SUMO (README, seção SUMO) e abra "
            "um terminal novo — o processo atual herdou o ambiente antigo."
        )
    caminho = Path(bruto.strip('"'))
    if not caminho.is_dir():
        raise SumoIndisponivelError(f"SUMO_HOME aponta para um caminho inexistente: {caminho}")
    return caminho


@cache
def registrar_ferramentas() -> Path:
    """Coloca `%SUMO_HOME%/tools` em `sys.path` e devolve o caminho.

    É a forma documentada pelo SUMO de importar `traci`, `libsumo` e `sumolib`.
    Idempotente — chamar duas vezes não duplica a entrada.
    """
    ferramentas = sumo_home() / "tools"
    if not ferramentas.is_dir():
        raise SumoIndisponivelError(f"{ferramentas} não existe; instalação do SUMO incompleta")
    if str(ferramentas) not in sys.path:
        sys.path.append(str(ferramentas))
    return ferramentas


def executavel(nome: str) -> str:
    """Resolve um binário do SUMO pelo `PATH` ou por `%SUMO_HOME%/bin`.

    Args:
        nome: `"netconvert"`, `"sumo"`, `"sumo-gui"`, `"duarouter"`...

    Returns:
        Caminho completo do executável.

    Raises:
        SumoIndisponivelError: se o binário não for encontrado em lugar nenhum.
    """
    if achado := shutil.which(nome):
        return achado
    achado = shutil.which(nome, path=str(sumo_home() / "bin"))
    if achado is None:
        raise SumoIndisponivelError(f"{nome} não encontrado no PATH nem em {sumo_home() / 'bin'}")
    return achado


def disponivel() -> bool:
    """Diz se o SUMO está instalado e utilizável, sem levantar exceção."""
    try:
        executavel("netconvert")
    except SumoIndisponivelError:
        return False
    return True
