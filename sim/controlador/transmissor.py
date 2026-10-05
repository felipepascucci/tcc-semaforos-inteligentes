"""Transmissão ao vivo da simulação para o backend (`--transmitir`, Bloco 6).

O executor empurra o estado ao backend, que o repassa ao WebSocket (RF04, RF06).
**Só quando pedido** (decisão de 2026-10-05): o atendente e a demonstração com
GUI ligam; o lote do Bloco 8 roda sem.

**O laço não paga a transmissão.** `publicar()` só anexa a referência ao
`EstadoMalha` (imutável, `context/08` §3) numa `deque` limitada, depois que o
cronômetro do RNF01 já parou. Montar o JSON, converter coordenadas e fazer o
POST acontece numa thread, a 5 Hz. Se o backend estiver fora do ar, a `deque`
descarta os mais antigos e a simulação segue: a transmissão é para o dashboard,
não é dado do experimento.

A cada envio vai o estado mais recente. Os eventos ("preempção iniciada em
CRUZ_03") saem de **todas** as fotografias acumuladas desde o envio anterior, e
não só da última, para que uma preempção curta entre dois envios não suma.

**Tráfego de fundo (Bloco 7).** O mapa do dashboard mostra também os demais
veículos, para que a fila se formando no vermelho e se desfazendo à frente do VE
fique visível. O `EstadoMalha` só tem os VEs, então o laço lê as posições do
resto direto do SUMO, mas só quando `quer_trafego()` diz que já passou um
intervalo de envio: a 5 Hz de relógio, e não a cada passo. Ler a posição não
altera a simulação. A leitura fica fora do trecho cronometrado, e o lote, que
não transmite, nunca a faz.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

import httpx

from core.modelos import EstadoMalha
from sim.rede.georreferencia import Georreferencia

#: Período de envio: o throttle do WebSocket (`context/01` §7).
INTERVALO_S: Final = 0.2

#: Fotografias guardadas entre dois envios. Com passo de 0,1 s, 60 s de folga.
LIMITE_FOTOS: Final = 600

Foto = tuple[EstadoMalha, float | None]

#: Casas decimais das coordenadas do tráfego: 6 casas são ~0,1 m, e cada
#: veículo a menos de bytes conta quando são centenas a 5 Hz.
CASAS_TRAFEGO: Final = 6


@dataclass
class Transmissor:
    """Envia a simulação ao backend em segundo plano.

    Args:
        url_backend: Base do backend, ex.: `http://localhost:8000`.
        cenario, modo, seed: O ponto que está rodando.
        georreferencia: Converte a posição do VE em latitude/longitude.
        id_pedido: O pedido do atendente, se houver.
        velocidade: Múltiplo do tempo real em que roda; `None` é o máximo.
        enviar: Substitui o POST (testes).
        relogio: Relógio monotônico (testes).
    """

    url_backend: str
    cenario: str
    modo: str
    seed: int
    georreferencia: Georreferencia
    id_pedido: int | None = None
    velocidade: float | None = None
    intervalo_s: float = INTERVALO_S
    enviar: Callable[[dict[str, Any]], None] | None = None
    relogio: Callable[[], float] = time.monotonic
    enviados: int = 0
    falhas: int = 0
    _fotos: deque[Foto] = field(default_factory=lambda: deque(maxlen=LIMITE_FOTOS))
    # Posições na rede, em metros. Trocado por inteiro a cada leitura: a thread
    # de envio só lê a referência, sem trava.
    _trafego: list[tuple[float, float]] = field(default_factory=list)
    _ultimo_trafego: float = float("-inf")
    _preempcao: dict[str, bool] = field(default_factory=dict)
    _parar: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None
    _cliente: httpx.Client | None = None

    def publicar(self, estado: EstadoMalha, latencia_ms: float | None) -> None:
        """Chamado pelo laço, a cada passo. Só anexa."""
        self._fotos.append((estado, latencia_ms))

    def quer_trafego(self) -> bool:
        """Se já passou um intervalo de envio desde a última leitura do tráfego."""
        return self.relogio() - self._ultimo_trafego >= self.intervalo_s

    def publicar_trafego(self, posicoes: Sequence[tuple[float, float]]) -> None:
        """Chamado pelo laço quando `quer_trafego()`: posições na rede, em metros."""
        self._ultimo_trafego = self.relogio()
        self._trafego = list(posicoes)

    def iniciar(self) -> None:
        if self.enviar is None:
            self._cliente = httpx.Client(base_url=self.url_backend, timeout=1.0)
        self._thread = threading.Thread(target=self._rodar, name="transmissor", daemon=True)
        self._thread.start()

    def encerrar(self) -> None:
        """Para a thread e manda o que sobrou."""
        self._parar.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self.enviar_pendentes()
        if self._cliente is not None:
            self._cliente.close()

    def enviar_pendentes(self) -> None:
        fotos = []
        while self._fotos:
            fotos.append(self._fotos.popleft())
        corpo = self.montar(fotos)
        if corpo is None:
            return
        try:
            if self.enviar is not None:
                self.enviar(corpo)
            else:
                assert self._cliente is not None
                self._cliente.post("/api/v1/simulacoes/transmissao", json=corpo).raise_for_status()
            self.enviados += 1
        except httpx.HTTPError:
            self.falhas += 1

    def montar(self, fotos: Sequence[Foto]) -> dict[str, Any] | None:
        """O corpo de `POST /simulacoes/transmissao`, a partir das fotos acumuladas."""
        if not fotos:
            return None
        eventos = []
        for estado, _ in fotos:
            for id_semaforo, semaforo in estado.semaforos.items():
                antes = self._preempcao.get(id_semaforo, False)
                if semaforo.em_preempcao != antes:
                    verbo = "iniciada" if semaforo.em_preempcao else "encerrada"
                    eventos.append(
                        {
                            "nivel": "INFO",
                            "texto": f"Preempção {verbo} em {id_semaforo} (t={estado.t:.1f} s)",
                        }
                    )
                self._preempcao[id_semaforo] = semaforo.em_preempcao
        estado, latencia_ms = fotos[-1]
        veiculos = []
        for ve in estado.veiculos_emergencia:
            lat, lon = self.georreferencia.para_lat_lon(*ve.posicao)
            veiculos.append(
                {
                    "id": ve.id,
                    "tipo": ve.tipo.value,
                    "criticidade": int(ve.criticidade),
                    "lat": lat,
                    "lon": lon,
                    "velocidade": ve.velocidade,
                }
            )
        return {
            "cenario": self.cenario,
            "modo": self.modo,
            "seed": self.seed,
            "id_pedido": self.id_pedido,
            "t": estado.t,
            "semaforos": [
                {
                    "id": id_semaforo,
                    "fase": semaforo.fase_atual,
                    "sinal": semaforo.sinal.value,
                    "em_preempcao": semaforo.em_preempcao,
                }
                for id_semaforo, semaforo in sorted(estado.semaforos.items())
            ],
            "veiculos": veiculos,
            "eventos": eventos,
            "latencia_ms": latencia_ms,
            "trafego": [self._lat_lon(x, y) for x, y in self._trafego],
            "velocidade": self.velocidade,
        }

    def _lat_lon(self, x: float, y: float) -> tuple[float, float]:
        lat, lon = self.georreferencia.para_lat_lon(x, y)
        return round(lat, CASAS_TRAFEGO), round(lon, CASAS_TRAFEGO)

    def _rodar(self) -> None:
        while not self._parar.wait(self.intervalo_s):
            self.enviar_pendentes()
