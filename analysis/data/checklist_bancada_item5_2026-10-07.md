# Checklist da bancada — o que a telemetria gravada mostra

Itens 6, 8 e 13, quantas vezes a tag do item 5 passou, e o LCD de 5b e 10, são observação de quem está na bancada (`context/06` §6).

## Sessão 2026-10-08T00:32:44.495549+00:00

De 2026-10-08T00:32:46.159443+00:00 a 2026-10-08T00:34:15.307024+00:00 (relógio do notebook, UTC)
Versão do código: bc88ecd
Linhas do UNO: 224 (0 ilegíveis); escritas da ponte: 1
Eventos: BOOT 1, PREEMP_FIM 1, PREEMP_INI 1, SEM_OCORRENCIA 1

| Item | Verificação | Pelo dado |
|---|---|---|
| 1 | Ciclo de 12 s, sem travar por 5 min; liga em all-red | sem veredito |
| 2 | Nunca verde nos dois eixos; em emergência só a aproximação do VE abre | **atende** |
| 3 | Verde → amarelo → vermelho, e all-red antes de todo verde, inclusive na emergência | **atende** |
| 5 | Tag fora das 4 ruas: sem envio e sem mexer no semáforo | **atende** |
| 5b | Tag sem ocorrência: SEM_OCORRENCIA, sem mexer no semáforo | **atende** |
| 10 | Prioridade pela criticidade: o mais crítico interrompe, o outro vai para a fila | sem veredito |
| 11 | Teto de 30 s (EV,TIMEOUT) e volta pelo eixo oposto | sem veredito |
| 12 | Operação contínua de 30 min sem travamento ou reboot | sem veredito |
| 14 | Ponte encerrada no meio de uma emergência | sem veredito |
| 15 | Ponte reiniciada: o UNO volta negando todos, e a lista volta | **não atende** |

### Item 1 — sem veredito

- Arranque 1: primeira ST RRRR; primeiro verde GGRR em 1125 ms do millis() — ok
- Ciclos puros: 6; período mín 12000 ms, máx 12001 ms (esperado 12000 ± 60 ms); fora da tolerância: 0
- Maior trecho contínuo de ciclo dentro da tolerância: 72.0 s (precisa de 300 s)
- Sessão sem 5 min de ciclo puro: nada a julgar no trecho.

### Item 2 — **atende**

- ST na sessão: 220; com verde nos dois eixos (I1): 0
- Verdes novos em emergência fora da aproximação do VE: 0
- Emergências atendidas até o fim: 1; sem verde exclusivo: 0

### Item 3 — **atende**

- Mudanças de luz conferidas: 41 (G→Y 26, R→G 26, Y→R 26)
- Entradas em emergência: 1; saídas: 1
- Violações de I2, I3 ou I4: 0

### Item 5 — **atende**

- Janela: da primeira ST com a ambulância em ocorrência (2026-10-08T00:33:08.289985+00:00) até a passagem de controle (2026-10-08T00:34:02.154510+00:00): 53.9 s
- Leituras do emissor na janela: 0 (a primeira depois da ocorrência é o controle)
- Eventos do UNO na janela: 0
- ST na janela: 135; fora do regime de ciclo: 0; com a ambulância sem ocorrência: 0
- Ciclos puros inteiros na janela: 4; período mín 12000 ms, máx 12000 ms (esperado 12000 ± 60 ms)
- Controle: F39BD606 (RUA1) → PREEMP_INI — ok
- Quantas vezes a tag fora do mapa passou na janela é observação de quem está na bancada.

### Item 5b — **atende**

- AMBULANCIA na RUA1 em 17283 ms: criticidade na ST 0; estado antes/depois igual; o ciclo que a contém durou 12000 ms, só em ciclo; decisão seguinte depois de a Central abrir a ocorrência: PREEMP_INI — ok

### Item 10 — sem veredito

- Nada na sessão.

### Item 11 — sem veredito

- Nada na sessão.

### Item 12 — sem veredito

- Da primeira à última ST: 1.5 min (precisa de 30)
- Reinícios do UNO no meio da sessão: 0
- Maior intervalo entre duas ST, no relógio do notebook: 1.12 s (a ponte dá o UNO por calado a partir de 2 s)
- Tempo pelo millis() do UNO: 1.5 min
- Sessão mais curta que 30 min, sem falha: não é o soak.

### Item 14 — sem veredito

- Última ST da sessão: RRRR, regime C, rua ativa —, lista 100 — a sessão não terminou em emergência.
- O que o UNO fez com a ponte fechada não passa pelo notebook: é observação.

### Item 15 — **não atende**

- Arranque 1: primeira lista 000; a ponte escreveu 100 22.10 s depois do BOOT, e a ST a trouxe inteira 22.13 s depois do BOOT; critério ≤ 2 s — FALHA
