# 05 — Software Integrado ao Protótipo Físico

> **Reescrito em 2026-10-05 — arquitetura da bancada adotada.** A equipe decidiu
> adaptar o sistema ao protótipo **como ele está montado**, sem mexer em fiação.
> A versão anterior deste arquivo descrevia outra arquitetura (tag no veículo,
> NodeMCU → Wi-Fi → backend → ponte → UNO, decisão no motor Python), que nunca
> chegou a existir na bancada. Registro e consequências em `09` (decisão de
> 2026-10-05) e no histórico do git. As respostas do questionário de hardware e
> os sketches originais estão em `docs/hardware/`.
>
> **Revisto em 2026-10-06 — a Central vale na bancada** (`09`, decisão de
> 2026-10-06). **Um fio muda**: o TX do receptor sai do RX (0) e vai para o
> **A0**, onde o UNO o lê numa serial por software. O RX (0) fica só para o
> USB, e a ponte passa a mandar ao UNO a lista da Central (quem tem ocorrência
> ativa, e com que criticidade). O UNO continua decidindo sozinho, e o notebook
> continua fora do caminho da decisão.

## 1. Inventário do hardware montado

Três placas. A única ligação que mudou desde o questionário é a do receptor,
do RX (0) para o A0 (decisão de 2026-10-06).

```
 VEÍCULO (carrinho)                       CRUZAMENTO
┌──────────────────────────┐   ESP-NOW   ┌────────────────────┐  TX→A0   ┌──────────────────────┐
│ NodeMCU EMISSOR + RC522  │ ──rádio──▶  │ NodeMCU RECEPTOR   │ ──9600──▶│ Arduino UNO R3       │
│ bateria 9 V (VIN)        │  MAC a MAC  │ 5 V vindo do UNO   │          │ 4 semáforos + LCD    │
└──────────▲───────────────┘             └────────────────────┘          └──────────┬───────────┘
           │ lê (2–5 cm)                                                            │ USB: ST/EV para
   [tag fixa na rua]                                                                │ o notebook; AUT e
                                                                                    │ injeção para o UNO
                                                                                    ▼
                                                                [Notebook — ponte, backend, Central]
```

### Subsistema A — Controlador do cruzamento (Arduino UNO R3)

ATmega328P a 16 MHz. Alimentado **só pelo USB do notebook**. LEDs acendem com
`HIGH`, ligados direto aos pinos; os módulos já têm resistor (P10). A placa da
bancada se identifica como UNO original (USB `2341:0043`, conversor 16U2), e
não como o clone com CH340 que o questionário descrevia; nada muda por isso.

| Semáforo | Aproximação | Rua (tag) | Eixo | R | Y | G |
| --- | --- | --- | --- | --- | --- | --- |
| S1 | Principal — Sentido A | `RUA1` | Principal | 13 | 12 | 11 |
| S2 | Principal — Sentido B | `RUA2` | Principal | 10 | 9 | 8 |
| S3 | Transversal — Sentido A | `RUA3` | Transversal | 7 | 6 | 5 |
| S4 | Transversal — Sentido B | `RUA4` | Transversal | 4 | 3 | 2 |

| Outro | Pino do UNO |
| --- | --- |
| LCD 16x2 I2C (`0x27`, 5 V) | SDA → A4 · SCL → A5 |
| TX do NodeMCU receptor | **A0** (serial por software, desde 2026-10-06) |
| Reservado: TX da serial por software, nada ligado | A1 |
| Alimentação do NodeMCU receptor | **5V do ICSP (pino 2)** → VIN do NodeMCU, e GND (desde 2026-10-06; ver a nota abaixo) |
| USB (a ponte) | RX (0) e TX (1) |

Livres: **A2 e A3**.

> **Por que o receptor saiu do RX (0).** O RX do UNO é o mesmo que o conversor
> USB usa, e o TX do NodeMCU, ligado direto ao pino, prevalecia sobre o
> conversor: o notebook não conseguia escrever no UNO, e para gravá-lo era
> preciso soltar o fio. Com o receptor no A0, o notebook manda a lista da
> Central e as injeções de teste com a bancada montada, e o upload não pede
> fio solto. O receptor continua a 9600 e continua sem mudar uma linha do
> sketch dele (§5).
>
> **Alimentação do receptor — o que a bancada mostrou em 2026-10-06.** O
> receptor estava ligado VIN (NodeMCU) → **VIN do UNO**. Com o UNO no USB, o VIN
> do UNO não é saída de 5V: só chega o que vaza de volta pelo regulador. O
> receptor funcionava no limite, e é a provável causa dos `RECUSADO` da primeira
> captura: ele reinicia, e o lixo do boot do ESP8266 gruda na linha seguinte. O
> **IOREF desta placa não fornece 5V** (o receptor nem ligou ali), e o 5V do UNO
> está ocupado pelo LCD. Na sessão de 2026-10-06 o receptor ficou **no USB do
> notebook** (COM4), com só o TX (A0) e o GND ligados ao UNO: 7 passagens, 7
> decisões, nenhum `RECUSADO`. A alimentação definitiva fica para decidir (USB
> próprio ou o 5V pela protoboard, junto com o LCD).
>
> **Decidido na mesma noite: o receptor tira 5V do pino 2 do ICSP do UNO**, com
> um jumper fêmea-fêmea até o VIN do NodeMCU. O pino 5V da barra está com o LCD;
> o **3.3V** do UNO não sustentou o ESP8266 (nenhuma passagem chegou), e o **VIN
> do UNO** também não (LED do ESP fraco, nenhuma passagem, e o UNO reiniciou ao
> ligar o receptor). No ICSP o LED do ESP acende forte, e as passagens chegaram
> (`SEM_OCORRENCIA`, nenhum `RECUSADO`). **Cuidado no ICSP:** o pino 5 é o RESET
> do ATmega328P; um fio nele mantém a placa reiniciando.
>
> **LCD sem texto = contraste.** Em 2026-10-06 o LCD acendia sem nenhum
> caractere, embora respondesse no I2C (`0x27`) e um sketch mínimo também não
> aparecesse: era o potenciômetro de contraste, atrás do módulo. Ajustado, o
> texto voltou, ainda fraco.
>
> **Custo da serial por software, medido no código e a confirmar na placa.** A
> `SoftwareSerial` do core desliga as interrupções enquanto recebe cada byte
> (~1 ms a 9600). O `millis()` não perde tique (o estouro do Timer0 fica
> pendente e é atendido logo depois), e a UART do USB guarda até 2 bytes nesse
> meio-tempo, mais do que chega em 1 ms. O nível lógico do TX do NodeMCU (3,3 V)
> é o mesmo que já chegava ao RX (0): acima do limiar de nível alto do
> ATmega328P a 5 V (0,6 × Vcc = 3,0 V), com pouca folga.

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
                              │ "RUA3,AMBULANCIA\r\n"  @9600, TX -> A0
                              ▼
                     [Arduino UNO — DECIDE e ATUA]  <── "AUT,AMBULANCIA,1"  @9600, USB -> RX(0)
                       Central (lista em RAM),            (a lista da Central, pela ponte)
                       criticidade, fila de 1,
                       verde exclusivo, transição segura, LCD
                              │ "EV,…,PREEMP_INI,3,AMBULANCIA" / "ST,…"  @9600, TX -> USB
                              ▼
                     [bridge/]  carimba no relógio do notebook; escreve AUT e injeções
                              │                                   ▲ PUT /autorizacoes
                              ▼                                   │
                     [Backend: log, métricas, WebSocket; compara a Central do banco com a ST]
                              │
                              ▼
                     [Dashboard: painel da bancada e aba Central]
```

**A decisão de preempção no protótipo é do UNO.** Ele roda uma regra local,
mais simples que o motor (`01` §5): a mesma regra que a equipe de hardware já
tinha escrita (fila de um lugar), agora com transição segura e, desde
2026-10-06, com a **Central**: só preempta o VE cujo tipo tem ocorrência ativa,
e quem interrompe quem é a criticidade dela. O motor de decisão continua sendo
o objeto do experimento, **na simulação** (`00` §3).

**O notebook não está no caminho da decisão.** A lista da Central fica na RAM do
UNO, e é contra ela que o UNO decide, sem perguntar nada a ninguém: se a ponte
cair, o cruzamento continua funcionando e preemptando com a última lista que
recebeu — o que muda é que o dashboard para de atualizar e a Central deixa de
alcançar o UNO. A borda (Edge) do pré-projeto é, na bancada, o próprio
controlador do cruzamento.

**A lista se perde quando o UNO reinicia**, e ele volta **negando todos**
(decisão de 2026-10-06). Abrir a porta serial reinicia o UNO (DTR), e fechá-la
não; por isso o backend compara a cada leitura (5 Hz) a lista do banco com a que
a `ST` traz, e manda a dele quando diferem — no máximo uma vez por segundo. Isso
cobre abrir e encerrar ocorrência e o reinício. Sem backend, o UNO fica negando
até alguém chamar `PUT /autorizacoes` na ponte.

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
`BOMBEIRO`, `POLICIA`. Chega pelo **A0** (desde 2026-10-06); a ponte pode
escrever a mesma linha pelo USB, para testar.

| Tipo | Verde do VE |
| --- | --- |
| `AMBULANCIA` | 9 s |
| `BOMBEIRO` | 8 s |
| `POLICIA` | 7 s |

**O tipo só fixa a duração do verde** desde 2026-10-06. Quem interrompe quem é a
criticidade da ocorrência (§3.3). Antes, o tipo era a prioridade (ambulância 1,
bombeiro 2, polícia 3), a regra do sketch da equipe.

Linha **com vírgula** e rua ou tipo desconhecido → `EV,<ms>,RECUSADO`, sem
efeito. **Mudança deliberada em relação ao sketch**, que dava prioridade 3 a
qualquer tipo desconhecido: um texto corrompido na serial não pode virar uma
viatura. Linha **sem vírgula** é ignorada em silêncio — é o que o ESP8266
imprime no próprio boot, a 74880 baud, e que chega ao UNO como lixo. Cada
entrada tem buffer próprio: **32 bytes no A0** (a maior linha que o receptor
manda tem 25) e **72 no USB**; linha maior é ruído e é recusada. **Pedaço de linha
seguido de mais de 100 ms de silêncio é descartado** (desde 2026-10-06): uma
linha de verdade chega inteira em ~26 ms, e o lixo que o ESP8266 deixa no fio ao
reiniciar grudava na linha seguinte e a fazia virar `RECUSADO` — era a causa dos
`RECUSADO` da primeira captura na bancada.

### 3.2.1 Entrada — a lista da Central, pelo USB (desde 2026-10-06)

`AUT,<VEICULO>,<criticidade>`, com `criticidade` de um dígito: **0** é "sem
ocorrência ativa", e **1 a 3** são os níveis de P20 (1 `RISCO_VIDA`, 2
`RISCO_COLETIVO`, 3 `URGENCIA`). Forma exata, sem espaços; o `\r` final sai.
Qualquer desvio → `EV,RECUSADO`, e a lista não muda.

- **Não gera evento.** A lista nova aparece na `ST` (§4.2), que sai na hora,
  porque a lista faz parte do que a `ST` publica.
- **Só pelo USB.** Pelo A0, a linha é uma detecção inválida e recebe
  `RECUSADO`: um VE não se autoriza pelo rádio.
- **Vive na RAM.** O UNO liga com `000`, negando todos, e volta a isso a cada
  reinício.

Na bancada a identidade do VE é o tipo (§3.3), então a lista é por tipo: a
criticidade mais alta entre as ocorrências abertas de veículos **ativos** daquele
tipo (`app.repositories.ocorrencia.criticidade_por_tipo`).

### 3.3 Decisão (a regra do sketch, com a Central)

Ao receber um VE válido, com a criticidade que o tipo dele tem **agora** na
lista:

0. **Criticidade 0** (sem ocorrência ativa) → `SEM_OCORRENCIA`, e nada muda no
   semáforo. O LCD mostra `SEM OCORRENCIA` por 3 s (§3.6).
1. **Sem emergência** → o VE é atendido (`PREEMP_INI`).
2. **Mesma rua e mesmo tipo do VE atendido** → o verde dele é **renovado**
   (`RENOVADO`): a duração recomeça a contar. *Acrescentado:* no sketch, o mesmo
   veículo relendo a tag ia para a fila e ganhava um segundo verde depois do
   primeiro.
3. **Criticidade estritamente mais alta** (número menor) que a do atendido → o
   atendido vai para a fila (`FILA`), ocupando o lugar de quem estivesse nela, e
   o novo é atendido (`PREEMP_INI`).
4. **Senão, fila vazia ou criticidade estritamente mais alta que a da fila** →
   o novo vai para a fila (`FILA`).
5. **Senão** → descartado (`DESCARTADO`).

**No mesmo nível, quem chegou primeiro fica.** É a guarda de oscilação do motor
(P20): só o estritamente mais crítico passa à frente. Com a Central dando a cada
tipo a criticidade da ordem antiga (ambulância 1, bombeiro 2, polícia 3), a
regra é exatamente a do sketch — é assim que o roteiro de aceitação roda.

**A criticidade vai com o VE lido.** Quem já está atendido ou na fila guarda a
criticidade que tinha quando foi lido; mudar a Central depois vale da próxima
leitura em diante. Em particular, **encerrar a ocorrência não corta um verde já
concedido nem tira o VE da fila**: o verde termina pela duração do tipo (no
máximo 9 s) ou pelo teto, e a releitura seguinte já recebe `SEM_OCORRENCIA`. Na
simulação o motor libera a preempção no passo seguinte ao encerramento (E6);
na bancada a diferença é de segundos, e é declarada.

A fila tem **um lugar**. Quem perde o lugar para outro VE (casos 3 e 4) sai com
`DESCARTADO`: no sketch ele sumia sem rastro, e o log da bancada perderia o VE de
vista. Quando o verde do VE atendido acaba (`PREEMP_FIM`), o da fila é atendido;
se não há fila, volta o ciclo.

A identidade do veículo é o tipo (§1). Dois veículos do mesmo tipo são
indistinguíveis — limitação da bancada, a declarar no texto. Pelo mesmo motivo,
**o mesmo carrinho lido em duas ruas vira dois VEs**: na captura de 2026-10-06,
o carrinho passou pela RUA1 e depois pela RUA3, e o UNO pôs a "segunda
ambulância" na fila. "Autorizar o veículo" na bancada é autorizar o tipo.

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
2. **Leitura das duas entradas a cada iteração** (o A0 e o USB), cada uma com o
   seu buffer de linha de tamanho fixo: os bytes delas chegam intercalados.
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
Sem ocorrência:   "SEM OCORRENCIA"    /  "AMBULANCIA na R3"   (por 3 s; 2026-10-06)
```

Cabem em 16 colunas (`AMBULANCIA na R1` tem exatamente 16). O LCD é decidido
pelo próprio UNO; não há texto vindo do backend. O aviso de `SEM OCORRENCIA`
passa por cima das outras mensagens por 3 s e some sozinho.

### 3.7 Implementação (entrega 5.3, 2026-10-05)

`firmware/uno/semaforo/`, em duas partes:

- **`controlador.h` e `.cpp` — o núcleo.** A decisão, as quatro regras das luzes
  (§8) e o protocolo. Não inclui nada do Arduino: o tempo entra como argumento,
  e pinos e serial entram pela interface `Placa`. Segue o dublê função a função,
  com os mesmos nomes.
- **`semaforo.ino` — a placa.** Pinos (tabela e índice), `Serial` a 9600, a
  `SoftwareSerial` do receptor no A0 (desde 2026-10-06), LCD e o `loop()`:
  `millis()`, depois `avancar()`, depois o A0 e o USB byte a byte, e o LCD **por
  último**, só quando o texto muda e sem `lcd.clear()`.

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

Desde 2026-10-06 cada entrada do teste diz **por onde chega** (A0 ou USB), as
sequências aleatórias incluem linhas `AUT` válidas e quase válidas nas duas
entradas, e há um caso com os bytes das duas linhas intercalados, para provar
que um buffer não corrompe o outro. O dublê modela o tamanho de cada buffer
(32 e 72 bytes), para que a igualdade continue exata.

**Verificação por mutação, 2026-10-05.** Nove sabotagens no `controlador.cpp`,
todas pegas: sem all-red, sem verde mínimo, renovação que não reinicia o verde,
rua 0 aceita, espaço ASCII de controle não aparado, teto que não descarta a
fila, volta pelo mesmo eixo, guarda lendo a máquina em vez do pino, e `ST`
periódica nunca pulada.

**Compilado com `arduino-cli`** (core `arduino:avr` 1.8.8, `LiquidCrystal I2C`
1.1.2, `SoftwareSerial` do core): **10.926 bytes de flash (33%) e 894 bytes de
RAM global (43%)** em 2026-10-06, contra 8.722 e 841 antes da Central. A
`SoftwareSerial` e o segundo buffer de linha passavam a RAM de 1 KB (1.080
bytes); os textos fixos (nomes de evento e mensagens do LCD) foram para a flash
(`FIXO(...)`, que é `PSTR` no AVR e literal comum no PC), e o buffer do A0 ficou
com 32 bytes. O teste confere que a RAM global fica abaixo de 1 KB:

```powershell
arduino-cli compile --fqbn arduino:avr:uno firmware/uno/semaforo
python -m bridge.gravar_uno --porta COM3     # compila, grava e relê a flash inteira
```

**Gravar com `bridge.gravar_uno`, não com `arduino-cli upload`** (2026-10-06).
Neste notebook o avrdude grava errado os bytes 60 a 63 de cada página de 128
bytes (a fronteira do segundo pacote USB de 64 bytes, no conversor 16U2 da
placa), e o `arduino-cli upload` não verifica por padrão. O gravador do
repositório fala o mesmo protocolo do bootloader em pedaços de 16 bytes e
**relê a flash inteira**; gravação que não confere é erro. Feche a ponte antes:
os dois disputam a porta.

**Boot e `lcd.init()`.** Na placa o `lcd.init()` bloqueia ~1,1 s logo depois do
boot. O all-red dura esse tempo, mais do que o 1 s mínimo, o que é seguro; desde
2026-10-06 a `ST` do all-red sai já no boot, e o primeiro verde aparece por volta
dos 1.125 ms.

**O que só a placa confirma:** os pinos, a serial a 9600, a serial por software
no A0, o LCD físico e o tempo real do `loop()`. É a aceitação abaixo (§6), com
`bridge.verificar` e o checklist de `06` §6.

## 4. Protocolo serial do UNO

Texto ASCII, linhas terminadas em `\r\n`, **9600 baud** — a velocidade do
NodeMCU receptor, mantida também no USB.

### 4.1 Entrada

| Por onde | Linha | §  |
| --- | --- | --- |
| A0 (receptor) | `<RUA>,<VEICULO>` | 3.2 |
| USB (ponte) | `AUT,<VEICULO>,<0..3>` — a lista da Central | 3.2.1 |
| USB (ponte) | `<RUA>,<VEICULO>` — a injeção de teste, igual à do receptor | 3.2 |

`PING`, `PRE`, `CLR`, `CFG`, `ST?`, `SAFE`, `TESTMODE` e `TEST`, do protocolo
anterior, deixaram de existir em 2026-10-05 e **não voltaram**: o host não
comanda o UNO; ele só lhe diz quem está em serviço (decisão de 2026-10-06).

### 4.2 Saída (TX → USB)

| Linha | Quando |
| --- | --- |
| `ST,<ms>,<s1><s2><s3><s4>,<regime>,<rua_ativa>,<rua_fila>,<aut>` | A 2 Hz **e** a cada mudança de estado (luz, regime, rua ativa, fila ou lista da Central); uma por instante |
| `EV,<ms>,BOOT` | No `setup()` |
| `EV,<ms>,PREEMP_INI,<rua>,<veiculo>` | VE passa a ser atendido (§3.3, casos 1 e 3, e quando sai da fila) |
| `EV,<ms>,RENOVADO,<rua>,<veiculo>` | Caso 2 |
| `EV,<ms>,FILA,<rua>,<veiculo>` | VE entra na fila, inclusive o interrompido no caso 3 |
| `EV,<ms>,DESCARTADO,<rua>,<veiculo>` | Caso 5, e quem perdeu o lugar na fila |
| `EV,<ms>,PREEMP_FIM,<rua>,<veiculo>` | O verde do VE acabou, ou o teto estourou |
| `EV,<ms>,TIMEOUT` | Teto de 30 s (§3.4, item 7), seguido do `PREEMP_FIM` do VE atendido |
| `EV,<ms>,RECUSADO` | Linha com vírgula e conteúdo inválido, inclusive `AUT` mal formada ou vinda do A0 |
| `EV,<ms>,SEM_OCORRENCIA,<rua>,<veiculo>` | Caso 0: o tipo do VE não tem ocorrência ativa na Central (desde 2026-10-06) |

- `<ms>`: `millis()` do UNO. Serve para ordenar e medir intervalos **dentro**
  do UNO; a latência oficial usa o relógio do notebook.
- Estados: `R`, `Y`, `G`, na ordem S1 S2 S3 S4.
- `<regime>`: `C` ciclo, `E` emergência. `<rua_ativa>` e `<rua_fila>`: `1..4`
  ou `0` (nenhuma).
- `<aut>`: três dígitos, a criticidade que o UNO tem para ambulância, bombeiro
  e polícia, nessa ordem; `0` é sem ocorrência. `100` = só a ambulância, com
  risco à vida. É por aqui que o backend confere se o UNO tem a lista certa.
- `<rua>` nos eventos: `1..4`.

**Cada linha válida recebida gera exatamente um evento de decisão**
(`PREEMP_INI`, `RENOVADO`, `FILA`, `DESCARTADO` ou `SEM_OCORRENCIA`), escrito **antes** de
qualquer outra linha. É o que mantém o carimbo de H3 sem fila de saída à frente
(§4.3). A única linha que pode sair antes é uma `ST` que já estava vencida
naquele mesmo milissegundo (a periódica, ou uma transição de luz): o firmware e
o dublê aplicam primeiro o que venceu, e só então decidem. É o caso de "uma
`ST` saindo quando o VE chega", declarado em §4.3.

Exemplo — VE na Rua 3 chegando com o eixo principal verde há 1 s:

```
uno <- EV,142350,PREEMP_INI,3,AMBULANCIA     (decisão, mesma iteração da leitura)
uno <- ST,142350,GGRR,E,3,0,100              (S1/S2 cumprem o resto do verde mínimo)
uno <- ST,144350,YYRR,E,3,0,100              (amarelo)
uno <- ST,146350,RRRR,E,3,0,100              (all-red)
uno <- ST,147350,RRGR,E,3,0,100              (verde exclusivo da Rua 3 — conta 9 s)
uno <- EV,156350,PREEMP_FIM,3,AMBULANCIA
uno <- ST,156350,RRYR,C,0,0,100              (volta pelo eixo principal, que esperou)
```

(Com a Central dando à ambulância risco à vida, `100`. Com `000`, a mesma
detecção teria virado `EV,142350,SEM_OCORRENCIA,3,AMBULANCIA`, e nada mudaria
nas luzes.)

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

**n = 100 passagens** (decisão do grupo de 2026-10-06, `06` §6): as mesmas 100
do RNF05, com p95 de verdade. Durante a medição a ambulância precisa estar **em
serviço na Central** — senão toda passagem vira `SEM_OCORRENCIA`, que não é
amostra. Cada passagem espera o ciclo voltar (~20 s), para virar `PREEMP_INI`
e não `RENOVADO`.

O intervalo cobre ESP-NOW, a serial do receptor ao UNO (desde 2026-10-06, pela
serial por software no A0) e a decisão do UNO. O
`PREEMP_INI` corresponde ao `ACK` do protocolo anterior: o UNO se compromete com
a transição, e a primeira mudança visível vem dali até 3 s depois, se o verde
mínimo estiver pendente. É a leitura de P14 ("até o início da atuação").

**Por que o primeiro byte, e não o fim da linha.** A 9600 baud cada caractere
leva ~1 ms; carimbar o fim da linha somaria ~35 ms à detecção e ~30 ms à
atuação, e a diferença entraria no resultado. **O que sobra e precisa ser
declarado:** a latência dos dois conversores USB-serial (o 16U2 do UNO e o do
emissor), que não se cancelam por serem chips diferentes, e até ~27 ms a mais
se uma `ST` estiver saindo do UNO quando o VE chega (erro para cima, contra a
hipótese).

**`t_decisao` não existe na bancada.** A decisão acontece dentro do UNO, em
microssegundos, e não é observável à parte. A latência de decisão (RNF01) é
medida na simulação, sobre o motor (`00` §5, decisão P2).

## 5. Firmware dos NodeMCUs — ficam como estão

Os sketches do emissor e do receptor **não mudam** (decisão de 2026-10-05,
mantida em 2026-10-06: mudou o pino do UNO em que o TX do receptor chega, não o
receptor).
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

## 6. A ponte (`bridge/`) — escuta, e escreve só a Central e a injeção

Processo Python no notebook. Responsabilidades:

- Abrir a serial do UNO (**9600**) e reconectar se o dispositivo sumir. Abrir a
  porta **reinicia o UNO** (DTR do conversor USB), que volta pelo all-red e
  **negando todos**; fechar não reinicia.
- **Levar a lista da Central ao UNO** (desde 2026-10-06): `PUT /autorizacoes`
  com `{"autorizacoes": {"AMBULANCIA": 1, …}}` escreve uma linha `AUT` por tipo
  e responde `202`; a confirmação é a `ST` seguinte, que traz a lista que o UNO
  tem. Quem chama é o backend (§2); sem backend, o roteiro de aceitação, ou
  qualquer um pelo `/docs` da ponte.
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
  `analysis/data/latencia_bancada.csv`. Detecção que vira `FILA`, `RENOVADO`,
  `DESCARTADO` ou `SEM_OCORRENCIA` não é amostra de H3: não houve atuação para
  medir. **Toda leitura do emissor**, amostra ou não, vira uma linha de
  `analysis/data/deteccoes_bancada.csv`, com o evento de decisão que teve ou
  `SEM_DECISAO` (desde 2026-10-07): é o dado do RNF05. `RECUSADO` não traz rua,
  não casa, e a leitura fica `SEM_DECISAO`. Os dois CSV levam a mesma `sessao`, e
  `python -m analysis.resumo_bancada` tira deles o RNF05 e o p95 de H3. O casamento
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
- **Checklist da bancada** (desde 2026-10-07): com `--telemetria`, cada linha do
  USB do UNO, a que ele escreve e a que a ponte escreve nele, vai crua e
  carimbada para `analysis/data/telemetria_bancada.csv` (`bridge/registro.py`),
  com a mesma `sessao` dos CSV de H3. O carimbo da linha do UNO é o mesmo
  `recebido_em` que o backend grava. `python -m analysis.checklist_bancada` tira
  dali os itens de `06` §6. Recusada com `--simulado`.
- **Injeção de teste** (`POST /injecao` com `rua` e `veiculo`): escreve no RX do
  UNO, pelo USB, a mesma linha que o receptor escreveria e devolve a decisão do
  UNO, com o `millis()` dela. Desde 2026-10-06 funciona **com a bancada
  montada**, e passa pela Central como a do receptor: tipo sem ocorrência volta
  `SEM_OCORRENCIA`. Sem decisão em 1 s, `504` (UNO calado, ou firmware anterior
  a 2026-10-06, com o receptor ainda no RX). `POST /injecao/bruta` escreve uma
  linha qualquer, para conferir o `EV,RECUSADO`.
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

**Aceitação do firmware (5.3).** Com a placa gravada e **o backend parado**,
subir `python -m bridge.main --porta COM3` e rodar o `python -m bridge.verificar`.
Ele manda a lista da Central (ambulância 1, bombeiro 2, polícia 3), injeta VEs
pela ponte e confere pela telemetria:

- boot em all-red e ciclo de 12 s; liga negando todos;
- a lista da Central chega ao UNO e aparece na `ST`, e fica (se mudar sozinha,
  o backend está no ar, e o roteiro para);
- verde exclusivo, atingido em no máximo 6 s;
- duração por tipo, renovação, interrupção por criticidade maior, fila e
  descarte;
- volta pelo eixo oposto, o teto de 30 s e o `RECUSADO`;
- `SEM_OCORRENCIA` sem mexer no semáforo, e a criticidade, e não o tipo,
  decidindo quem interrompe;
- I1 a I4 em toda a telemetria.

As durações são conferidas no `millis()` do UNO, com folga de 60 ms (uma volta do
`loop()`). O mesmo roteiro, contra o dublê, é o que valida o próprio roteiro
antes de haver placa: **16 de 16 em 2026-10-05**, em ~3 min, e **20 de 20 em
2026-10-06**, com a Central, em ~4 min. Ele mesmo pegou um defeito seu na
primeira rodada de 2026-10-05: renovava depois do `TIMEOUT` e confundia a
emergência nova com a antiga.

## 7. Modo de demonstração

Roteiro em `bridge/demo.py` (2026-10-07), com o dashboard aberto e o backend
no ar:

```powershell
python -m bridge.main --porta COM3      # terminal 1 (--telemetria, se quiser o registro)
python -m bridge.demo                   # terminal 2; pede a senha do operador
```

O roteiro diz ao apresentador o que fazer, espera o evento chegar pela ponte e
narra as luzes ao vivo. A Central entra pela API do backend (`POST
/ocorrencias` e o encerramento, com o token do operador), e quem leva a lista ao
UNO é o backend, como na operação normal: o roteiro só confere na `ST` que ela
chegou. Ele começa encerrando as ocorrências abertas (passo 1) e, no fim,
encerra as que a demonstração abriu. Opções: `--central-pela-api` (o passo 3
sem o dashboard), `--sem-carrinho` (a ponte injeta a ambulância no lugar do
carrinho; plano B, e o passo 6 é pulado), `--passos 45` (só alguns passos) e
`--sem-pausa`. **Não é medição:** as conferências dizem ao apresentador que o
passo saiu como devia, e nenhum número dali vai para o texto.

Validado contra o dublê em 2026-10-07, com um backend falso que só sincroniza a
Central (para não gravar evento simulado no banco da bancada): **18 de 18**, em
~4 min, e o passo 6 com a ponte derrubada de fora. **Ensaiado na placa no
mesmo dia: 19 de 19**, com a ocorrência do passo 3 aberta pelo dashboard e a
ponte encerrada com Ctrl+C no passo 6.

1. **Ciclo normal** — os dois eixos se alternando (12 s), ao vivo no dashboard.
   Ninguém em serviço na Central.
2. **Tag sem ocorrência** (volta em 2026-10-06) — o carrinho passa pela tag da
   Rua 3 → nada muda no semáforo, o LCD mostra `SEM OCORRENCIA` /
   `AMBULANCIA na R3`, e o dashboard registra a negação.
3. **A Central despacha a ambulância** — na aba Central, abrir uma ocorrência
   para a ambulância. Em até ~1 s o painel da bancada mostra "Em serviço no UNO:
   Ambulância".
4. **O carrinho passa de novo** → amarelo no eixo principal, all-red, verde só
   no S3. O LCD mostra `AMBULANCIA na R3`, e o dashboard mostra o evento. Ao fim
   do verde, o ciclo volta pelo eixo principal, que ficou esperando.
5. **Prioridade pela criticidade** — com a ambulância em `RISCO_COLETIVO` e um
   bombeiro em `RISCO_VIDA` na Central, a ponte injeta a ambulância na Rua 3 e,
   logo depois, o bombeiro na Rua 1: o bombeiro interrompe a ambulância (pelo
   amarelo e pelo all-red), e ela vai para a fila. Com as criticidades
   trocadas, quem interrompe é a ambulância. O emissor físico é sempre
   ambulância, então o segundo VE vem da injeção — que, desde 2026-10-06,
   funciona com a bancada montada.
6. **Autonomia do cruzamento** — encerrar a ponte. O semáforo continua, e o
   carrinho continua preemptando com a última lista; só o dashboard e a Central
   param de alcançar o UNO. O cruzamento não depende do notebook para decidir.
   Sem a ponte ninguém no notebook lê o UNO (abrir a porta o reiniciaria), então
   o roteiro pergunta ao apresentador o que ele viu.

**O que continua fora do roteiro, por consequência da arquitetura:**

- a tag não cadastrada → `ACESSO NEGADO`: tag desconhecida é ignorada no
  veículo, sem nada visível no cruzamento;
- o puxão do cabo USB → watchdog: o UNO não depende de comunicação, e o cabo é a
  alimentação dele.

## 8. Testes com hardware desconectado

`adapters/hardware/simulado.py` — o dublê do UNO, **reescrito em 2026-10-05**
com o comportamento de §3 e §4 (entrega 5.2 refeita). Continua em duas camadas:
`UnoSimulado`, dirigido por tempo injetado, e `TransporteSimulado`, a mesma
interface da porta real. O transporte modela a fiação de 2026-10-06: o que a
ponte escreve chega pelo USB (`Entrada.USB`), e `simular_receptor()` faz o papel
do NodeMCU, pelo A0 (`Entrada.RECEPTOR`). Reabrir a porta reinicia o UNO, que
perde a lista da Central.

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
