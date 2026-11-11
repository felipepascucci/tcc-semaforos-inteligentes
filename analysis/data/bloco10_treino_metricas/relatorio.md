# Política de desempate (P19) — matriz de confusão e métricas por classe

> Gerado por `python -m analysis.metricas_politica`. Nenhum número foi digitado à mão.

Pesos: `backend/config/politica_desempate.yaml`. Rótulos: `analysis/data/bloco10_rotulos/rotulos.csv`.
A = VE do corredor; B = o outro VE da disputa. Empates ficam de fora, como no treino.

## Divisão `treino` (517 exemplos)

| Rótulo \ escolha do modelo | A | B | Total |
| --- | ---: | ---: | ---: |
| A | 360 | 16 | 376 |
| B | 127 | 14 | 141 |
| Total | 487 | 30 | 517 |

Acurácia: 72,3%

| Classe | Precisão | Revocação | F1 | Suporte |
| --- | ---: | ---: | ---: | ---: |
| A | 73,9% | 95,7% | 83,4% | 376 |
| B | 46,7% | 9,9% | 16,4% | 141 |
| macro | 60,3% | 52,8% | 49,9% | 517 |

## Divisão `validacao` (135 exemplos)

| Rótulo \ escolha do modelo | A | B | Total |
| --- | ---: | ---: | ---: |
| A | 85 | 1 | 86 |
| B | 44 | 5 | 49 |
| Total | 129 | 6 | 135 |

Acurácia: 66,7%

| Classe | Precisão | Revocação | F1 | Suporte |
| --- | ---: | ---: | ---: | ---: |
| A | 65,9% | 98,8% | 79,1% | 86 |
| B | 83,3% | 10,2% | 18,2% | 49 |
| macro | 74,6% | 54,5% | 48,6% | 135 |

## O que isto não é

A divisão `validacao` também escolheu o λ, então não é teste cego. O teste
independente da política é H4 (`analysis/saida/h4.md`), sem rótulo de bifurcação.
