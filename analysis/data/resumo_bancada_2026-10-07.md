# Passagens de bancada — RNF05 e H3

Sessões da ponte: 2026-10-07T16:18:08.177357+00:00
Versão do código: 5409d93
Condição: emissor no USB do notebook (decisão de 2026-10-06, `context/09`).

## RNF05 — leituras que chegam ao UNO com a rua certa

Leituras impressas pelo emissor (denominador): 100
Viraram evento de decisão com a rua certa: 100 (100.0%)
Desfechos: PREEMP_INI: 100
- RUA1: 25 de 25
- RUA2: 25 de 25
- RUA3: 25 de 25
- RUA4: 25 de 25

Critério (≥ 95%): **atende**.

## H3 — latência fim a fim (leitura da tag → PREEMP_INI)

| Amostras | n | Mín | Mediana | Média | p95 | p99 | Máx |
|---|---|---|---|---|---|---|---|
| Todas | 100 | 0.1 ms | 24.9 ms | 25.7 ms | 31.6 ms | 43.3 ms | 46.3 ms |
| Sem carimbo atrasado | 98 | 23.4 ms | 25.0 ms | 26.1 ms | 33.0 ms | 46.3 ms | 46.3 ms |

Critério (p95 < 200 ms), sobre todas: **atende**.
Carimbo atrasado (≥ 10 bytes já esperando na porta, em qualquer lado): 2 — 0.1 ms na RUA4 (35/86 bytes), 8.8 ms na RUA2 (15/6 bytes). Ficam no resultado; a segunda linha da tabela é só a sensibilidade.
