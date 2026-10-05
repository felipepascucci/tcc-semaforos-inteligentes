"""Ritmo da simulação ao vivo: N vezes o tempo real (Bloco 7).

Sem ritmo, o executor roda o mais rápido que a máquina permite, ~50x o tempo
real, e um VE atravessa o mapa do dashboard em segundos. Com ritmo, o laço
dorme no fim de cada passo até o relógio de parede alcançar o tempo simulado
dividido pela velocidade.

**Não muda o resultado.** O SUMO não sabe do ritmo: a espera fica fora dele e
fora do trecho cronometrado do RNF01. A mesma seed dá a mesma execução em
qualquer velocidade. Se a máquina não acompanhar a velocidade pedida, o laço só
não dorme, e a simulação anda o mais rápido que conseguir.

O lote do Bloco 8 roda sem ritmo.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Ritmo:
    """Segura o laço para a simulação andar a `velocidade` vezes o tempo real.

    Args:
        velocidade: Múltiplo do tempo real; 1 é tempo real.
        relogio: Relógio monotônico, em segundos (injetável nos testes).
        dormir: Função de espera (injetável nos testes).
    """

    velocidade: float
    relogio: Callable[[], float] = time.monotonic
    dormir: Callable[[float], None] = time.sleep
    _inicio: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        if self.velocidade <= 0:
            raise ValueError(f"velocidade precisa ser positiva, não {self.velocidade}")

    def esperar(self, t: float) -> float:
        """Espera até o passo `t` (segundos simulados) estar no horário.

        Returns:
            Quanto dormiu, em segundos.
        """
        agora = self.relogio()
        if self._inicio is None:
            self._inicio = (t, agora)
            return 0.0
        t0, relogio0 = self._inicio
        falta = relogio0 + (t - t0) / self.velocidade - agora
        if falta <= 0:
            return 0.0
        self.dormir(falta)
        return falta
