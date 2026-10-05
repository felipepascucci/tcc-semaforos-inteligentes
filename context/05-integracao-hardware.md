# 05 — Software Integrado ao Protótipo Físico

> **Reescrito em 2026-10-05 — arquitetura da bancada adotada.** A equipe decidiu
> adaptar o sistema ao protótipo **como ele está montado**, sem mexer em fiação.
> A versão anterior deste arquivo descrevia outra arquitetura (tag no veículo,
> NodeMCU → Wi-Fi → backend → ponte → UNO, decisão no motor Python), que nunca
> chegou a existir na bancada. Registro e consequências em `09` (decisão de
> 2026-10-05) e no histórico do git. As respostas do questionário de hardware e
> os sketches originais estão em `docs/hardware/`.

## 1. Inventário do hardware montado

Três placas. **Nenhuma ligação física muda** (decisão de 2026-10-05).

```
 VEÍCULO (carrinho)                       CRUZAMENTO
┌──────────────────────────┐   ESP-NOW   ┌────────────────────┐ TX→RX(0) ┌──────────────────────┐
│ NodeMCU EMISSOR + RC522  │ ──rádio──▶  │ NodeMCU RECEPTOR   │ ──9600──▶│ Arduino UNO R3       │
│ bateria 9 V (VIN)        │  MAC a MAC  │ 5 V vindo do UNO   │          │ 4 semáforos + LCD    │
└──────────▲───────────────┘             └────────────────────┘          └──────────┬───────────┘
           │ lê (2–5 cm)                                                            │ USB (TX do UNO
   [tag fixa na rua]                                                                │  + alimentação)
                                                                                    ▼
                                                                         [Notebook — só escuta]
```

### Subsistema A — Controlador do cruzamento (Arduino UNO R3, clone com CH340)

ATmega328P a 16 MHz. Alimentado **só pelo USB do notebook**. LEDs acendem com
`HIGH`, ligados direto aos pinos; os módulos já têm resistor (P10).

| Semáforo | Aproximação | Rua (tag) | Eixo | R | Y | G |
| --- | --- | --- | --- | --- | --- | --- |
| S1 | Principal — Sentido A | `RUA1` | Principal | 13 | 12 | 11 |
| S2 | Principal — Sentido B | `RUA2` | Principal | 10 | 9 | 8 |
| S3 | Transversal — Sentido A | `RUA3` | Transversal | 7 | 6 | 5 |
| S4 | Transversal — Sentido B | `RUA4` | Transversal | 4 | 3 | 2 |

| Outro | Pino do UNO |
| --- | --- |
| LCD 16x2 I2C (`0x27`, 5 V) | SDA → A4 · SCL → A5 |
| TX do NodeMCU receptor | RX (0) |
| Alimentação do NodeMCU receptor | 5V e GND |

Livres: **A0–A3** e o TX (1), que vai só para o USB.

> **O pino RX (0) é do NodeMCU, não do notebook.** O RX do UNO é o mesmo que o
> conversor USB usa, e o TX do NodeMCU, ligado direto ao pino, prevalece sobre o
> conversor. Duas consequências: (a) para **gravar** o UNO é preciso soltar esse
> fio (relatado pela equipe); (b) o notebook **não manda nada** ao UNO em operação
> — só **ouve** o que o UNO escreve no TX, que chega intacto pelo USB. Soltando o
> fio, o notebook pode escrever no RX: é assim que se testa a bancada sem o
> veículo (§6).

> **Atenção elétrica.** P10 resolvida (resistores integrados). Pior caso de
> corrente nos LEDs: 4 acesos, ~80 mA. O 5V do UNO também alimenta o NodeMCU
> receptor, que tem picos de ~200–300 mA ao usar o rádio; pelo USB isso cabe nos
> 500 mA da porta.

### Subsistema B — Veículo (NodeMCU 1.0 ESP-12E "emissor" + RC522)

Bateria de 9 V em VIN/GND. Lê a tag a **2–5 cm**. Sketch:
`firmware/nodemcu/veiculo_ambulancia/` (o original da equipe está em
`docs/hardware/`).

| RC522 | NodeMCU | Função |
| --- | --- | --- |
| 3.3V | 3V3 | Alimentação (**nunca 5 V**) |
| RST | D3 (GPIO 0) | Reset — **P8 fechada**: o boot funciona em 5 de 5 resets e religamentos |
| GND | GND | Terra |
| MISO | D6 (GPIO 12) | SPI |
| MOSI | D7 (GPIO 13) | SPI |
| SCK | D5 (GPIO 14) | SPI clock |
| SDA/SS | D8 (GPIO 15) | Chip select |

O tipo do veículo é **fixo no código** (`"AMBULANCIA"`), assim como o MAC do
receptor (`40:91:51:58:A8:E1`). Há **um** emissor: a bancada tem um veículo.

### Subsistema C — Cruzamento (NodeMCU 1.0 ESP-12E "receptor")

Recebe o ESP-NOW e repassa ao UNO pelo TX, a 9600 baud. Sem outros periféricos.
Sketch: `firmware/nodemcu/nodeMCU_semaforo/`.

### Tags RFID — identificam a **rua**, não o veículo

| UID | Rua | Semáforo |
| --- | --- | --- |
| `F39BD606` | `RUA1` | S1 |
| `1BD2308E` | `RUA2` | S2 |
| `B7EF8FA0` | `RUA3` | S3 |
| `97ABAFA0` | `RUA4` | S4 |

A tag fica na pista, antes do cruzamento, e o leitor vai no veículo. Ler a tag é
saber **por qual aproximação** o veículo chega — é o que o radar + V2I do
pré-projeto entregariam, e o RFID os emula (P7). A identidade do veículo é o
**tipo**, gravado no emissor; não há placa nem ID individual. O mapa UID → rua
vive no sketch do emissor; tag fora dessa lista é ignorada ali mesmo, sem envio.

**P9 não se aplica mais.** O LCD está no UNO, que é de 5 V, então o barramento
I2C a 5 V está dentro da especificação. A preocupação de P9 era um LCD de 5 V num
GPIO de 3,3 V do ESP8266, ligação que não existe.

## 2. Arquitetura de software do protótipo

```
[tag da RUA3] --RFID--> [NodeMCU emissor]  "Tag B7EF8FA0 lida -> Enviando RUA3"  (serial do emissor)
                              │ ESP-NOW { rua: "RUA3", veiculo: "AMBULANCIA" }
                              ▼
                     [NodeMCU receptor]
                              │ "RUA3,AMBULANCIA\r\n"  @9600, TX -> RX(0)
                              ▼
                     [Arduino UNO — DECIDE e ATUA]
                       prioridade por tipo, fila de 1, verde exclusivo,
                       transição segura, LCD
                              │ "EV,…,PREEMP_INI,3,AMBULANCIA" / "ST,…"  @9600, TX -> USB
                              ▼
                     [bridge/ — só escuta]  carimba no relógio do notebook
                              │
                              ▼
                     [Backend: log, métricas, WebSocket -> Dashboard]   (Bloco 6)
```

**A decisão de preempção no protótipo é do UNO.** Ele roda uma regra local,
mais simples que o motor (`01` §5): a mesma regra que a equipe de hardware já
tinha escrita (prioridade por tipo e fila), agora com transição segura. O motor
de decisão continua sendo o objeto do experimento, **na simulação** (`00` §3).

**O notebook não está no caminho da decisão.** Ele só observa: se a ponte cair,
o cruzamento continua funcionando e preemptando — o que muda é que o dashboard
para de atualizar. A borda (Edge) do pré-projeto é, na bancada, o próprio
controlador do cruzamento.

## 3. Firmware do Arduino UNO — requisitos (entrega 5.3)

O sketch atual (`docs/hardware/semaforo.ino`) já é não-bloqueante e tem a lógica
de prioridade. **Ele precisa ser reescrito mesmo assim**, porque viola os
invariantes de segurança:

- a emergência apaga o verde e acende o verde da aproximação do VE **no mesmo
  instante**, sem amarelo e sem all-red (I2, I3) e sem verde mínimo (I4);
- a troca de eixo no ciclo normal não tem all-red (I3), e na volta da emergência
  o verde do VE vai direto para o vermelho (I2);
- verde e amarelo estão invertidos (verde 2 s, amarelo 5 s), e a placa liga com
  tudo apagado por 5 s;
- usa `String` (fragmenta o heap de 2 KB do ATmega328P).

**O que se preserva é o comportamento**: a mesma entrada, as mesmas prioridades,
as mesmas durações, a mesma fila e as mesmas mensagens no LCD. O que muda é como
as luzes chegam lá.

### 3.1 Regimes

```
CICLO — 2 fases (eixo principal / eixo transversal), autônomo
  F1: S1+S2 verde (3 s) -> amarelo (2 s) -> ALL_RED (1 s)
  F2: S3+S4 verde (3 s) -> amarelo (2 s) -> ALL_RED (1 s) -> F1 ...     ciclo = 12 s

EMERGÊNCIA — verde EXCLUSIVO na aproximação do VE (as outras três em vermelho)
  dura o tempo do tipo do VE; ao fim, atende a fila ou volta ao CICLO
```

Implementar com tabela de pinos e índice, não com estados enumerados um a um:

```c
const uint8_t VERDE_DE[4] = {11, 8, 5, 2};      // pino G de S1..S4
const uint8_t AMAR_DE[4]  = {12, 9, 6, 3};
const uint8_t VERM_DE[4]  = {13, 10, 7, 4};
const uint8_t EIXO_DE[4]  = {0, 0, 1, 1};       // 0 principal, 1 transversal
```

Tempos da bancada (`parametros.hardware.yaml`): **verde 3 s, amarelo 2 s,
all-red 1 s, verde mínimo 3 s**. Como o verde mínimo é igual ao verde, a
emergência **nunca trunca** um verde: espera o corrente completar 3 s.

### 3.2 Entrada — a linha do NodeMCU receptor

`<RUA>,<VEICULO>` terminada em `\n` (o receptor usa `println`, então chega
`\r\n`; o `\r` é descartado). `RUA` ∈ `RUA1`..`RUA4` (o sketch atual também
aceita `1`..`4`, e o firmware mantém isso). `VEICULO` ∈ `AMBULANCIA`,
`BOMBEIRO`, `POLICIA`.

| Tipo | Prioridade | Verde do VE |
| --- | --- | --- |
| `AMBULANCIA` | 1 (maior) | 9 s |
| `BOMBEIRO` | 2 | 8 s |
| `POLICIA` | 3 | 7 s |

Linha **com vírgula** e rua ou tipo desconhecido → `EV,<ms>,RECUSADO`, sem
efeito. **Mudança deliberada em relação ao sketch**, que dava prioridade 3 a
qualquer tipo desconhecido: um texto corrompido na serial não pode virar uma
viatura. Linha **sem vírgula** é ignorada em silêncio — é o que o ESP8266
imprime no próprio boot, a 74880 baud, e que chega ao UNO como lixo.

### 3.3 Decisão (a regra do sketch, preservada)

Ao receber um VE válido:

1. **Sem emergência** → o VE é atendido (`PREEMP_INI`).
2. **Mesma rua e mesmo tipo do VE atendido** → o verde dele é **renovado**
   (`RENOVADO`): a duração recomeça a contar. *Acrescentado:* no sketch, o mesmo
   veículo relendo a tag ia para a fila e ganhava um segundo verde depois do
   primeiro.
3. **Prioridade maior** que a do atendido → o atendido vai para a fila
   (`FILA`), ocupando o lugar de quem estivesse nela, e o novo é atendido
   (`PREEMP_INI`).
4. **Senão, fila vazia ou prioridade maior que a da fila** → o novo vai para a
   fila (`FILA`).
5. **Senão** → descartado (`DESCARTADO`).

A fila tem **um lugar**. Quem perde o lugar para outro VE (casos 3 e 4) sai com
`DESCARTADO`: no sketch ele sumia sem rastro, e o log da bancada perderia o VE de
vista. Quando o verde do VE atendido acaba (`PREEMP_FIM`), o da fila é atendido;
se não há fila, volta o ciclo.

A identidade do veículo é o tipo (§1). Dois veículos do mesmo tipo são
indistinguíveis — limitação da bancada, a declarar no texto.

### 3.4 Transição segura (o que muda em relação ao sketch)

Valem nos dois regimes, sem exceção:

1. **Todo verde que precisa apagar** cumpre o verde mínimo (contado de quando
   acendeu), passa **amarelo** por 2 s e só então vai a vermelho (I2, I4).
2. **Antes de acender qualquer verde novo**, todas as aproximações que estavam
   verdes ou amarelas já estão vermelhas há **1 s de all-red** (I3).
3. **Nunca amarelo → verde.** Se o destino muda durante um amarelo ou um
   all-red (VE chegando no meio da troca de eixo, por exemplo), a transição em
   curso segue até o all-red e só então abre o novo destino, sem recomeçar.
4. **Se a aproximação do VE já está verde**, ela não apaga: só as outras saem
   pelo amarelo. O VE ganha passagem desde o primeiro instante.
5. **O verde do VE conta a partir de quando o verde exclusivo dele está
   estabelecido**, para que ele receba os 9/8/7 s inteiros.
6. **Fim da emergência sem fila: o ciclo recomeça pelo eixo oposto ao do último
   VE**, pelo amarelo e pelo all-red. É o eixo que ficou esperando. No sketch o
   ciclo recomeçava sempre pelo F1, e o verde do VE ia direto para o vermelho.
7. **Teto: `PREEMP_MAX_MS = 30000`** de emergência contínua, contando renovações
   e fila. Estourou → descarta a fila, `EV,TIMEOUT`, e volta ao ciclo pelo eixo
   oposto. Com o teto, nenhuma aproximação fica mais de ~40 s no vermelho, o que
   cumpre I5 (120 s) na bancada sem depender do motor.

Pior caso da chegada do VE até o verde dele: `3 + 2 + 1` = **6 s**.

### 3.5 Requisitos de implementação

1. **Nenhum `delay()` no `loop()`.** `lcd.init()` no `setup()` pode bloquear.
2. **Leitura da serial a cada iteração**, com buffer de linha de tamanho fixo.
3. **Sem `String`.** Só `char[]`.
4. **Guarda de conflito local (I1)** antes de acender qualquer verde:
   - nunca há verde nos dois eixos ao mesmo tempo;
   - em emergência, só a aproximação do VE fica verde.

   É verificação independente da máquina de estados, não consequência dela.
5. **Boot em all-red** (1 s) antes de abrir F1. Nenhum verde no reset.
6. **Evento antes do LCD.** No mesmo `loop()` em que decide, o UNO escreve o
   evento na serial e só depois atualiza o LCD, cuja escrita I2C leva
   milissegundos e não pode atrasar o carimbo de H3 (§4.3).
7. **Não travar no `Serial.print`.** A 9600 baud o buffer de saída (64 bytes) se
   esvazia a ~1 byte/ms. A `ST` periódica é **pulada** se
   `Serial.availableForWrite()` não comporta a linha; eventos e a `ST` de
   mudança de estado nunca são pulados.

### 3.6 LCD — mensagens do sketch, mantidas

```
Ciclo:            "Semaforo: Normal"  /  "Aguardando Sinal"
VE atendido:      "AMBULANCIA na R3"  /  ""
Com fila:         "AMBULANCIA na R3"  /  "Fila:BOMB na R1 "
```

Cabem em 16 colunas (`AMBULANCIA na R1` tem exatamente 16). O LCD é decidido
pelo próprio UNO; não há texto vindo do backend.

### 3.7 Implementação (entrega 5.3, 2026-10-05)

`firmware/uno/semaforo/`, em duas partes:

- **`controlador.h` e `.cpp` — o núcleo.** A decisão, as quatro regras das luzes
  (§8) e o protocolo. Não inclui nada do Arduino: o tempo entra como argumento,
  e pinos e serial entram pela interface `Placa`. Segue o dublê função a função,
  com os mesmos nomes.
- **`semaforo.ino` — a placa.** Pinos (tabela e índice), `Serial` a 9600, LCD e o
  `loop()`: `millis()`, depois `avancar()`, depois a serial byte a byte, e o LCD
  **por último**, só quando o texto muda e sem `lcd.clear()`.

**A guarda de I1 lê os pinos** (`digitalRead` do verde de cada aproximação), não o
vetor de cores da máquina de estados. Se ela recusar, nada acende e o cruzamento
fica em all-red, que é o estado seguro. No dublê essa recusa é exceção, porque
nunca deve acontecer.

**O núcleo é testado contra o dublê no PC, linha por linha**
(`tests/firmware/test_firmware_uno.py`). O mesmo `controlador.cpp` da placa é
compilado com o compilador C++ do pacote `ziglang` (`firmware/uno/teste_host/`),
recebe as mesmas entradas nos mesmos instantes e precisa escrever na serial
**exatamente** as mesmas linhas, com o mesmo `millis()`. O teste roda os cenários
de §3 e §4, entradas aceitas e recusadas pelo parser, e 200 sequências
aleatórias (Hypothesis) com VEs, lixo e linhas quase válidas. Acrescenta o que o
dublê não modela: as mensagens do LCD, a `ST` periódica pulada com o buffer
cheio e a guarda de I1 diante de um pino verde aceso por fora da máquina.

**Verificação por mutação, 2026-10-05.** Nove sabotagens no `controlador.cpp`,
todas pegas: sem all-red, sem verde mínimo, renovação que não reinicia o verde,
rua 0 aceita, espaço ASCII de controle não aparado, teto que não descarta a
fila, volta pelo mesmo eixo, guarda lendo a máquina em vez do pino, e `ST`
periódica nunca pulada.

**Compilado com `arduino-cli`** (core `arduino:avr` 1.8.8, `LiquidCrystal I2C`
1.1.2): 8.722 bytes de flash (27%) e 841 bytes de RAM global (41%), sem aviso nos
arquivos do projeto. O teste confere que a RAM global fica abaixo de 1 KB:

```powershell
arduino-cli compile --fqbn arduino:avr:uno firmware/uno/semaforo
```

**O que só a placa confirma:** os pinos, a serial a 9600, o LCD físico e o tempo
real do `loop()`. É a aceitação abaixo (§6), com `bridge.verificar`.

## 4. Protocolo serial do UNO

Texto ASCII, linhas terminadas em `\r\n`, **9600 baud** nos dois sentidos — é a
velocidade do NodeMCU receptor, e o RX e o TX do UNO compartilham a mesma UART.

### 4.1 Entrada (RX)

Só a linha de §3.2. **Não há comandos do host**: `PING`, `PRE`, `CLR`, `CFG`,
`ST?`, `SAFE`, `TESTMODE` e `TEST`, do protocolo anterior, deixaram de existir
(decisão de 2026-10-05). Para testar sem o veículo, solta-se o fio do RX e a
ponte escreve a **mesma** linha que o receptor escreveria (§6).

### 4.2 Saída (TX → USB)

| Linha | Quando |
| --- | --- |
| `ST,<ms>,<s1><s2><s3><s4>,<regime>,<rua_ativa>,<rua_fila>` | A 2 Hz **e** a cada mudança de estado (luz, regime, rua ativa ou fila); uma por instante |
| `EV,<ms>,BOOT` | No `setup()` |
| `EV,<ms>,PREEMP_INI,<rua>,<veiculo>` | VE passa a ser atendido (§3.3, casos 1 e 3, e quando sai da fila) |
| `EV,<ms>,RENOVADO,<rua>,<veiculo>` | Caso 2 |
| `EV,<ms>,FILA,<rua>,<veiculo>` | VE entra na fila, inclusive o interrompido no caso 3 |
| `EV,<ms>,DESCARTADO,<rua>,<veiculo>` | Caso 5, e quem perdeu o lugar na fila |
| `EV,<ms>,PREEMP_FIM,<rua>,<veiculo>` | O verde do VE acabou, ou o teto estourou |
| `EV,<ms>,TIMEOUT` | Teto de 30 s (§3.4, item 7), seguido do `PREEMP_FIM` do VE atendido |
| `EV,<ms>,RECUSADO` | Linha com vírgula e conteúdo inválido |

- `<ms>`: `millis()` do UNO. Serve para ordenar e medir intervalos **dentro**
  do UNO; a latência oficial usa o relógio do notebook.
- Estados: `R`, `Y`, `G`, na ordem S1 S2 S3 S4.
- `<regime>`: `C` ciclo, `E` emergência. `<rua_ativa>` e `<rua_fila>`: `1..4`
  ou `0` (nenhuma).
- `<rua>` nos eventos: `1..4`.

**Cada linha válida recebida gera exatamente um evento de decisão**
(`PREEMP_INI`, `RENOVADO`, `FILA` ou `DESCARTADO`), escrito **antes** de
qualquer outra linha. É o que mantém o carimbo de H3 sem fila de saída à frente
(§4.3). A única linha que pode sair antes é uma `ST` que já estava vencida
naquele mesmo milissegundo (a periódica, ou uma transição de luz): o firmware e
o dublê aplicam primeiro o que venceu, e só então decidem. É o caso de "uma
`ST` saindo quando o VE chega", declarado em §4.3.

Exemplo — VE na Rua 3 chegando com o eixo principal verde há 1 s:

```
uno <- EV,142350,PREEMP_INI,3,AMBULANCIA     (decisão, mesma iteração da leitura)
uno <- ST,142350,GGRR,E,3,0                  (S1/S2 cumprem o resto do verde mínimo)
uno <- ST,144350,YYRR,E,3,0                  (amarelo)
uno <- ST,146350,RRRR,E,3,0                  (all-red)
uno <- ST,147350,RRGR,E,3,0                  (verde exclusivo da Rua 3 — conta 9 s)
uno <- EV,156350,PREEMP_FIM,3,AMBULANCIA
uno <- ST,156350,RRYR,C,0,0                  (volta pelo eixo principal, que esperou)
```

Em nenhuma linha há `G` nos dois eixos. A verificação de I1, I2 e I3 sobre a
telemetria continua automatizável: como há `ST` a cada mudança de estado, a
sequência de `ST` é a sequência completa de transições, com o `millis()` de cada
uma — dá para conferir também I4 e os 2 s de amarelo e 1 s de all-red.

### 4.3 Onde a latência é medida (H3 e RF02)

**H3 vai do instante em que o veículo lê a tag ao instante em que o UNO decide
atendê-lo**, os dois carimbados **no relógio do notebook** (decisão de
2026-10-05):

- `t_deteccao` — chegada do **primeiro byte** da linha
  `Tag <UID> lida -> Enviando RUAn`, que o emissor imprime logo depois do
  `esp_now_send`. Para isso, **durante a medição** o NodeMCU do veículo fica
  ligado ao notebook por USB e alimentado por ele (bateria desconectada).
  Nenhum fio da bancada muda.
- `t_atuacao` — chegada do primeiro byte da linha `EV,…,PREEMP_INI,…` do UNO.

O intervalo cobre ESP-NOW, a serial do receptor ao UNO e a decisão do UNO. O
`PREEMP_INI` corresponde ao `ACK` do protocolo anterior: o UNO se compromete com
a transição, e a primeira mudança visível vem dali até 3 s depois, se o verde
mínimo estiver pendente. É a leitura de P14 ("até o início da atuação").

**Por que o primeiro byte, e não o fim da linha.** A 9600 baud cada caractere
leva ~1 ms; carimbar o fim da linha somaria ~35 ms à detecção e ~30 ms à
atuação, e a diferença entraria no resultado. **O que sobra e precisa ser
declarado:** a latência dos dois conversores USB-serial (o CH340 do UNO e o do
emissor), que não se cancelam por serem chips diferentes, e até ~27 ms a mais
se uma `ST` estiver saindo do UNO quando o VE chega (erro para cima, contra a
hipótese).

**`t_decisao` não existe na bancada.** A decisão acontece dentro do UNO, em
microssegundos, e não é observável à parte. A latência de decisão (RNF01) é
medida na simulação, sobre o motor (`00` §5, decisão P2).

## 5. Firmware dos NodeMCUs — ficam como estão

Os sketches do emissor e do receptor **não mudam** (decisão de 2026-10-05).
**Versionados em 2026-10-05 (entrega 5.6)** em
`firmware/nodemcu/veiculo_ambulancia/` e `firmware/nodemcu/nodeMCU_semaforo/`,
byte a byte iguais aos de `docs/hardware/`, com um cabeçalho de comentário: MAC
do receptor, tipo do veículo, mapa UID → rua e pinagem.
`tests/firmware/test_sketches_nodemcu.py` confere que o corpo continua idêntico
ao original, que o cabeçalho diz o que o código faz (MAC, tipo, mapa e pinos do
RC522), que o mapa bate com a tabela de §1 e que a linha `Tag … lida` impressa
pelo emissor é a que a ponte interpreta para H3.

O que eles já fazem e o protótipo usa:

- **Deduplicação no emissor:** só envia se passaram mais de 3 s desde o último
  envio. Uma tag que fica no campo não é relida: depois do `PICC_HaltA()` ela só
  volta a ser lida se sair e entrar de novo.
- **Rua desconhecida não é enviada.**
- **O receptor repassa sem interpretar.**

O que **não** se aplica mais: Wi-Fi, HTTP, `secrets.h`, `sequencia`,
`X-Device-Token`, reconexão e a mensagem `SEM CONEXAO`. Não há rede (ESP-NOW é
rádio direto, MAC a MAC, sem roteador).

## 6. A ponte (`bridge/`) — só escuta

Processo Python no notebook. Responsabilidades:

- Abrir a serial do UNO (**9600**) e reconectar se o dispositivo sumir. Abrir a
  porta **reinicia o UNO** (DTR do conversor USB), que volta pelo all-red;
  fechar não reinicia.
- Carimbar cada linha na chegada do **primeiro byte**, com `perf_counter`
  ancorado no relógio de parede (resolução de 100 ns contra os 15,6 ms do
  relógio de parede do Windows; o `datetime` final guarda microssegundos).
  Entre uma linha e outra o transporte lê **um** byte só (`read(1)`), que volta
  assim que ele chega, e lê o `perf_counter` ali mesmo, na thread da leitura; o
  resto da linha vem depois. Cada linha carrega também `bytes_em_espera`:
  quantos bytes já esperavam na porta quando o primeiro foi lido. Zero quer
  dizer que a ponte estava esperando o byte chegar; um número alto denuncia um
  carimbo atrasado.
- Interpretar `ST` e `EV` e expor o estado em `GET /estado` e `GET /health`
  (`503` enquanto não chegar `ST`).
- **Na medição de H3**, abrir também a serial do emissor
  (`--porta-veiculo COM4`), casar cada `Tag … lida -> Enviando RUAn` com a
  decisão do UNO para ela e gravar a amostra em
  `analysis/data/latencia_bancada.csv`. Detecção que vira `FILA`, `RENOVADO` ou
  `DESCARTADO` não é amostra de H3: não houve atuação para medir. O casamento
  está em `bridge/latencia.py`:
  - cada detecção casa com o **primeiro evento de decisão da mesma rua**
    carimbado depois dela, seja qual for. Só se ele for `PREEMP_INI` há amostra.
    Casar com "o próximo `PREEMP_INI`" estaria errado: a detecção que virou
    `FILA` seria casada com a saída da fila, segundos depois;
  - **pelos carimbos, não pela ordem de leitura.** As duas portas são lidas em
    paralelo, e a linha do emissor (~36 caracteres) pode terminar de chegar
    depois do começo da decisão;
  - **janela de 3 s** (o limite do RF02), folgada de propósito: uma janela justa
    descartaria justamente as amostras lentas, a favor da hipótese. Detecção sem
    decisão na janela é `SEM_DECISAO`;
  - quem não vira amostra vai para o log da ponte e para o contador
    `deteccoes_sem_amostra` do `/health`, não para o CSV.

  O CSV acumula sessões, uma linha por amostra, gravada na hora:
  `sessao, t_deteccao, t_atuacao, latencia_total_ms, rua, uid, veiculo, uno_ms,
  bytes_em_espera_deteccao, bytes_em_espera_atuacao, versao_codigo`. A ponte
  **recusa** `--porta-veiculo` com `--simulado`: nenhum número do dublê chega
  ao CSV.
- **Injeção de teste** (`POST /injecao` com `rua` e `veiculo`): escreve no RX do
  UNO a mesma linha que o receptor escreveria e devolve a decisão do UNO, com o
  `millis()` dela. **Só funciona com o fio do NodeMCU solto do RX**; com ele
  ligado, o que a ponte escreve se perde, e a resposta é `504`.
  `POST /injecao/bruta` escreve uma linha qualquer, para conferir o
  `EV,RECUSADO`.
- `GET /estado` traz as **últimas 200 telemetrias**, não só a mais recente: como
  a `ST` sai a cada mudança de estado, quem lê o histórico não perde transição
  entre duas consultas.
- **Repassar ao backend: é o backend que lê** (decisão de 2026-10-05, Bloco 6).
  Ele consulta `GET /estado` a 5 Hz, e a ponte continua sem saber que ele
  existe. Por isso o `/estado` traz também `amostras_h3`, as amostras da sessão,
  com o mesmo carimbo do `EV,…,PREEMP_INI` que as originou. É por esse carimbo
  que o backend liga a amostra à linha de `log_prioridade`. O código de H3 (o
  casamento e o CSV) não mudou. O backend grava a amostra em `metrica_latencia`
  com `t_decisao` nulo, e o CSV continua sendo a fonte do número de H3.

**Refeito em 2026-10-05 (entregas 5.1, 5.2 e 5.7).** Saíram o envio de comandos
(`POST /comandos`, `PING` a cada 1 s, tradução `Comando` → linha) e o
`t_atuacao` na chegada do `ACK`. Ficaram a estrutura (transporte real × dublê,
laço asyncio, API FastAPI em `:8001`, relógio). O protocolo, o dublê e o
`bridge.verificar` foram reescritos. **A parte de H3 entrou no mesmo dia**: o
carimbo no primeiro byte (`Transporte.ler_linha` devolve `LinhaRecebida`), a
segunda porta e o `latencia_bancada.csv`, testados sem hardware com `loop://` e
portas roteirizadas. O CSV ainda não existe: ele só nasce de medição na
bancada.

**Aceitação do firmware (5.3).** Com a placa gravada e o fio do RX solto, subir
`python -m bridge.main --porta COM3` e rodar o `python -m bridge.verificar`
reescrito. Ele injeta VEs pela ponte e confere pela telemetria:

- boot em all-red e ciclo de 12 s;
- verde exclusivo, atingido em no máximo 6 s;
- duração por tipo, renovação, interrupção por prioridade maior, fila e
  descarte;
- volta pelo eixo oposto, o teto de 30 s e o `RECUSADO`;
- I1 a I4 em toda a telemetria.

As durações são conferidas no `millis()` do UNO, com folga de 60 ms (uma volta do
`loop()`). O mesmo roteiro, contra o dublê, é o que valida o próprio roteiro
antes de haver placa: **16 de 16 em 2026-10-05**, em ~3 min. Ele mesmo pegou um
defeito seu na primeira rodada: renovava depois do `TIMEOUT` e confundia a
emergência nova com a antiga.

## 7. Modo de demonstração

Roteiro em `bridge/demo.py`, com o dashboard aberto:

1. **Ciclo normal** — os dois eixos se alternando (12 s), ao vivo no dashboard.
2. **O carrinho passa pela tag da Rua 3** → amarelo no eixo principal, all-red,
   verde só no S3. O LCD mostra `AMBULANCIA na R3`, e o dashboard mostra o
   evento.
3. **Fim do verde da ambulância** → o ciclo volta pelo eixo principal, que ficou
   esperando.
4. **Prioridade entre VEs** — com o fio do RX solto, a ponte injeta um
   `BOMBEIRO` na Rua 1 e, logo depois, a `AMBULANCIA` na Rua 3. A ambulância
   interrompe o bombeiro (pelo amarelo e pelo all-red), o LCD mostra
   `Fila:BOMB na R1`, e o bombeiro é atendido em seguida. O emissor físico é
   sempre ambulância, então este passo precisa da injeção.
5. **Autonomia do cruzamento** — encerrar a ponte. O semáforo continua, e o
   carrinho continua preemptando; só o dashboard para. O cruzamento não depende
   do notebook.

**O que saiu do roteiro em 2026-10-05, por consequência da arquitetura:**

- o passo 1b (tag sem ocorrência, P20): não há como o UNO saber de ocorrência;
- a tag não cadastrada → `ACESSO NEGADO`: tag desconhecida é ignorada no
  veículo, sem nada visível no cruzamento;
- o puxão do cabo USB → watchdog: o UNO não depende de comunicação, e o cabo é a
  alimentação dele.

P20 continua no motor, na API e na simulação.

## 8. Testes com hardware desconectado

`adapters/hardware/simulado.py` — o dublê do UNO, **reescrito em 2026-10-05**
com o comportamento de §3 e §4 (entrega 5.2 refeita). Continua em duas camadas:
`UnoSimulado`, dirigido por tempo injetado, e `TransporteSimulado`, a mesma
interface da porta real. O transporte modela a fiação: com
`fio_do_nodemcu_no_rx=True` o que a ponte escreve se perde, e
`simular_receptor()` faz o papel do NodeMCU.

**O dublê é o modelo de referência do firmware:** o firmware deve se comportar
como ele, e o `bridge.verificar` passa igual contra os dois. Desde 2026-10-05 o
núcleo do firmware também é comparado com ele no PC, linha por linha (§3.7).
Mudar a regra é mudar os dois juntos: um teste quebra se só um mudar.

**Como ele anda, e por que isso interessa ao firmware.** Em vez de enumerar
estados, o dublê persegue um *destino* (o eixo do ciclo, ou a aproximação do
VE). Quatro regras, aplicadas até nada mais mudar, levam qualquer estado ao
destino:

1. verde fora do destino cumpre o mínimo e vai a amarelo;
2. amarelo cumpre o tempo e vai a vermelho;
3. o destino só abre com tudo vermelho há o all-red inteiro, e passando pela
   guarda de I1;
4. nunca amarelo → verde.

A exceção é a aproximação do VE já verde, que fica acesa. O firmware pode
seguir o mesmo desenho: é curto, e as interações (VE chegando no amarelo,
interrupção no meio da troca) saem dele sem caso especial.

O dublê processa cada mudança **no instante exato em que vence**, e não no passo
de quem o dirige. Por isso os testes conferem durações com igualdade exata.

**Testes** (`backend/tests/adapters/test_hardware_simulado.py`, 44): os casos de
§3.3 e §3.4 um a um, e, com Hypothesis, sobre sequências aleatórias de chegadas
(VEs válidos e linhas inválidas, em instantes aleatórios):

- I1 a I4, pelo mesmo conferidor do `bridge.verificar`;
- o teto de 30 s e a volta ao ciclo;
- I5;
- exatamente uma decisão por detecção, escrita antes de tudo.

**Verificação por mutação, refeita em 2026-10-05.** Quatro sabotagens, cada uma
pega pelos testes, inclusive pelo de propriedade:

| Sabotagem | Testes que falham |
| --- | --- |
| sem all-red | 6 |
| sem amarelo | 5 |
| sem verde mínimo | 3 |
| guarda de I1 e espera do all-red desligadas | 9 |

O dublê deixa de reusar a máquina de estados de `core/priorizacao/fases.py`: a
regra da bancada (2 fases, verde exclusivo, fila por tipo) não é a do motor.

**Nenhum número produzido com o dublê é dado experimental.** H3 se mede na
bancada.
