"""`POST /deteccoes` — o contrato do V2I com rede (`context/01` §7, P20).

Na bancada nenhum dispositivo chama esta rota; ver `app/services/deteccoes.py`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response, status

from app.api.dependencias import RecursosDep, SessaoDep
from app.schemas.deteccoes import PedidoDeteccao, RespostaDeteccao
from app.services import deteccoes

router = APIRouter(tags=["deteccoes"])


@router.post(
    "/deteccoes",
    response_model=RespostaDeteccao,
    summary="Detecção de um leitor V2I",
    responses={
        401: {"description": "X-Device-Token ausente ou inválido"},
        403: {"model": RespostaDeteccao, "description": "Tag desconhecida ou inativa"},
    },
)
def receber_deteccao(
    pedido: PedidoDeteccao,
    sessao: SessaoDep,
    recursos: RecursosDep,
    resposta: Response,
    x_device_token: Annotated[str | None, Header()] = None,
) -> RespostaDeteccao:
    """Autentica o leitor, descarta repetição, aplica P20 e grava a detecção.

    Tag reconhecida **sem ocorrência** responde 200 com `SEM_OCORRENCIA`: a
    credencial é válida e só falta o serviço. O 403 é da tag desconhecida ou
    inativa, e a tentativa fica gravada em `deteccao`.
    """
    try:
        resultado = deteccoes.processar(sessao, pedido, x_device_token, recursos.deduplicador)
    except deteccoes.DispositivoNaoAutenticadoError as erro:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(erro)) from erro
    sessao.commit()
    corpo = resultado.resposta
    if not corpo.duplicada:
        recursos.publicar_evento(
            {
                "nivel": "INFO" if corpo.autorizado else "WARNING",
                "texto": f"Detecção {corpo.acao} via {pedido.id_leitor}",
                "origem": "API",
                "id_veiculo": corpo.id_veiculo,
                "id_log": corpo.id_log,
            }
        )
    resposta.status_code = resultado.status_http
    return corpo
