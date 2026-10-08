# 10 — Inteligência artificial e aprendizado de máquina no projeto

Este arquivo reúne num só lugar **onde há IA no trabalho e como o modelo de
aprendizado de máquina é usado**. Serve para explicar o assunto para a equipe, o
orientador e a banca sem precisar garimpar a pendência P19.

**Este arquivo explica, mas não decide.** As decisões e as justificativas
completas continuam registradas em `09-pendencias-e-decisoes.md` (P19, P20 e a
tabela "Decisões tomadas"). Os números vêm dos CSV e relatórios em
`analysis/data/`, gerados pelos comandos da §11. Se algo aqui divergir do `09`
ou dos dados, quem vale é o `09` ou os dados, e este arquivo tem de ser
corrigido.

---

## 1. Onde há IA no trabalho, e onde não há

O trabalho usa IA em **duas camadas**, e deixa outras decisões de propósito
**fora** de qualquer modelo estatístico:

| Camada | Técnica | Onde | Aprende com dados? |
| --- | --- | --- | --- |
| Motor de decisão (E1–E7, e E8 no braço determinístico) | **Agente reativo** com otimização determinística baseada em conhecimento (Russell & Norvig) | `backend/core/priorizacao/` | Não |
| Escolha entre VEs em conflito, **de mesmo nível de criticidade** (E8 no braço `PREEMPCAO_ML`) | **Aprendizado supervisionado**: regressão logística par a par | `analysis/treino_politica.py` (treino) e `backend/config/politica_desempate.yaml` (pesos) | **Sim** |

**Decidido por regra declarada, sem ML, de propósito:**

- **Se há emergência de fato.** É preciso tag reconhecida **e** ocorrência ativa
  aberta pela central (P20). É autenticação: tem de ser auditável e não pode ter
  falso negativo estatístico.
- **Qual emergência importa mais.** A criticidade da ocorrência (1 `RISCO_VIDA`,
  2 `RISCO_COLETIVO`, 3 `URGENCIA`) é decisão normativa, e não se aprende de
  dado de trânsito (P20).
- **Guarda de oscilação.** Com preempção em curso, ela vence dentro do mesmo
  nível. Fica fora do modelo para que as invariantes I4 e I5 não dependam do que
  ele aprendeu (P19).
- **Invariantes de segurança** (`01` §6). Nenhuma passa pelo modelo.

**O que não é IA neste trabalho**, para evitar confusão na banca:

- **Não há modelo de linguagem (LLM).** "Agente" aqui é *agente reativo* no
  sentido de Russell & Norvig, sem relação com agentes de LLM ou com orquestração
  de modelos de linguagem.
- **Q-learning na compensação (E7)** é trabalho futuro e não foi implementado
  (`00` §8).
- **Detecção acústica de sirene** foi considerada e recusada (P20).

> **Frase de defesa:** *"a IA decide quem passa primeiro; se é emergência, e o que
> importa mais, são regras declaradas."*

## 2. Por que o ML entrou, e por que exatamente em E8

**Histórico.** Em 2026-08-24, a decisão P3 punha o aprendizado de máquina fora
de escopo e reservava a palavra "IA" ao agente reativo. Em 2026-09-10, o
orientador informou que a banca espera ML e indicou o ponto: decidir **qual VE é
priorizado** quando há mais de uma emergência simultânea. Isso revogou P3 e
abriu P19. O escopo não perdeu nada: o ML foi **acrescentado** como Bloco 10
(`docs/plano-desenvolvimento.md`).

**A lacuna que o modelo preenche — E8 é míope.** O desempate determinístico
decide um cruzamento por vez, num instante, por uma ordem fixa: criticidade,
depois tipo, depois menor ETA, depois preempção em curso (`01` §5.2). Ele não
pesa a consequência adiante. Priorizar o VE A agora pode custar muito mais ao VE
B no cruzamento seguinte. A ordem fixa é uma convenção, não uma otimização.

Uma política aprendida pode pesar essa consequência. É isso que torna a entrega
**defensável, e não decorativa**: há uma lacuna real, e não se está apenas
vestindo de ML algo que já funcionava.

## 3. Ordem de decisão em E8, por braço

Quando dois VEs pedem **fases distintas** no mesmo cruzamento, um espera. Dois
VEs pedindo a mesma fase não são conflito, porque o mesmo verde serve os dois.

| Passo | `PREEMPCAO` (baseline de H4) | `PREEMPCAO_ML` (entregas 10.6 e 10.7) |
| --- | --- | --- |
| 1 | Criticidade: o nível mais crítico vence | Criticidade, **regra**: o nível mais crítico vence, inclusive sobre preempção em curso |
| 2 | Tipo (`AMBULANCIA > BOMBEIRO > POLICIA`) | Guarda de oscilação, **regra**: no mesmo nível, a preempção em curso vence |
| 3 | Menor ETA | **Modelo** |
| 4 | Preempção em curso vence | — |

**O modelo só atua entre VEs de mesmo nível de criticidade e sem preempção em
curso.** Por isso H4 é analisada estratificada por `mesmo_nivel`, e a análise
declara quantas disputas o modelo de fato decidiu (`07` §3.3.1). Desde a 10.7
isso é medido, e não estimado: `conflitos_por_execucao.csv` traz, por episódio,
`decidida_pelo_modelo` e `modelo_divergiu_do_e8` (§8).

**A guarda de oscilação também separa os braços.** Na tabela acima, o
`PREEMPCAO` só aplica "preempção em curso vence" depois de tipo e ETA, e o
`PREEMPCAO_ML` a aplica antes do modelo. Numa disputa de mesmo nível que abre
com preempção em curso, o E8 ainda pode trocar o verde de VE, e o braço de ML
não troca. As colunas acima contam só as decisões do modelo. Como tratar essa
diferença na análise de H4 é questão da 10.8.

**A garantia é por construção, e não por disciplina.** A política só *propõe* um
vencedor (`PoliticaDesempate`, em `core/priorizacao/conflito.py`). Quem decide é
`resolver`, que só aceita a proposta se ela for um dos pedidos **e** tiver a
criticidade mais alta entre eles.

**Como a 10.6 implementou a ordem** (`core/priorizacao/politica.py`, função
`decidir`). As duas regras vêm antes do modelo, no código, e não leem os pesos:

1. só os pedidos do nível mais crítico seguem; se sobra um, ele vence;
2. se um deles é o dono da preempção em curso no cruzamento, ele vence;
3. se todos os que sobraram pedem a **mesma fase**, não há conflito (o mesmo
   verde serve todos), e a política devolve `None`, para o E8 de sempre decidir;
4. senão, o modelo decide, por torneio (§4).

O modelo só é consultado no passo 4. Os atributos dos VEs também só são
calculados ali.

**Por que a criticidade pode passar por cima da preempção em curso sem
oscilar:** A só toma o verde de B se `crit(A) < crit(B)`, e então B nunca o toma
de volta. São no máximo duas trocas por episódio (3 → 2 → 1), cada uma pela
transição segura de E5.

## 4. O modelo

### Forma: comparação par a par sobre diferenças

```
score = Σ pesos[a] · (x_A[a] − x_B[a])      escolhe A se score > 0, senão B
```

Com três ou mais VEs, a disputa se resolve por torneio. Nos cenários medidos até
agora, porém, toda disputa foi entre dois VEs.

**O torneio é todos-contra-todos, e vence o invicto**, o VE que nenhum outro
bate. Como o score é linear, `score(A, B) = s(A) − s(B)` com `s(X) = pesos · x_X`,
então o invicto é o VE de maior `s`, e não há ciclo possível: a ordem em que os
pedidos chegam não muda o vencedor.

**Empate exato** (`score = 0`, na prática só com os quatro atributos iguais): o
modelo não tem preferência, e decide a chave do E8 **entre os empatados** (tipo,
depois ETA). Decisão da equipe em 2026-10-07. Seguir "senão B" ao pé da letra
faria o vencedor depender da ordem de apresentação, justamente o que a forma do
modelo existe para impedir. Nos 652 exemplos rotulados nenhum score sai zero, e o
desempate não age sobre eles. O treino (10.5) contou `score = 0` como B ao medir
o acerto, o que, pelo mesmo motivo, não altera nenhum número de lá.

**Por que diferenças, e sem intercepto.** Um modelo que recebesse os dois vetores
soltos poderia preferir A a B *e* B a A conforme a ordem em que fossem
apresentados, e isso apareceria como oscilação na rua. Sobre diferenças, e sem
termo constante, `score(B, A) = −score(A, B)` **por construção**. O modelo não
precisa aprender essa propriedade: ele não consegue violá-la.

**Por que regressão logística.** Ela exporta como um vetor de quatro números, a
inferência é um produto escalar em Python puro dentro de `core/`, e cada peso
pode ser lido e explicado na banca.

### Entrada: quatro atributos, como diferença A − B

Calculados em `core/priorizacao/atributos.py`. A **mesma função** serve à
rotulagem e à inferência, para que o modelo não seja treinado sobre uma coisa e
consultado sobre outra.

| Atributo | O que é | Por quê |
| --- | --- | --- |
| `eta_s` | Tempo estimado até a linha de retenção do cruzamento disputado | Quando cada um chega |
| `velocidade_ms` | Velocidade atual | Substitui `distancia_m`, que seria quase colinear com o ETA |
| `fila_por_faixa` | Veículos parados no acesso do VE, divididos pelas faixas | A fila que o VE tem à frente, a mesma que E3 usa (P16) |
| `cruzamentos_restantes` | Cruzamentos semaforizados que o VE ainda vai atravessar, incluindo o disputado | Dá caráter sequencial à decisão |

**Fora do vetor, e por quê:**

- `distancia_m`: redundante com `eta_s`.
- `preempcao_em_curso`: não informa a decisão, ela a **suspende**, e é regra
  acima do modelo.
- `tipo`: saiu em 2026-09-29 (P20). Sob um rótulo em tempo, o peso do tipo só
  captaria diferenças de dinâmica entre os `vType`, e não relevância. A
  relevância virou criticidade, que é regra.

### Critério: minimax sobre o tempo dos VEs

```
escolha = argmin( max(tempo_travessia_A, tempo_travessia_B) )
```

O critério minimiza o tempo do **VE mais prejudicado**. Foi declarado em
2026-09-10, antes de qualquer treino. As alternativas recusadas:

- **Soma dos tempos:** aceitaria atrasar muito um VE para ganhar pouco no outro,
  e esse VE pode ser a ambulância.
- **Atraso total da rede:** poderia atrasar uma ambulância para favorecer o
  tráfego de fundo, o que contradiz a premissa do trabalho. O custo transversal
  continua medido e reportado, mas não entra na troca.
- **Minimax ponderado por tipo:** exigiria pesos numéricos por tipo, sem lastro
  para justificá-los.

## 5. De onde vêm os dados

### Cenário de treino separado do de avaliação

O cenário de avaliação (`multiplas_emergencias`) rendeu **85 disputas decidíveis**
em 10 execuções, abaixo do piso de 100 que P19 declarou (entrega 10.1, remedida
em 2026-10-05). Por isso foi criado um cenário só de treino, o `treino_multiplas`
(entrega 10.2, em `cenarios_treino` de `sim/config/cenarios.yaml`). Ele usa as
mesmas rotas e o mesmo tráfego de fundo da avaliação, com três diferenças:

- um par de VEs a cada 300 s, e não a cada 600 s;
- atraso da segunda partida sorteado por par, em [0, 20] s, para o ETA variar;
- tipo e criticidade desacoplados: criticidade em rodízio `[1, 2, 3, 2]`, com
  um par a cada cinco de nível misto.

**Divisão por seed, fixada antes de qualquer rótulo:**

| Uso | Seeds | Cenário |
| --- | --- | --- |
| Treino | 201..240 | `treino_multiplas` |
| Validação (escolha de λ) | 241..250 | `treino_multiplas` |
| **Teste de H4** | 1..50 | cenários do experimento, no Bloco 8 |

O modelo **nunca vê** as seeds nem o cenário em que H4 é testada.

### Rótulos por bifurcação da simulação (entrega 10.4)

Para supervisionar é preciso saber qual escolha foi melhor, e isso se **mede**,
não se estima. Em cada disputa decidível de mesmo nível, a simulação é bifurcada
em dois ramos: um força A e o outro força B. Cada ramo roda até os dois VEs
chegarem, e o rótulo é o ramo com o melhor minimax.

- **Por que não rotular por heurística:** rotular por "menor ETA vence", por
  exemplo, ensinaria ao modelo a própria heurística. O resultado seria uma
  imitação cara de E8, e H4 não teria como ser superada nem refutada.
- **Como a bifurcação é feita:** cada ramo **reexecuta a seed do zero** até a
  disputa. O `saveState`/`loadState` do SUMO foi testado e descartado, porque o
  estado carregado não reproduzia a trajetória exatamente.
- **Fidelidade medida:** 668 de 668 disputas reencontradas no mesmo passo, com os
  mesmos VEs e ETAs, nos dois ramos.
- **Depois da escolha forçada**, decide o E8 determinístico. O rótulo responde
  "qual escolha é melhor agora, se o resto seguir a regra atual", que é
  exatamente a pergunta de H4.
- **Empates** de minimax ficam fora do treino e são contados.

| Grandeza | Treino | Validação |
| --- | ---: | ---: |
| Disputas bifurcadas | 529 | 139 |
| Rótulo A / B | 376 / 141 | 86 / 49 |
| Empates (fora do treino) | 12 | 4 |
| **Exemplos usados** | **517** | **135** |

Fonte: `analysis/data/bloco10_rotulos/`.

## 6. Treino e resultado (entrega 10.5)

**Como foi treinado:** regressão logística sem intercepto, ajustada por L-BFGS
(`scipy.optimize`), com perda e gradiente em numpy. Sem scikit-learn e sem
dependência nova. Cada exemplo pesa a margem do minimax entre as escolhas, para
que errar uma disputa que custa 30 s pese mais que errar uma que custa 1 s. A
regularização L2 teve λ escolhido na validação, numa grade declarada antes do
treino. Venceu λ = 0,01. O treino é determinístico: duas execuções deram arquivos
idênticos byte a byte.

**Pesos aprendidos**, nas unidades originais (`backend/config/politica_desempate.yaml`):

| Atributo (diferença A − B) | Peso | Peso sobre o atributo escalado |
| --- | ---: | ---: |
| `eta_s` | −0,0397 por s | −1,40 |
| `velocidade_ms` | −0,153 por m/s | −1,10 |
| `fila_por_faixa` | +0,0007 por veículo | +0,002 |
| `cruzamentos_restantes` | +0,523 por cruzamento | +1,83 |

**Em uma frase:** o modelo aprendeu a dar o verde ao VE com mais rota pela
frente, a menos que o outro esteja bem mais perto. A fila ficou com peso
praticamente nulo.

**Avaliação pela régua do rótulo** (o custo de uma escolha errada é a margem do
minimax daquela disputa):

| Política | Validação: acerto | Validação: custo médio |
| --- | ---: | ---: |
| **Modelo** | 66,7% | **4,30 s** |
| E8 como rodou no treino (decide por tipo) | 60,7% | 7,19 s |
| Menor ETA (o E8 que H4 vai enfrentar, pares de mesmo tipo) | 56,3% | 6,43 s |
| Sempre o VE do corredor | 63,7% | 4,83 s |

Fonte: `analysis/data/bloco10_treino/relatorio.md`.

### Como ler esses números, e o que eles não são

- **Não são resultado de H4.** Descrevem o modelo nas seeds de treino e
  validação. H4 só é testada no Bloco 8.
- **O ganho se concentra no segundo encontro (CRUZ_08).** Na validação, ali o
  modelo custa 0,53 s, contra 7,61 s do E8 e 7,25 s do menor ETA. No primeiro
  encontro (CRUZ_02), o modelo (6,82 s) empata com o E8 (6,90 s) e **perde para
  o menor ETA** (5,88 s). É resultado a declarar, não a esconder.
- **O modelo fica perto de "sempre o corredor".** Em 517 de 517 exemplos de
  treino, o VE mais prejudicado no ramo vencedor é o do corredor, que tem a
  viagem mais longa. `cruzamentos_restantes` funciona, neste cenário, como um
  indicador de corredor, e os outros atributos acrescentam pouco: 4,30 s contra
  4,83 s na validação.
- **Transferência não garantida.** Em pares com outra geometria, a forma da regra
  provavelmente se manteria (mais rota restante pesa a favor), mas nada garante
  que o peso se transfira.

## 7. Como o modelo roda no sistema

**Treinado fora, exportado como dado.** O modelo não é um serviço nem um
framework dentro do motor. São quatro números num YAML versionado:

```
rotulos.csv ──► analysis/treino_politica.py ──► backend/config/politica_desempate.yaml
                (numpy + scipy, offline)          (pesos, λ, seeds, escala, sha256 dos rótulos)
                                                        │  lido em adapters/configuracao.py
                                                        │  (carregar_politica)
                                                        ▼
                    core/priorizacao/politica.py: score = Σ pesos · (x_A − x_B)
                    (PoliticaAprendida, no ponto PoliticaDesempate do motor)
```

Isso preserva três decisões já tomadas:

1. **O motor é agnóstico ao atuador** (`01` §1). O `core/` não importa
   framework nem lê arquivo, e `test_arquitetura.py` continua verde. *(Até
   2026-10-07 este item dizia "o mesmo motor roda na simulação e no protótipo".
   Isso deixou de valer em 2026-10-05: o UNO decide sozinho, como diz o
   parágrafo logo abaixo e `00` §3.)*
2. **RNF01 (< 100 ms).** A inferência é um produto escalar de quatro termos, e
   fica dentro de `motor.avaliar()`, no trecho cronometrado. `test_desempenho.py`
   mede o p95 com o modelo consultado em todo passo.
3. **Reprodutibilidade.** O YAML guarda o `sha256` de `rotulos.csv`. O teste
   `test_pesos_versionados_saem_do_treino_sobre_os_rotulos_versionados` refaz o
   treino e confere os pesos. Ninguém edita os pesos à mão. E
   `test_inferencia_do_core_escolhe_como_o_treino_em_todos_os_rotulos` confere
   que a inferência do `core/`, com os pesos lidos por `adapters/`, escolhe como
   o treino nos 652 exemplos: o modelo consultado é o que foi treinado.

**Na bancada física, o modelo não roda.** O UNO decide localmente por
criticidade e ordem de chegada (`05` §3.3). O ML é avaliado só na simulação, onde
há múltiplos VEs em rotas que se cruzam.

## 8. Como será avaliado: H4

> **H4:** uma política aprendida para escolher entre VEs em conflito **reduz o
> tempo de travessia do VE mais prejudicado**, em cenários com múltiplos VEs, em
> relação ao desempate determinístico de E8.

- Formulada em 2026-09-10, **antes de qualquer treino** (`00` §5).
- **Braço `PREEMPCAO_ML` contra `PREEMPCAO`**, pareado por seed (1..50), nos
  cenários com múltiplos VEs, no lote do Bloco 8. Hoje o único é o
  `multiplas_emergencias`: são 50 execuções a mais, 650 no lote (decisão da
  equipe, 2026-10-07).
- **O braço é o `PREEMPCAO` com o modelo, sem E7** (decisão da equipe,
  2026-10-07). A política é a única diferença entre os dois:
  `executor.montar_motor()` dá a `PoliticaAprendida` só ao `PREEMPCAO_ML`, e
  `parametros_do_modo()` o deixa com `n_ciclos_compensacao = 0`.
- **Sem meta percentual.** É hipótese comparativa direcional. Inventar um
  percentual seria fabricar régua. A avaliação usa Wilcoxon pareado, Cliff's δ e
  IC 95% por bootstrap, com o mesmo rigor de H1.
- **Estratificada por `mesmo_nivel`**, declarando quantas disputas o modelo de
  fato decidiu (`07` §3.3.1). Por episódio, `decidida_pelo_modelo` diz se o
  modelo decidiu em algum passo, e `modelo_divergiu_do_e8` se, em algum deles,
  escolheu diferente do E8. Um episódio sem divergência decorreu igual nos dois
  braços no que dependeu do modelo. A comparação com o E8 é feita pelo coletor,
  fora do trecho cronometrado do RNF01.
- **Veredito nulo é veredito.** Se o modelo não superar o E8, isso é reportado
  com tamanho de efeito e intervalo de confiança. O que não pode acontecer é o
  modelo entrar sem avaliação, só para cumprir a expectativa.

## 9. Estado atual

| Entrega | O quê | Estado |
| --- | --- | --- |
| 10.1 | Contar disputas no cenário de avaliação | ✅ 105 disputas, 85 decidíveis (rota nova) |
| 10.2 | Cenário de treino mais denso | ✅ 529 / 139 disputas de mesmo nível |
| 10.3 | Declarar o critério (minimax) antes de treinar | ✅ 2026-09-10 |
| 10.4 | Rotulagem por bifurcação | ✅ 517 / 135 exemplos |
| 10.5 | Treino e exportação dos pesos | ✅ `politica_desempate.yaml` |
| 10.6 | Inferência pura em `core/priorizacao/` | ✅ `politica.py` (2026-10-07); nenhum número dos braços existentes muda |
| 10.7 | Braço `PREEMPCAO_ML` no executor e no lote | ✅ 2026-10-07: só no `multiplas_emergencias` (650 execuções no Bloco 8), sem E7, com quem decidiu cada disputa registrado; nenhum número dos braços existentes muda |
| 10.8 | Análise estatística de H4 | ⏳ por fazer (depois do Bloco 8) |

Atualizar esta tabela no mesmo commit de cada entrega, junto com
`docs/plano-desenvolvimento.md` e o `09`.

## 10. Limitações a declarar no texto

- **Na simulação, a criticidade é atribuída pelo cenário**, não por uma
  ocorrência real. É ameaça à validade de construção (`07` §7).
- **Uma única geometria de encontro.** O treino usa as mesmas rotas da
  avaliação, de propósito (o modelo treina no tipo de encontro em que é testado).
  Por isso ele aprendeu sobretudo "o corredor primeiro", e não há garantia de
  que generalize para outra malha.
- **Rótulo desbalanceado:** A, o VE do corredor, vence em 73% do treino.
- **Exceção declarada ao pareamento:** no `treino_multiplas`, o atraso da segunda
  partida depende da seed. Vale só no treino, onde não há comparação entre braços
  a parear.
- **Rotulagem cara:** cerca de 4,5 h de máquina para as 50 seeds. Foi feita uma
  vez, e o resultado está versionado.
- **Ressalva de versão em `rotulos.csv`:** a coluna `versao_codigo` traz
  `48fff16`, mas o lote rodou com a rotulagem ainda não commitada. O código de
  `sim/` e `backend/` não mudou até o commit da 10.4 (`09` P19).

## 11. Onde está cada coisa

| O quê | Onde |
| --- | --- |
| Decisões e justificativas completas | `09-pendencias-e-decisoes.md`, P19 e P20 |
| E8 e o ponto de entrada da política | `backend/core/priorizacao/conflito.py` (`PoliticaDesempate`, `resolver`) |
| Inferência e as regras acima do modelo | `backend/core/priorizacao/politica.py` (`PoliticaAprendida`, `decidir`, `ConsultaModelo`) |
| O braço `PREEMPCAO_ML` | `sim/controlador/executor.py` (`montar_motor`, `parametros_do_modo`), `sim/controlador/lote.py` (`matriz`) |
| Quem decidiu cada disputa | `sim/controlador/coletor.py` (`registrar_consultas`), colunas de `conflitos_por_execucao.csv` |
| Carga dos pesos | `backend/adapters/configuracao.py` (`carregar_politica`) |
| Atributos do modelo | `backend/core/priorizacao/atributos.py` |
| Cenário de treino | `sim/config/cenarios.yaml` (`cenarios_treino`), `sim/demanda/gerar_rotas.py` (`partidas_de_treino`) |
| Rotulagem | `sim/controlador/rotulagem.py` |
| Treino | `analysis/treino_politica.py` |
| Pesos | `backend/config/politica_desempate.yaml` |
| Dados | `analysis/data/bloco10_conflitos_rota_nova/`, `bloco10_treino_volume/`, `bloco10_rotulos/`, `bloco10_treino/` |
| H4 | `00` §5, `07` §3.3.1 e T6 |

**Reproduzir a cadeia inteira:**

```bash
# 10.1 — disputas no cenário de avaliação
python -m sim.controlador.lote --cenarios multiplas_emergencias --modos PREEMPCAO \
    --seeds 101..110 --paralelo 6 --sem-banco --saida analysis/data/bloco10_conflitos_rota_nova
# 10.2 — volume do cenário de treino
python -m sim.controlador.lote --cenarios treino_multiplas --modos PREEMPCAO \
    --seeds 201..250 --paralelo 6 --sem-banco --saida analysis/data/bloco10_treino_volume
# 10.4 — rótulos por bifurcação (~4,5 h)
python -m sim.controlador.rotulagem --seeds 201..250 --paralelo 6 \
    --saida analysis/data/bloco10_rotulos
# 10.5 — treino e pesos
python -m analysis.treino_politica --relatorio analysis/data/bloco10_treino/relatorio.md
# 10.7 — o braço, no lote do Bloco 8 (o lote tira o PREEMPCAO_ML dos cenários de um VE)
python -m sim.controlador.lote --modos FIXO,PREEMPCAO,PREEMPCAO_COMPENSADA,PREEMPCAO_ML \
    --seeds 1..50 --paralelo 6 --saida <pasta própria do Bloco 8>
```

## 12. Perguntas prováveis da banca

| Pergunta | Resposta curta | Onde aprofundar |
| --- | --- | --- |
| "Onde está a IA?" | Em duas camadas: o motor é um agente reativo (IA clássica), e a escolha entre VEs de mesmo nível é aprendida | §1 |
| "Por que não usar ML para tudo?" | Confirmar a emergência e definir o que importa mais são decisões de segurança e normativas. Precisam ser auditáveis e não se aprendem de dado de trânsito | §1, P20 |
| "Por que regressão logística e não uma rede neural?" | Com 517 exemplos e 4 atributos, um modelo maior não se justifica. Os pesos são explicáveis, a antissimetria sai por construção e a inferência cabe no RNF01 | §4 |
| "De onde vem o 'certo' para treinar?" | Da consequência medida: a simulação é bifurcada, e as duas escolhas são rodadas | §5 |
| "O modelo não está só decorando 'o corredor primeiro'?" | Em boa parte, sim, e isso está declarado. É o que o minimax pede neste cenário, e o ganho se concentra no segundo encontro | §6 |
| "E se o modelo não for melhor que a regra?" | O resultado é nulo, e é reportado com tamanho de efeito e IC. H4 não tem meta inventada | §8 |
| "O modelo pode causar um verde conflitante?" | Não. Ele só propõe; `resolver` valida a proposta, e as invariantes ficam fora do modelo | §3, `01` §6 |
| "Por que não aprendizado por reforço?" | P19 preferiu o supervisionado por custo e explicabilidade, e deixou Q-learning como alternativa. Na compensação (E7), Q-learning é trabalho futuro | §1, P19 |
