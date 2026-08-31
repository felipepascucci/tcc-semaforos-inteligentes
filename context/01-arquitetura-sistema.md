# 01 — Arquitetura do Sistema

## 1. Princípio arquitetural central

O **motor de decisão é único e agnóstico ao mundo**. Ele recebe um estado normalizado e devolve comandos abstratos. Quem traduz comando abstrato em ação concreta é um *adaptador*.

```
                    ┌─────────────────────────────────┐
   Detecções  ───▶  │      MOTOR DE DECISÃO           │  ───▶  Comandos
   (evento)         │  backend/core/priorizacao/      │        (abstratos)
                    │  puro, síncrono, sem I/O        │
                    └─────────────────────────────────┘
                              ▲             │
                              │             ▼
                    ┌─────────┴─────────────────────────┐
                    │           ADAPTADORES             │
                    ├───────────────────┬───────────────┤
                    │  AdaptadorSUMO    │ AdaptadorHW   │
                    │  (TraCI)          │ (serial/MQTT) │
                    └───────────────────┴───────────────┘
```

**Consequência prática obrigatória:** nada dentro de `backend/core/priorizacao/` pode importar `traci`, `pyserial`, `sqlalchemy` ou `fastapi`. Se precisar, o desenho está errado. O núcleo é testável com `pytest` puro, sem SUMO instalado e sem hardware ligado.

## 2. Componentes

| # | Componente | Stack | Responsabilidade |
| --- | --- | --- | --- |
| C1 | **Motor de decisão** | Python puro | Detectar, decidir preempção, planejar corredor, compensar |
| C2 | **API / Orquestrador** | FastAPI + Uvicorn | REST + WebSocket, persistência, coordenação dos adaptadores |
| C3 | **Adaptador SUMO** | Python + TraCI | Loop de simulação, leitura de estado, aplicação de fases |
| C4 | **Adaptador Hardware** | Python + pyserial | Traduz comandos para o protocolo serial do Arduino |
| C5 | **Firmware controlador** | C++ / Arduino UNO R3 | Máquina de estados dos 4 semáforos, executa comandos |
| C6 | **Firmware V2I** | C++ / NodeMCU ESP8266 | Lê tag RFID, publica detecção via Wi-Fi, atualiza LCD |
| C7 | **Banco de dados** | PostgreSQL 16 | Persistência de cadastros, logs e métricas |
| C8 | **Dashboard** | React + Vite + TS | Monitoramento em tempo real e relatórios |
| C9 | **Pipeline de análise** | Python (pandas, scipy) | Estatística, tabelas e figuras do TCC |

## 3. Fluxo end-to-end — modo SIMULAÇÃO

```
SUMO (passo t)
  │ traci.simulationStep()
  ▼
AdaptadorSUMO coleta EstadoMalha
  │  - posição/velocidade de todos os veículos
  │  - VEs ativos e suas rotas
  │  - fase atual e tempo decorrido de cada TLS
  ▼
MotorDecisao.avaliar(EstadoMalha) -> list[Comando]
  │  (mede t_decisao; deve ser < 100 ms — RNF01)
  ▼
AdaptadorSUMO aplica os comandos via traci.trafficlight.setPhase()
  ▼
Persistência assíncrona: log_prioridade, estado_semaforo_amostra
  ▼
Broadcast WebSocket -> Dashboard
```

O loop roda com `--step-length 0.1` (100 ms de tempo simulado por passo). O motor é chamado **a cada passo**.

## 4. Fluxo end-to-end — modo HARDWARE

```
Tag RFID aproxima do leitor RC522
  ▼
NodeMCU lê UID -> POST /api/v1/deteccoes  (Wi-Fi)   [t_deteccao]
  ▼
API resolve UID -> veiculo_emergencia (tabela tag_rfid)
  ▼
MotorDecisao.avaliar(...) -> Comando(PREEMPTAR, tls=CRUZ_01, fase=EIXO_A)  [t_decisao]
  ▼
AdaptadorHardware -> serial USB -> "PRE,1,20\n"
  ▼
Arduino UNO executa transição segura e responde "ACK,PRE"  [t_atuacao]
  ▼
API grava log_prioridade + envia texto ao LCD do NodeMCU
  ▼
Broadcast WebSocket -> Dashboard
```

### 4.1 Por que a ponte serial existe

O Arduino UNO R3 **não tem rede**. O NodeMCU tem Wi-Fi mas está do lado do "veículo". Ligar os dois diretamente (serial cruzado, ou ESP como ponte) foi descartado porque:

- perderíamos o ponto de instrumentação de latência no backend;
- o motor de decisão precisa rodar em um único lugar (§1);
- o dashboard precisa ver os dois lados.

Então: **NodeMCU → Wi-Fi → Backend → USB serial → Arduino UNO**. O notebook que roda o backend faz o papel do "controlador de borda" (Edge). Isso é coerente com a narrativa de Edge Computing do pré-projeto e deve ser dito assim no texto: o nó de borda é o processo `bridge`, colocado fisicamente junto ao cruzamento.

## 5. O algoritmo de priorização

> Este é o núcleo do TCC. Implementar em `backend/core/priorizacao/motor.py`.

### 5.1 Estruturas de entrada

```python
@dataclass(frozen=True)
class VeiculoEmergencia:
    id: str
    tipo: TipoVeiculo          # AMBULANCIA | BOMBEIRO | POLICIA
    posicao: tuple[float, float]
    velocidade: float          # m/s
    rota: tuple[str, ...]      # ids de vias, em ordem
    indice_via_atual: int
    posicao_na_via_m: float    # já percorrido dentro da via atual

@dataclass(frozen=True)
class EstadoSemaforo:
    id: str
    fase_atual: int
    tempo_na_fase: float       # s
    fila_por_acesso: Mapping[str, int]
    em_preempcao: bool
    sinal: Sinal               # VERDE | AMARELO | VERMELHO (all-red)

@dataclass(frozen=True)
class EstadoMalha:
    t: float                   # s de simulação ou epoch
    semaforos: Mapping[str, EstadoSemaforo]
    veiculos_emergencia: Sequence[VeiculoEmergencia]
    densidade_por_via: Mapping[str, float]
```

> **Três ajustes de forma, feitos no Bloco 2** (2026-08-24). Nenhum muda o
> significado dos campos; a implementação em `backend/core/modelos.py` é a
> referência.
>
> 1. **Contêineres imutáveis** — `tuple`/`Mapping` no lugar de `list`/`dict`.
>    `frozen=True` só impede reatribuir o atributo: a lista e o dicionário
>    continuavam mutáveis por dentro, e a razão declarada em `08` §3 para exigir
>    estado imutável (evitar bug de concorrência entre o loop de simulação e o
>    broadcast do WebSocket) ficava sem efeito.
> 2. **`posicao_na_via_m`** — campo novo. Sem ele, a distância ao longo da rota
>    (E1) teria resolução de via inteira, e o critério de aceitação do RF01 é
>    justamente distinguir 480 m de 520 m (`06` §2). O TraCI fornece o valor por
>    `traci.vehicle.getLanePosition()`.
> 3. **`sinal`** — campo novo em `EstadoSemaforo`. E3 e E5 precisam saber se a
>    fase corrente está em verde, amarelo ou all-red para calcular o verde mínimo
>    residual; sem isso o motor não tem como respeitar I4.
>
> A topologia estática (fases, matriz de conflito, comprimento das vias) **não**
> está nestas estruturas: ela vive em `core/malha.py` e é injetada no motor na
> construção. Estado é o que muda a cada passo; topologia é configuração.

### 5.2 Etapas

**E1 — Detecção (RF01).** Para cada VE, listar os TLS cuja distância *ao longo da rota* (não euclidiana) seja ≤ `RAIO_DETECCAO` (500 m). Usar distância de rota evita priorizar um cruzamento que está perto no mapa mas que o VE não vai atravessar. Este é um erro clássico — não usar `math.dist`.

**E2 — ETA por cruzamento.** `eta_i = distancia_rota_i / max(v_atual, V_MIN_ESTIMATIVA)`, com `V_MIN_ESTIMATIVA = 4.0 m/s` para não explodir quando o VE está parado. Guardar o ETA: ele define *quando* preemptar, não apenas *se*.

**E3 — Janela de ativação.** Só preempta quando `eta_i <= TEMPO_ANTECIPACAO`, com `TEMPO_ANTECIPACAO = tempo_transicao_segura(tls) + MARGEM` (`MARGEM = 5 s`). Preemptar cedo demais trava a transversal sem necessidade — é exatamente o custo que H2 quer minimizar.

> **`MARGEM` fixa é a causa provável de P16** (piloto do Bloco 4, 2026-08-26): em
> regime saturado o corredor abre a tempo mas não **esvazia** a tempo, e o VE
> chega ao verde com veículos parados adiante — 2,76 paradas residuais no
> `intenso` contra 0,76 no `moderado`. A margem não consulta a fila, que o motor
> já recebe em `EstadoSemaforo.fila_por_acesso`. **Decisão de 2026-08-31: corrigir
> o mecanismo antes de mexer em H1.** A alteração veio com critério declarado
> antes do ajuste, e a calibração roda em seeds fora de 1..50 (ver P16).
>
> **A fórmula em vigor desde 2026-08-31**, com o teto derivado de
> `preempcao_timeout_s` (não é parâmetro novo — antecipar mais do que a preempção
> sobrevive derrubaria o corredor no rosto do VE):
>
> ```
> TEMPO_ANTECIPACAO = min( AMARELO + ALL_RED + verde_min_residual + MARGEM
>                            + fila_por_faixa * HEADWAY_SATURACAO,
>                          PREEMPCAO_TIMEOUT - (AMARELO + ALL_RED) )
> ```
>
> `HEADWAY_SATURACAO` (2,13 s) é **medido** em
> `analysis/data/fluxo_saturacao.csv`, não adotado de manual — mesma regra do
> fluxo de saturação em P11. `fila_por_faixa` divide a fila do acesso, que os
> detectores E2 entregam somada, pelo número de faixas da via. A correção **não
> introduz parâmetro livre**, e é esse o argumento de defesa dela.

**E4 — Seleção da fase.** Dado o movimento do VE (via de entrada → via de saída), consultar o mapa `movimento → fase` do cruzamento e escolher a fase que o serve. Esse mapa é configuração estática, carregada de `sim/config/mapa_fases.yaml` e da tabela `fase_semaforo`.

**E5 — Transição segura.** Nunca saltar direto para a fase alvo. Sequência obrigatória:

```
se fase_atual == fase_alvo:
    estender verde até min(tempo_restante_necessario, VERDE_MAX)
senão:
    aguardar MIN_GREEN residual   (se tempo_na_fase < MIN_GREEN)
    -> AMARELO   (AMARELO_S)
    -> ALL_RED   (ALL_RED_S)
    -> fase_alvo (verde)
```

**E6 — Manutenção e liberação.** Manter a fase até o VE cruzar a linha de retenção, com timeout de segurança `PREEMPCAO_TIMEOUT_S = 45`. Ao liberar, registrar em `log_prioridade` com `status_execucao`.

**E7 — Compensação pós-evento (H2).** Após a liberação, por `N_CICLOS_COMPENSACAO = 2` ciclos, redistribuir o verde proporcionalmente à fila acumulada de cada acesso, respeitando `VERDE_MIN` e `VERDE_MAX`:

```
verde_i = clamp(VERDE_BASE_i + K * (fila_i / soma_filas) * DEFICIT_TOTAL, VERDE_MIN, VERDE_MAX)
```

onde `DEFICIT_TOTAL` é o tempo de verde que o acesso deixou de receber durante a preempção, e `K` é o ganho de compensação (parâmetro do experimento, começar em `K = 0.7`).

> **"Começar em `K = 0.7`" foi onde parou, e é P17.** O piloto do Bloco 4 mede uma
> mitigação entre −1,0% e +0,6% contra a meta de H2 — `K` e
> `N_CICLOS_COMPENSACAO` nunca foram calibrados contra dado real. **Antes de
> calibrar, verificar se a métrica não está diluindo o efeito:**
> `tempo_espera_medio_transversal_s` é a média sobre a hora inteira, e a
> compensação atua por ~140 s depois de cada evento, com um VE a cada 10 min.
> Calibrar contra uma métrica que dilui é calibrar contra ruído.

**E8 — Conflito entre múltiplos VEs.** Cenário obrigatório de teste. Regra de desempate, em ordem:

1. Maior prioridade por tipo — configurável, padrão: `AMBULANCIA > BOMBEIRO > POLICIA`.
2. Menor ETA ao cruzamento.
3. Preempção já em curso vence (evita oscilação/thrashing).

Se dois VEs demandam fases conflitantes no mesmo TLS, **um espera**. Nunca conceder as duas. Registrar em `log_prioridade` com `status_execucao = 'CONFLITO_ADIADO'`.

### 5.3 Parâmetros (arquivo `backend/config/parametros.yaml`)

Todo número mágico do algoritmo vive aqui, nunca no código:

```yaml
raio_deteccao_m: 500
tempo_antecipacao_margem_s: 5.0
verde_min_s: 7.0
verde_max_s: 60.0
amarelo_s: 3.0
all_red_s: 2.0
preempcao_timeout_s: 45.0
n_ciclos_compensacao: 2
ganho_compensacao_k: 0.7
velocidade_min_estimativa_ms: 4.0
prioridade_tipo: [AMBULANCIA, BOMBEIRO, POLICIA]
```

> No protótipo físico os tempos são reduzidos para caber numa demonstração de bancada. Perfil separado em `parametros.hardware.yaml` (decisão de 2026-08-24, após P13):
>
> ```yaml
> verde_s:     3.0    # duração do verde de cada fase no ciclo fixo
> verde_min_s: 3.0    # piso de I4 — coincide com verde_s na bancada
> amarelo_s:   2.0
> all_red_s:   1.0
> ```
>
> Com 4 fases, o ciclo completo passa a levar `4 × (3 + 2 + 1)` = **24 s**.
>
> **Consequência de `verde_s == verde_min_s`:** na bancada a preempção **nunca trunca** um verde — ela sempre aguarda o verde corrente terminar, o que leva no máximo 3 s. Isso simplifica o firmware e é mais fácil de explicar na banca do que um truncamento parcial. O caso de truncamento continua exercitado e testado no perfil de simulação, onde `verde_min_s = 7.0` é menor que a duração base das fases.
>
> **Não altere o perfil de simulação para "combinar" com o protótipo** — os dados estatísticos vêm da simulação com tempos realistas. Se a banca perguntar se 3 s de verde não é perigoso: a bancada é um modelo em escala para demonstração; os valores com significado de engenharia de tráfego estão em `parametros.yaml`, que é o que produz os resultados.

## 6. Invariantes de segurança (NUNCA violar)

Implementar como asserções verificadas a cada passo, em `backend/core/seguranca.py`. Se violada, a ação é **abortar a preempção e retornar ao ciclo fixo** (fail-safe), registrando o incidente.

1. **I1** — Dois grupos de movimentos conflitantes nunca recebem verde simultâneo. A matriz de conflito é **aplicada duas vezes, de forma independente** (decisão P13): o motor não emite comando conflitante, e o firmware recusa com `NAK,<cmd>,CONFLITO` caso receba um. Defesa em profundidade — a segurança não pode depender da serial estar íntegra nem de o backend estar correto. No protótipo, sob *split phasing*, I1 se reduz a `contar_verdes() <= 1`.
2. **I2** — Nenhuma transição verde → vermelho sem amarelo intermediário de `AMARELO_S`.
3. **I3** — Todo troca de fase é precedida de `ALL_RED_S` com todos os acessos em vermelho.
4. **I4** — Nenhum verde é truncado antes de `VERDE_MIN`.
5. **I5** — Nenhum acesso permanece em vermelho por mais de `VERMELHO_MAX_S = 120 s` (starvation).
6. **I6** — Falha de comunicação com o atuador por mais de `WATCHDOG_S = 3 s` → o firmware retoma o ciclo fixo autonomamente.

I6 é responsabilidade do firmware, não do backend. Se o cabo USB cair, o Arduino não pode congelar com um verde aceso.

## 7. Contratos de API

Base: `/api/v1`. Documentação automática em `/docs` (FastAPI).

### REST

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/deteccoes` | Recebe detecção do NodeMCU (V2I) |
| `GET` | `/semaforos` | Lista semáforos e estado atual |
| `GET` | `/semaforos/{id}` | Detalhe + histórico recente |
| `POST` | `/semaforos/{id}/preempcao` | Preempção manual (operador / teste) |
| `DELETE` | `/semaforos/{id}/preempcao` | Cancela preempção ativa |
| `GET` | `/veiculos` | Cadastro de VEs |
| `POST` | `/veiculos` | Cadastra VE + tag |
| `GET` | `/logs/prioridade` | Logs paginados, com filtros |
| `POST` | `/simulacoes` | Dispara execução de cenário |
| `GET` | `/simulacoes/{id}` | Status e métricas da execução |
| `GET` | `/metricas/resumo` | Agregados para o dashboard |
| `GET` | `/health` | Liveness/readiness |

**`POST /deteccoes` — payload:**

```json
{
  "origem": "V2I_RFID",
  "uid_tag": "A3 4F 21 9C",
  "id_leitor": "LEITOR_CRUZ_01",
  "rssi": -47,
  "timestamp_dispositivo": 1234567,
  "sequencia": 42
}
```

**Resposta:**

```json
{
  "reconhecido": true,
  "id_veiculo": 3,
  "tipo": "AMBULANCIA",
  "acao": "PREEMPCAO_SOLICITADA",
  "id_log": 1187,
  "mensagem_lcd": "AMBULANCIA\nPRIORIDADE ATIVA"
}
```

`timestamp_dispositivo` é `millis()` do ESP8266 — sem sincronia com o relógio do servidor. Serve apenas para detectar reordenação e para calcular *deltas* dentro do dispositivo. **A latência oficial é medida com o relógio do servidor.** `sequencia` é um contador monotônico para descartar duplicatas (o RC522 lê a mesma tag várias vezes por segundo).

### WebSocket

`ws://host/api/v1/stream` — o servidor empurra:

```json
{ "tipo": "estado_semaforo", "dados": { "id": "CRUZ_01", "fase": 2, "estado": "VERDE", "em_preempcao": true } }
{ "tipo": "posicao_ve",      "dados": { "id_veiculo": 3, "lat": -23.55, "lon": -46.63, "velocidade": 11.2 } }
{ "tipo": "evento",          "dados": { "nivel": "INFO", "texto": "Preempção iniciada em CRUZ_01" } }
{ "tipo": "metrica",         "dados": { "latencia_ms": 68, "priorizacoes_ativas": 1 } }
```

Throttle de 5 Hz no broadcast. Sem isso, uma simulação a 10 passos/s satura o navegador.

## 8. Estrutura de diretórios do backend

```
backend/
├── app/
│   ├── main.py                 # FastAPI app, lifespan, CORS
│   ├── api/v1/
│   │   ├── deteccoes.py
│   │   ├── semaforos.py
│   │   ├── veiculos.py
│   │   ├── simulacoes.py
│   │   ├── metricas.py
│   │   └── ws.py
│   ├── models/                 # SQLAlchemy ORM
│   ├── schemas/                # Pydantic v2
│   ├── repositories/           # acesso a dados
│   └── services/               # orquestração (usa core + repositories)
├── core/                       # ⚠️ SEM I/O, SEM FRAMEWORK
│   ├── priorizacao/
│   │   ├── motor.py            # avaliar() -> list[Comando]
│   │   ├── deteccao.py         # E1, E2, E3
│   │   ├── fases.py            # E4, E5
│   │   ├── compensacao.py      # E7
│   │   └── conflito.py         # E8
│   ├── seguranca.py            # invariantes I1..I5
│   ├── modelos.py              # dataclasses de estado
│   └── comandos.py             # tipos de comando abstratos
├── adapters/
│   ├── sumo/
│   └── hardware/
├── config/
│   ├── parametros.yaml
│   └── parametros.hardware.yaml
└── tests/
```

## 9. Comandos abstratos

```python
class TipoComando(StrEnum):
    ESTENDER_VERDE   = "ESTENDER_VERDE"
    IR_PARA_FASE     = "IR_PARA_FASE"
    LIBERAR          = "LIBERAR"
    COMPENSAR        = "COMPENSAR"
    FALLBACK_SEGURO  = "FALLBACK_SEGURO"

@dataclass(frozen=True)
class Comando:
    tipo: TipoComando
    id_semaforo: str
    fase_alvo: int | None = None
    duracao_s: float | None = None
    id_veiculo: str | None = None
    motivo: str = ""
```

`motivo` é obrigatório na prática: é o que aparece no dashboard e no relatório de validação, e é o que permite explicar na banca *por que* o sistema tomou cada decisão. Um log de decisão sem justificativa não sustenta uma defesa.
