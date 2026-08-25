"""Núcleo de decisão — Python puro, sem I/O e sem framework.

Regra arquitetural central (context/01 §1): nada aqui pode importar `traci`,
`pyserial`, `sqlalchemy` ou `fastapi`. É o que torna o mesmo algoritmo válido
para a simulação e para o protótipo físico, e o que permite testar tudo sem SUMO
instalado e sem hardware ligado.

A regra é verificada por `backend/tests/test_arquitetura.py` (Bloco 2).
"""
