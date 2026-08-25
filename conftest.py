"""Configuração global do pytest.

Coloca `%SUMO_HOME%/tools` em `sys.path`, que é a forma documentada pelo SUMO de
importar `traci`/`libsumo` — garantindo que o cliente Python seja exatamente o da
versão do binário instalado. Instalar `traci` pelo pip criaria uma segunda cópia,
possivelmente de versão diferente (ver comentário em `pyproject.toml`).

Sem SUMO instalado nada acontece: os testes que dependem dele estão marcados com
`@pytest.mark.sumo` e ficam fora da execução padrão (context/06 §1).
"""

import os
import sys
from pathlib import Path


def _registrar_ferramentas_do_sumo() -> None:
    sumo_home = os.getenv("SUMO_HOME")
    if not sumo_home:
        return
    ferramentas = Path(sumo_home) / "tools"
    if ferramentas.is_dir() and str(ferramentas) not in sys.path:
        sys.path.append(str(ferramentas))


_registrar_ferramentas_do_sumo()
