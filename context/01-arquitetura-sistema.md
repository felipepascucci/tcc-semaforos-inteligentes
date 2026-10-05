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

> **Desde 2026-10-05 o lado hardware não recebe comandos do motor.** O protótipo
> decide localmente no Arduino UNO (§4), e `adapters/hardware/` passou a só
> **observar** a bancada. O princípio deste parágrafo continua valendo para o
> motor e para a simulação, que é onde ele é avaliado (`00` §3).

**Consequência prática obrigatória:** nada dentro de `backend/core/priorizacao/` pode importar `traci`, `pyserial`, `sqlalchemy` ou `fastapi`. Se precisar, o desenho está errado. O núcleo é testável com `pytest` puro, sem SUMO instalado e sem hardware ligado.

## 2. Componentes

| # | Componente | Stack | Responsabilidade |
| --- | --- | --- | --- |
| C1 | **Motor de decisão** | Python puro | Detectar, decidir preempção, planejar corredor, compensar |
| C2 | **API / Orquestrador** | FastAPI + Uvicorn | REST + WebSocket, persistência, coordenação dos adaptadores |
| C3 | **Adaptador SUMO** | Python + TraCI | Loop de simulação, leitura de estado, aplicação de fases |
| C4 | **Ponte / Adaptador Hardware** | Python + pyserial | **Só escuta** a telemetria e os eventos do UNO, carimba no relógio do notebook, mede H3 e injeta VEs em teste (`05` §6) |
| C5 | **Firmware controlador** | C++ / Arduino UNO R3 | Decide a preempção (regra local, `05` §3), máquina de estados dos 4 semáforos com transição segura, LCD |
| C6 | **Firmware V2I** | C++ / 2 × NodeMCU ESP8266 | Emissor no veículo: lê a tag da rua e envia por ESP-NOW. Receptor no cruzamento: repassa ao UNO pela serial |
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
  │  - VEs ativos e suas rotas — só os EM SERVIÇO: vClass de emergência
  │    E parâmetro `criticidade` na rota gerada (P20)
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

Arquitetura **da bancada como está montada** (decisão de 2026-10-05). Detalhes,
pinagem e protocolo em `05`.

```
Veículo passa sobre a tag da rua (RUA1..RUA4)
  ▼
NodeMCU emissor lê o UID, resolve a rua e envia { rua, veiculo } por ESP-NOW
  │  imprime "Tag <UID> lida -> Enviando RUAn" na própria serial   [t_deteccao, só na medição de H3]
  ▼
NodeMCU receptor repassa "RUA3,AMBULANCIA" ao RX do UNO (9600)
  ▼
Arduino UNO DECIDE (prioridade por tipo, fila de 1) e emite "EV,…,PREEMP_INI,3,AMBULANCIA"  [t_atuacao]
  ▼
UNO executa a transição segura até o verde exclusivo da Rua 3 e atualiza o LCD
  ▼
bridge/ (só escuta, pelo USB; expõe GET /estado)
  ▲
  │ o backend LÊ /estado a 5 Hz (decisão de 2026-10-05, Bloco 6)
backend: log_prioridade (um registro por decisão do UNO), metrica_latencia (amostras de H3)
  ▼
Broadcast WebSocket -> Dashboard
```

> **Bloco 6 (2026-10-05).** A ponte continua sem saber que o backend existe: é
> ele que consulta `GET /estado` (`app/services/bancada.py`). Os eventos do UNO
> não passam por `core/autorizacao`, porque o UNO já decidiu, e o backend só
> **registra**. Cada evento de decisão (`PREEMP_INI`, `RENOVADO`, `FILA`,
> `DESCARTADO`) vira uma linha em `log_prioridade` no `PROTO_CRUZ_01`, com
> `id_correlacao` próprio. A aproximação (S1..S4) vai em `motivo`, e
> `fase_aplicada` fica nula. As amostras de H3 vão para `metrica_latencia` com
> `t_decisao` nulo, ligadas ao `PREEMP_INI` pelo carimbo. A tabela de tradução
> evento → status está no docstring do módulo.

### 4.1 Por que o NodeMCU fala direto com o UNO

A versão anterior deste parágrafo descartava ligar o ESP direto ao Arduino. Era
o desenho de um protótipo que ainda não existia. A bancada foi montada assim, e
a equipe decidiu adaptar o sistema a ela em vez de remontá-la. Os três motivos
da recusa original, revistos:

- **Ponto de instrumentação de latência.** Resolvido sem backend: o notebook
  ouve as duas pontas (a serial do emissor e a do UNO) e carimba as duas no
  mesmo relógio (`05` §4.3). Perde-se o `t_decisao` separado, que não é
  observável dentro do UNO; RNF01 continua medido na simulação.
- **Motor num lugar só.** Não se aplica mais: o protótipo não roda o motor
  (`00` §3). O texto precisa dizer isso explicitamente.
- **Dashboard vendo os dois lados.** Atendido pela ponte, que ouve o UNO.

O ganho para o texto é que **a borda é o próprio controlador do cruzamento**: a
decisão crítica acontece no cruzamento, sem rede e sem notebook. Se a ponte
cair, o cruzamento continua preemptando.

## 5. O algoritmo de priorização

> Este é o núcleo do TCC. Implementar em `backend/core/priorizacao/motor.py`.

### 5.1 Estruturas de entrada

```python
class Criticidade(IntEnum):    # P20 — menor = mais crítico
    RISCO_VIDA = 1
    RISCO_COLETIVO = 2
    URGENCIA = 3

@dataclass(frozen=True)
class VeiculoEmergencia:
    id: str
    tipo: TipoVeiculo          # AMBULANCIA | BOMBEIRO | POLICIA
    criticidade: Criticidade   # da ocorrência ativa (P20) — obrigatório
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

> **`criticidade` — campo novo, P20 (2026-09-29).** Vem da ocorrência ativa do
> VE, e é **obrigatório**: um valor padrão daria prioridade silenciosa a quem não
> a declarou. Um VE só chega a `EstadoMalha` se estiver **em serviço**, e quem
> garante isso é quem monta o estado, não o motor:
>
> - **hardware** — o serviço de `/deteccoes` chama `core/autorizacao.autorizar()`,
>   função pura que exige tag reconhecida, veículo ativo **e** ocorrência aberta;
> - **simulação** — o adaptador só entrega VE cuja rota gerada traz o parâmetro
>   SUMO `criticidade`. O `vClass` diz *que* é VE; o parâmetro diz que *está em
>   serviço*.
>
> A regra fica fora do motor porque depende de dado que o motor não tem (o
> cadastro de ocorrências), e fica em `core/` porque precisa ser a mesma nos dois
> modos e testável sem banco.

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

**E7 — Compensação pós-evento (H2).** Após a liberação, por `N_CICLOS_COMPENSACAO = 3` ciclos, redistribuir o verde proporcionalmente à fila acumulada de cada acesso, respeitando `VERDE_MIN` e `VERDE_MAX`:

```
verde_i = clamp(VERDE_BASE_i + K * (fila_i / soma_filas) * DEFICIT_TOTAL, VERDE_MIN, VERDE_MAX)
```

onde `DEFICIT_TOTAL` é o tempo de verde que o acesso deixou de receber durante a preempção, e `K` é o ganho de compensação (parâmetro do experimento; começou em `K = 0.7` e foi calibrado para `K = 1.0` em P17).

> **"Começar em `K = 0.7`" foi onde parou, e é P17.** O piloto do Bloco 4 mede uma
> mitigação entre −1,0% e +0,6% contra a meta de H2 — `K` e
> `N_CICLOS_COMPENSACAO` nunca foram calibrados contra dado real. **Antes de
> calibrar, verificar se a métrica não está diluindo o efeito:**
> `tempo_espera_medio_transversal_s` é a média sobre a hora inteira, e a
> compensação atua por ~140 s depois de cada evento, com um VE a cada 10 min.
> Calibrar contra uma métrica que dilui é calibrar contra ruído.
>
> **Decidido em 2026-10-01 (P17):** a suspeita de diluição não se sustenta. Com
> H2 medida como fração do *acréscimo*, os períodos sem evento se cancelam e a
> média horária não enviesa a razão. `K`/`N_CICLOS_COMPENSACAO` são calibrados
> uma vez, em seeds 101..105, pela grade e regra declaradas em `09` P17.
>
> **Calibrado em 2026-10-01:** `K = 1.0`, `N_CICLOS_COMPENSACAO = 3`, escolhidos
> pela regra com pontuação +6,2%, abaixo da meta de 15%. As 15 combinações da
> grade ficam dentro de cerca de um erro-padrão de zero: com esta fórmula, E7
> não mitiga de forma mensurável. Ver `09` P17, "Resultado da calibração".

**E8 — Conflito entre múltiplos VEs.** Cenário obrigatório de teste. Regra de desempate, em ordem:

0. **Maior criticidade da ocorrência** — `RISCO_VIDA` (1) > `RISCO_COLETIVO` (2) > `URGENCIA` (3). Acrescentado por P20, em 2026-09-29.
1. Maior prioridade por tipo — configurável, padrão: `AMBULANCIA > BOMBEIRO > POLICIA`.
2. Menor ETA ao cruzamento.
3. Preempção já em curso vence (evita oscilação/thrashing).

Se dois VEs demandam fases conflitantes no mesmo TLS, **um espera**. Nunca conceder as duas. Registrar em `log_prioridade` com `status_execucao = 'CONFLITO_ADIADO'`.

> **Criticidade — P20, 2026-09-29.** Os critérios de relevância por tipo
> (ambulância: vida humana; bombeiro: coletividade e meio ambiente; polícia:
> ordem pública) viraram uma escala **da ocorrência**, não do tipo, porque uma
> ambulância com caso leve não pode passar na frente de um incêndio com vítima:
>
> | Nível | `Criticidade` | Ambulância | Bombeiro | Polícia |
> | --- | --- | --- | --- | --- |
> | 1 | `RISCO_VIDA` | Suporte avançado; risco iminente de morte ou instabilidade grave | Incêndio ou resgate com vítima | Ocorrência em andamento com risco à vida |
> | 2 | `RISCO_COLETIVO` | Suporte básico, paciente estável | Sinistro que ameaça coletividade ou meio ambiente | Crime em andamento, perseguição |
> | 3 | `URGENCIA` | Deslocamento sem paciente crítico | Apoio, prevenção | Preservação da ordem pública |
>
> No **braço determinístico** o item 0 só entra na frente da chave antiga, sem
> mexer no resto. Nos cenários do experimento cada VE atende a ocorrência típica
> do seu tipo (AMB → 1, BOMB → 2, POL → 3), na mesma ordem de `prioridade_tipo` —
> então a decisão é a mesma de antes, e nenhum número medido muda.

> **E8 é o ponto onde entra o aprendizado de máquina** (pendência **P19**, aberta
> em 2026-09-10 por decisão do orientador). O desempate acima é lexicográfico e
> **míope**: decide um cruzamento por vez, sem pesar a consequência sequencial —
> priorizar o VE A agora pode custar mais ao VE B adiante. A ordem por tipo é
> convenção declarada, não otimização.
>
> **Desenho decidido em 2026-09-10** (detalhes e justificativas em P19):
>
> ```
> score = w · (x_A − x_B)      escolhe A se score > 0, senão B
>
> x = (eta_s, velocidade_ms, fila_no_acesso, cruzamentos_restantes)
> ```
>
> **`tipo` saiu do vetor em 2026-09-29 (P20).** Sob o rótulo minimax em tempo, o
> peso de `tipo` não carregaria relevância — o tempo não sabe que a ambulância
> leva uma vida. A relevância virou **criticidade**, e no braço `PREEMPCAO_ML` a
> ordem é: (1) criticidade, regra — o nível mais crítico vence, inclusive sobre
> preempção em curso; (2) guarda de oscilação, regra — no mesmo nível, a
> preempção em curso vence; (3) o modelo. A troca por criticidade não oscila:
> A só toma de B se `crit(A) < crit(B)`, e B nunca toma de volta.
>
> **Comparação par a par sobre diferenças**, com torneio para três ou mais VEs. As
> diferenças não são conveniência: elas garantem `score(B,A) = −score(A,B)` **por
> construção**, e sem isso o modelo poderia preferir A a B e B a A conforme a
> ordem de apresentação — inconsistência que apareceria como oscilação na rua.
>
> **Critério de treino: minimax** — minimizar o tempo de travessia do VE mais
> prejudicado. Rótulos vêm de **bifurcar a simulação** no instante do conflito
> (`traci.simulation.saveState`/`loadState`), rodando as duas escolhas e medindo a
> consequência. Rotular por heurística ensinaria ao modelo a própria heurística.
>
> **O item 3 acima — "preempção em curso vence" — continua sendo regra rígida
> ACIMA do modelo.** A política decide só quando não há preempção em curso;
> iniciada uma, a troca é governada pela regra. Assim o argumento de I4 e I5 não
> passa a depender do que o modelo aprendeu, e não há tempestade de trocas de fase.
>
> Restrição arquitetural: o modelo é **treinado fora e exportado como dado** — no
> desenho escolhido, um vetor de pesos em arquivo versionado —, com inferência
> pura em `core/`. É o que preserva a decisão do §1 deste documento e o que mantém
> `test_arquitetura.py` verde.
>
> **Continua aberto apenas o volume de dados**, que é a entrega 10.1. ~~Ninguém
> conta eventos de conflito hoje.~~ **A instrumentação existe desde 2026-09-10**;
> falta rodar o lote e ler o número. Ver abaixo.

**Observação dos conflitos (entrega 10.1, 2026-09-10).** E8 passou a ser
observável de fora, sem deixar de ser a mesma regra. `MotorDecisao` aceita um
`observador_conflito` opcional e publica um `EventoConflito` por passo e por
cruzamento em que **mais de um VE demanda fases distintas**. Três decisões de
projeto merecem registro, porque definem o que o número da 10.1 significa:

- **A publicação precede `resolver`.** `_decidir_para` pode retornar antes de E8
  pelo timeout de E6, e uma disputa que existiu não pode deixar de ser contada
  por causa do caminho que a decisão tomou.
- **A unidade é o episódio, não o passo.** Uma disputa contígua no mesmo
  cruzamento entre o mesmo conjunto de VEs é **uma** escolha, e é a escolha que a
  política aprendida vai tomar. Com passo de 0,1 s, contar por passo inflaria o
  número em duas ordens de grandeza. A agregação vive no coletor
  (`sim/controlador/coletor.py`), fora do trecho cronometrado do laço, para não
  contaminar a latência que sustenta o RNF01.
- **Episódio decidível é o que se pode treinar.** Quando já há preempção em curso
  no cruzamento, a escolha está **suspensa** pela guarda de oscilação, que é
  regra rígida acima do modelo. O evento carrega o VE que detém a preempção, e o
  agregado separa os dois casos.

Pedidos pela **mesma** fase não são conflito: o mesmo verde serve os dois, e
`resolver` os devolve em `atendidos_juntos`. O motor **não acumula** os eventos —
quem observa que os guarde. É o que mantém o estado do motor nos mesmos três
dicionários, e portanto mantém pequena a fotografia que a bifurcação da entrega
10.4 terá de salvar e restaurar junto com o estado do SUMO.

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
n_ciclos_compensacao: 3      # calibrado em P17 (era 2)
ganho_compensacao_k: 1.0     # calibrado em P17 (era 0.7)
velocidade_min_estimativa_ms: 4.0
prioridade_tipo: [AMBULANCIA, BOMBEIRO, POLICIA]
```

> `prioridade_tipo` passou a ser o **segundo** critério de E8 (P20): antes dele
> vem a criticidade da ocorrência. A escala de criticidade é enum ordinal em
> `core/modelos.py`, não parâmetro — não há número a calibrar, só precedência.

> No protótipo físico os tempos são reduzidos para caber numa demonstração de bancada. Perfil separado em `parametros.hardware.yaml` (decisão de 2026-08-24, após P13):
>
> ```yaml
> verde_s:     3.0    # duração do verde de cada fase no ciclo fixo
> verde_min_s: 3.0    # piso de I4 — coincide com verde_s na bancada
> amarelo_s:   2.0
> all_red_s:   1.0
> ```
>
> Com as 2 fases do ciclo da bancada (decisão de 2026-10-05, que revê P13), o ciclo completo leva `2 × (3 + 2 + 1)` = **12 s**. Esses tempos são aplicados pelo **firmware do UNO**, que decide sozinho na bancada (`05` §3); o arquivo é a referência dos valores para o dublê e para a ponte.
>
> **Consequência de `verde_s == verde_min_s`:** na bancada a preempção **nunca trunca** um verde — ela sempre aguarda o verde corrente terminar, o que leva no máximo 3 s. Isso simplifica o firmware e é mais fácil de explicar na banca do que um truncamento parcial. O caso de truncamento continua exercitado e testado no perfil de simulação, onde `verde_min_s = 7.0` é menor que a duração base das fases.
>
> **Não altere o perfil de simulação para "combinar" com o protótipo** — os dados estatísticos vêm da simulação com tempos realistas. Se a banca perguntar se 3 s de verde não é perigoso: a bancada é um modelo em escala para demonstração; os valores com significado de engenharia de tráfego estão em `parametros.yaml`, que é o que produz os resultados.

## 6. Invariantes de segurança (NUNCA violar)

Implementar como asserções verificadas a cada passo, em `backend/core/seguranca.py`. Se violada, a ação é **abortar a preempção e retornar ao ciclo fixo** (fail-safe), registrando o incidente.

1. **I1** — Dois grupos de movimentos conflitantes nunca recebem verde simultâneo. Na simulação, quem garante é o motor (com verificação a cada passo). **No protótipo** (decisão de 2026-10-05), a matriz de conflito é a dos dois eixos: o principal (S1, S2) conflita com o transversal (S3, S4). Em emergência a regra é mais estrita, e só a aproximação do VE fica verde. Quem garante é o firmware: uma guarda independente da máquina de estados, verificada antes de acender qualquer verde (`05` §3.5).
2. **I2** — Nenhuma transição verde → vermelho sem amarelo intermediário de `AMARELO_S`.
3. **I3** — Todo troca de fase é precedida de `ALL_RED_S` com todos os acessos em vermelho.
4. **I4** — Nenhum verde é truncado antes de `VERDE_MIN`.
5. **I5** — Nenhum acesso permanece em vermelho por mais de `VERMELHO_MAX_S = 120 s` (starvation).
6. **I6** — **Nenhum verde de emergência depende de comunicação para terminar.** Toda emergência acaba sozinha, pela duração do tipo do VE, e o regime de emergência contínuo tem teto de `PREEMP_MAX_MS = 30 s`, depois do qual o firmware volta ao ciclo.

I6 é responsabilidade do firmware. **Redefinido em 2026-10-05.** A versão anterior era um watchdog (sem comando do notebook por 3 s → ciclo fixo), que fazia sentido quando o notebook comandava o UNO. Na arquitetura da bancada o UNO não recebe comando do notebook, então não há comunicação cuja queda vigiar. A garantia que o watchdog dava — nenhum verde travado — passa a vir do fim por duração e do teto.

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
| `POST` | `/ocorrencias` | Central abre ocorrência: `id_veiculo`, `criticidade` (1..3), `descricao` (P20) |
| `POST` | `/ocorrencias/{id}/encerramento` | Central encerra a ocorrência; o VE deixa de ter prioridade |
| `GET` | `/ocorrencias?ativas=true` | Ocorrências abertas — o painel "Central" do dashboard |
| `GET` | `/logs/prioridade` | Logs paginados, com filtros |
| `POST` | `/simulacoes` | Pede execução de cenário ao atendente do host (Bloco 6) |
| `GET` | `/simulacoes` | Pedidos mais recentes (Bloco 6) |
| `GET` | `/simulacoes/{id}` | Status e métricas da execução |
| `POST` | `/simulacoes/transmissao` | Estado ao vivo da simulação, empurrado pelo executor (Bloco 6) |
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
  "autorizado": true,
  "id_veiculo": 3,
  "tipo": "AMBULANCIA",
  "criticidade": 1,
  "acao": "PREEMPCAO_SOLICITADA",
  "id_log": 1187,
  "mensagem_lcd": "AMBULANCIA\nPRIORIDADE ATIVA"
}
```

**Tag reconhecida sem ocorrência ativa (P20)** — HTTP **200**, porque a
credencial é válida e só falta o serviço. O **403** continua reservado à tag
desconhecida ou inativa.

```json
{
  "reconhecido": true,
  "autorizado": false,
  "id_veiculo": 3,
  "tipo": "AMBULANCIA",
  "criticidade": null,
  "acao": "SEM_OCORRENCIA",
  "id_log": null,
  "mensagem_lcd": "SEM OCORRENCIA\nSEM PRIORIDADE"
}
```

A decisão entre os dois casos é de `core/autorizacao.autorizar()`, pura, e a
tentativa negada é gravada em `deteccao` com `autorizado = false`.

> **Decidido no Bloco 6 (2026-10-05).** `POST /deteccoes` **continua** como o
> contrato do V2I com rede (a arquitetura-alvo), com payload, `X-Device-Token`,
> anti-replay e P20 como acima. **Na bancada nenhum dispositivo chama a rota**:
> os eventos do UNO entram pela leitura de `GET /estado` da ponte (§4), só para
> registro. A rota é exercitada pelos testes e pelo Swagger. Três pontos a
> declarar no texto:
>
> - **`PREEMPCAO_SOLICITADA` não aciona atuador.** Na simulação o motor roda no
>   processo do executor, e na bancada quem decide é o UNO. A rota grava a
>   detecção e, se o leitor pertence a um cruzamento, uma linha `SUCESSO` em
>   `log_prioridade` com o mesmo `id_correlacao`, e o `motivo` diz isso por
>   extenso.
> - **Anti-replay.** A mesma tag (UID normalizado) ou a mesma `sequencia` do
>   mesmo leitor dentro de 2 s recebe a resposta da primeira, com
>   `duplicada: true`, e nada é gravado.
> - **`VEICULO_INATIVO`**, tag reconhecida de veículo fora de operação, responde
>   200 sem prioridade, como `SEM_OCORRENCIA`. O 403 é só da tag desconhecida
>   ou inativa (`acao: ACESSO_NEGADO`).
>
> **Preempção manual.** `POST /semaforos/PROTO_CRUZ_01/preempcao` (`rua`,
> `veiculo`) usa a injeção da ponte, que exige o fio do NodeMCU solto do RX
> (`05` §6). Nos cruzamentos da simulação a resposta é 409, porque a API não
> comanda o executor. `DELETE .../preempcao` é sempre 409: o UNO não aceita
> cancelamento, porque a emergência termina sozinha (I6), e na simulação vale o
> mesmo motivo.
>
> **Simulações pela API.** O backend está no contêiner, e o SUMO no host
> (`02` §3). `POST /simulacoes` grava em `pedido_simulacao`, e
> `python -m sim.controlador.atendente` executa o pedido com transmissão ao
> vivo. A API e o atendente recusam as seeds 1..50 e 101..105, que são do
> experimento, e a execução nunca escreve em `analysis/data/`.

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

> **Implementado no Bloco 6** (`app/services/difusao.py`). O throttle é pela
> **borda de subida**: sem descarga recente, a mensagem sai na hora; senão, no
> fim do intervalo. Estado (`estado_semaforo`, `posicao_ve`, `metrica`) é fundido
> por chave, e só o mais recente sai. `evento` nunca é descartado. Quem conecta
> recebe primeiro o último estado de cada semáforo e VE. Duas extensões do
> contrato acima:
>
> - **Bancada**, em `estado_semaforo` do `PROTO_CRUZ_01`: `aproximacoes`
>   (`"RRGR"`, S1..S4), `regime`, `rua_ativa` e `rua_fila`. `fase` é o eixo do
>   ciclo aberto (1 ou 2), nula em emergência e no all-red, porque o verde
>   exclusivo não é fase.
> - **Simulação**, em `posicao_ve`: `id_veiculo` é o id do SUMO (`ve_amb_0`), não
>   uma chave do cadastro. `lat` e `lon` vêm de `sim/rede/georreferencia.py`,
>   ancorado em `CRUZ_01` como os seeds.

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
│   │   ├── ocorrencias.py      # P20: a central de despacho simulada
│   │   ├── logs.py
│   │   └── ws.py
│   ├── api/dependencias.py     # recursos do processo, sessão (commit explícito)
│   ├── configuracao.py         # ambiente -> Configuracao (testes montam a sua)
│   ├── logs.py                 # structlog: os seis campos obrigatórios (02 §7)
│   ├── models/                 # SQLAlchemy ORM
│   ├── schemas/                # Pydantic v2
│   ├── repositories/           # acesso a dados
│   └── services/               # bancada (leitura da ponte), deteccoes, difusao,
│                               # ao_vivo, simulacoes, metricas
├── core/                       # ⚠️ SEM I/O, SEM FRAMEWORK
│   ├── priorizacao/
│   │   ├── motor.py            # avaliar() -> list[Comando]
│   │   ├── deteccao.py         # E1, E2, E3
│   │   ├── fases.py            # E4, E5
│   │   ├── compensacao.py      # E7
│   │   └── conflito.py         # E8
│   ├── autorizacao.py          # P20: tag + ocorrência ativa -> em serviço?
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
