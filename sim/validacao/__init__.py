"""Validação da malha e das execuções — entrega 3.4 e `context/06` §4.

Dois níveis, com propósitos diferentes:

* `malha` — roda **antes** de experimentar. Confere que a rede, a demanda e a
  calibração descrevem o mesmo mundo. É o passo que `context/04` §12 declara
  não opcional: *"um gridlock não detectado invalida silenciosamente todo o
  experimento"*.
* `execucao` — roda em **toda** execução do lote. Reprova o que não pode entrar
  na análise, com critério fixado de antemão. Descarte silencioso de execução
  ruim é má prática científica; descarte documentado com critério pré-definido é
  metodologia (`context/06` §4).
"""
