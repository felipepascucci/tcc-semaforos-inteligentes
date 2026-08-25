# 04 — Simulação de Tráfego (SUMO + TraCI)

## 1. Papel da simulação

A simulação **é** o experimento do TCC. Todos os números das hipóteses H1, H2 e H3 saem daqui. O protótipo físico demonstra viabilidade; ele não gera estatística.

## 2. Estrutura de arquivos

```
sim/
├── rede/
│   ├── malha.nod.xml         # nós (cruzamentos)
│   ├── malha.edg.xml         # vias
│   ├── malha.con.xml         # conexões e movimentos permitidos
│   ├── malha.tll.xml         # programas semafóricos (baseline fixo)
│   ├── malha.typ.xml         # tipos de via (velocidade, faixas)
│   └── malha.net.xml         # GERADO por netconvert — não editar à mão
├── demanda/
│   ├── veiculos.typ.xml      # tipos: carro, ônibus, ambulância, bombeiro, polícia
│   ├── fluxo_leve.rou.xml
│   ├── fluxo_moderado.rou.xml
│   ├── fluxo_intenso.rou.xml
│   └── emergencias.rou.xml   # rotas dos VEs
├── config/
│   ├── mapa_fases.yaml       # movimento -> fase, por TLS
│   ├── cenarios.yaml         # definição dos cenários experimentais
│   └── *.sumocfg
├── controlador/
│   ├── executor.py           # CLI: roda 1 execução
│   ├── lote.py               # roda a matriz completa de execuções
│   ├── adaptador_traci.py    # implementa a interface de adaptador
│   └── coletor.py            # extrai métricas do SUMO
└── saida/                    # tripinfo, summary, queue — gitignored
```

## 3. Modelagem da malha

Parâmetros do pré-projeto (seção 1.2), a serem respeitados:

| Parâmetro | Valor |
| --- | --- |
| Tipo de ambiente | Malha urbana arterial |
| Cruzamentos | 4 a 8 |
| Fluxo | 300 a 1200 veíc./h |
| Velocidade | 40 a 60 km/h |
| Ciclo semafórico | 30 a 90 s |
| Frequência de emergências | 1 VE a cada 10 min |
| Raio de detecção | até 500 m |
| Duração | 60 min por cenário |

**Geometria proposta:** grade de 2×4 = 8 cruzamentos. Eixo arterial horizontal (via principal, 2 faixas por sentido, 60 km/h, ~500 m entre cruzamentos, totalizando o percurso de ~5 km citado na seção 5 do pré-projeto quando somados os trechos de aproximação) cruzado por 4 vias transversais (1 faixa por sentido, 40 km/h).

A rota do VE percorre o eixo arterial de ponta a ponta, atravessando os 8 cruzamentos. Isso é o que torna o "corredor verde" mensurável — se o VE cruzasse só um semáforo, não haveria efeito de coordenação para medir.

**Comando de build da rede:**

```bash
netconvert --node-files=malha.nod.xml --edge-files=malha.edg.xml \
           --connection-files=malha.con.xml --tllogic-files=malha.tll.xml \
           --type-files=malha.typ.xml --output-file=malha.net.xml
```

Versionar os arquivos-fonte, não o `.net.xml` gerado. Adicionar um alvo `make rede`.

## 4. Tipos de veículo

```xml
<vType id="carro"     accel="2.6" decel="4.5" sigma="0.5" length="4.5" maxSpeed="16.7" vClass="passenger"/>
<vType id="onibus"    accel="1.2" decel="4.0" sigma="0.5" length="12.0" maxSpeed="13.9" vClass="bus"/>
<vType id="ambulancia" accel="3.0" decel="5.0" sigma="0.1" length="5.5" maxSpeed="22.2"
       vClass="emergency" guiShape="emergency" color="1,0,0"
       speedFactor="1.3" jmIgnoreFoeProb="0.3" jmIgnoreFoeSpeed="5.0"/>
```

`vClass="emergency"` é importante: o SUMO reconhece a classe e permite comportamentos específicos. `speedFactor="1.3"` modela o VE trafegando acima do limite, como acontece na prática. `jmIgnoreFoe*` modela a passagem cautelosa em vermelho — **usar com parcimônia e documentar**, porque afeta diretamente a comparação: se o VE do baseline já ignora sinal vermelho, o ganho medido da preempção cai. Recomendação: manter `jmIgnoreFoeProb` **igual nos dois braços** para que a comparação seja justa, e discutir isso na seção de metodologia.

## 5. Cenários experimentais

`sim/config/cenarios.yaml`:

| Cenário | Saturação | Fluxo (veíc./h) | Objetivo |
| --- | --- | --- | --- |
| `leve` | < 40% | 300 | Validar resposta rápida |
| `moderado` | 40–75% | 700 | Medir ganho operacional |
| `intenso` | > 75% | 1200 | Testar eficiência crítica |
| `multiplas_emergencias` | 40–75% | 700 | Validar resolução de conflitos (2 VEs simultâneos em cruzamentos compartilhados) |

## 6. Braços de comparação (modos de controle)

| Modo | Descrição | Serve para |
| --- | --- | --- |
| `FIXO` | Baseline: programa semafórico estático do `.tll.xml`, sem TraCI intervindo | Controle |
| `PREEMPCAO` | Preempção sem compensação pós-evento | H1 e H3 |
| `PREEMPCAO_COMPENSADA` | Preempção + compensação (E7) | H1, H2, H3 |

Rodar os três é o que permite isolar o efeito da compensação. Comparar apenas fixo vs. compensado não permite afirmar nada sobre H2.

## 7. Protocolo experimental

**Matriz:** 4 cenários × 3 modos × 50 seeds = **600 execuções** de 3600 s de tempo simulado.

**Pareamento por seed — regra crítica.** A seed determina a geração do tráfego de fundo e os instantes de entrada dos VEs. A execução com `seed=17` no modo `FIXO` e no modo `PREEMPCAO` precisa ter **exatamente o mesmo tráfego**. Isso transforma a comparação em teste pareado, que tem muito mais poder estatístico e elimina a variância entre cenários de tráfego. Concretamente: gerar os arquivos de rota uma vez por (cenário, seed) e reutilizá-los nos três modos.

```bash
python -m sim.controlador.lote \
    --cenarios leve,moderado,intenso,multiplas_emergencias \
    --modos FIXO,PREEMPCAO,PREEMPCAO_COMPENSADA \
    --seeds 1..50 \
    --duracao 3600 \
    --paralelo 4 \
    --saida analysis/data/
```

Com `libsumo` e 4 processos em paralelo, isso roda em algumas horas. Com `traci` + GUI, em dias. Rodar o lote com `libsumo` e headless.

## 8. Loop do controlador

```python
def executar(cenario, modo, seed, duracao) -> ResultadoExecucao:
    traci.start(cmd_sumo(cenario, seed))
    execucao = repo.criar_execucao(cenario, modo, seed, versao_codigo(), parametros())
    motor = MotorDecisao(parametros(), mapa_fases())
    buffer = BufferMetricas(execucao.id)

    t = 0.0
    while t < duracao:
        traci.simulationStep()
        t = traci.simulation.getTime()

        estado = adaptador.ler_estado()          # EstadoMalha

        if modo != Modo.FIXO:
            inicio = time.perf_counter()
            comandos = motor.avaliar(estado)      # PURO — sem I/O
            latencia_ms = (time.perf_counter() - inicio) * 1000
            adaptador.aplicar(comandos)
            buffer.registrar_decisao(t, comandos, latencia_ms)

        buffer.registrar_transicoes(t, estado)    # P5: só quando a fase muda

    traci.close()
    return buffer.consolidar()
```

Pontos de atenção:

- `motor.avaliar()` cronometrado com `perf_counter()` — é a **latência de decisão (RNF01, < 100 ms)**, não a fim-a-fim. Não incluir I/O de banco nessa medição, ou o número deixa de significar o que se quer afirmar. A latência fim-a-fim de H3 (< 200 ms) só é mensurável no fluxo com detecção física; na simulação, `t_deteccao` é o instante do passo em que o VE entrou no raio. Ver decisão P2 em `09-pendencias-e-decisoes.md`.
- No modo `FIXO`, o motor **não é chamado**. O baseline precisa ser genuinamente sem intervenção.
- Registro de estado **por transição de fase**, não por amostragem periódica (decisão P5 — ver `03-banco-de-dados.md` §3.3).

## 9. Métricas coletadas

### 9.1 Do VE (por veículo, via `tripinfo`)

| Métrica | Fonte |
| --- | --- |
| `tempo_viagem_s` | `tripinfo.duration` |
| `tempo_espera_s` | `tripinfo.waitingTime` |
| `paradas` | `tripinfo.waitingCount` |
| `velocidade_media_ms` | `routeLength / duration` |
| `atraso_s` | `tripinfo.timeLoss` |

### 9.2 Do tráfego geral (impacto — H2)

| Métrica | Fonte |
| --- | --- |
| `tempo_espera_medio_transversal_s` | `tripinfo` filtrado por vias transversais |
| `fila_maxima_por_acesso` | `traci.lanearea` (detectores E2) |
| `throughput_veic_h` | contagem em detectores de saída |
| `atraso_total_rede_s` | soma de `timeLoss` |

### 9.3 Do sistema (H3 / RNF01)

`latencia_decisao_ms` — mín, média, p95, p99, máx. **Reportar p95 e p99, não só a média.** Sistema crítico se avalia pela cauda; média de 68 ms com p99 de 400 ms não atende ao requisito, e a banca pode perguntar exatamente isso.

### 9.4 Segurança

`colisoes` — extrair de `--collision-output`. Precisa ser **zero**. O pré-projeto afirma zero colisões; isso tem que ser verificado, não assumido.

## 10. Saída em CSV

Um arquivo por execução, mais um consolidado:

```
analysis/data/
├── execucoes.csv                      # 1 linha por execução (600 linhas)
├── ve_por_execucao.csv                # 1 linha por VE por execução
├── transversal_por_execucao.csv
├── latencias.csv                      # 1 linha por decisão
└── raw/<cenario>_<modo>_<seed>/       # tripinfo.xml, summary.xml, queue.xml
```

Esses CSVs são o insumo de `07-resultados-e-analise.md`. Devem ser regeneráveis do zero com um comando.

## 11. Detectores necessários no `.add.xml`

- **E2 (lanearea)** em cada acesso de cruzamento, 100 m antes da linha de retenção → fila e ocupação.
- **E1 (induction loop)** na saída de cada cruzamento → throughput.
- **E3** no eixo arterial completo → tempo de viagem por trecho.

Sem os detectores não há como medir o impacto transversal, e H2 fica sem evidência.

## 12. Validação da malha antes de experimentar

Antes de rodar as 600 execuções, verificar:

1. `netconvert` sem warnings de conexão inválida.
2. Rodar 600 s com fluxo leve e `--collision.action warn` — zero colisões no baseline.
3. Nenhum veículo teleportado (`--time-to-teleport -1` para desabilitar teleporte e expor gridlocks reais; se houver teleporte, a demanda está mal calibrada e os resultados serão inválidos).
4. Grau de saturação medido bate com o pretendido para cada cenário (v/c ratio nos acessos).

Um gridlock não detectado invalida silenciosamente todo o experimento. Este passo não é opcional.
