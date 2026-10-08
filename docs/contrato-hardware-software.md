# Contrato Hardware–Software

Documento de validação da integração entre o software e o protótipo físico. Escrito para ser lido pela equipe de hardware e por agentes de código que trabalhem em `firmware/`, `bridge/` ou `adapters/hardware/`.

> **Autoridade deste arquivo.** A fonte da verdade do escopo continua sendo `context/`. Este documento é uma **síntese orientada à integração**, derivada sobretudo de `context/05`. Onde houver divergência, `context/` vence e este arquivo é que está desatualizado.

| | |
| --- | --- |
| Versão | **4** — 2026-10-06 · **a Central vale na bancada**: o receptor passa do RX (0) para o A0, a ponte leva ao UNO a lista de quem tem ocorrência ativa, e a criticidade decide quem interrompe quem. A v3 (2026-10-05) adaptava o sistema à bancada como estava montada (`docs/hardware/questionario-bloco5.md`) |
| Versões anteriores | v1 e v2 (2026-08-24), no histórico do git. Descreviam outra arquitetura: tag no veículo, Wi-Fi, backend decidindo e o UNO só executando comandos |
| Equipe | Felipe Rafael Tancredi Pascucci · Giovanna Santos da Silva · Isabelle Rosa Moura Ferreira |

---

## §1 — O que o sistema faz

Um veículo de emergência (VE) se aproxima de um cruzamento. O sistema descobre por qual aproximação ele chega e executa a **preempção**: interrompe o ciclo normal e dá verde à aproximação do VE, sempre passando por amarelo e all-red.

Duas frentes de validação, com papéis diferentes:

| Frente | O que é | Papel |
| --- | --- | --- |
| **A — Simulação** | SUMO + TraCI, malha de 8 cruzamentos, 600 execuções, controlada pelo **motor de decisão** em Python | Produz os números de H1, H2 e H4, e o objeto do experimento é o motor |
| **B — Protótipo físico** | Arduino UNO + 4 NodeMCU (3 emissores, um por tipo de veículo, e o receptor) + 3 RC522 + LCD, 4 semáforos | Demonstra a camada V2I por rádio e a atuação segura em hardware real, e produz a medida de H3 |

Consequência prática: uma falha de bancada na véspera não derruba o capítulo de resultados.

---

## §2 — A decisão arquitetural (2026-10-05)

**O protótipo decide sozinho, no Arduino UNO.** A equipe decidiu adaptar o sistema ao hardware montado, sem remontá-lo. O UNO roda a regra que a equipe de hardware já tinha escrito (prioridade por tipo, fila de um lugar, verde exclusivo), agora com transição segura (§7).

O que isso significa:

- **O protótipo não roda o motor de decisão da simulação.** O texto do TCC não pode afirmar o contrário (`context/00` §3).
- **O notebook não está no caminho da decisão.** Ele só ouve o UNO, para o dashboard, o banco e a medida de latência. Se o notebook cair, o cruzamento continua preemptando.
- **A borda (Edge) do pré-projeto é o próprio controlador do cruzamento.**

---

## §3 — Fluxo fim-a-fim no protótipo

```
 [tag fixa na pista — identifica a RUA]
                │  RC522 lê o UID a 2–5 cm
                ▼
 [NodeMCU EMISSOR — no veículo, bateria 9 V]
   UID -> RUA1..RUA4 ; tipo fixo "AMBULANCIA"
                │  ESP-NOW { rua, veiculo }  (rádio direto, MAC a MAC, sem roteador)
                ▼
 [NodeMCU RECEPTOR — no cruzamento, 5 V do UNO]
                │  "RUA3,AMBULANCIA\r\n"   TX -> A0 do UNO, 9600 baud (desde 2026-10-06)
                ▼
 [Arduino UNO R3 — DECIDE e ATUA]
   Central (lista na RAM), criticidade, fila, transição segura, LCD 16x2
                │  pinos 2–13 -> 4 semáforos ;  A4/A5 -> LCD
                │
                │  "EV,…" e "ST,…"   TX -> USB, 9600 baud
                │  "AUT,AMBULANCIA,1"  USB -> RX(0): a lista da Central
                ▼
 [Notebook — bridge/] <-> backend (Central, no banco) -> dashboard
```

---

## §4 — Por que o NodeMCU fala direto com o UNO

A v2 deste documento descartava ligar o ESP ao Arduino. Era o desenho de um protótipo que ainda não existia, e a bancada foi montada assim. Os três motivos da recusa, revistos:

1. **Ponto de medição de latência.** Resolvido sem backend: o notebook ouve o emissor e o UNO e carimba os dois no mesmo relógio (§10).
2. **Motor num lugar só.** Não se aplica: o protótipo não roda o motor (§2).
3. **Dashboard vendo os dois lados.** Atendido pela ponte, que ouve o UNO.

---

## §5 — Inventário e pinagem

**Uma ligação muda (2026-10-06):** o TX do receptor sai do RX (0) e vai para o **A0**. Tabelas completas em `context/05` §1.

### Arduino UNO R3 · `COM3` · alimentado só pelo USB

| Semáforo | Aproximação | Rua (tag) | Eixo | R | Y | G |
| --- | --- | --- | --- | --- | --- | --- |
| S1 | Principal — Sentido A | `RUA1` | Principal | 13 | 12 | 11 |
| S2 | Principal — Sentido B | `RUA2` | Principal | 10 | 9 | 8 |
| S3 | Transversal — Sentido A | `RUA3` | Transversal | 7 | 6 | 5 |
| S4 | Transversal — Sentido B | `RUA4` | Transversal | 4 | 3 | 2 |

LEDs acendem com `HIGH`. LCD I2C `0x27` em A4/A5, a 5 V. **A0 ← TX do NodeMCU receptor** (serial por software; A1 reservado). RX (0) e TX (1) só para o USB. 5V/GND → NodeMCU receptor.

> **Por que o receptor saiu do RX (0).** O conversor USB e o NodeMCU disputavam o mesmo pino, e o NodeMCU prevalecia: o upload falhava com o fio ligado, e o notebook não conseguia escrever no UNO. Com o receptor no A0, a ponte manda a lista da Central e as injeções de teste com a bancada montada, e gravar não pede fio solto.

### NodeMCU emissor (veículo) · RC522 — três, um por carrinho

| RC522 | NodeMCU |
| --- | --- |
| 3.3V | 3V3 |
| RST | D3 — **P8 fechada**: boot normal |
| GND | GND |
| MISO / MOSI / SCK | D6 / D7 / D5 |
| SDA/SS | D8 |

Tipo do veículo fixo no código de cada um (`AMBULANCIA`, `BOMBEIRO` e `POLICIA`, desde 2026-10-08); MAC do receptor fixo (`40:91:51:58:A8:E1`), o mesmo nos três. A mesma pinagem nos três.

### Tags

| UID | Rua |
| --- | --- |
| `F39BD606` | `RUA1` |
| `1BD2308E` | `RUA2` |
| `B7EF8FA0` | `RUA3` |
| `97ABAFA0` | `RUA4` |

---

## §6 — Protocolo serial do UNO

ASCII, linhas com `\r\n`, **9600 baud** — a velocidade do receptor.

### Entrada — a linha do receptor (A0) e a lista da Central (USB)

`<RUA>,<VEICULO>` — `RUA1`..`RUA4` (ou `1`..`4`) e `AMBULANCIA` | `BOMBEIRO` | `POLICIA`. Chega pelo A0; a ponte pode escrever a mesma linha pelo USB, para testar.

`AUT,<VEICULO>,<0..3>` — só pelo USB: a criticidade da ocorrência ativa daquele tipo (0 = sem ocorrência; 1 risco à vida, 2 risco coletivo, 3 urgência). Não gera evento; a lista aparece na `ST`. Pelo A0 é `RECUSADO`: um VE não se autoriza pelo rádio. O UNO liga com todos em 0.

- Linha com vírgula e valor desconhecido → `EV,<ms>,RECUSADO`, sem efeito.
- Linha sem vírgula → ignorada (é o lixo que o ESP8266 imprime no próprio boot).

**Não há comandos do notebook.** O protocolo da v2 (`PING`, `PRE`, `CLR`, `CFG`, `ST?`, `SAFE`, `TESTMODE`, `TEST`) deixou de existir. A lista da Central é um dado contra o qual o UNO decide sozinho, não um comando.

**Teste sem o veículo:** a ponte escreve no UNO, pelo USB, a mesma linha que o receptor escreveria (`POST /injecao`), com a bancada montada. É também assim que o roteiro da demonstração mostra a prioridade entre VEs diferentes, com o intervalo entre as chegadas controlado. Desde 2026-10-08 há também um carrinho por tipo (ambulância, bombeiro e polícia), então a disputa pode ser feita com os carrinhos.

### Saída (TX → USB)

| Linha | Quando |
| --- | --- |
| `ST,<ms>,<s1><s2><s3><s4>,<C\|E>,<rua_ativa>,<rua_fila>,<aut>` | A 2 Hz **e** a cada mudança de estado; `<aut>` = criticidade de ambulância, bombeiro e polícia (`100`: só a ambulância, risco à vida) |
| `EV,<ms>,BOOT` | No `setup()` |
| `EV,<ms>,PREEMP_INI,<rua>,<veiculo>` | O VE passa a ser atendido |
| `EV,<ms>,RENOVADO,<rua>,<veiculo>` | O mesmo VE releu a mesma rua |
| `EV,<ms>,FILA,<rua>,<veiculo>` | O VE entrou na fila |
| `EV,<ms>,DESCARTADO,<rua>,<veiculo>` | Fila ocupada por alguém de criticidade igual ou maior, ou o VE perdeu o lugar na fila |
| `EV,<ms>,PREEMP_FIM,<rua>,<veiculo>` | Acabou o verde do VE, ou estourou o teto |
| `EV,<ms>,TIMEOUT` | Teto de 30 s de emergência contínua, seguido do `PREEMP_FIM` |
| `EV,<ms>,RECUSADO` | Linha inválida |
| `EV,<ms>,SEM_OCORRENCIA,<rua>,<veiculo>` | O tipo do VE não tem ocorrência ativa na Central: não preempta (desde 2026-10-06) |

`R`/`Y`/`G` na ordem S1..S4. `C` ciclo, `E` emergência. Ruas `1..4`, `0` = nenhuma. **Cada linha válida recebida gera exatamente um evento de decisão, escrito antes de qualquer outra coisa** — é o que H3 carimba (§10).

```
uno <- EV,142350,PREEMP_INI,3,AMBULANCIA     VE na Rua 3, eixo principal verde há 1 s
uno <- ST,142350,GGRR,E,3,0,100              resto do verde mínimo
uno <- ST,144350,YYRR,E,3,0,100              amarelo
uno <- ST,146350,RRRR,E,3,0,100              all-red
uno <- ST,147350,RRGR,E,3,0,100              verde exclusivo da Rua 3 — 9 s
uno <- EV,156350,PREEMP_FIM,3,AMBULANCIA
uno <- ST,156350,RRYR,C,0,0,100              volta pelo eixo principal, que esperou
```

---

## §7 — Firmware do UNO (entrega 5.3)

> **O sketch atual precisa ser reescrito, mas o comportamento dele fica.** Ele já é não-bloqueante e tem a lógica de prioridade. O problema é de segurança: na emergência ele apaga o verde e acende o verde do VE **no mesmo instante**, sem amarelo nem all-red, e na troca de eixos do ciclo também não há all-red. Isso viola I2, I3 e I4 (§9), que não são negociáveis. Também tem verde e amarelo invertidos (2 s e 5 s) e usa `String`.

### Regimes

```
CICLO — 2 fases, autônomo
  F1: S1+S2 verde 3 s -> amarelo 2 s -> all-red 1 s
  F2: S3+S4 verde 3 s -> amarelo 2 s -> all-red 1 s -> F1 ...        ciclo = 12 s

EMERGÊNCIA — verde EXCLUSIVO na aproximação do VE, as outras três em vermelho
```

### A regra de decisão — a do sketch, com a Central (2026-10-06)

| Tipo | Verde do VE |
| --- | --- |
| `AMBULANCIA` | 9 s |
| `BOMBEIRO` | 8 s |
| `POLICIA` | 7 s |

O tipo fixa só a duração. Quem interrompe quem é a **criticidade** que a Central deu ao tipo (1 a mais crítica); na v3 era o tipo (ambulância 1, bombeiro 2, polícia 3).

0. Tipo sem ocorrência ativa → `SEM_OCORRENCIA`; LCD `SEM OCORRENCIA` por 3 s.
1. Sem emergência → atende.
2. Mesma rua e mesmo tipo do atendido → **renova** o verde.
3. Criticidade **estritamente** maior que a do atendido → o atendido vai para a fila, e o novo é atendido.
4. Fila vazia, ou criticidade estritamente maior que a da fila → vai para a fila.
5. Senão → descartado. No mesmo nível, fica quem chegou primeiro.

Fila de **um** lugar; quem perde o lugar sai com `DESCARTADO`. Fim do verde do VE → atende a fila, ou volta ao ciclo.

### Transição segura — o que muda

1. Todo verde que apaga cumpre o **verde mínimo (3 s)**, passa **amarelo (2 s)** e vai a vermelho.
2. Antes de acender um verde novo, **1 s de all-red**.
3. **Nunca amarelo → verde.** Destino mudando no meio de uma troca: a troca segue até o all-red, e só então abre o novo destino.
4. Se a aproximação do VE já está verde, ela não apaga; só as outras saem pelo amarelo.
5. O verde do VE conta **a partir do verde exclusivo estabelecido** (ele recebe os 9/8/7 s inteiros).
6. Fim da emergência sem fila → o ciclo recomeça **pelo eixo oposto** ao do último VE (o que ficou esperando).
7. **Teto de 30 s** de emergência contínua, contando renovações e fila → descarta a fila, `EV,TIMEOUT`, e volta ao ciclo.

Pior caso, da chegada ao verde do VE: `3 + 2 + 1` = **6 s**.

### Requisitos de implementação

| # | Requisito | Por quê |
| --- | --- | --- |
| 1 | Nenhum `delay()` no `loop()` | Durante o delay a serial não é lida |
| 2 | As duas entradas (A0 e USB) lidas a cada iteração, cada uma com buffer de linha de tamanho fixo (32 e 72 bytes) | As linhas chegam a qualquer momento, e intercaladas |
| 3 | **Sem `String`** — só `char[]` | `String` fragmenta os 2 KB de RAM, e o sketch trava depois de ~20 min |
| 4 | **Guarda de conflito (I1)**, independente da máquina de estados, antes de acender qualquer verde | Defesa em profundidade |
| 5 | Boot em all-red | Nenhum verde no reset |
| 6 | **Evento na serial antes de atualizar o LCD** | A escrita I2C leva milissegundos e atrasaria o carimbo de H3 |
| 7 | `ST` periódica pulada se o buffer de saída não comporta; evento e `ST` de mudança de estado nunca | A 9600 baud o `Serial.print` bloqueia se o buffer de 64 bytes enche |

### LCD — mensagens do sketch, mantidas

```
Ciclo:        "Semaforo: Normal" / "Aguardando Sinal"
VE atendido:  "AMBULANCIA na R3" / ""
Com fila:     "AMBULANCIA na R3" / "Fila:BOMB na R1"
Sem ocorrência: "SEM OCORRENCIA" / "AMBULANCIA na R3"   (3 s)
```

### Aceitação

Placa gravada, **backend parado**, `python -m bridge.main --porta COM3` e então `python -m bridge.verificar`. O roteiro manda a lista da Central, injeta VEs e confere pela telemetria:

- ciclo de 12 s; liga negando todos; a lista chega e aparece na `ST`;
- `SEM_OCORRENCIA` sem mexer no semáforo, e a criticidade, e não o tipo, decidindo quem interrompe;
- verde exclusivo em ≤ 6 s;
- duração por tipo, renovação, interrupção, fila e descarte;
- volta pelo eixo oposto, teto de 30 s e recusa;
- I1 a I4 em toda a telemetria.

Passa igual contra o dublê (`adapters/hardware/simulado.py`) e contra a placa.

---

## §8 — Firmware dos NodeMCUs

**Ficam como estão** (entrega 5.6 só os versiona em `firmware/nodemcu/`). O emissor já deduplica (3 s entre envios), já ignora tag que não é de rua e já imprime `Tag <UID> lida -> Enviando RUAn`, que é a linha que H3 carimba. O receptor repassa sem interpretar.

Os emissores do bombeiro e da polícia (2026-10-08) são o sketch da ambulância com só a linha do tipo trocada (`firmware/nodemcu/veiculo_bombeiro/` e `veiculo_policia/`).

Saem da v2: Wi-Fi, HTTP, `secrets.h`, `sequencia`, `X-Device-Token`, `mensagem_lcd` e `SEM CONEXAO`.

---

## §9 — Invariantes de segurança

| ID | Regra | Na bancada, quem garante |
| --- | --- | --- |
| **I1** | Sem verdes conflitantes. Na bancada: nunca verde nos dois eixos; em emergência, só a aproximação do VE | Firmware (guarda independente) |
| **I2** | Nenhum verde → vermelho sem amarelo de 2 s | Firmware |
| **I3** | All-red de 1 s antes de todo verde novo | Firmware |
| **I4** | Nenhum verde truncado antes de 3 s | Firmware |
| **I5** | Nenhuma aproximação mais de 120 s no vermelho | Firmware, pelo teto de 30 s (no pior caso ~40 s de vermelho) |
| **I6** | Nenhum verde de emergência depende de comunicação para terminar | Firmware: fim por duração e teto de 30 s. **Redefinido em 2026-10-05**; na v2 era um watchdog do notebook, que não comanda mais o UNO |

Verificação: Hypothesis contra o dublê e `bridge.verificar` contra a placa, sobre a sequência de `ST` (que traz toda mudança de estado com o `millis()` dela).

---

## §10 — Onde a latência é medida

| Métrica | Intervalo | Meta | Onde |
| --- | --- | --- | --- |
| **Decisão** · RNF01 | Só `motor.avaliar()` | < 100 ms (p95) | **Simulação.** Na bancada a decisão é interna ao UNO e não é observável à parte |
| **Fim-a-fim** · H3 | Tag lida no veículo → `PREEMP_INI` do UNO | < 200 ms (p95) | **Bancada**, 100 passagens (decisão de 2026-10-06; antes, 5 repetições) |

**Como medir H3:**

1. Ligar o NodeMCU emissor ao notebook por USB, alimentado por ele (bateria desconectada). Nenhum fio da bancada muda.
2. Rodar `python -m bridge.main --porta COM3 --porta-veiculo COM4`.
3. Com a ambulância **em serviço na Central** (senão toda passagem vira `SEM_OCORRENCIA`), passar o carrinho pela tag de uma rua, com o cruzamento em ciclo normal. Uma passagem durante a emergência anterior vira `RENOVADO` e não conta. São 100 passagens, as mesmas do RNF05.

A ponte carimba o **primeiro byte** das duas linhas (`Tag … lida` e `EV,…,PREEMP_INI`) no relógio do notebook e grava `analysis/data/latencia_bancada.csv`. Primeiro byte, porque a 9600 baud cada caractere leva ~1 ms.

**A declarar no texto:** a latência dos dois conversores USB-serial entra na medida e não se cancela, e uma `ST` saindo no instante da chegada soma até ~27 ms (erro para cima).

---

## §11 — Rede do protótipo

**Não há rede.** ESP-NOW entre os NodeMCUs, dos três emissores ao receptor (rádio 2,4 GHz, MAC a MAC), USB entre o UNO e o notebook. Sem roteador, sem SSID, sem IP.

**Limitação a declarar:** o ESP-NOW está sem criptografia nos sketches, então qualquer ESP8266 que conheça o MAC do receptor pode preemptar o cruzamento. Chave por par (CCMP) é trabalho futuro.

---

## §12 — Pendências da bancada

- ✅ **P8** — boot com o RC522 no D3: normal (5 de 5).
- ✅ **P9** — não se aplica: o LCD está no UNO, de 5 V.
- ✅ **P10** — resistores integrados nos módulos.
- **Fotos da bancada** — pendentes (questionário, seção 7).
- **Versões das bibliotecas e do pacote `esp8266`** — informadas pelo Felipe em 2026-10-07: `MFRC522` 1.4.12 (GithubCommunity) e `LiquidCrystal I2C` 1.1.2 (Frank de Brabander). **Falta o número de versão do pacote `esp8266`** (ESP8266 Community) com que a equipe gravou o emissor da ambulância e o receptor; ele traz também o `ESP8266WiFi` e o `espnow`. Os emissores do bombeiro e da polícia (2026-10-08) foram gravados com o `esp8266` **3.1.2** e a `MFRC522` 1.4.12. O firmware novo do UNO foi compilado com `arduino:avr` 1.8.8 e a mesma `LiquidCrystal I2C` 1.1.2.

---

## §13 — Decisões já fechadas

| Item | Decisão |
| --- | --- |
| **Arquitetura** (2026-10-05) | A da bancada: ESP-NOW, UNO decide, notebook fora do caminho da decisão |
| **Central na bancada** (2026-10-06) | Receptor no A0; a ponte leva ao UNO a lista da Central; o UNO liga negando todos e decide pela criticidade |
| **Fases** (2026-10-05, revê P13) | Ciclo de 2 fases (12 s); verde exclusivo na emergência |
| **H3** (2026-10-05 e 2026-10-06) | Tag lida → `PREEMP_INI`, no relógio do notebook; 100 passagens, critério no p95 |
| **Tempos** (2026-08-24) | Verde 3 s, amarelo 2 s, all-red 1 s, verde mínimo 3 s |
| **P14** (2026-08-25) | RF02 mede até o **início da atuação**; na bancada, o `PREEMP_INI` |
| **P7** | O RFID emula radar + V2I; fusão de sensores só na simulação |
| **P20** | Vale no motor, na API, na simulação e, **desde 2026-10-06, na bancada** (o UNO decide contra a lista da Central) |

Registro completo em `context/09`.

---

## §14 — Plano do Bloco 5

Detalhado em [`docs/plano-desenvolvimento.md`](plano-desenvolvimento.md). Feito em 2026-10-05: protocolo (5.1), dublê com a regra da bancada (5.2), a ponte que escuta e mede H3 (5.7), os sketches dos NodeMCUs versionados como estão (5.6), os seeds da bancada (5.8) e o firmware do UNO (5.3), em `firmware/uno/semaforo/`, compilado e comparado com o dublê linha por linha no PC.

**Feito na bancada (2026-10-06 e 2026-10-07):** o firmware gravado no UNO e a aceitação (§7, 20 de 20, com a Central), H3 e RNF05 nas 100 passagens (§10), o checklist de `context/06` §6 (o item 5 com a tag fora do mapa, à noite de 2026-10-07) e o ensaio da demonstração (`bridge/demo.py`, 19 de 19). O firmware dos NodeMCUs não muda.

---

## §15 — O que a equipe de hardware precisa confirmar

| # | Item | Status |
| --- | --- | --- |
| 1 | **As mudanças de comportamento do firmware do UNO** (§7): renovação do mesmo VE, recusa de tipo desconhecido, volta pelo eixo oposto e teto de 30 s. As demais mudanças são de segurança e não estão em discussão | ✅ confirmadas pelo Felipe em 2026-10-07, as 8 da mensagem do Bloco 5 e o receptor no A0 |
| 2 | Fotos da bancada | pendente |
| 3 | Versões das bibliotecas e do pacote `esp8266` | parcial: `MFRC522` 1.4.12 e `LiquidCrystal I2C` 1.1.2; falta o número do pacote `esp8266` (§12) |
| 4 | Quem fica com a bancada e grava os programas novos (questionário 6.1) | ✅ o Felipe, que desde 2026-10-07 responde também pela parte de hardware |

---

**Regra de manutenção.** Quando uma decisão mudar, `context/` muda **no mesmo commit** (`context/08` §4.7), e este arquivo é atualizado em seguida. Contexto desatualizado é pior que contexto ausente, porque induz ao erro com confiança.
