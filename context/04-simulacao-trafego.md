# 04 — Simulação de Tráfego (SUMO + TraCI)

## 1. Papel da simulação

A simulação **é** o experimento do TCC. Todos os números das hipóteses H1, H2 e H3 saem daqui. O protótipo físico demonstra viabilidade; ele não gera estatística.

## 2. Estrutura de arquivos

```
sim/
├── ambiente.py               # localiza SUMO_HOME, binários e o cliente Python
├── rede/
│   ├── malha.nod.xml         # nós (cruzamentos)
│   ├── malha.edg.xml         # vias
│   ├── malha.con.xml         # conexões — gerado uma vez e CONGELADO
│   ├── malha.tll.xml         # programas semafóricos (baseline fixo)
│   ├── malha.typ.xml         # tipos de via (velocidade, faixas)
│   ├── construir.py          # `make rede` — netconvert + detectores
│   ├── detectores.py         # gera os E1/E2/E3 a partir da rede
│   ├── malha.net.xml         # GERADO por netconvert — não editar, não versionar
│   └── malha.det.add.xml     # GERADO — detectores E1, E2 e E3
├── calibracao/
│   ├── fluxo_saturacao.py    # MEDE o fluxo de saturação (exige SUMO)
│   └── cenarios.py           # deriva o grau de saturação (puro)
├── demanda/
│   ├── veiculos.typ.xml      # tipos: carro, ônibus, ambulância, bombeiro, polícia
│   ├── fluxo_leve.rou.xml    # GERADOS da calibração e versionados
│   ├── fluxo_moderado.rou.xml
│   ├── fluxo_intenso.rou.xml
│   ├── emergencias.rou.xml   # rotas dos VEs
│   ├── teste_60s.rou.xml     # cenário curto de integração (context/06 §7)
│   ├── gerar_fluxos.py       # calibração -> arquivos de fluxo
│   └── gerar_rotas.py        # fluxos -> veículos concretos por (cenário, seed)
├── config/
│   ├── mapa_fases.yaml       # aproximação -> fase, por TLS
│   ├── cenarios.yaml         # definição dos cenários experimentais
│   ├── malha.sumocfg         # configuração base das execuções
│   └── teste_60s.sumocfg
├── controlador/
│   ├── executor.py           # CLI: roda 1 execução
│   ├── lote.py               # roda a matriz completa (Bloco 8)
│   ├── coletor.py            # extrai métricas do SUMO
│   └── traco.py              # séries no tempo de uma execução, para F3, F4 e F6 (Bloco 9)
├── validacao/
│   ├── malha.py              # os quatro itens do §12, automatizados
│   └── execucao.py           # validar_execucao() do context/06 §4
└── saida/                    # tripinfo, rotas por seed, detectores — gitignored
```

O **adaptador** não mora em `sim/`: ele é `backend/adapters/sumo/` (`cliente.py`,
`topologia.py`, `adaptador.py`), porque é a peça que traduz entre o simulador e o
motor — o mesmo papel que `adapters/hardware/` cumpre do lado da bancada
(`context/01` §1). `sim/` é o experimento; `adapters/` é a ponte.

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

**Geometria implementada:** grade de 2×4 = 8 cruzamentos. **Duas** arteriais horizontais (2 faixas por sentido, 60 km/h) cruzadas por 4 transversais (1 faixa por sentido, 40 km/h), com 500 m entre cruzamentos em ambos os eixos e trechos de aproximação de 500 m em cada fronteira.

```
            x=0     x=500   x=1000  x=1500
             |        |        |        |
y= 500     EXT_T1_N EXT_T2_N EXT_T3_N EXT_T4_N
             |        |        |        |
y=   0  ═══CRUZ_01══CRUZ_02══CRUZ_03══CRUZ_04═══   arterial 1
             |        |        |        |
y=-500  ═══CRUZ_05══CRUZ_06══CRUZ_07══CRUZ_08═══   arterial 2
             |        |        |        |
y=-1000    EXT_T1_S EXT_T2_S EXT_T3_S EXT_T4_S
```

A numeração é a mesma de `db/seeds/dados.yaml` (linha a linha), e as coordenadas geográficas dos seeds são derivadas desta grade.

**Convenção de nomes das vias**, usada em todo o Bloco 3:

| Padrão | Significado |
| --- | --- |
| `A{linha}_{L\|O}{segmento}` | arterial 1 ou 2, sentido Leste ou Oeste, segmento 0..4 (de oeste para leste) |
| `T{coluna}_{S\|N}{segmento}` | transversal 1..4, sentido Sul ou Norte, segmento 0..2 (de norte para sul) |

O índice do segmento identifica o **trecho físico**, não a ordem de percurso: `A1_L2` e `A1_O2` são as duas mãos do mesmo trecho.

**Rota do VE — o "U" pelos oito cruzamentos** (decisão de 2026-08-25, `context/09`):

```
A1_L0 A1_L1 A1_L2 A1_L3   T4_S1   A2_O3 A2_O2 A2_O1 A2_O0
└─ CRUZ_01..04 ─────────┘ └ 08 ┘ └─ CRUZ_07..05 ─────────┘
```

São 4.500 m — os ~5 km do pré-projeto — e **oito** cruzamentos semaforizados. O texto original dizia "percorre o eixo arterial de ponta a ponta, atravessando os 8 cruzamentos", o que é impossível numa grade 2×4 (cada arterial cruza 4); o "U" é a leitura que preserva as duas afirmações sem mexer na geometria.

Isso é o que torna o "corredor verde" mensurável — se o VE cruzasse só um semáforo, não haveria efeito de coordenação para medir. E há um ganho de brinde: o corredor **muda de eixo** no meio do percurso (em CRUZ_04 o VE converte à direita para a transversal; em CRUZ_08 ele chega **pela** transversal e pede a fase transversal, não a arterial), o que exercita E4 de verdade.

**Rota do segundo VE em `multiplas_emergencias`** (estendida em 2026-10-05, `context/09`):

```
T2_S0   T2_S1    A2_L2   A2_L3   A2_L4
└ 02 ┘  └ 06 ┘   └ 07 ┘  └ 08 ┘  (sai pelo leste)
```

Encontra o corredor em CRUZ_02 (arterial × transversal) e, se os dois chegarem
juntos, de novo em CRUZ_08 (o corredor pela transversal, este pela arterial). A
conversão em CRUZ_06 é à esquerda e **permissiva**: o VE cede ao tráfego oposto,
o que aparece como paradas do VE nesse cenário e precisa ser declarado.

**Comando de build da rede:**

```bash
make rede                      # ou, sem make:
python -m sim.rede.construir   # netconvert + geração dos detectores
python -m sim.rede.construir --verificar   # confere se o .net.xml está em dia
```

Versionar os arquivos-fonte, não o `.net.xml` nem o `.det.add.xml` gerados.

Três detalhes da construção que valem registro:

- **Aviso do `netconvert` é erro.** O item 1 do §12 exige build sem aviso, e um aviso que ninguém lê é um aviso que não existe. `--permitir-avisos` existe para inspeção, não para uso normal.
- **`malha.con.xml` é gerado uma vez e congelado.** Saiu da própria inferência do netconvert (`plain-output-prefix`), foi conferido e virou fonte. Continuar inferindo a cada build amarraria a rede à versão do netconvert instalada — e uma troca de versão poderia mudar em silêncio quais movimentos existem e, com eles, os índices de link do `.tll.xml`.
- **`--no-turnarounds`.** Retornos em U não existem no cenário modelado e criariam links a mais no semáforo, mudando o comprimento das *state strings*.

**O `.tll.xml` é fonte versionada, não saída.** O programa que o netconvert gera sozinho tem quatro fases (verde/amarelo por eixo) e vai do amarelo direto ao verde seguinte — **viola I3**. O arquivo versionado tem seis: verde 30 s, amarelo 3 s, all-red 2 s, por eixo, fechando o ciclo de 70 s. Offset zero em todos os oito: o baseline é temporização fixa **sem** coordenação, e vale registrar como limitação no texto que uma progressão coordenada seria um baseline mais forte.

## 4. Tipos de veículo

```xml
<vType id="carro"     accel="2.6" decel="4.5" sigma="0.5" length="4.5" maxSpeed="16.7" vClass="passenger"/>
<vType id="onibus"    accel="1.2" decel="4.0" sigma="0.5" length="12.0" maxSpeed="13.9" vClass="bus"/>
<vType id="ambulancia" accel="3.0" decel="5.0" sigma="0.1" length="5.5" maxSpeed="22.2"
       vClass="emergency" guiShape="emergency" color="1,0,0"
       speedFactor="1.3" jmIgnoreFoeProb="0.3" jmIgnoreFoeSpeed="5.0"/>
```

> **`tau` foi calibrado em 2026-08-25 e não consta do bloco acima.** O headway temporal desejado não era declarado em lugar nenhum, e o padrão do SUMO (1,0 s) produzia um fluxo de saturação de ~2.400 veíc./h/faixa — fora da faixa de plausibilidade de via urbana. Passou a **1,6 s** no carro e 1,8 s no ônibus, por critério declarado antes do ajuste. Ver `context/09` e o cabeçalho de `sim/demanda/veiculos.typ.xml`.
>
> **Consequência operacional:** mexer em `tau`, `minGap`, `length`, `accel` ou `decel` obriga a rodar, nesta ordem, `python -m sim.calibracao.fluxo_saturacao`, `python -m sim.calibracao.cenarios` e `python -m sim.demanda.gerar_fluxos`. Sem isso o v/c passa a descrever uma malha que não é a que roda.

`vClass="emergency"` é importante: o SUMO reconhece a classe e permite comportamentos específicos. **É por ela — e não por convenção de id — que o adaptador identifica o VE.**

> **Ser VE não é estar em serviço — P20 (2026-09-29).** O `vClass` diz *que* o
> veículo é de emergência; o parâmetro `<param key="criticidade" value="N"/>`,
> escrito por `sim/demanda/gerar_rotas.py` em cada VE da rota gerada, diz que ele
> *está atendendo uma ocorrência*, e com qual criticidade (1 `RISCO_VIDA`,
> 2 `RISCO_COLETIVO`, 3 `URGENCIA`). O adaptador lê o parâmetro **uma vez, na
> partida**, e um VE sem ele **não é entregue ao motor**: trafega como veículo
> comum, com um aviso na execução. É a mesma regra da bancada, onde a tag sem
> ocorrência aberta não preempta. O parâmetro não altera a dinâmica do SUMO. `speedFactor="1.3"` modela o VE trafegando acima do limite, como acontece na prática. `jmIgnoreFoe*` modela a passagem cautelosa em vermelho — **usar com parcimônia e documentar**, porque afeta diretamente a comparação: se o VE do baseline já ignora sinal vermelho, o ganho medido da preempção cai. Recomendação: manter `jmIgnoreFoeProb` **igual nos dois braços** para que a comparação seja justa, e discutir isso na seção de metodologia.

## 5. Cenários experimentais

`sim/config/cenarios.yaml`:

| Cenário | Saturação **medida** (v/c) | Caracterização | Fluxo (veíc./h) | Objetivo |
| --- | --- | --- | --- | --- |
| `leve` | 0,18 | leve | 300 | Validar resposta rápida |
| `moderado` | 0,42 | moderada | 700 | Medir ganho operacional |
| `intenso` | 0,73 | moderada-**alta** | 1200 | Testar eficiência crítica |
| `multiplas_emergencias` | 0,42 | moderada | 700 | Validar resolução de conflitos (2 VEs simultâneos em cruzamentos compartilhados) |

> **Criticidade dos VEs nos cenários — P20 (2026-09-29).** `emergencias` ganhou
> `criticidades: [1, 2, 3]`, que roda **em passo** com `tipos: [AMBULANCIA,
> BOMBEIRO, POLICIA]`: cada VE atende a ocorrência típica do seu tipo. É
> **simplificação declarada** — numa central real o nível vem da ocorrência, e
> não do tipo — e tem uma consequência deliberada: como essa ordem coincide com
> `prioridade_tipo`, o E8 determinístico decide exatamente como antes da P20, e
> nenhum número medido muda. O gerador recusa listas de tamanhos diferentes. O
> cenário de treino da 10.2 é que vai desacoplar criticidade de tipo.

> **Cenário de treino da entrega 10.2 — fora do experimento (2026-10-05).**
> `treino_multiplas` fica na seção `cenarios_treino` de `cenarios.yaml`, e não em
> `cenarios`: não entra nesta tabela, no lote padrão nem na API. Usa as rotas e o
> fundo de `multiplas_emergencias`, com um par a cada 300 s, atraso da segunda
> partida sorteado por par em [0, 20] s e criticidade desacoplada do tipo
> (rodízio `[1, 2, 3, 2]`, um par a cada cinco de nível misto). Serve só para
> produzir as disputas que a 10.4 rotula; seeds 201..240 (treino) e 241..250
> (validação). Ver a decisão em `context/09`.

> **A coluna de saturação era declarada e passou a ser medida** (decisão de
> 2026-08-25, `context/09`). Os fluxos e os nomes dos cenários **não mudaram** —
> vêm do pré-projeto e já estão no texto entregue. O que mudou é que a
> caracterização agora sai da medição, e não de uma faixa suposta.
>
> **Consequência para a redação: o nome do cenário é rótulo do ponto
> experimental, não afirmação sobre o regime.** `intenso` mede v/c = 0,73, que
> fica no topo da faixa moderada (o corte é 0,75) — descrevê-lo como "tráfego
> intenso" no texto seria afirmar mais do que o dado sustenta. A formulação
> correta é *"saturação moderada-alta (v/c = 0,73)"*.
>
> Os limiares de 0,40 e 0,75 continuam intocados, e a função de classificação
> continua devolvendo `moderado` para o cenário `intenso`. Esse é o resultado
> certo, e é o que vai na tabela da metodologia.
>
> **H1 continua de pé.** A decisão P1 condiciona a meta a "saturação moderada a
> intensa"; os dois cenários em que ela se aplica medem 0,42 e 0,73 — dois pontos
> distintos dentro dessa faixa, que é exatamente o que a comparação precisa.

### 5.1 Saturação **medida**, não declarada (entrega 3.0, encaminhamento de P11)

Os percentuais da tabela acima estão *declarados*. A partir do Bloco 3 eles são
**calculados**, por uma cadeia inteiramente em código versionado:

```
fluxo de saturação MEDIDO na malha        sim/calibracao/fluxo_saturacao.py
  -> capacidade = faixas × s × g_ef/C     sim/calibracao/cenarios.py
  -> v/c derivado por cenário             analysis/data/calibracao_cenarios.csv
  -> v/c MEDIDO na malha completa         sim/validacao/malha.py  (§12 item 4)
```

Resultado da execução de 2026-08-25 (`analysis/data/`):

| Cenário | Fluxo arterial | Capacidade | v/c | Classificação | Fluxo transversal **derivado** |
| --- | --- | --- | --- | --- | --- |
| `leve` | 300 | 1.652 | 0,18 | leve | 135 |
| `moderado` | 700 | 1.652 | 0,42 | moderado | 314 |
| `intenso` | 1.200 | 1.652 | **0,73** | **moderado** | 539 |
| `multiplas_emergencias` | 700 | 1.652 | 0,42 | moderado | 314 |

Fluxo de saturação medido: **1.752 veíc./h/faixa** na arterial (média das duas
faixas) e **1.573** na transversal — ambos dentro da faixa de plausibilidade
declarada para via urbana.

**Duas consequências que precisam entrar no texto:**

1. **A demanda transversal é derivada**, não escolhida: é o fluxo que põe a
   transversal no mesmo grau de saturação da arterial. Repetir os 1.200 numa via
   de uma faixa daria v/c > 1,5 e gridlock.
2. **O cenário `intenso` mede v/c = 0,73**, abaixo do limiar de 0,75 da própria
   tabela. **Decidido em 2026-08-25:** fluxos e nomes ficam; a caracterização
   passa a ser a medida, e o cenário é descrito como *saturação moderada-alta*.
   Ver a nota do §5 e a tabela de decisões de `context/09`.

## 6. Braços de comparação (modos de controle)

| Modo | Descrição | Serve para |
| --- | --- | --- |
| `FIXO` | Baseline: programa semafórico estático do `.tll.xml`, sem TraCI intervindo | Controle |
| `PREEMPCAO` | Preempção sem compensação pós-evento | H1 e H3 |
| `PREEMPCAO_COMPENSADA` | Preempção + compensação (E7) | H1, H2, H3 |
| `PREEMPCAO_ML` | `PREEMPCAO` com a política aprendida em E8 (P19). Só nos cenários com mais de um VE | H4 |

Rodar os três primeiros é o que permite isolar o efeito da compensação. Comparar apenas fixo vs. compensado não permite afirmar nada sobre H2.

> **`PREEMPCAO_ML` é o quarto braço, desde a entrega 10.7** (2026-10-07). Três
> decisões da equipe, registradas em `09` P19:
>
> - **É o `PREEMPCAO` com o modelo, sem E7.** Mesmos parâmetros, e a única
>   diferença é quem propõe o vencedor de E8. É o que permite atribuir ao modelo
>   a diferença contra o `PREEMPCAO`, que é o baseline de H4.
> - **Só roda nos cenários com mais de um VE simultâneo**, hoje o
>   `multiplas_emergencias`. Com um VE só não há disputa, o modelo nunca é
>   consultado, e a execução repetiria a do `PREEMPCAO`. Quem corta é
>   `lote.matriz()`, lendo `ves_simultaneos` de `cenarios.yaml`, e o lote avisa
>   na tela; o Bloco 8 continua sendo um comando só.
> - **O coletor registra quem decidiu cada disputa**: as colunas
>   `decidida_pelo_modelo` e `modelo_divergiu_do_e8` de
>   `conflitos_por_execucao.csv` (§10).

## 7. Protocolo experimental

**Matriz:** 4 cenários × 3 modos × 50 seeds = 600 execuções, mais o `PREEMPCAO_ML` no `multiplas_emergencias` × 50 seeds = **650 execuções** de 3600 s de tempo simulado (o quarto braço desde a entrega 10.7, §6).

**Pareamento por seed — regra crítica.** A seed determina a geração do tráfego de fundo e os instantes de entrada dos VEs. A execução com `seed=17` no modo `FIXO` e no modo `PREEMPCAO` precisa ter **exatamente o mesmo tráfego**. Isso transforma a comparação em teste pareado, que tem muito mais poder estatístico e elimina a variância entre cenários de tráfego. Concretamente: gerar os arquivos de rota uma vez por (cenário, seed) e reutilizá-los em todos os modos, inclusive no `PREEMPCAO_ML`.

> **Como isso é garantido (Bloco 3).** `python -m sim.demanda.gerar_rotas --cenario X --seed N` materializa `sim/saida/rotas/X_N.rou.xml` com veículos **concretos**, cujos instantes de partida saem de um `random.Random(seed)` próprio — não do `--seed` do SUMO. A escolha é deliberada: deixar o simulador sortear amarraria a garantia mais importante do experimento a um detalhe interno dele (qual gerador alimenta qual sorteio, e se a ordem de consumo muda quando o TraCI intervém). Com o arquivo materializado, a garantia é verificável com `diff`, e há teste conferindo que a mesma seed produz o mesmo arquivo byte a byte.
>
> As chegadas seguem processo de **Poisson** (intervalos exponenciais). Intervalos constantes produziriam um tráfego artificialmente regular, que forma menos fila para o mesmo fluxo médio — e subestimaria justamente o efeito que o trabalho quer medir.
>
> **Os VEs partem nos mesmos instantes em toda seed**, e com o mesmo rodízio de tipos e de criticidades (P20).
>
> **Exceção declarada: o cenário de treino `treino_multiplas` (10.2).** Lá o atraso da segunda partida é sorteado por um gerador próprio, `Random("emergencias:<seed>")`, separado do gerador do fundo, para o modelo ver diferenças de ETA variadas. A exceção não toca nenhum cenário do experimento, e o pareamento entre braços de uma mesma seed continua garantido pelo arquivo materializado.
>
> **O cache de rotas só é reaproveitado se for idêntico ao que o código atual
> geraria** (P20, 2026-09-29). Antes, `garantir()` reaproveitava qualquer arquivo
> que existisse em `sim/saida/rotas/` — e os arquivos anteriores à P20, sem o
> parâmetro `criticidade`, fariam o lote rodar sem preempção nenhuma, sem erro.
> Como a geração é determinística, regenerar produz os mesmos bytes: o pareamento
> continua garantido, agora também contra mudanças no gerador. A seed varia o tráfego de fundo; o VE encontra um trânsito diferente a cada seed. Misturar as duas fontes de variação impediria atribuir a diferença medida ao controle.

```bash
python -m sim.controlador.lote \
    --cenarios leve,moderado,intenso,multiplas_emergencias \
    --modos FIXO,PREEMPCAO,PREEMPCAO_COMPENSADA,PREEMPCAO_ML \
    --seeds 1..50 \
    --duracao 3600 \
    --paralelo 4 \
    --saida analysis/data/
```

Com `libsumo` e 4 processos em paralelo, isso roda em algumas horas. Com `traci` + GUI, em dias. Rodar o lote com `libsumo` e headless.

> **Implementado no Bloco 4** (`sim/controlador/lote.py`), antecipado porque o
> piloto já são 60 execuções. A CLI é a de cima, com dois acréscimos: `--repetir
> MOTIVO`, que apaga do banco os pontos já gravados antes de reexecutar, e
> `--sem-banco`.
>
> **`--ajuste NOME=VALOR` (P17, 2026-10-01).** Substitui `ganho_compensacao_k` ou
> `n_ciclos_compensacao` sem editar `parametros.yaml` — nenhum outro parâmetro é
> ajustável. Exige `--sem-banco` (o snapshot de `execucao_simulacao` é o do YAML)
> e consolida numa subpasta de `--saida` com o rótulo do ajuste, porque os CSV
> não têm coluna de parâmetro. Existe para a calibração de E7
> (`python -m sim.calibracao.compensacao`); o Bloco 8 roda sem ajuste, com os
> valores congelados no YAML.
>
> **O lote paraleliza com processos `traci`, não com `libsumo`** — o módulo
> Python do `libsumo` não vem no instalador Windows (P15). O adaptador abstrai os
> dois (3.6), então trocar é passar `--libsumo` quando a decisão for tomada. O
> ganho perdido é menor do que os "10x" nominais sugerem: o adaptador lê o estado
> por **assinaturas**, ~4 chamadas de IPC por passo, e é o custo de IPC que o
> `libsumo` elimina. Medido em 8 núcleos físicos, com `--paralelo 6`: uma execução
> de 3.600 s leva ~1 min no `leve`, ~2 min no `moderado` e ~4 min no `intenso`.
>
> **O pareamento é garantido no processo pai.** Os arquivos de rota são gerados
> em série, antes de qualquer processo subir: dois trabalhadores correndo para
> escrever o mesmo `sim/saida/rotas/<cenario>_<seed>.rou.xml` produziriam um
> arquivo truncado, e o pareamento morreria em silêncio.
>
> **Cada execução escreve seus CSV na própria pasta**, e o pai consolida na ordem
> da matriz. Escrever direto no arquivo compartilhado intercalaria as linhas a
> cada `flush`, e a ordem mudaria a cada corrida — um `diff` entre duas corridas
> deixaria de significar nada.

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

> **Como o adaptador aplica os comandos (Bloco 3).** O TraCI oferece
> `trafficlight.setPhase()`, que **salta** para a fase pedida — usá-lo violaria
> I2 e I3 na primeira preempção. Em vez disso, `backend/adapters/sumo/adaptador.py`
> roda a máquina de estados de `core/priorizacao/fases.py` (a mesma que o
> property-based testing exercita e que o firmware do UNO reimplementa em C++) e
> empurra para o SUMO a *state string* correspondente ao estado resultante. Os
> invariantes passam a valer na simulação pela mesma construção que os faz valer
> na bancada.
>
> No modo `FIXO` o adaptador **não escreve nada** no simulador, mas continua
> reconstruindo o mesmo `EstadoControlador` a partir da fase observada. Com isso
> o verificador de invariantes e o coletor de transições rodam idênticos nos três
> braços, e o relatório pode afirmar "zero violações" sobre o baseline com a mesma
> evidência que sobre o proposto — em vez de deixar o controle sem auditoria.

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
├── fluxo_saturacao.csv                # medição da entrega 3.0, por faixa
├── calibracao_cenarios.csv            # v/c derivado por cenário
├── execucoes.csv                      # 1 linha por execução (650 linhas)
├── ve_por_execucao.csv                # 1 linha por VE por execução
├── transversal_por_execucao.csv       # fila máxima por aproximação
├── latencias.csv                      # 1 linha por decisão — só execução exemplar
├── conflitos_por_execucao.csv         # 1 linha por episódio de disputa entre VEs
└── descartes.csv                      # execuções reprovadas e reexecuções, com motivo
```

> **`conflitos_por_execucao.csv` é a entrega 10.1** (Bloco 10, 2026-09-10). Uma
> linha por **episódio**: uma disputa contígua no mesmo cruzamento entre o mesmo
> conjunto de VEs, e não uma linha por passo — a definição está em `context/01`
> §5.2, e a razão é que há **uma** escolha a fazer por episódio, que é a escolha
> que a política aprendida de P19 vai tomar. Traz o instante, o cruzamento, os
> VEs com tipo, ETA e fase demandada, e se a escolha estava em aberto ou suspensa
> pela guarda de "preempção em curso vence". Os agregados
> (`eventos_conflito`, `eventos_conflito_decidiveis`, `passos_em_conflito`) vão em
> `execucoes.csv` de toda execução, e `python -m analysis.resumo_conflitos` lê os
> dois. Cenários de um VE só produzem zero linhas, o que é resultado e não falha.
>
> **Duas colunas novas em 2026-09-29 (P20):** `criticidades` (uma por VE, na
> ordem de `ids_veiculos`) e `mesmo_nivel` (1 se todos os VEs da disputa têm a
> mesma criticidade). Só as disputas de mesmo nível são decididas pelo modelo de
> P19 — as demais a regra de criticidade decide nos dois braços —, então é essa
> coluna que a análise de H4 estratifica. Os dados de
> `analysis/data/bloco10_conflitos/` são anteriores e não a têm; o resumo os lê
> assim mesmo, marcando a informação como indisponível.
>
> **Mais duas colunas em 2026-10-07 (entrega 10.7):** `decidida_pelo_modelo`
> (1 se o modelo de P19 decidiu a disputa em algum passo do episódio) e
> `modelo_divergiu_do_e8` (1 se, em algum desses passos, ele escolheu diferente
> do que o E8 determinístico escolheria). Só podem valer 1 no braço
> `PREEMPCAO_ML`. São o denominador que `context/07` §3.3.1 pede: nem toda
> disputa de mesmo nível chega ao modelo, porque a guarda de oscilação, o
> timeout de E6 e os pedidos pela mesma fase a desviam antes. A comparação com o
> E8 é feita pelo coletor, fora do trecho cronometrado. Com elas o cabeçalho
> muda de novo, e os CSV de `analysis/data/bloco10_*` não aceitam linhas novas,
> pela guarda abaixo.
>
> **Nenhum CSV aceita linhas com cabeçalho diferente do seu** (P20). Tanto o
> coletor, ao escrever a pasta de uma execução, quanto `consolidar()`, ao juntar
> as execuções em `analysis/data/`, comparam o cabeçalho antes de escrever e
> falham com `CabecalhoDivergenteError` se ele mudou. Antes, acrescentar linhas de
> 25 colunas a um `execucoes.csv` de 22 corrompia o arquivo em silêncio — o risco
> que P19 registrou ao ganhar três colunas, e que este acréscimo repetiria.

> **`descartes.csv` é entregue pelo lote** (Bloco 4). Só execução **válida** entra
> nos cinco primeiros arquivos; a que `validar_execucao()` reprova fica na
> própria pasta de `sim/saida/`, com a evidência bruta, e o motivo vai para
> `descartes.csv` junto com o caminho dessa pasta. O arquivo registra também as
> remoções feitas por `--repetir`, que é como se apaga a linha de
> `execucao_simulacao` que a restrição única bloqueia. É a prova documental que
> `context/06` §4 exige.

A saída bruta do SUMO (`tripinfo.xml`, `summary.xml`, `colisoes.xml`,
detectores) fica em `sim/saida/<cenario>_<modo>_<seed>/`, fora do Git.

> **`queue.xml` ficou de fora do padrão** (decisão de 2026-08-25). O SUMO grava
> `queue` e `summary` a **cada passo**; com passo de 0,1 s isso são 36.000
> amostras por execução, e a primeira execução completa produziu **77 MB de
> `queue.xml`** — ~46 GB nas 600 do Bloco 8, para um dado que os detectores E2 já
> cobrem e que o coletor já acumula como fila máxima. `summary` passou a ser
> agregado a cada 60 s. Quem precisar do detalhe para depurar uma execução roda
> com `--saida-detalhada`.
>
> Efeito: a saída bruta de uma execução caiu de ~88 MB para ~1,5 MB.

> **`latencias.csv` detalhado só em execução exemplar.** São 36.000 decisões por
> execução — mais de 20 milhões de linhas nas 600 do Bloco 8. É a mesma aritmética
> da decisão P5. Os percentis, que são o que RNF01 e H3 exigem, vão em
> `execucoes.csv` de **toda** execução.
>
> **E `latencias.csv` é o único CSV de `analysis/data/` que NÃO é versionado**
> (decisão de 2026-08-26). Mesmo restrito às exemplares ele dá 13 MB, e o lote o
> reescreve inteiro a cada corrida — cada reexecução acrescentaria ~1,3 MB
> permanentes à história do repositório. Seu único consumidor é a figura **F2**
> (`context/07` §5, histograma + CDF da latência de decisão); os números que vão
> ao **texto** são os percentis, que ficam em `execucoes.csv`.
>
> **Ressalva para quem for gerar F2 no Bloco 9:** latência é a única grandeza
> deste experimento que **não** é reprodutível a partir da seed — é relógio de
> parede e depende da máquina e da carga. Regerar F2 dá uma distribuição
> equivalente, não idêntica. Se a figura precisar ser estável entre gerações, o
> caminho é o pipeline de análise emitir um resumo por quantis (~1.000 linhas por
> execução exemplar, algumas centenas de KB) e **esse** ser versionado.

Esses CSVs são o insumo de `07-resultados-e-analise.md`. Devem ser regeneráveis do zero com um comando.

## 11. Detectores necessários no `.add.xml`

- **E2 (lanearea)** em cada acesso de cruzamento, 100 m antes da linha de retenção → fila e ocupação.
- **E1 (induction loop)** na saída de cada cruzamento → throughput.
- **E3** no eixo arterial completo → tempo de viagem por trecho.

Sem os detectores não há como medir o impacto transversal, e H2 fica sem evidência.

> **Implementado (entrega 3.2).** `sim/rede/detectores.py` **gera**
> `malha.det.add.xml` a partir da rede: 48 laneArea (uma por faixa de
> aproximação), 48 induction loops (uma por faixa de saída) e 12 entryExit (um
> por trecho interno da arterial, por sentido). Gerar em vez de escrever à mão
> não é preguiça: os ids de faixa vêm do `.net.xml`, e mantê-los à mão
> significaria reescrever uma centena de linhas a cada mudança de geometria — com
> a garantia de esquecer uma.
>
> Os E2 servem a **dois consumidores diferentes**, e vale saber qual é qual: em
> tempo real o adaptador lê `getLastStepHaltingNumber` por assinatura para montar
> `EstadoSemaforo.fila_por_acesso` (entrada do motor, portanto insumo de E7); em
> lote, os arquivos agregados alimentarão `metrica_via_transversal`.
>
> O executor **copia** o `.add.xml` para dentro da pasta da execução. O SUMO
> resolve o `file` de cada detector relativo a quem o declara, e a opção
> `output-prefix` é prefixada ao nome já resolvido — o que quebra com caminho
> absoluto. Com a cópia, cada execução fica com sua própria saída sem nenhuma
> opção extra.

## 12. Validação da malha antes de experimentar

Antes de rodar as 650 execuções, verificar:

1. `netconvert` sem warnings de conexão inválida.
2. Rodar 600 s com fluxo leve e `--collision.action warn` — zero colisões no baseline.
3. Nenhum veículo teleportado (`--time-to-teleport -1` para desabilitar teleporte e expor gridlocks reais; se houver teleporte, a demanda está mal calibrada e os resultados serão inválidos).
4. Grau de saturação medido bate com o pretendido para cada cenário (v/c ratio nos acessos).

Um gridlock não detectado invalida silenciosamente todo o experimento. Este passo não é opcional.

> **Automatizado (entrega 3.4):**
>
> ```bash
> make validar CENARIO=leve          # ou:
> python -m sim.validacao.malha --cenario leve
> python -m sim.validacao.malha --todos
> ```
>
> Os quatro itens viraram código. O item 1 sai de graça (o construtor trata aviso
> do netconvert como erro); os itens 2 e 3 saem de uma execução no baseline; o
> item 4 confronta o **v/c medido** — fluxo contado nos laços E1, descartado o
> aquecimento — com o **v/c derivado** da calibração, dentro de uma tolerância
> declarada de **10%**.
>
> Os 10% cobrem o que separa legitimamente os dois números: a execução é finita,
> as chegadas são um processo de Poisson com variância própria, e o descarte do
> aquecimento não cai exatamente na virada do regime. Desvio maior não é ruído — é
> a malha operando em regime diferente do previsto.
>
> **Primeira execução, 2026-08-25, cenário `leve` (1.200 s):** v/c derivado 0,182
> contra medido 0,186 na arterial e 0,194 na transversal. Zero colisão, zero
> teleporte, zero violação de invariante no baseline. **Malha aprovada** — e com
> isso a cadeia de P11 fecha: saturação medida → capacidade → v/c derivado → v/c
> medido na malha completa.
>
> A verificação estrutural de **cada execução** (`context/06` §4) é outra coisa e
> mora em `sim/validacao/execucao.py`: ela roda em toda execução do lote e reprova
> o que não pode entrar na análise.
