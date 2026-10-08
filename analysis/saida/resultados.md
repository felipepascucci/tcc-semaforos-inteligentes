# Capítulo 5 — resultados gerados

> Gerado por `python -m analysis.gerar_resultados_tcc`. Nenhum número deste
> arquivo foi digitado à mão; as tabelas em LaTeX estão em `tabelas/`.

## 1. Caracterização das execuções

- Pasta dos dados: `C:/Users/User/Desktop/tcc/analysis/data/bloco8`
- Execuções válidas: 650
- Seeds: 1..50 (50)
- Versão do código: `85b1803`

| Cenário | Modo | Execuções |
| --- | --- | ---: |
| intenso | FIXO | 50 |
| intenso | PREEMPCAO | 50 |
| intenso | PREEMPCAO_COMPENSADA | 50 |
| leve | FIXO | 50 |
| leve | PREEMPCAO | 50 |
| leve | PREEMPCAO_COMPENSADA | 50 |
| moderado | FIXO | 50 |
| moderado | PREEMPCAO | 50 |
| moderado | PREEMPCAO_COMPENSADA | 50 |
| multiplas_emergencias | FIXO | 50 |
| multiplas_emergencias | PREEMPCAO | 50 |
| multiplas_emergencias | PREEMPCAO_COMPENSADA | 50 |
| multiplas_emergencias | PREEMPCAO_ML | 50 |

Registros em `descartes.csv`: 36
REEXECUCAO: 36

## 2. Tabelas

### T1 — Tempo de deslocamento do VE por cenário e braço

| Cenário | Modo | n | Mediana (s) | IQR (s) | Redução vs. FIXO | IC 95% da redução | p Wilcoxon | p Holm | Cliff's δ |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| leve (v/c 0,18) | FIXO | 50 | 456,9 | 17,4 | — | — | — | — | — |
| leve (v/c 0,18) | PREEMPCAO | 50 | 270,8 | 13,3 | 40,5% | [39,8%; 41,2%] | < 0,001 | < 0,001 | -1,00 (grande) |
| leve (v/c 0,18) | PREEMPCAO_COMPENSADA | 50 | 266,9 | 8,3 | 41,1% | [40,5%; 41,7%] | < 0,001 | < 0,001 | -1,00 (grande) |
| moderado (v/c 0,42) | FIXO | 50 | 492,6 | 14,5 | — | — | — | — | — |
| moderado (v/c 0,42) | PREEMPCAO | 50 | 320,2 | 14,1 | 35,0% | [34,4%; 35,7%] | < 0,001 | < 0,001 | -1,00 (grande) |
| moderado (v/c 0,42) | PREEMPCAO_COMPENSADA | 50 | 315,8 | 18,7 | 35,6% | [34,9%; 36,4%] | < 0,001 | < 0,001 | -1,00 (grande) |
| intenso (v/c 0,73) | FIXO | 50 | 528,9 | 21,6 | — | — | — | — | — |
| intenso (v/c 0,73) | PREEMPCAO | 50 | 381,0 | 16,6 | 28,1% | [27,3%; 29,0%] | < 0,001 | < 0,001 | -1,00 (grande) |
| intenso (v/c 0,73) | PREEMPCAO_COMPENSADA | 50 | 389,1 | 22,9 | 26,5% | [25,5%; 27,5%] | < 0,001 | < 0,001 | -1,00 (grande) |
| multiplas_emergencias (v/c 0,42) | FIXO | 50 | 368,5 | 8,2 | — | — | — | — | — |
| multiplas_emergencias (v/c 0,42) | PREEMPCAO | 50 | 253,0 | 7,7 | 31,8% | [31,3%; 32,4%] | < 0,001 | < 0,001 | -1,00 (grande) |
| multiplas_emergencias (v/c 0,42) | PREEMPCAO_COMPENSADA | 50 | 250,2 | 9,1 | 32,0% | [31,5%; 32,6%] | < 0,001 | < 0,001 | -1,00 (grande) |
| multiplas_emergencias (v/c 0,42) | PREEMPCAO_ML | 50 | 255,0 | 9,1 | 30,9% | [30,3%; 31,5%] | < 0,001 | < 0,001 | -1,00 (grande) |

n é o número de seeds pareadas; cada uma entra com a travessia média dos VEs presentes em todos os braços do cenário (`analysis/carregar.py`). VEs fora da interseção: 120.
Redução: média, sobre as seeds, de (FIXO - braço) / FIXO; IC por bootstrap percentil das seeds. Wilcoxon bilateral; p de Holm sobre a família do capítulo. δ = P(braço > FIXO) - P(braço < FIXO): negativo é travessia menor.

### T1b — Diferença pareada da travessia do VE e o teste secundário

| Cenário | Modo | Mediana da diferença (s) | IC 95% | t pareado | p (t) | Shapiro-Wilk (dif.) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| leve (v/c 0,18) | PREEMPCAO | -185,2 | [-189,4; -178,2] | -82,37 | < 0,001 | 0,971 |
| leve (v/c 0,18) | PREEMPCAO_COMPENSADA | -190,1 | [-193,3; -182,8] | -87,15 | < 0,001 | 0,163 |
| moderado (v/c 0,42) | PREEMPCAO | -171,9 | [-174,4; -167,0] | -86,08 | < 0,001 | 0,012 |
| moderado (v/c 0,42) | PREEMPCAO_COMPENSADA | -176,3 | [-179,7; -169,3] | -85,82 | < 0,001 | 0,883 |
| intenso (v/c 0,73) | PREEMPCAO | -148,0 | [-156,0; -144,1] | -50,54 | < 0,001 | 0,580 |
| intenso (v/c 0,73) | PREEMPCAO_COMPENSADA | -142,1 | [-152,1; -131,7] | -44,84 | < 0,001 | 0,364 |
| multiplas_emergencias (v/c 0,42) | PREEMPCAO | -117,6 | [-119,9; -114,3] | -108,09 | < 0,001 | 0,710 |
| multiplas_emergencias (v/c 0,42) | PREEMPCAO_COMPENSADA | -118,3 | [-120,5; -114,8] | -97,18 | < 0,001 | 0,696 |
| multiplas_emergencias (v/c 0,42) | PREEMPCAO_ML | -113,3 | [-117,0; -111,3] | -87,41 | < 0,001 | 0,169 |

Diferença por seed: braço - FIXO. O t pareado é o teste secundário; o Shapiro-Wilk das diferenças é informado para o leitor julgar a normalidade, e não escolhe o teste (`context/07` §3.2).

### T2 — Latência do sistema

| Ambiente | Modo | n | Mín (ms) | Mediana (ms) | Média (ms) | p95 (ms) | p99 (ms) | Máx (ms) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SIMULACAO (decisão) | PREEMPCAO | 144000 | 0,006 | 0,025 | 0,042 | 0,110 | 0,158 | 4,457 |
| SIMULACAO (decisão) | PREEMPCAO_COMPENSADA | 144000 | 0,006 | 0,047 | 0,051 | 0,116 | 0,155 | 12,163 |
| SIMULACAO (decisão) | PREEMPCAO_ML | 36000 | 0,007 | 0,024 | 0,053 | 0,141 | 0,188 | 0,715 |
| SIMULACAO (decisão) | pior execução | 450 execuções | — | — | — | 0,199 | 0,295 | 12,163 |
| HARDWARE (fim a fim) | bancada | 100 | 0,114 | 24,920 | 25,683 | 31,617 | 43,311 | 46,349 |

SIMULACAO: latência de **decisão** (RNF01), `motor.avaliar()` cronometrado; as linhas por modo juntam as decisões das execuções exemplares (`latencias.csv`), e a linha *pior execução* traz o maior p95, p99 e máximo entre todas as execuções com motor (`execucoes.csv`). HARDWARE: latência **fim a fim** de H3, da leitura da tag ao `PREEMP_INI`, sessão `2026-10-07T16:18:08.177357+00:00`. São grandezas diferentes (`context/07` §1, nota de T2). Percentis pelo posto mais próximo.

### T3 — Impacto nas vias transversais

| Cenário | Modo | Espera média transversal (s) | Fila máxima (veíc.) | Throughput (veíc./h) | Δ vs. FIXO | p Wilcoxon | p Holm |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| leve (v/c 0,18) | FIXO | 19,16 | 7,0 | 2127 | — | — | — |
| leve (v/c 0,18) | PREEMPCAO | 18,91 | 7,0 | 2161 | -1,3% | 0,023 | 0,091 |
| leve (v/c 0,18) | PREEMPCAO_COMPENSADA | 18,74 | 7,0 | 2159 | -2,2% | 0,003 | 0,019 |
| moderado (v/c 0,42) | FIXO | 15,36 | 10,0 | 4950 | — | — | — |
| moderado (v/c 0,42) | PREEMPCAO | 18,34 | 12,0 | 5023 | +19,4% | < 0,001 | < 0,001 |
| moderado (v/c 0,42) | PREEMPCAO_COMPENSADA | 18,30 | 13,0 | 5016 | +19,2% | < 0,001 | < 0,001 |
| intenso (v/c 0,73) | FIXO | 16,31 | 15,0 | 8457 | — | — | — |
| intenso (v/c 0,73) | PREEMPCAO | 24,17 | 15,0 | 8533 | +48,2% | < 0,001 | < 0,001 |
| intenso (v/c 0,73) | PREEMPCAO_COMPENSADA | 23,59 | 15,0 | 8519 | +44,6% | < 0,001 | < 0,001 |
| multiplas_emergencias (v/c 0,42) | FIXO | 15,39 | 10,5 | 4956 | — | — | — |
| multiplas_emergencias (v/c 0,42) | PREEMPCAO | 18,38 | 12,0 | 5024 | +19,5% | < 0,001 | < 0,001 |
| multiplas_emergencias (v/c 0,42) | PREEMPCAO_COMPENSADA | 18,63 | 13,0 | 5014 | +21,1% | < 0,001 | < 0,001 |
| multiplas_emergencias (v/c 0,42) | PREEMPCAO_ML | 18,66 | 13,0 | 5021 | +21,3% | < 0,001 | < 0,001 |

Espera: média entre as seeds de `tempo_espera_medio_transversal_s` (a hora inteira, aquecimento descartado; P17). Fila máxima: mediana entre as seeds do maior pico de fila entre os acessos transversais. Throughput: veículos que completaram a rota por hora simulada, na malha inteira.

### T3b — Mitigação do acréscimo de espera transversal pela compensação (H2)

| Cenário | Seeds | Custo da preempção | Mitigação | IC 95% | p (COMP. x PREEMP.) | p Holm | Meta ≥ 15% |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| leve (v/c 0,18) | 50 | -1,3% | -71,5% | [-551,4%; 36,5%] | 0,255 | 0,509 | sem meta |
| moderado (v/c 0,42) | 50 | +19,4% | +1,3% | [-5,2%; 7,6%] | 0,815 | 0,815 | não atinge |
| intenso (v/c 0,73) | 50 | +48,2% | +7,4% | [3,3%; 11,2%] | 0,002 | 0,014 | não atinge |
| multiplas_emergencias (v/c 0,42) | 50 | +19,5% | -8,3% | [-14,9%; -2,1%] | 0,014 | 0,071 | sem meta |

Custo: (PREEMPCAO - FIXO) / FIXO. Mitigação: (PREEMPCAO - COMPENSADA) / (PREEMPCAO - FIXO), com as médias entre as seeds (P17). A meta vale em `moderado` e `intenso`; nos demais, e onde o acréscimo é próximo de zero, a fração é instável e é só descritiva.

### T4 — Priorização: travessias sem parada, conflitos adiados e abortos

| Cenário | Modo | VEs | Sem parada (RF03) | Conflitos adiados | Abortos |
| --- | --- | ---: | ---: | ---: | ---: |
| leve (v/c 0,18) | PREEMPCAO | 298 | 185 (62,1%) | 0 | 0 |
| leve (v/c 0,18) | PREEMPCAO_COMPENSADA | 299 | 188 (62,9%) | 0 | 0 |
| moderado (v/c 0,42) | PREEMPCAO | 262 | 210 (80,2%) | 0 | 0 |
| moderado (v/c 0,42) | PREEMPCAO_COMPENSADA | 274 | 225 (82,1%) | 0 | 0 |
| intenso (v/c 0,73) | PREEMPCAO | 250 | 198 (79,2%) | 0 | 0 |
| intenso (v/c 0,73) | PREEMPCAO_COMPENSADA | 250 | 185 (74,0%) | 0 | 0 |
| multiplas_emergencias (v/c 0,42) | PREEMPCAO | 566 | 289 (51,1%) | 529 | 0 |
| multiplas_emergencias (v/c 0,42) | PREEMPCAO_COMPENSADA | 567 | 295 (52,0%) | 531 | 0 |
| multiplas_emergencias (v/c 0,42) | PREEMPCAO_ML | 576 | 257 (44,6%) | 560 | 0 |

**T4 adaptada ao que o lote registra.** O `context/07` §4 prevê as colunas *priorizações solicitadas*, *sucesso*, *conflito adiado*, *timeout* e *abortado*, que viriam de `log_prioridade`; a simulação não grava `log_prioridade`, e o lote não conta pedidos de priorização nem timeouts de E6. O que existe: VEs que completaram a rota e quantos não pararam (`waitingCount = 0`, o critério do RF03); episódios de disputa entre VEs, em cada um dos quais um VE é adiado (`conflitos_por_execucao.csv`); e abortos, que o executor só faz por violação de invariante (`executor.decidir_e_aplicar`).

### T5 — Segurança

| Cenário | Modo | Execuções válidas | Colisões | Violações I1-I5 | Teleportes | Descartadas |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| leve (v/c 0,18) | FIXO | 50 | 0 | 0 | 0 | 0 |
| leve (v/c 0,18) | PREEMPCAO | 50 | 0 | 0 | 0 | 0 |
| leve (v/c 0,18) | PREEMPCAO_COMPENSADA | 50 | 0 | 0 | 0 | 0 |
| moderado (v/c 0,42) | FIXO | 50 | 0 | 0 | 0 | 0 |
| moderado (v/c 0,42) | PREEMPCAO | 50 | 0 | 0 | 0 | 0 |
| moderado (v/c 0,42) | PREEMPCAO_COMPENSADA | 50 | 0 | 0 | 0 | 0 |
| intenso (v/c 0,73) | FIXO | 50 | 0 | 0 | 0 | 0 |
| intenso (v/c 0,73) | PREEMPCAO | 50 | 0 | 0 | 0 | 0 |
| intenso (v/c 0,73) | PREEMPCAO_COMPENSADA | 50 | 0 | 0 | 0 | 0 |
| multiplas_emergencias (v/c 0,42) | FIXO | 50 | 0 | 0 | 0 | 0 |
| multiplas_emergencias (v/c 0,42) | PREEMPCAO | 50 | 0 | 0 | 0 | 0 |
| multiplas_emergencias (v/c 0,42) | PREEMPCAO_COMPENSADA | 50 | 0 | 0 | 0 | 0 |
| multiplas_emergencias (v/c 0,42) | PREEMPCAO_ML | 50 | 0 | 0 | 0 | 0 |

Todas devem ser zero (`context/07` §4). Descartadas: execuções que `validar_execucao()` reprovou, registradas em `descartes.csv` e fora das demais tabelas (`context/06` §4).

### T6 — Verificação das hipóteses

| Hipótese | Critério | Resultado medido | Veredito |
| --- | --- | --- | --- |
| H1 | Redução ≥ 25% em moderado e intenso, braço PREEMPCAO (P1) | moderado: 35,0% [34,4%; 35,7%], p Holm < 0,001; intenso: 28,1% [27,3%; 29,0%], p Holm < 0,001 | ACEITA |
| H1 (exploratório) | leve — sem meta | leve: 40,5% [39,8%; 41,2%], p Holm < 0,001 | n/a |
| H2 | Mitigação ≥ 15% do acréscimo em moderado e intenso (P17) | moderado: +1,3% [-5,2%; 7,6%]; intenso: +7,4% [3,3%; 11,2%] | REJEITADA |
| H3 | p95 fim a fim < 200 ms, bancada | p95 31,6 ms, n = 100 | ACEITA |
| RNF01 | p95 da decisão < 100 ms | pior p95 entre as execuções: 0,199 ms | ATENDE |
| H4 | PREEMPCAO_ML reduz o tempo do VE mais prejudicado — direcional, sem meta (P19) | mediana da diferença -4,6 s [-11,0; 2,6], δ -0,22, p Holm 0,174 | NULO |

Regras de veredito no docstring de `analysis/gerar_resultados_tcc.py`, declaradas antes dos dados do Bloco 8.

## 3. H4 — disputas e o que o modelo decidiu

| Braço | Execuções | Disputas | Mesmo nível | Mesmo nível, decidíveis | Mesmo nível, sob preempção em curso | Decididas pelo modelo | Modelo ≠ E8 | Execuções com divergência |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `PREEMPCAO` | 50 | 529 | 529 | 411 | 118 | — | — | — |
| `PREEMPCAO_ML` | 50 | 560 | 560 | 429 | 131 | 429 | 323 | 50 |

Relatório completo em `h4.md`.

## 4. Figuras

- `figuras/F1_travessia_ve.pdf`
- `figuras/F2_latencia_decisao.pdf`
- `figuras/F5_reducao_saturacao.pdf`
- `figuras/F3_espaco_tempo.pdf`
- `figuras/F4_fila_transversal.pdf`
- `figuras/F6_fases.pdf`

## 5. Pendências e conferências

- Traço x lote: 15 VEs comparados, 0 divergentes (maior diferença 0,00 s) — confere.
