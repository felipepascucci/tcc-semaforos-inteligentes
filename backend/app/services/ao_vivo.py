"""A simulação ao vivo: o que o executor transmite chega ao WebSocket.

O executor empurra o estado a 5 Hz, só quando é pedido (`--transmitir`; decisão
de 2026-10-05). O lote do Bloco 8 roda sem transmissão. Aqui o backend guarda a
última transmissão, para o `GET /semaforos`, e a repassa ao difusor.

Os ids de VE da simulação são os do SUMO (`ve_amb_0`), e não chaves de
`veiculo_emergencia`. O VE simulado não está no cadastro.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from app.schemas.simulacoes import TransmissaoSimulacao
from app.services.difusao import Difusor

#: Depois disto sem transmissão, o estado deixa de ser "ao vivo".
VALIDADE: Final = timedelta(seconds=5)


@dataclass
class SimulacaoAoVivo:
    difusor: Difusor
    ultima: TransmissaoSimulacao | None = None
    recebida_em: datetime | None = None
    transmissoes: int = 0

    def receber(self, transmissao: TransmissaoSimulacao) -> None:
        self.ultima = transmissao
        self.recebida_em = datetime.now(UTC)
        self.transmissoes += 1
        recebido = self.recebida_em.isoformat()
        origem = {
            "cenario": transmissao.cenario,
            "modo": transmissao.modo,
            "seed": transmissao.seed,
        }
        for semaforo in transmissao.semaforos:
            self.difusor.publicar_estado(
                "estado_semaforo",
                semaforo.id,
                {
                    "id": semaforo.id,
                    "fase": semaforo.fase,
                    "estado": semaforo.sinal,
                    "em_preempcao": semaforo.em_preempcao,
                    "t_simulacao": transmissao.t,
                    "recebido_em": recebido,
                },
            )
        for ve in transmissao.veiculos:
            self.difusor.publicar_estado(
                "posicao_ve",
                ve.id,
                {
                    "id_veiculo": ve.id,
                    "tipo": ve.tipo,
                    "criticidade": ve.criticidade,
                    "lat": ve.lat,
                    "lon": ve.lon,
                    "velocidade": ve.velocidade,
                    "t_simulacao": transmissao.t,
                },
            )
        for evento in transmissao.eventos:
            self.difusor.publicar_evento(
                {"nivel": evento.nivel, "texto": evento.texto, "origem": "SIMULACAO", **origem}
            )
        self.difusor.publicar_estado(
            "metrica",
            "SIMULACAO",
            {
                "origem": "SIMULACAO",
                "latencia_ms": transmissao.latencia_ms,
                "priorizacoes_ativas": sum(s.em_preempcao for s in transmissao.semaforos),
                **origem,
            },
        )

    def ativa(self) -> bool:
        return self.recebida_em is not None and datetime.now(UTC) - self.recebida_em < VALIDADE
