"""`GET /metricas/resumo` — agregados para o dashboard (`context/01` §7)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.dependencias import RecursosDep, SessaoDep
from app.services import metricas

router = APIRouter(tags=["metricas"])


@router.get("/metricas/resumo", summary="Agregados para o dashboard")
def resumo(sessao: SessaoDep, recursos: RecursosDep) -> dict[str, Any]:
    """Contagens e latências calculadas no banco, mais o que está ao vivo agora.

    Não é fonte de número do capítulo 5, que sai de `analysis/`.
    """
    leitor = recursos.leitor
    return {
        **metricas.resumo(sessao),
        "ao_vivo": {
            "bancada": leitor is not None and leitor.disponivel,
            "simulacao": recursos.ao_vivo.ativa(),
        },
    }
