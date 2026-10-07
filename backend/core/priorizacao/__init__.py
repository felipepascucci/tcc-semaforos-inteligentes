"""Algoritmo de priorização de veículos de emergência — etapas E1 a E8.

Implementação no Bloco 2, seguindo context/01 §5.2:

* `deteccao.py`    — E1, E2, E3 (distância ao longo da rota, nunca euclidiana)
* `fases.py`       — E4, E5 (transição segura obrigatória)
* `compensacao.py` — E7 (compensação pós-evento, hipótese H2)
* `conflito.py`    — E8 (desempate entre múltiplos VEs)
* `atributos.py`   — o que o modelo de P19 vê de cada VE
* `politica.py`    — inferência do modelo de P19 em E8 (entrega 10.6)
* `motor.py`       — `avaliar(EstadoMalha) -> list[Comando]`
"""
