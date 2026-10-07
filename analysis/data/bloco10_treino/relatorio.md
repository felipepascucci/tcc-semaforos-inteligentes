# Treino da política de desempate — entrega 10.5

## O conjunto de treino, antes do ajuste

- Exemplos de treino: 517
- VE mais prejudicado no ramo vencedor é o A (corredor): 517 de 517
- Diferença de cruzamentos_restantes (A - B): mín 2, máx 4, positiva em 517
- Diferença de fila_por_faixa igual a zero: 122
- Pares de tipos diferentes: 517; E8 seguiu a ordem de tipo em 517 de 517

## Seleção da regularização (ajuste no treino, escolha na validação)

| λ | perda treino | perda validação | acerto validação | custo médio validação (s) |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 0.3993 | 0.5187 | 66.7% | 4.30 |
| 0.0001 | 0.3993 | 0.5183 | 66.7% | 4.30 |
| 0.001 | 0.3996 | 0.5158 | 66.7% | 4.30 |
| 0.01 **←** | 0.4103 | 0.5118 | 66.7% | 4.30 |
| 0.1 | 0.4992 | 0.5671 | 63.7% | 4.83 |
| 1 | 0.6383 | 0.6596 | 63.7% | 4.83 |

λ escolhido: 0.01

## Pesos (unidades originais)

- `eta_s`: -0.0396944  (escalado: -1.4035)
- `velocidade_ms`: -0.152886  (escalado: -1.0966)
- `fila_por_faixa`: +0.000681437  (escalado: +0.0018)
- `cruzamentos_restantes`: +0.522932  (escalado: +1.8265)

## Avaliação pela régua do rótulo

| divisão | cruzamento | política | exemplos | escolhe B | acerto | custo médio (s) |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| treino | todos | rotulo | 517 | 141 | 100.0% | 0.00 |
| treino | todos | modelo | 517 | 30 | 72.3% | 3.26 |
| treino | todos | e8 | 517 | 171 | 66.0% | 5.12 |
| treino | todos | menor_eta | 517 | 357 | 48.9% | 8.48 |
| treino | todos | sempre_a | 517 | 0 | 72.7% | 3.29 |
| treino | CRUZ_02 | rotulo | 301 | 113 | 100.0% | 0.00 |
| treino | CRUZ_02 | modelo | 301 | 30 | 61.8% | 5.21 |
| treino | CRUZ_02 | e8 | 301 | 104 | 64.5% | 5.19 |
| treino | CRUZ_02 | menor_eta | 301 | 236 | 48.5% | 8.73 |
| treino | CRUZ_02 | sempre_a | 301 | 0 | 62.5% | 5.28 |
| treino | CRUZ_08 | rotulo | 216 | 28 | 100.0% | 0.00 |
| treino | CRUZ_08 | modelo | 216 | 0 | 87.0% | 0.54 |
| treino | CRUZ_08 | e8 | 216 | 67 | 68.1% | 5.02 |
| treino | CRUZ_08 | menor_eta | 216 | 121 | 49.5% | 8.14 |
| treino | CRUZ_08 | sempre_a | 216 | 0 | 87.0% | 0.54 |
| validacao | todos | rotulo | 135 | 49 | 100.0% | 0.00 |
| validacao | todos | modelo | 135 | 6 | 66.7% | 4.30 |
| validacao | todos | e8 | 135 | 48 | 60.7% | 7.19 |
| validacao | todos | menor_eta | 135 | 90 | 56.3% | 6.43 |
| validacao | todos | sempre_a | 135 | 0 | 63.7% | 4.83 |
| validacao | CRUZ_02 | rotulo | 81 | 40 | 100.0% | 0.00 |
| validacao | CRUZ_02 | modelo | 81 | 4 | 53.1% | 6.82 |
| validacao | CRUZ_02 | e8 | 81 | 28 | 58.0% | 6.90 |
| validacao | CRUZ_02 | menor_eta | 81 | 60 | 58.0% | 5.88 |
| validacao | CRUZ_02 | sempre_a | 81 | 0 | 50.6% | 7.45 |
| validacao | CRUZ_08 | rotulo | 54 | 9 | 100.0% | 0.00 |
| validacao | CRUZ_08 | modelo | 54 | 2 | 87.0% | 0.53 |
| validacao | CRUZ_08 | e8 | 54 | 20 | 64.8% | 7.61 |
| validacao | CRUZ_08 | menor_eta | 54 | 30 | 53.7% | 7.25 |
| validacao | CRUZ_08 | sempre_a | 54 | 0 | 83.3% | 0.88 |

## O que isto não é

Não é resultado de H4. É o modelo descrito nas seeds de treino e validação, pela régua do rótulo; H4 é testada no Bloco 8, com o braço PREEMPCAO_ML nas seeds 1..50 do cenário de avaliação.
