# Contrato Hardware–Software

Documento de validação da integração entre o software e o protótipo físico. Escrito para ser lido pela equipe de hardware e por agentes de código que trabalhem em `firmware/`, `bridge/` ou `adapters/hardware/`.

> **Autoridade deste arquivo.** A fonte da verdade do escopo continua sendo `context/`. Este documento é uma **síntese orientada à integração**, derivada de `context/01`, `context/02`, `context/05` e `context/09`. Onde houver divergência, `context/` vence e este arquivo é que está desatualizado. Trechos marcados `INFERÊNCIA` não constam de nenhum documento original — são leituras minhas, ainda não confirmadas pela equipe.

| | |
| --- | --- |
| Versão | **2** — 2026-08-24 · incorpora as respostas da equipe de hardware (P10 resolvida, P13 definida: 4 fases em *split phasing*) |
| Equipe | Felipe Rafael Tancredi Pascucci · Giovanna Santos da Silva · Isabelle Rosa Moura Ferreira |
| Versão navegável | Artifact "Contrato Hardware–Software" (mesmo conteúdo, para leitura humana) |

---

## §1 — O que o sistema faz

Um veículo de emergência (VE) se aproxima de um cruzamento. O sistema o identifica, calcula quais semáforos da rota precisam mudar, e executa a **preempção** — interrompe o ciclo normal para conceder verde à aproximação do VE. Depois da passagem, **compensa** o ciclo por `n_ciclos_compensacao = 2` ciclos, redistribuindo verde às transversais que ficaram esperando.

Duas frentes de validação, com papéis diferentes:

| Frente | O que é | Papel |
| --- | --- | --- |
| **A — Simulação** | SUMO + TraCI, malha de 8 cruzamentos, 600 execuções | Produz **todos** os números estatísticos (H1, H2, H3) |
| **B — Protótipo físico** | Arduino UNO + NodeMCU + RC522 + LCD, 4 semáforos | Prova de viabilidade da camada V2I e do atuador. **Não** gera estatística |

Consequência prática: uma falha de bancada na véspera não derruba o capítulo de resultados.

---

## §2 — A decisão arquitetural central

Existe **um único motor de decisão**, em Python puro (`backend/core/priorizacao/`), agnóstico ao atuador. Ele recebe um `EstadoMalha` normalizado e devolve `list[Comando]` abstratos.

```python
class TipoComando(StrEnum):
    ESTENDER_VERDE  = "ESTENDER_VERDE"
    IR_PARA_FASE    = "IR_PARA_FASE"
    LIBERAR         = "LIBERAR"
    COMPENSAR       = "COMPENSAR"
    FALLBACK_SEGURO = "FALLBACK_SEGURO"
```

Quem traduz comando abstrato em ação concreta é um adaptador: `adapters/sumo/` ou `adapters/hardware/`.

**Para o lado do hardware isso significa: o Arduino nunca decide nada.** Ele não sabe o que é um VE, não conhece rotas, não calcula ETA. Recebe `PRE,1,20` e executa com segurança.

**Restrição de arquitetura, verificada por teste** (`backend/tests/test_arquitetura.py`, via AST): nada dentro de `backend/core/` pode importar `traci`, `pyserial`, `sqlalchemy` ou `fastapi`.

> O que isso **não** quer dizer: o Arduino não decide *quando* preemptar, mas continua dono da **segurança**. Pode recusar comando inseguro (`NAK`), impõe verde mínimo, e retoma o ciclo fixo sozinho se o notebook sumir. Segurança viária não é delegada pela rede — §9.

---

## §3 — Fluxo fim-a-fim no protótipo

```
      [Tag Mifare S50 — no VE]
                │  lê UID (SPI)
                ▼
      [NodeMCU ESP8266 · RC522 · LCD 16x2]
                │  POST /api/v1/deteccoes   (Wi-Fi 2,4 GHz)
                ▼
 ┌──────────────────────────────────────────────┐
 │ NÓ DE BORDA — notebook, junto ao cruzamento  │
 │                                              │
 │   [API FastAPI]        ◀── t_deteccao        │
 │    resolve UID → veículo, valida token       │
 │         │                                    │
 │         ▼                                    │
 │   [MotorDecisao.avaliar()]  ◀── t_decisao    │
 │    Python puro, sem I/O, < 100 ms            │
 │         │                                    │
 │         ▼                                    │
 │   [bridge/ — pyserial]  ◀── t_atuacao        │
 │                             (na chegada do ACK)
 └──────────────────────────────────────────────┘
                │  "PRE,1,20\n"   (USB serial 115200)
                ▼
      [Arduino UNO R3 — máquina de estados]
                │  pinos digitais 2–13
                ▼
      [4 módulos semáforo — S1 S2 principal · S3 S4 transversal]

 Retornos:
   Arduino → bridge : "ACK,PRE" · "ST,..." · "EV,..."
   API → NodeMCU    : campo mensagem_lcd na resposta HTTP
```

**O NodeMCU e o Arduino nunca conversam entre si.** Todo tráfego passa pelo notebook.

---

## §4 — Por que a ponte serial existe

Ligar o ESP8266 direto ao Arduino, ou usar o ESP como ponte, foi considerado e descartado:

1. **Perderíamos o ponto de medição de latência.** Com a decisão no ESP não haveria onde carimbar `t_decisao` separado de `t_atuacao`, e H3 ficaria sem instrumentação.
2. **O motor precisa rodar em um lugar só** (§2). Lógica duplicada entre firmware e backend quebra a equivalência simulação↔protótipo, que é a afirmação central do trabalho.
3. **O dashboard precisa ver os dois lados** — detecção e atuação — e só o backend está entre eles.

Ganho narrativo para o texto: o processo `bridge`, rodando no notebook colocado junto ao cruzamento, **é** o nó de borda da arquitetura Edge do pré-projeto. Não é metáfora — é o componente que toma a decisão crítica localmente, sem depender de internet.

---

## §5 — Inventário e pinagem

Pinagem **como documentada em `context/05` §1**. O firmware será escrito contra esta tabela; divergência na bancada precisa ser reportada antes do Bloco 5.

### Subsistema A — Controlador semafórico · Arduino UNO R3 · `COM3`

Placa: Arduino AVR Boards → Arduino Uno. LEDs ligados diretamente aos pinos digitais, GND comum na protoboard.

**Um cruzamento com 4 aproximações**, em regime de ***split phasing*** — cada aproximação tem sua própria fase exclusiva, um verde por vez (decisão P13, 2026-08-24).

| Semáforo | Aproximação | Fase | R | Y | G |
| --- | --- | --- | --- | --- | --- |
| S1 | Principal — sentido A | 1 | 13 | 12 | 11 |
| S2 | Principal — sentido B | 2 | 10 | 9 | 8 |
| S3 | Transversal — sentido A | 3 | 7 | 6 | 5 |
| S4 | Transversal — sentido B | 4 | 4 | 3 | 2 |

> **Matriz de conflito — o ponto mais importante desta seção.**
>
> Sob *split phasing*, **toda fase conflita com todas as outras**. Isso simplifica a invariante I1 a uma única condição verificável:
>
> ```
> em qualquer instante:  contar_verdes(S1,S2,S3,S4) <= 1
> ```
>
> Três linhas de guarda no AVR, e uma verificação `grep`-ável sobre a telemetria no relatório de validação.
>
> A matriz é aplicada **duas vezes, de forma independente** (decisão P13): o motor não emite comando conflitante, **e** o firmware recusa com `NAK,<cmd>,CONFLITO` se receber um. A segurança não pode depender de a serial estar íntegra nem de o backend estar correto.

> **Tempos da bancada — definidos em 2026-08-24.** Verde **3 s**, amarelo 2 s, all-red 1 s. Com 4 fases o ciclo completo leva `4 × (3 + 2 + 1)` = **24 s** — seriam 32 s com verde de 5 s. Detalhes e consequências no §7. **Não tocar em `parametros.yaml`**, que é o perfil de simulação e alimenta os dados estatísticos.

> **Histórico.** A v1 deste documento inferiu 2 fases (S1+S2 juntos, S3+S4 juntos). A equipe de hardware refutou em 2026-08-24. §6 e §7 abaixo já refletem a definição correta.

### Subsistema B — Identificação V2I · NodeMCU ESP8266 + RC522 · `COM4`

Placa: NodeMCU 1.0 (ESP-12E Module).

| RC522 | NodeMCU | Função |
| --- | --- | --- |
| 3.3V | 3V3 | Alimentação — **nunca 5 V** |
| RST | D3 (GPIO 0) | Reset — **ver P8, §12** |
| GND | GND | Terra |
| IRQ | — | Não usado |
| MISO | D6 (GPIO 12) | SPI |
| MOSI | D7 (GPIO 13) | SPI |
| SCK | D5 (GPIO 14) | SPI clock |
| SDA/SS | D8 (GPIO 15) | Chip select |

### Subsistema C — Sinalização · LCD 16x2 I2C, no NodeMCU

| LCD I2C | NodeMCU | Observação |
| --- | --- | --- |
| GND | GND | — |
| VCC | VIN (5 V) | **Ver P9, §12** |
| SDA | D2 (GPIO 4) | — |
| SCL | D1 (GPIO 5) | — |

---

## §6 — Protocolo serial

**O contrato entre `bridge/` e o firmware do UNO.** Fechado este contrato, os dois lados avançam em paralelo.

Texto ASCII puro, linhas terminadas em `\n`, **115200 baud**. Formato compacto para parsing barato no ATmega328P.

Implementação: `bridge/protocolo.py` — **100% testável sem hardware conectado** (entra `Comando`, sai `bytes`; entra `bytes`, sai evento). Testes em `bridge/tests/test_protocolo.py`.

### Comandos — host → Arduino

| Formato | Nome | Descrição |
| --- | --- | --- |
| `PING\n` | Ping | Verifica vida e alimenta o watchdog. Enviado a cada 1 s pela bridge |
| `PRE,<fase>,<dur_s>\n` | Preempção | Vai para a fase indicada pela duração indicada. **`fase` ∈ `1..4`** |
| `CLR\n` | Liberar | Encerra a preempção, retoma o ciclo fixo |
| `CFG,<verde_s>,<amarelo_s>,<allred_s>\n` | Configurar | Ajusta os tempos do ciclo, em segundos |
| `ST?\n` | Consultar | Solicita telemetria imediata |
| `SAFE\n` | Parada segura | Força todos os acessos em vermelho |
| `TESTMODE,<0\|1>\n` | Modo de bancada | Entra ou sai do modo de teste |
| `TEST,<c1><c2><c3><c4>\n` | Acionamento direto | **Só em modo de teste.** `c` ∈ `R` `Y` `G` `-` (apagado) |

### O modo de teste

`TEST` existe para conferir fiação e gravar vídeo da bancada. Três regras o mantêm seguro:

1. **Fora do modo de teste é sempre recusado** — `NAK,TEST,MODO`.
2. **Em modo de teste, o ciclo fixo é suspenso e a preempção é recusada.** Os dois regimes nunca coexistem.
3. **A guarda de conflito continua ativa mesmo em modo de teste.** `TEST,GG--` recebe `NAK,TEST,CONFLITO`. O modo de teste libera combinações de cor — não libera violar I1.

O watchdog de 3 s vale também no modo de teste: se a comunicação cair, o Arduino sai dele e volta ao ciclo fixo sozinho.

### Respostas — Arduino → host

| Formato | Descrição |
| --- | --- |
| `ACK,<comando>\n` | Comando aceito |
| `NAK,<comando>,<motivo>\n` | Comando inválido ou não aplicável no estado atual |
| `ST,<ms>,<fase>,<s1><s2><s3><s4>,<preemp>,<teste>\n` | Telemetria completa, a 2 Hz |
| `EV,<ms>,<tipo>\n` | `WATCHDOG` · `TIMEOUT` · `PREEMP_INI` · `PREEMP_FIM` · `TESTE_INI` · `TESTE_FIM` · `CONFLITO_RECUSADO` |

**Motivos de `NAK`:** `FASE_INVALIDA` (fora de 1..4) · `CONFLITO` (violaria I1) · `MODO` (comando não permitido no regime atual) · `VERDE_MIN` (truncaria verde antes do mínimo) · `FORMATO`.

O campo `<teste>` (`0`/`1`) foi acrescentado ao fim da telemetria em P13. O parser de `bridge/protocolo.py` deve **tolerar sua ausência**, para não quebrar com firmware antigo gravado na placa.

Estados dos quatro semáforos: um caractere cada — `R`, `Y`, `G` — na ordem S1 S2 S3 S4.

```
RRGR  →  S3 verde, os outros três vermelhos   (fase 3 ativa)
RYRR  →  S2 em amarelo, transição em curso
RRRR  →  all-red
GRGR  →  INVÁLIDO — dois verdes. O firmware nunca produz isso,
         e recusa qualquer comando que levaria a esse estado.
```

### Sessão de exemplo — preempção para a fase 3, partindo da fase 1 em verde

```
host  -> PRE,3,20
uno   <- ACK,PRE
uno   <- EV,142350,PREEMP_INI
uno   <- ST,142350,1,YRRR,0,0      (fase 1 em amarelo)
uno   <- ST,142850,1,RRRR,0,0      (all-red, cruzamento limpo)
uno   <- ST,143350,3,RRGR,1,0      (preempção ativa na fase 3)
host  -> CLR
uno   <- ACK,CLR
uno   <- EV,156100,PREEMP_FIM
```

**Em nenhum instante há mais de um `G` na string de estado.** Essa é a verificação de I1 sobre a telemetria, e ela é automatizável — o relatório de validação conta as ocorrências de estados com dois ou mais verdes, e o resultado esperado é zero.

`<ms>` é o `millis()` do próprio Arduino, sem relação com o relógio do servidor. Serve para detectar reordenação e medir intervalos *dentro* do dispositivo. **A latência oficial é sempre medida no relógio do notebook.**

---

## §7 — Firmware do UNO

> **O sketch atual precisa ser reescrito.** O código do documento de protótipo usa `delay()` em sequência. O motivo é estrutural, não estético: **durante um `delay(5000)` o Arduino não lê a serial**, então é fisicamente impossível reagir a um comando de preempção. Um sketch bloqueante nunca atenderá ao RF02 (alterar semáforos em até 3 s da detecção).

### Máquina de estados não-bloqueante (`millis()`)

```
CICLO FIXO — 4 fases, autônomo, nunca depende da serial
 ┌───────────────────────────────────────────────────────────────────────┐
 │                                                                       │
 └▶ F1_VERDE ▶ F1_AMAR ▶ ALL_RED ▶ F2_VERDE ▶ F2_AMAR ▶ ALL_RED ▶ ... F4 ┘
     (3 s)      (2 s)     (1 s)     (3 s)      (2 s)     (1 s)      ciclo = 24 s

          │  PRE,<fase 1..4>,<dur_s>   — aceito em qualquer estado
          ▼
PREEMPÇÃO — único caminho comandado de fora
    PREEMP_TRANSICAO ─▶ PREEMP_ATIVA ─▶ PREEMP_LIBERANDO
    verde mín → Y → AR    verde alvo       Y → all-red
          ▲                                     │
          └── volta ao CICLO FIXO ◀─────────────┘
              CLR · timeout 30 s · watchdog 3 s

          │  TESTMODE,1
          ▼
TESTE — bancada; ciclo suspenso, preempção recusada, guarda de conflito ativa
    TESTE ──▶ volta ao CICLO FIXO por TESTMODE,0 ou watchdog 3 s
```

Os caminhos de saída — liberação normal, estouro de tempo, perda de comunicação e saída do modo de teste — voltam todos ao mesmo ciclo fixo.

**Implementar o ciclo como índice de fase + tabela de pinos, não como estados enumerados.** Com 4 fases a versão enumerada fica repetitiva, e a tabela permite mudar o número de fases sem reescrever a máquina:

```c
const uint8_t VERDE_DE[4] = {11, 8, 5, 2};      // pino G de cada fase
const uint8_t AMAR_DE[4]  = {12, 9, 6, 3};
const uint8_t VERM_DE[4]  = {13, 10, 7, 4};
```

### Requisitos obrigatórios

| # | Requisito | Por quê |
| --- | --- | --- |
| 1 | **Zero `delay()` no `loop()`** | Durante o delay a serial não é lida; RF02 fica impossível. Único uso aceitável: debounce de ms na inicialização |
| 2 | Leitura da serial a cada iteração, com buffer de linha e parser | Comandos chegam a qualquer momento |
| 3 | Transição sempre segura: verde mín → amarelo → all-red → alvo | Invariantes I2, I3, I4 |
| 4 | Watchdog `WATCHDOG_MS = 3000`: sem comando nem ping durante preempção → retoma ciclo fixo | Invariante I6. Cabo USB caindo não pode deixar verde travado |
| 5 | Timeout `PREEMP_MAX_MS = 30000`, mesmo sem `CLR` | Backend travado não bloqueia a transversal indefinidamente |
| 6 | Telemetria `ST` a 2 Hz | Alimenta dashboard e relatório de validação |
| 7 | **Sem `String` do Arduino** — só `char[]` de tamanho fixo | `String` fragmenta o heap de 2 KB do ATmega328P; o sketch trava depois de horas |
| 8 | **Guarda de conflito local (I1):** antes de acender qualquer verde, verificar que nenhum outro está verde — `contar_verdes() <= 1` | Defesa em profundidade. Vale inclusive em modo de teste |

> **O item 7 é o que trava apresentação.** Sketches com `String` costumam rodar bem por 15–20 min e travar depois. Por isso o checklist de aceitação (`context/06` §6, item 12) exige um teste de **30 minutos contínuos**, feito antes do dia da apresentação.

### Perfil de tempos da bancada

`backend/config/parametros.hardware.yaml` — reduzido para caber numa demonstração (definido em 2026-08-24):

```yaml
verde_s:     3.0    # duração do verde de cada fase no ciclo fixo
verde_min_s: 3.0    # piso de I4 — coincide com verde_s na bancada
amarelo_s:   2.0
all_red_s:   1.0
```

| Grandeza | Valor |
| --- | --- |
| Ciclo fixo completo (4 fases) | `4 × (3 + 2 + 1)` = **24 s** |
| Transição de preempção — pior caso | `3 + 2 + 1` = **6 s** |
| Transição de preempção — caso típico | ~4,5 s |

> **Consequência de `verde_s == verde_min_s`.** Na bancada a preempção **nunca trunca** um verde — ela aguarda o verde corrente terminar, o que leva no máximo 3 s. Isso simplifica o firmware (não há caminho de truncamento parcial a testar) e é mais fácil de explicar na banca. O caso de truncamento continua exercitado no perfil de simulação, onde `verde_min_s = 7.0` é menor que a duração base das fases.

> **Não alterar `parametros.yaml` (perfil de simulação) para "combinar" com o protótipo.** Os dados estatísticos vêm da simulação com tempos realistas.
>
> Se a banca perguntar se 3 s de verde não é perigoso: a bancada é um **modelo em escala para demonstração**; os valores com significado de engenharia de tráfego estão em `parametros.yaml`, que é o que produz os resultados do trabalho.

### Como a transição segura se parece no tempo

Cenário: fase 1 (S1) verde há 1 s quando chega `PRE,3,20` — o VE vem pela transversal, sentido A. Faltam 2 s para completar o verde de 3 s.

| t (s) | S1 | S2 | S3 | S4 | Telemetria | Etapa | Invariante |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 → 2 | `G` | `R` | `R` | `R` | `GRRR` | resto do verde da fase 1 (2 s de 3) | **I4** |
| 2 → 4 | `Y` | `R` | `R` | `R` | `YRRR` | amarelo (`AMARELO_S`) | **I2** |
| 4 → 5 | `R` | `R` | `R` | `R` | `RRRR` | all-red — cruzamento limpo | **I3** |
| 5 → … | `R` | `R` | `G` | `R` | `RRGR` | preempção ativa na fase 3, VE atravessa | **I1** |

```
t=0        t=2        t=4  t=5                              t=12
 │          │          │    │                                │
 S1  ██ verde ██│██ amarelo ██│██████████ vermelho ██████████
 S2  ████████████████ vermelho ████████████████████████████████
 S3  ██████████ vermelho ██████│█████████ verde ██████████████
 S4  ████████████████ vermelho ████████████████████████████████
                              ▲
                       ALL-RED: RRRR
```

**A coluna "Telemetria" nunca contém dois `G`.** São **5 s de transição** antes de o verde acender na fase alvo — o mesmo custo de antes, porque a transição não depende de quantas fases existem, só do verde mínimo pendente.

> ### ✅ Relação com o RF02 — **decidida em 2026-08-25 (P14)**
>
> Os 5 s de transição excederiam os 3 s do RF02 **se** o critério fosse medido
> até o *verde final*. A equipe adotou a leitura **"até o início da atuação"**: o
> amarelo já é a alteração do semáforo, e o marco é o `ACK` do Arduino — o mesmo
> instante que o §10 já define como `t_atuacao`. Nesse critério há folga
> confortável, e **nada muda** no perfil de tempos nem no ciclo de 24 s de P13.
>
> A alternativa faria o RF02 absorver o RF03 e embutir o verde mínimo (que é o
> invariante I4, não latência) no número. Registro completo, com a justificativa,
> em `context/09`; a definição do RF02 em `context/00` §6 passou a declarar o
> ponto final de medição explicitamente.

---

## §8 — Firmware do NodeMCU

| # | Requisito | Por quê |
| --- | --- | --- |
| 1 | Deduplicar: enviar só quando o UID mudar **ou** passarem `COOLDOWN_MS = 3000` do último envio do mesmo UID | O RC522 lê a mesma tag várias vezes por segundo; sem isso o backend é inundado |
| 2 | Contador `sequencia` monotônico, reiniciado no boot | Descarte de duplicatas e detecção de reordenação (anti-replay) |
| 3 | HTTP com timeout curto — `setTimeout(2000)` | Um POST pendurado congela o loop e o LCD para de atualizar |
| 4 | Reconexão Wi-Fi com backoff; enquanto desconectado, LCD mostra `SEM CONEXAO` | A rede vai cair na apresentação |
| 5 | `secrets.h` gerado por `firmware/gerar_secrets.py` a partir do `.env`, no `.gitignore` | Credencial de Wi-Fi hardcoded em sketch commitado é o erro mais comum em TCC de IoT |
| 6 | Descobrir o endereço I2C do LCD com I2C Scanner antes de fixar (`0x27` ou `0x3F`) | Varia por módulo. Rodar uma vez, anotar em comentário |
| 7 | Nenhum `delay()` no loop principal | Mesmo motivo do UNO |

### Contrato HTTP

```jsonc
// POST /api/v1/deteccoes — envio do NodeMCU
{
  "origem": "V2I_RFID",
  "uid_tag": "A3 4F 21 9C",
  "id_leitor": "LEITOR_CRUZ_01",
  "rssi": -47,
  "timestamp_dispositivo": 1234567,   // millis() do ESP, sem sincronia com o servidor
  "sequencia": 42                     // monotônico, reiniciado no boot
}

// Resposta
{
  "reconhecido": true,
  "id_veiculo": 3,
  "tipo": "AMBULANCIA",
  "acao": "PREEMPCAO_SOLICITADA",
  "id_log": 1187,
  "mensagem_lcd": "AMBULANCIA\nPRIORIDADE ATIVA"
}
```

Header obrigatório: `X-Device-Token`, validado contra `dispositivo_iot.token_hash`. UID ausente de `tag_rfid` ou com `ativo = false` → **HTTP 403** e registro da tentativa em `deteccao`.

**O firmware não decide o texto do LCD** — imprime o que vier em `mensagem_lcd`. Mantém a regra do §2 e permite mudar mensagens sem regravar o ESP.

### Mensagens do LCD — 16 colunas x 2 linhas

Contadas para caber exatamente em 16 caracteres:

```
Normal:       "SISTEMA ATIVO   "  /  "AGUARDANDO...   "
Ambulância:   "AMBULANCIA      "  /  "PRIORIDADE ATIVA"
Bombeiro:     "BOMBEIROS       "  /  "PRIORIDADE ATIVA"
Polícia:      "POLICIA         "  /  "PRIORIDADE ATIVA"
Liberado:     "VIA LIBERADA    "  /  "CICLO NORMAL    "
Não autoriz.: "TAG DESCONHECIDA"  /  "ACESSO NEGADO   "
Sem rede:     "SEM CONEXAO     "  /  "MODO LOCAL      "
```

---

## §9 — Invariantes de segurança

Não são requisitos negociáveis. Violação → **abortar a preempção e voltar ao ciclo fixo** (fail-safe), registrando o incidente. Implementação em `backend/core/seguranca.py` (I1–I5) e no firmware (I6).

| ID | Regra | Quem garante |
| --- | --- | --- |
| **I1** | Dois grupos de movimentos conflitantes nunca recebem verde simultâneo. No protótipo, sob *split phasing*: `contar_verdes() <= 1` | **Motor e firmware, independentemente** |
| **I2** | Nenhuma transição verde → vermelho sem amarelo intermediário de `AMARELO_S` | Firmware |
| **I3** | Toda troca de fase é precedida de `ALL_RED_S` com todos os acessos em vermelho | Firmware |
| **I4** | Nenhum verde é truncado antes de `VERDE_MIN` | Firmware |
| **I5** | Nenhum acesso em vermelho por mais de `VERMELHO_MAX_S = 120 s` (starvation) | Motor |
| **I6** | Falha de comunicação por mais de `WATCHDOG_S = 3 s` → firmware retoma o ciclo fixo autonomamente | **Firmware, sozinho** |

> **I6 é responsabilidade exclusiva do firmware.** O backend não pode garanti-la — se ele travar ou o cabo cair, ele não está lá para garantir nada. Por isso o Arduino precisa saber voltar sozinho.
>
> É também a demonstração mais forte e mais barata que temos (`context/05` §7, item 6): **puxar o cabo USB no meio de uma preempção e mostrar o sistema voltando ao ciclo fixo em menos de 3 s.**

Verificação automatizada: I1 por property-based testing (Hypothesis) sobre sequências aleatórias de comandos; I2/I3/I4 pela sequência de transições em `estado_semaforo_amostra`; I6 por teste manual cronometrado (checklist item 10).

---

## §10 — Onde a latência é medida

Havia conflito entre RNF01 (< 100 ms) e H3 (< 200 ms). **Decisão P2, 2026-08-24: são duas métricas diferentes e ambas ficam no texto.**

| Métrica | Intervalo | Meta | Onde |
| --- | --- | --- | --- |
| **Latência de decisão** · RNF01 | `t_deteccao` → `t_decisao`. Só `motor.avaliar()`, sem rede e sem I/O de banco. Medida com `perf_counter()` | < 100 ms (p95) | Simulação e hardware |
| **Latência fim-a-fim** · H3 | `t_deteccao` → `t_atuacao`. Inclui Wi-Fi, HTTP, serial e resposta do Arduino | < 200 ms (p95) | Sobretudo no protótipo |

Persistidas em `metrica_latencia`, com `id_correlacao` gerado na detecção e propagado até a atuação.

**`t_atuacao` é carimbado quando o `ACK` chega ao backend**, não quando o comando é enviado. Medir o envio mediria apenas a velocidade do próprio código.

Reportar **p95 e p99, não só a média**. Sistema crítico se avalia pela cauda: média de 68 ms com p99 de 400 ms não atende ao requisito.

> **Risco a observar cedo.** Os 200 ms fim-a-fim são apertados para o caminho físico: Wi-Fi do ESP8266 + HTTP + processamento + serial 115200 + resposta do Arduino. Medir isso no primeiro dia em que o fluxo completo funcionar, não perto da entrega. Se estourar, ainda dá tempo de otimizar (por exemplo, emitir o `ACK` antes de iniciar a transição em vez de depois) ou de ajustar a hipótese com honestidade.

---

## §11 — Rede do protótipo

```
[NodeMCU ESP8266] --Wi-Fi 2,4GHz--> [Roteador] <--> [Notebook]
                                                      ├── backend  :8000
                                                      ├── postgres :5432
                                                      ├── frontend :5173
                                                      └── bridge --USB--> [Arduino UNO]
```

- **O ESP8266 é 2,4 GHz apenas.** Não conecta em rede 5 GHz. Se o roteador for dual-band com mesmo SSID, criar SSID separado.
- **Roteador próprio ou hotspot do notebook**, não a rede da faculdade — costuma bloquear tráfego entre clientes.
- **IP do backend fixo** do ponto de vista do ESP: reserva de DHCP por MAC, ou IP estático no sketch.
- Anti-replay: campo `sequencia` monotônico + janela de deduplicação de 2 s por UID no backend.

---

## §12 — Pendências que dependem da bancada

Não podem ser resolvidas por software. Precisam de teste físico, **antes** de gravar o firmware definitivo.

### ✅ P10 — Resistores nos LEDs · RESOLVIDA em 2026-08-24

A equipe de hardware confirmou: **os módulos semáforo já trazem resistores integrados.** Nenhum resistor externo é necessário.

Verificação de corrente com essa informação: cada módulo acende **um LED por vez**, e sob *split phasing* o pior caso é ainda mais folgado — no máximo um verde, os outros três em vermelho, ou seja 4 LEDs simultâneos a ~20 mA cada, **~80 mA no total**. Confortavelmente abaixo dos 200 mA do ATmega328P e dos 40 mA por pino.

**Sem restrição elétrica para operação prolongada.** O teste de 30 min do checklist pode ser feito sem ressalva.

### P8 — GPIO 0 no RST do RC522 · pode impedir o boot

O RST do RC522 está em `D3` = **GPIO 0**, pino de boot do ESP8266. Se estiver em nível baixo durante o reset, o NodeMCU entra em modo de gravação em vez de executar o sketch.

**Teste:** ligar o NodeMCU com o RC522 conectado e confirmar boot normal. Se falhar, remanejar RST para `D0` (GPIO 16) e atualizar `context/05` §1 e este arquivo §5.

### P9 — LCD I2C em 5 V com GPIO de 3,3 V · fora de especificação

O módulo I2C do LCD alimentado em 5 V tem pull-ups para 5 V em SDA/SCL, e os GPIOs do ESP8266 são de 3,3 V e **não são 5 V-tolerantes**. Na prática costuma funcionar, mas está fora de especificação.

Duas saídas seguras: **(a)** alimentar o LCD em 3,3 V — contraste mais fraco, barramento correto; **(b)** conversor de nível bidirecional. Caracteres corrompidos intermitentes são o sintoma. Escolher uma e documentar no TCC.

**Status em 2026-08-24:** a equipe vai testar o display assim que as peças chegarem. Se a opção (b) for a escolhida, o conversor de nível precisa ser comprado junto — vale verificar agora, para não descobrir depois que falta a peça.

### Também pendente

**UIDs reais das tags RFID.** Assim que o RC522 estiver lendo, os UIDs entram em `db/seeds/` — hoje estão como placeholder. Normalizados: maiúsculas, sem espaços.

---

## §13 — Decisões já fechadas

Sete pendências resolvidas em 2026-08-24, registradas com justificativa em `context/09-pendencias-e-decisoes.md`:

| Item | Decisão |
| --- | --- |
| **P1** meta de redução | H1 passa a ser **≥ 25% em saturação moderada e intensa**. Cenário leve medido e discutido, sem meta — a Tabela 1 do pré-projeto já mostrava 8,3% ali |
| **P2** latência | Duas métricas distintas, ambas mantidas — §10 |
| **P3** o que é a "IA" | **Agente reativo com otimização determinística baseada em conhecimento** (Russell & Norvig, já na bibliografia). ML como trabalho futuro explícito. **Falta comunicar ao orientador** |
| **P5** volume de dados | Banco grava só **transições de fase**, e só de execuções exemplares. 173 M de linhas → centenas de milhares |
| **P7** o radar inexistente | Declarar no texto que o **RFID emula** radar + V2I; fusão de sensores validada só em simulação. Sem sensor adicional |
| **P10** resistores nos LEDs | **Módulos já têm resistores integrados.** Pior caso ~80 mA para 4 LEDs. Sem restrição elétrica — §12 |
| **P13** conjunto de fases | Protótipo é **um cruzamento de 4 aproximações em *split phasing*** — 4 fases, um verde por vez. `PRE` aceita `1..4`; acrescentados `TESTMODE` e `TEST`; matriz de conflito no motor **e** no firmware — §5, §6, §7 |

| **P14** ponto final do RF02 | Mede da detecção **até o início da atuação** — o amarelo já é a alteração, marcada pelo `ACK`. Medir até o verde final faria o RF02 absorver o RF03 e embutir o verde mínimo (invariante I4) no número. Perfil de tempos e ciclo de 24 s **inalterados** — §7 |

Continuam abertas: **P4, P6, P11, P12** (redação do texto do TCC) e **P8, P9** (§12).

---

## §14 — Plano de desenvolvimento

Detalhado em [`docs/plano-desenvolvimento.md`](plano-desenvolvimento.md).

| Bloco | Entrega | Prazo |
| --- | --- | --- |
| 0 | Fundação — git, Docker, toolchain, **instalar SUMO** | ~3 dias · ✅ concluído |
| 1 | Banco de dados — migrations, models, seeds | ~1 semana · ✅ concluído |
| 2 | **Motor de decisão** + invariantes — núcleo do TCC | ~2 semanas · ✅ concluído |
| 3 | Malha SUMO + adaptador TraCI | ~2 semanas |
| 4 | **Piloto de 5 seeds** — descobrir cedo se as hipóteses se sustentam | ~3 dias |
| 5 | **Camada IoT** — protocolo, bridge, firmware UNO e NodeMCU, P8 e P9 | ~2 semanas |
| 6 | API REST + WebSocket | ~1 semana |
| 7 | Dashboard React | ~2 semanas |
| 8 | Lote completo — 600 execuções | ~1 semana + máquina |
| 9 | Análise estatística, tabelas, figuras, diagramas | ~2 semanas |

O Bloco 4 está deslocado de propósito: o maior risco do projeto é descobrir na última semana que os resultados reais não sustentam as hipóteses. Rodar 5 seeds cedo custa três dias e elimina esse risco.

**Desenvolvimento em paralelo sem bancada.** Enquanto o firmware não existe, o backend é desenvolvido contra `adapters/hardware/simulado.py` — um dublê que responde ao protocolo do §6 em memória, com latências artificiais. Sem ele ninguém consegue trabalhar quando o protótipo não está disponível, e num trabalho em trio isso é a regra, não a exceção.

---

## §15 — O que precisa ser confirmado

Fechados na rodada de 2026-08-24: pinagem confirmada, P10 resolvida, e o conjunto de fases definido (P13). Restam:

| # | Item | Responsável | Status |
| --- | --- | --- | --- |
| 1 | **P9** — testar o LCD quando as peças chegarem, e escolher entre 3,3 V ou conversor de nível | Hardware | aguardando peças |
| 2 | **P8** — testar boot do NodeMCU com o RC522 conectado (GPIO 0) | Hardware | pendente |
| 3 | ~~Tempos de bancada~~ | Equipe | ✅ **fechado 24/08** — verde 3 s, ciclo de 24 s |
| 4 | O **protocolo do §6** atende — falta algum comando ou telemetria? | Equipe | pendente |
| 5 | ~~Ponto final de medição do RF02~~ | Equipe | ✅ **fechado 25/08** — P14: mede até o **início da atuação**; perfil de tempos inalterado |
| 6 | Divisão: quem reescreve o firmware do UNO, quem faz o NodeMCU | Equipe | pendente |
| 7 | **UIDs reais das tags**, para os seeds | Hardware | assim que o RC522 ler |
| 8 | Decisão **P3** comunicada ao Prof. Marco Gomes | Equipe | pendente |

---

**Regra de manutenção.** Quando uma decisão deste arquivo mudar, o arquivo correspondente em `context/` muda **no mesmo commit** (`context/08` §4.7). Contexto desatualizado é pior que contexto ausente, porque induz ao erro com confiança.
