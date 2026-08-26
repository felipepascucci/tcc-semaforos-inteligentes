"""Calibração dos cenários — entrega 3.0, encaminhamento de P11.

Dois módulos com papéis deliberadamente separados:

* `fluxo_saturacao` — **mede** o fluxo de saturação da própria malha. Precisa do
  SUMO, produz `analysis/data/fluxo_saturacao.csv`.
* `cenarios` — **deriva** o grau de saturação de cada cenário a partir daquela
  medição. Aritmética pura, testável sem SUMO instalado.

A separação é o que permite testar a conta sem depender do simulador, e é
também o que deixa explícito onde termina a medição e começa a interpretação.
"""
