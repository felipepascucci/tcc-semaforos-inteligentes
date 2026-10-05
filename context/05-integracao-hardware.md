# 05 — Software Integrado ao Protótipo Físico

## 1. Inventário do hardware montado

### Subsistema A — Controlador semafórico (Arduino UNO R3)

**Um cruzamento com 4 aproximações** (decisão P13, 2026-08-24). Cada módulo semáforo 8 mm serve uma aproximação e tem sua **própria fase exclusiva** — regime de *split phasing*, um verde por vez. LEDs ligados diretamente aos pinos digitais, GND comum na protoboard.

| Semáforo | Aproximação | Fase | R | Y | G |
| --- | --- | --- | --- | --- | --- |
| S1 | Principal — Sentido A | 1 | 13 | 12 | 11 |
| S2 | Principal — Sentido B | 2 | 10 | 9 | 8 |
| S3 | Transversal — Sentido A | 3 | 7 | 6 | 5 |
| S4 | Transversal — Sentido B | 4 | 4 | 3 | 2 |

Porta: `COM3` · Placa: Arduino AVR Boards → Arduino Uno.

> **Matriz de conflito.** Sob *split phasing*, **toda fase conflita com todas as outras**. A invariante I1 se reduz a uma única condição verificável: *no máximo um dos quatro semáforos pode exibir verde em qualquer instante*. Isso é aplicado **duas vezes** — no motor de decisão e, independentemente, no firmware, que recusa com `NAK,PRE,CONFLITO` qualquer comando que a violaria. Defesa em profundidade: mesmo com bug no backend ou ruído na serial, o hardware não acende dois verdes conflitantes.

> **Duração do ciclo fixo.** Perfil de bancada definido em 2026-08-24: **verde 3 s, amarelo 2 s, all-red 1 s**. Com 4 fases, o ciclo completo leva `4 × (3 + 2 + 1)` = **24 s**.
>
> Como `verde_s == verde_min_s == 3 s`, a preempção na bancada **nunca trunca** um verde: aguarda o verde corrente terminar, o que leva no máximo 3 s. Pior caso da transição completa: `3 + 2 + 1` = **6 s** da chegada do `PRE` até o verde na fase alvo.

> **Atenção elétrica — P10 RESOLVIDA em 2026-08-24.** A equipe de hardware confirmou que **os módulos semáforo 8 mm já trazem resistores integrados**. Nenhum resistor externo é necessário.
>
> Verificação de corrente com essa informação: cada módulo acende **um LED por vez** (R, Y ou G), então o pior caso são 4 LEDs simultâneos — tipicamente ~20 mA cada, ~80 mA no total. Fica confortavelmente abaixo do limite de 200 mA do ATmega328P e dos 40 mA por pino. **Sem restrição para operação prolongada na apresentação.**

### Subsistema B — Identificação V2I (NodeMCU ESP8266 + RC522)

| RC522 | NodeMCU | Função |
| --- | --- | --- |
| 3.3V | 3V3 | Alimentação (**nunca 5 V**) |
| RST | D3 (GPIO 0) | Reset |
| GND | GND | Terra |
| IRQ | — | Não usado |
| MISO | D6 (GPIO 12) | SPI |
| MOSI | D7 (GPIO 13) | SPI |
| SCK | D5 (GPIO 14) | SPI clock |
| SDA/SS | D8 (GPIO 15) | Chip select |

Porta: `COM4` · Placa: NodeMCU 1.0 (ESP-12E Module).

### Subsistema C — Sinalização (LCD 16x2 I2C, no NodeMCU)

| LCD I2C | NodeMCU |
| --- | --- |
| GND | GND |
| VCC | VIN (5 V) |
| SDA | D2 (GPIO 4) |
| SCL | D1 (GPIO 5) |

> **Atenção:** o módulo I2C do LCD alimentado em 5 V tem pull-ups para 5 V nas linhas SDA/SCL, enquanto os GPIOs do ESP8266 são de 3,3 V e **não são 5 V-tolerantes**. Na prática costuma funcionar, mas é operação fora de especificação. Duas saídas seguras: (a) alimentar o LCD em 3,3 V — o contraste fica fraco mas o barramento fica correto; (b) usar um conversor de nível bidirecional. Se o LCD apresentar caracteres corrompidos intermitentes, é este o motivo. Documentar a escolha no TCC — é exatamente o tipo de detalhe que rende ponto na banca.
>
> **Cuidado com GPIO 0 (D3):** é pino de boot. Se estiver em nível baixo no reset, o ESP entra em modo de gravação. O RST do RC522 mantém D3 em estado indefinido durante o boot e isso pode impedir a inicialização. Se o NodeMCU não bootar com o RC522 conectado, remanejar RST para D0 (GPIO 16) e atualizar a documentação de pinagem.

## 2. Arquitetura de software do protótipo

```
[Tag S50] --RFID--> [NodeMCU: leitura UID]
                          │ HTTP POST /api/v1/deteccoes  (Wi-Fi)
                          ▼
                  [Backend FastAPI]
                          │ tag reconhecida? ocorrência ativa? (P20)
                          │   não -> "SEM OCORRENCIA", sem preempção
                          ▼   sim -> VE com a criticidade da ocorrência
                  [MotorDecisao]
                          │ comando abstrato
                          ▼
                  [bridge/ — pyserial]
                          │ "PRE,1,20\n"  @115200
                          ▼
                  [Arduino UNO — máquina de estados]
                          │ "ACK,PRE" / telemetria "ST,..."
                          ▼
                  [Backend grava log + WebSocket -> Dashboard]
                          │ resposta HTTP com mensagem_lcd
                          ▼
                  [NodeMCU atualiza LCD 16x2]
```

## 3. Firmware do Arduino UNO — requisitos

O código atual do documento de protótipo usa `delay()` em sequência. **Ele precisa ser reescrito**, e o motivo é estrutural, não estético: durante um `delay(5000)` o Arduino não lê a serial, então é fisicamente impossível reagir a um comando de preempção. Um sketch bloqueante nunca poderá atender ao RF02 (alterar semáforos em até 3 s).

Reescrever como **máquina de estados não-bloqueante** com `millis()`:

```
Ciclo fixo, 4 fases (split phasing — uma aproximação verde por vez):

  FASE_1_VERDE -> FASE_1_AMARELO -> ALL_RED
  -> FASE_2_VERDE -> FASE_2_AMARELO -> ALL_RED
  -> FASE_3_VERDE -> FASE_3_AMARELO -> ALL_RED
  -> FASE_4_VERDE -> FASE_4_AMARELO -> ALL_RED -> (loop)

  Tempos de bancada: verde 3 s · amarelo 2 s · all-red 1 s  ->  ciclo de 24 s

Estados de preempção: PREEMP_TRANSICAO -> PREEMP_ATIVA -> PREEMP_LIBERANDO

Estado de bancada:     TESTE  (entra por TESTMODE,1; sai por TESTMODE,0)
```

Implementar o ciclo como **índice de fase + tabela**, não como estados enumerados um a um. Com 4 fases a versão enumerada já fica repetitiva, e a tabela permite mudar o número de fases sem reescrever a máquina:

```c
const uint8_t VERDE_DE[4] = {11, 8, 5, 2};      // pino G de cada fase
const uint8_t AMAR_DE[4]  = {12, 9, 6, 3};
const uint8_t VERM_DE[4]  = {13, 10, 7, 4};
```

Requisitos obrigatórios do firmware:

1. **Não-bloqueante.** Nenhum `delay()` no `loop()`. Único uso aceitável é debounce de milissegundos na inicialização.
2. **Leitura serial a cada iteração**, com buffer de linha e parser de comandos.
3. **Transição segura.** Ao receber `PRE`, nunca apagar verde e acender vermelho no mesmo instante: passar por amarelo (`AMARELO_MS`) e all-red (`ALL_RED_MS`). Respeitar verde mínimo antes de truncar.
4. **Watchdog de comunicação (I6).** Se não receber nenhum comando nem ping por `WATCHDOG_MS = 3000` enquanto estiver em preempção **ou em modo de teste**, retomar o ciclo fixo sozinho. Este é o comportamento fail-safe que garante que o cabo USB caindo não deixe um verde travado — e o modo de teste entra na regra justamente porque é o regime em que combinações arbitrárias são permitidas.
5. **Timeout de preempção.** Preempção nunca dura mais que `PREEMP_MAX_MS = 30000`, mesmo sem comando de liberação.
6. **Telemetria periódica** a 2 Hz.
7. **Sem `String` do Arduino.** Usar `char[]` de tamanho fixo. `String` fragmenta o heap de 2 KB do ATmega328P e o sketch trava depois de horas — justamente durante a apresentação.
8. **Guarda de conflito local (I1).** Antes de acender qualquer verde, verificar que nenhum outro semáforo está em verde. Sob *split phasing* isso é literalmente `contar_verdes() <= 1`. A guarda vale **inclusive no modo de teste**: `TEST,GG--` é recusado com `NAK,TEST,CONFLITO`. O modo de teste libera combinações de cor, não libera violar I1.

## 4. Protocolo serial (backend ↔ Arduino UNO)

Texto ASCII, linhas terminadas em `\n`, **115200 baud**. Formato compacto para parsing barato no AVR.

### Comandos (host → Arduino)

| Comando | Formato | Descrição |
| --- | --- | --- |
| Ping | `PING\n` | Verifica vida; mantém o watchdog |
| Preempção | `PRE,<fase>,<dur_s>\n` | Preempta para a fase indicada. **`fase` ∈ 1..4** (P13) |
| Liberar | `CLR\n` | Encerra preempção, retoma ciclo |
| Configurar | `CFG,<verde_s>,<amarelo_s>,<allred_s>\n` | Ajusta tempos do ciclo |
| Consultar | `ST?\n` | Solicita telemetria imediata |
| Emergência | `SAFE\n` | Força todos vermelhos (parada segura) |
| Modo de teste | `TESTMODE,<0\|1>\n` | Entra/sai do modo de bancada |
| Acionamento direto | `TEST,<c1><c2><c3><c4>\n` | Só em modo de teste. `c` ∈ `R` `Y` `G` `-` (apagado) |

`TEST` existe para conferir fiação e gravar vídeo da bancada. **Fora do modo de teste é sempre recusado** com `NAK,TEST,MODO`. Em modo de teste o ciclo fixo é suspenso e a preempção é recusada — os dois regimes nunca coexistem.

### Respostas (Arduino → host)

| Resposta | Formato | Descrição |
| --- | --- | --- |
| Confirmação | `ACK,<comando>\n` | Comando aceito |
| Rejeição | `NAK,<comando>,<motivo>\n` | Comando inválido ou não aplicável |
| Telemetria | `ST,<ms>,<fase>,<estado_s1><estado_s2><estado_s3><estado_s4>,<preemp>,<teste>\n` | Estado completo |
| Evento | `EV,<ms>,<tipo>\n` | `WATCHDOG`, `TIMEOUT`, `PREEMP_INI`, `PREEMP_FIM`, `TESTE_INI`, `TESTE_FIM`, `CONFLITO_RECUSADO` |

Estados codificados como um caractere: `R`, `Y`, `G`. O campo `<teste>` (`0`/`1`) foi acrescentado ao final da telemetria em P13 — o parser deve tolerar sua ausência para não quebrar com firmware antigo.

**Motivos de `NAK`:** `FASE_INVALIDA` (fora de 1..4), `CONFLITO` (violaria I1), `MODO` (comando não permitido no regime atual), `VERDE_MIN` (truncaria verde antes do mínimo), `FORMATO`.

Exemplo de sessão — preempção para a fase 3, partindo da fase 1 em verde:

```
host  -> PRE,3,20
uno   <- ACK,PRE
uno   <- EV,142350,PREEMP_INI
uno   <- ST,142350,1,YRRR,0,0      (fase 1 em amarelo)
uno   <- ST,142850,1,RRRR,0,0      (all-red — cruzamento limpo)
uno   <- ST,143350,3,RRGR,1,0      (preempção ativa na fase 3)
host  -> CLR
uno   <- ACK,CLR
uno   <- EV,156100,PREEMP_FIM
```

Note que **em nenhum instante há mais de um `G`** na string de estado. Essa é a verificação de I1 sobre a telemetria, e ela é grep-ável no log de validação.

**A latência de atuação (`t_atuacao`) é carimbada quando o backend recebe o `ACK`**, não quando envia o comando. Medir o envio mediria apenas a velocidade do próprio código.

### Tradução comando abstrato → linha (entrega 5.1, 2026-10-02)

Implementada em `bridge/protocolo.py` (`traduzir()`), testada em `bridge/tests/test_protocolo.py`.

| Comando do motor (`01` §9) | Linha | Por quê |
| --- | --- | --- |
| `IR_PARA_FASE` | `PRE,<fase>,<dur_s>` | Preempção (E5) |
| `ESTENDER_VERDE` **com** `id_veiculo` | `PRE,<fase>,<dur_s>` | A fase pedida já está verde |
| `ESTENDER_VERDE` **sem** `id_veiculo` | nenhuma | Extensão de compensação do E7, ver abaixo |
| `LIBERAR` | `CLR` | Fim da preempção |
| `COMPENSAR` | `CLR` | O motor o emite **no lugar** de `LIBERAR`; sem `CLR` o UNO ficaria em preempção até o timeout de 30 s |
| `FALLBACK_SEGURO` | `CLR` | O fail-safe de `01` §6 é voltar ao ciclo fixo. `SAFE` (todos em vermelho) é parada de operador, não fail-safe |

Regras que saem dessa tabela:

- **`PRE` para a fase que já está verde estende o verde, sem recomeçar a transição.** É o primeiro ramo de E5 (`01` §5.2), e é requisito do firmware (5.3).
- **`dur_s` é inteiro, arredondado para cima.** Arredondar para baixo poderia fechar o verde antes de o VE passar; o erro para cima custa no máximo 1 s à transversal. Os tempos de `CFG`, ao contrário, **não** são arredondados: são tempos de segurança (I2–I4), e valor fracionário é recusado.
- **O protocolo valida formato; a semântica é do firmware.** `PRE,5,20` e `TEST,GG--` saem da ponte, e quem recusa é o UNO (`FASE_INVALIDA`, `CONFLITO`). A ponte não é uma terceira cópia da matriz de conflito, e recusar ali esconderia a guarda que a bancada precisa demonstrar.
- **Telemetria com dois `G` é interpretada, não rejeitada.** É a evidência de violação de I1 que o relatório de validação conta; descartá-la como linha malformada apagaria o que se quer detectar.
- **O parser aceita `\r\n`**, que é o que `Serial.println` envia, além do `\n` do contrato. Em modo de teste a telemetria pode trazer `-` (módulo apagado).

**Compensação não é demonstrada na bancada — decisão da equipe, 2026-10-04.** A extensão de compensação sai do motor sem `id_veiculo` justamente para não ser contada como preempção, e o protocolo não tem linha para "estender o verde do ciclo fixo sem preempção": `PRE` marcaria o UNO como em preempção. Nada se perde, porque a bancada não mede fila: com fila zero o plano de E7 é a própria duração base, e a extensão coincide com o ciclo fixo. Não haveria o que mostrar mesmo com um comando novo, então **o protocolo do §4 fica como está** (contrato §15, item 4, fechado) e a compensação sai do roteiro de demonstração (§7, passo 4). E7 continua no motor e é medida onde H2 é avaliada, na simulação — que é a fonte dos dados estatísticos de qualquer forma (`00` §3, Frente A).

## 5. Firmware do NodeMCU — requisitos

1. **Deduplicação de leitura.** O RC522 lê a mesma tag continuamente enquanto ela estiver no campo. Enviar um POST por leitura inunda o backend. Regra: enviar apenas quando o UID mudar **ou** quando tiverem passado mais de `COOLDOWN_MS = 3000` desde o último envio do mesmo UID.
2. **Contador `sequencia`** monotônico, incrementado a cada envio, reiniciado no boot.
3. **HTTP não-bloqueante ou com timeout curto** (`setTimeout(2000)`). Um POST pendurado congela o loop e o LCD para de atualizar.
4. **Reconexão de Wi-Fi** com backoff; enquanto desconectado, mostrar `SEM CONEXAO` no LCD.
5. **`secrets.h` gerado**, nunca commitado (ver `02-arquitetura-infraestrutura.md` §4).
6. **Descoberta do endereço I2C** do LCD com I2C Scanner antes de fixar (`0x27` ou `0x3F`). Rodar uma vez, anotar no código com comentário.
7. **Nada de `delay()` no loop principal**, mesmo motivo do UNO.

### Mensagens do LCD (16 colunas × 2 linhas)

Contar os caracteres — 16 é pouco:

```
Normal:      "SISTEMA ATIVO   "  /  "AGUARDANDO...   "
Detecção:    "AMBULANCIA      "  /  "PRIORIDADE ATIVA"
Bombeiro:    "BOMBEIROS       "  /  "PRIORIDADE ATIVA"
Polícia:     "POLICIA         "  /  "PRIORIDADE ATIVA"
Liberado:    "VIA LIBERADA    "  /  "CICLO NORMAL    "
Não autoriz: "TAG DESCONHECIDA"  /  "ACESSO NEGADO   "
Sem serviço: "SEM OCORRENCIA  "  /  "SEM PRIORIDADE  "
Sem rede:    "SEM CONEXAO     "  /  "MODO LOCAL      "
```

**"Sem serviço" (P20, 2026-09-29)** é a tag **reconhecida** de um veículo que não
tem ocorrência aberta pela central — uma ambulância voltando para a base, por
exemplo. Não é credencial inválida (essa é "TAG DESCONHECIDA", com HTTP 403): a
resposta é HTTP 200 com `acao = "SEM_OCORRENCIA"`, e o firmware só imprime o que
vier em `mensagem_lcd`, sem lógica nova.

## 6. A ponte (`bridge/`)

Processo Python separado, responsabilidades:

- Abrir a serial, reconectar automaticamente se o dispositivo sumir.
- Enviar `PING` a cada 1 s (alimenta o watchdog do UNO).
- Traduzir `Comando` abstrato → linha do protocolo.
- Parsear telemetria → publicar no backend (HTTP interno ou fila).
- Carimbar `t_atuacao` na chegada do `ACK`.
- Expor `/health` próprio com estado da porta serial.

Estrutura (implementada nas entregas 5.1 e 5.7, 2026-10-04):

```
bridge/
├── main.py            # CLI: python -m bridge.main [--porta COM3 | --simulado]
├── api.py             # HTTP da ponte: /health, /estado, /comandos (FastAPI, :8001)
├── ponte.py           # laço asyncio: PING 1 s, reconexão, ACK -> t_atuacao
├── protocolo.py       # serialização/parsing das linhas
├── serial_client.py   # pyserial, uma thread por leitura/escrita com timeout curto
├── transporte.py      # a interface comum à porta real e ao dublê
├── verificar.py       # roteiro de conferência pelo HTTP — dublê ou bancada
└── tests/             # protocolo, ponte, API e cliente serial — tudo sem hardware
```

**Conferência de ponta a ponta.** `python -m bridge.verificar`, rodado logo depois de subir a ponte, dirige `/comandos` como o backend vai dirigir e confere pela telemetria: boot em all-red, ciclo de 24 s, recusas, `PRE` em verde (≤ 6 s) e em amarelo, fim por `dur_s`, extensão, fail-safe, timeout de 30 s e I1 a I3 em toda a telemetria. Leva ~2 min. Contra o dublê, em 2026-10-05: **17 de 17**. O mesmo roteiro serve para aceitar o firmware da 5.3 na bancada. Watchdog, reconexão, `SAFE` e modo de teste não têm `Comando` que os acione pelo HTTP: ficam com os testes automatizados e o checklist.

`protocolo.py` deve ser 100% testável sem hardware conectado: entra `Comando`, sai `bytes`; entra `bytes`, sai evento. Isso permite desenvolver e testar o protocolo mesmo quando o Arduino não está na mesa.

**Como o backend fala com a ponte (5.7).** A ponte expõe HTTP em `127.0.0.1:8001`, e o sentido é **backend → ponte**: o backend chama `POST /comandos` com o `Comando` do motor e o `id_correlacao` da detecção, e recebe de volta a linha enviada, o `ACK`/`NAK` e o **`t_atuacao`**, numa só ida e volta, que é o que `metrica_latencia` precisa. A telemetria e os eventos do UNO ficam em `GET /estado`. Se a ponte deve **empurrar** telemetria ao backend, em vez de o backend ler, decide-se no Bloco 6, que é quando ele passa a ter rota para recebê-la. Códigos: `503` com a porta fechada, `504` se o UNO não responde em 1 s, `422` para comando sem fase ou duração. `/health` responde `503` enquanto o UNO não estiver mandando telemetria.

**Relógio.** `t_atuacao` é carimbado pela tarefa que lê a porta **no instante em que a linha chega**, antes de interpretá-la. O relógio é o do notebook, em UTC, mas lido com a resolução do `perf_counter` (100 ns) e ancorado no relógio de parede uma vez, porque no Windows o relógio de parede declara resolução de 15,6 ms. **O backend precisa carimbar `t_deteccao` do mesmo jeito** (Bloco 6). Senão a subtração de H3 mistura duas resoluções.

**A ponte não sabe se há Arduino.** `ponte.py` fala com um `Transporte`. `serial_client.py` implementa a porta real e `adapters/hardware/simulado.py`, o dublê (§8). `python -m bridge.main --simulado` sobe a ponte inteira sem bancada.

## 7. Modo de demonstração

Para a apresentação, um roteiro determinístico em `bridge/demo.py`:

1. Sistema em ciclo normal — mostrar as 4 fases se sucedendo, uma aproximação verde por vez.
1b. **Emergência é estado declarado (P20).** Aproximar a tag da ambulância **sem ocorrência aberta** → LCD `SEM OCORRENCIA`, o semáforo não muda, a tentativa aparece no dashboard. Abrir a ocorrência no painel "Central" do dashboard (criticidade 1, `RISCO_VIDA`). É a resposta, na bancada, à pergunta "como o semáforo sabe que a emergência é real?".
2. Aproximar a tag da ambulância (agora com ocorrência aberta) → LCD muda, o semáforo da aproximação do VE vai para verde com transição segura (amarelo → all-red → verde), dashboard acende o alerta.
3. Mostrar o log de priorização aparecendo em tempo real no dashboard, com a latência medida.
4. ~~Após a passagem, mostrar a compensação nas transversais.~~ **Retirado em 2026-10-04:** a bancada não mede fila, então a compensação coincide com o ciclo fixo e não há o que mostrar (§4, "Compensação não é demonstrada na bancada"). Se a banca perguntar, a resposta é que E7 é avaliada na simulação, onde H2 é medida.
5. Aproximar uma tag não cadastrada → `ACESSO NEGADO`, sem preempção, tentativa registrada.
6. Desconectar o cabo do Arduino → watchdog dispara, sistema retorna ao ciclo fixo (demonstração do fail-safe).

O item 6 é o mais impressionante para a banca e é o mais barato de implementar. Não deixe de fora.

## 8. Testes com hardware desconectado

Implementar `adapters/hardware/simulado.py`: um dublê que responde ao protocolo em memória, com latências artificiais. Sem ele, ninguém consegue desenvolver o backend quando o protótipo não está disponível — e num trabalho em trio isso é a regra, não a exceção.

**Implementado na entrega 5.2 (2026-10-04).** Duas camadas: `UnoSimulado`, o firmware puro e dirigido por tempo injetado, e `TransporteSimulado`, a mesma interface da porta real, com relógio de verdade e latência artificial.

**O semáforo do dublê é a máquina de estados de `core/priorizacao/fases.py`**, que já era o modelo de referência do firmware e o alvo dos testes de I1 a I4. O dublê só acrescenta o que é do firmware: `ACK`/`NAK`, eventos, telemetria a 2 Hz, watchdog, modo de teste e `SAFE`. Os testes verificam I1 a I4 com Hypothesis sobre sequências aleatórias de linhas, e uma verificação por mutação confirmou que eles pegam uma guarda de I1 e um all-red sabotados.

**O dublê fixa o comportamento que o contrato deixava em aberto, e isso vira requisito do firmware (5.3):**

| Situação | Comportamento |
| --- | --- |
| Boot | Liga em **all-red** e só então abre a fase 1. Nenhum verde acende no reset |
| `PRE` durante amarelo ou all-red | **Aceito**: muda o destino da transição em curso, sem refazê-la. Recusar e esperar levaria o pior caso a 9 s, contra os **6 s** que o contrato §7 promete. Verificado em qualquer instante do ciclo |
| Fim de `PRE,<fase>,<dur_s>` | O verde alvo vale até `dur_s` contados do recebimento, com o verde mínimo como piso. Quando ele acaba, a preempção acaba junto, com `EV,PREEMP_FIM`. Na bancada não há como ver o VE cruzar e mandar `CLR` |
| `CLR` sem preempção | `NAK,CLR,MODO` |
| `SAFE` | Termina o verde (respeitando o mínimo) e o amarelo, e **segura o all-red**. Sai por `CLR` ou pelo watchdog. Vale em qualquer regime, e no modo de teste encerra o teste |
| `CFG` | Só no ciclo fixo, sem preempção (`NAK,CFG,MODO`). Verde abaixo do mínimo recebe `NAK,CFG,VERDE_MIN` |
| `ST?` | Responde só com a linha `ST`, sem `ACK` |
| `TESTMODE` repetido | Idempotente: `ACK` sem efeito. `TESTMODE,1` durante preempção ou `SAFE` recebe `NAK,TESTMODE,MODO` |
| Saída do modo de teste | Pelo **all-red**, por `TESTMODE,0` ou pelo watchdog. O modo de teste garante I1, não I2 a I4 |
| Linha malformada | Com nome de comando reconhecível: `NAK,<cmd>,FORMATO`. Sem nome reconhecível: ignorada. **Nenhuma das duas alimenta o watchdog** |
| Abrir a porta | **Reinicia a placa** (DTR do USB serial), como no UNO real |

**Nenhum número produzido com o dublê é dado experimental.** A latência é uma constante arbitrária (5 ms); H3 se mede na bancada.
