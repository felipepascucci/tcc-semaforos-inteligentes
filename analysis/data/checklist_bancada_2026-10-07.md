# Checklist da bancada — o que a telemetria gravada mostra

Itens 5, 6, 8 e 13, e o LCD de 5b e 10, são observação de quem está na bancada (`context/06` §6).

## Sessão 2026-10-07T17:44:10.212497+00:00

De 2026-10-07T17:44:11.941043+00:00 a 2026-10-07T18:17:16.478459+00:00 (relógio do notebook, UTC)
Versão do código: 71a8b96
Linhas do UNO: 4968 (0 ilegíveis); escritas da ponte: 17
Eventos: BOOT 1, FILA 1, PREEMP_FIM 4, PREEMP_INI 6, RENOVADO 6, SEM_OCORRENCIA 1, TIMEOUT 1

| Item | Verificação | Pelo dado |
|---|---|---|
| 1 | Ciclo de 12 s, sem travar por 5 min; liga em all-red | **atende** |
| 2 | Nunca verde nos dois eixos; em emergência só a aproximação do VE abre | **atende** |
| 3 | Verde → amarelo → vermelho, e all-red antes de todo verde, inclusive na emergência | **atende** |
| 5b | Tag sem ocorrência: SEM_OCORRENCIA, sem mexer no semáforo | **atende** |
| 9 | Log no PostgreSQL com id_correlacao completo | **atende** |
| 10 | Prioridade pela criticidade: o mais crítico interrompe, o outro vai para a fila | **atende** |
| 11 | Teto de 30 s (EV,TIMEOUT) e volta pelo eixo oposto | **atende** |
| 12 | Operação contínua de 30 min sem travamento ou reboot | **atende** |
| 14 | Ponte encerrada no meio de uma emergência | sem veredito |
| 15 | Ponte reiniciada: o UNO volta negando todos, e a lista volta | **atende** |

### Item 1 — **atende**

- Arranque 1: primeira ST RRRR; primeiro verde GGRR em 1125 ms do millis() — ok
- Ciclos puros: 157; período mín 12000 ms, máx 12032 ms (esperado 12000 ± 60 ms); fora da tolerância: 0
- Maior trecho contínuo de ciclo dentro da tolerância: 1140.0 s (precisa de 300 s)

### Item 2 — **atende**

- ST na sessão: 4948; com verde nos dois eixos (I1): 0
- Verdes novos em emergência fora da aproximação do VE: 0
- Emergências atendidas até o fim: 5; sem verde exclusivo: 0 (mais 1 interrompida(s) por VE mais crítico, que volta(m) pela fila)

### Item 3 — **atende**

- Mudanças de luz conferidas: 972 (G→Y 643, R→G 644, Y→R 643)
- Entradas em emergência: 4; saídas: 3
- Violações de I2, I3 ou I4: 0

### Item 5b — **atende**

- AMBULANCIA na RUA3 em 478106 ms: criticidade na ST 0; estado antes/depois igual; o ciclo que a contém durou 12032 ms, só em ciclo; decisão seguinte depois de a Central abrir a ocorrência: PREEMP_INI — ok

### Item 9 — **atende**

- Eventos de decisão na sessão: 14; com exatamente uma linha em log_prioridade no mesmo instante: 14
- Linhas de log_prioridade na janela: 14; sem id_correlacao: 0
- PREEMP_INI sem timestamp_fim (atendimento não fechado): 0 de 6
- Amostras de H3 em metrica_latencia na janela: 2; ligadas a um log: 2; com o mesmo id_correlacao do log: 2

### Item 10 — **atende**

- BOMBEIRO (criticidade 1) na RUA1 interrompeu AMBULANCIA (criticidade 2) na RUA3 em 743613 ms; o interrompido foi atendido no PREEMP_FIM do outro, 9.5 s depois — ok
- O amarelo e o all-red da interrupção estão no item 3; o `Fila:…` do LCD é observação.

### Item 11 — **atende**

- TIMEOUT em 828823 ms: 30000 ms depois do PREEMP_INI (esperado 30000 ± 60), 6 renovações no meio; PREEMP_FIM na RUA4; depois abriu GGRR — ok

### Item 12 — **atende**

- Da primeira à última ST: 33.1 min (precisa de 30)
- Reinícios do UNO no meio da sessão: 0
- Maior intervalo entre duas ST, no relógio do notebook: 1.12 s (a ponte dá o UNO por calado a partir de 2 s)
- Tempo pelo millis() do UNO: 33.1 min

### Item 14 — sem veredito

- Última ST da sessão: RGRR, regime E, rua ativa 2, lista 210 — a ponte foi encerrada no meio de uma emergência.
- O que o UNO fez com a ponte fechada não passa pelo notebook: é observação.

### Item 15 — **atende**

- Arranque 1: primeira lista 000; a ponte escreveu 110 0.17 s depois do BOOT, e a ST a trouxe inteira 1.17 s depois do BOOT; critério ≤ 2 s — ok

## Sessão 2026-10-07T18:18:37.223864+00:00

De 2026-10-07T18:18:38.876413+00:00 a 2026-10-07T18:18:56.381460+00:00 (relógio do notebook, UTC)
Versão do código: 71a8b96
Linhas do UNO: 45 (0 ilegíveis); escritas da ponte: 3
Eventos: BOOT 1

| Item | Verificação | Pelo dado |
|---|---|---|
| 1 | Ciclo de 12 s, sem travar por 5 min; liga em all-red | sem veredito |
| 2 | Nunca verde nos dois eixos; em emergência só a aproximação do VE abre | **atende** |
| 3 | Verde → amarelo → vermelho, e all-red antes de todo verde, inclusive na emergência | sem veredito |
| 5b | Tag sem ocorrência: SEM_OCORRENCIA, sem mexer no semáforo | sem veredito |
| 9 | Log no PostgreSQL com id_correlacao completo | sem veredito |
| 10 | Prioridade pela criticidade: o mais crítico interrompe, o outro vai para a fila | sem veredito |
| 11 | Teto de 30 s (EV,TIMEOUT) e volta pelo eixo oposto | sem veredito |
| 12 | Operação contínua de 30 min sem travamento ou reboot | sem veredito |
| 14 | Ponte encerrada no meio de uma emergência | sem veredito |
| 15 | Ponte reiniciada: o UNO volta negando todos, e a lista volta | **atende** |

### Item 1 — sem veredito

- Arranque 1: primeira ST RRRR; primeiro verde GGRR em 1125 ms do millis() — ok
- Ciclos puros: 1; período mín 12001 ms, máx 12001 ms (esperado 12000 ± 60 ms); fora da tolerância: 0
- Maior trecho contínuo de ciclo dentro da tolerância: 12.0 s (precisa de 300 s)
- Sessão sem 5 min de ciclo puro: nada a julgar no trecho.

### Item 2 — **atende**

- ST na sessão: 44; com verde nos dois eixos (I1): 0
- Verdes novos em emergência fora da aproximação do VE: 0
- Emergências atendidas até o fim: 0; sem verde exclusivo: 0

### Item 3 — sem veredito

- Mudanças de luz conferidas: 8 (G→Y 6, R→G 6, Y→R 4)
- Entradas em emergência: 0; saídas: 0
- Violações de I2, I3 ou I4: 0
- Sem entrada e saída de emergência na sessão: falta metade do item.

### Item 5b — sem veredito

- Nada na sessão.

### Item 9 — sem veredito

- Nada na sessão.

### Item 10 — sem veredito

- Nada na sessão.

### Item 11 — sem veredito

- Nada na sessão.

### Item 12 — sem veredito

- Da primeira à última ST: 0.3 min (precisa de 30)
- Reinícios do UNO no meio da sessão: 0
- Maior intervalo entre duas ST, no relógio do notebook: 1.12 s (a ponte dá o UNO por calado a partir de 2 s)
- Tempo pelo millis() do UNO: 0.3 min
- Sessão mais curta que 30 min, sem falha: não é o soak.

### Item 14 — sem veredito

- Última ST da sessão: YYRR, regime C, rua ativa —, lista 210 — a sessão não terminou em emergência.
- O que o UNO fez com a ponte fechada não passa pelo notebook: é observação.

### Item 15 — **atende**

- Arranque 1: primeira lista 000; a ponte escreveu 210 0.23 s depois do BOOT, e a ST a trouxe inteira 1.17 s depois do BOOT; critério ≤ 2 s — ok

## Sessão 2026-10-07T18:19:00.314018+00:00

De 2026-10-07T18:19:01.996480+00:00 a 2026-10-07T18:19:19.501532+00:00 (relógio do notebook, UTC)
Versão do código: 71a8b96
Linhas do UNO: 45 (0 ilegíveis); escritas da ponte: 6
Eventos: BOOT 1

| Item | Verificação | Pelo dado |
|---|---|---|
| 1 | Ciclo de 12 s, sem travar por 5 min; liga em all-red | sem veredito |
| 2 | Nunca verde nos dois eixos; em emergência só a aproximação do VE abre | **atende** |
| 3 | Verde → amarelo → vermelho, e all-red antes de todo verde, inclusive na emergência | sem veredito |
| 5b | Tag sem ocorrência: SEM_OCORRENCIA, sem mexer no semáforo | sem veredito |
| 9 | Log no PostgreSQL com id_correlacao completo | sem veredito |
| 10 | Prioridade pela criticidade: o mais crítico interrompe, o outro vai para a fila | sem veredito |
| 11 | Teto de 30 s (EV,TIMEOUT) e volta pelo eixo oposto | sem veredito |
| 12 | Operação contínua de 30 min sem travamento ou reboot | sem veredito |
| 14 | Ponte encerrada no meio de uma emergência | sem veredito |
| 15 | Ponte reiniciada: o UNO volta negando todos, e a lista volta | **atende** |

### Item 1 — sem veredito

- Arranque 1: primeira ST RRRR; primeiro verde GGRR em 1125 ms do millis() — ok
- Ciclos puros: 1; período mín 12001 ms, máx 12001 ms (esperado 12000 ± 60 ms); fora da tolerância: 0
- Maior trecho contínuo de ciclo dentro da tolerância: 12.0 s (precisa de 300 s)
- Sessão sem 5 min de ciclo puro: nada a julgar no trecho.

### Item 2 — **atende**

- ST na sessão: 44; com verde nos dois eixos (I1): 0
- Verdes novos em emergência fora da aproximação do VE: 0
- Emergências atendidas até o fim: 0; sem verde exclusivo: 0

### Item 3 — sem veredito

- Mudanças de luz conferidas: 8 (G→Y 6, R→G 6, Y→R 4)
- Entradas em emergência: 0; saídas: 0
- Violações de I2, I3 ou I4: 0
- Sem entrada e saída de emergência na sessão: falta metade do item.

### Item 5b — sem veredito

- Nada na sessão.

### Item 9 — sem veredito

- Nada na sessão.

### Item 10 — sem veredito

- Nada na sessão.

### Item 11 — sem veredito

- Nada na sessão.

### Item 12 — sem veredito

- Da primeira à última ST: 0.3 min (precisa de 30)
- Reinícios do UNO no meio da sessão: 0
- Maior intervalo entre duas ST, no relógio do notebook: 1.12 s (a ponte dá o UNO por calado a partir de 2 s)
- Tempo pelo millis() do UNO: 0.3 min
- Sessão mais curta que 30 min, sem falha: não é o soak.

### Item 14 — sem veredito

- Última ST da sessão: YYRR, regime C, rua ativa —, lista 210 — a sessão não terminou em emergência.
- O que o UNO fez com a ponte fechada não passa pelo notebook: é observação.

### Item 15 — **atende**

- Arranque 1: primeira lista 000; a ponte escreveu 210 0.11 s depois do BOOT, e a ST a trouxe inteira 1.20 s depois do BOOT; critério ≤ 2 s — ok

## Sessão 2026-10-07T18:19:23.332859+00:00

De 2026-10-07T18:19:24.991764+00:00 a 2026-10-07T18:19:42.496902+00:00 (relógio do notebook, UTC)
Versão do código: 71a8b96
Linhas do UNO: 45 (0 ilegíveis); escritas da ponte: 3
Eventos: BOOT 1

| Item | Verificação | Pelo dado |
|---|---|---|
| 1 | Ciclo de 12 s, sem travar por 5 min; liga em all-red | sem veredito |
| 2 | Nunca verde nos dois eixos; em emergência só a aproximação do VE abre | **atende** |
| 3 | Verde → amarelo → vermelho, e all-red antes de todo verde, inclusive na emergência | sem veredito |
| 5b | Tag sem ocorrência: SEM_OCORRENCIA, sem mexer no semáforo | sem veredito |
| 9 | Log no PostgreSQL com id_correlacao completo | sem veredito |
| 10 | Prioridade pela criticidade: o mais crítico interrompe, o outro vai para a fila | sem veredito |
| 11 | Teto de 30 s (EV,TIMEOUT) e volta pelo eixo oposto | sem veredito |
| 12 | Operação contínua de 30 min sem travamento ou reboot | sem veredito |
| 14 | Ponte encerrada no meio de uma emergência | sem veredito |
| 15 | Ponte reiniciada: o UNO volta negando todos, e a lista volta | **atende** |

### Item 1 — sem veredito

- Arranque 1: primeira ST RRRR; primeiro verde GGRR em 1125 ms do millis() — ok
- Ciclos puros: 1; período mín 12001 ms, máx 12001 ms (esperado 12000 ± 60 ms); fora da tolerância: 0
- Maior trecho contínuo de ciclo dentro da tolerância: 12.0 s (precisa de 300 s)
- Sessão sem 5 min de ciclo puro: nada a julgar no trecho.

### Item 2 — **atende**

- ST na sessão: 44; com verde nos dois eixos (I1): 0
- Verdes novos em emergência fora da aproximação do VE: 0
- Emergências atendidas até o fim: 0; sem verde exclusivo: 0

### Item 3 — sem veredito

- Mudanças de luz conferidas: 8 (G→Y 6, R→G 6, Y→R 4)
- Entradas em emergência: 0; saídas: 0
- Violações de I2, I3 ou I4: 0
- Sem entrada e saída de emergência na sessão: falta metade do item.

### Item 5b — sem veredito

- Nada na sessão.

### Item 9 — sem veredito

- Nada na sessão.

### Item 10 — sem veredito

- Nada na sessão.

### Item 11 — sem veredito

- Nada na sessão.

### Item 12 — sem veredito

- Da primeira à última ST: 0.3 min (precisa de 30)
- Reinícios do UNO no meio da sessão: 0
- Maior intervalo entre duas ST, no relógio do notebook: 1.12 s (a ponte dá o UNO por calado a partir de 2 s)
- Tempo pelo millis() do UNO: 0.3 min
- Sessão mais curta que 30 min, sem falha: não é o soak.

### Item 14 — sem veredito

- Última ST da sessão: YYRR, regime C, rua ativa —, lista 210 — a sessão não terminou em emergência.
- O que o UNO fez com a ponte fechada não passa pelo notebook: é observação.

### Item 15 — **atende**

- Arranque 1: primeira lista 000; a ponte escreveu 210 0.20 s depois do BOOT, e a ST a trouxe inteira 1.17 s depois do BOOT; critério ≤ 2 s — ok
