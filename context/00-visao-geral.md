# 00 — Visão Geral do Projeto

## 1. Identificação

| Campo | Valor |
| --- | --- |
| Título | Modelo Inteligente de Controle Dinâmico de Semáforos Baseado em Dados de Tráfego para Priorização de Veículos de Emergência em Ambientes Urbanos |
| Instituição | Universidade Paulista (UNIP) — Instituto de Ciências Exatas e Tecnologia |
| Curso | Bacharelado em Ciência da Computação |
| Orientador | Prof. Marco Gomes |
| Equipe | Felipe Rafael Tancredi Pascucci (T895HG3), Giovanna Santos da Silva (G828HA5), Isabelle Rosa Moura Ferreira (N075465) |
| Ano | 2026 |

## 2. Problema

Congestionamento urbano atrasa a chegada de ambulâncias, viaturas policiais e veículos do Corpo de Bombeiros. Semáforos de tempo fixo não reagem ao tráfego real, e sistemas atuados tradicionais respondem apenas ao próprio cruzamento, sem coordenação na malha.

## 3. Proposta

Sistema que detecta o veículo de emergência (VE) na aproximação, calcula quais semáforos da rota devem ser alterados e executa a preempção semafórica de forma coordenada, criando um corredor verde ("onda verde") à frente do veículo — e, após a passagem, compensa o ciclo para reduzir o impacto nas vias transversais.

A validação ocorre em **duas frentes complementares**:

- **Frente A — Simulação (SUMO + TraCI):** produz os dados quantitativos que sustentam as hipóteses. É a fonte dos resultados estatísticos do TCC.
- **Frente B — Protótipo físico (Arduino + ESP8266 + RFID):** prova de conceito tangível da camada V2I e do atuador semafórico. É demonstração de viabilidade, **não** fonte de dados estatísticos.

O **motor de decisão** (`backend/core/priorizacao/`) é o objeto do experimento e controla a **simulação**. Ele é agnóstico ao atuador: o SUMO é um adaptador, e o motor não sabe que está numa simulação.

**O protótipo não roda o motor** (decisão de 2026-10-05). O controlador do cruzamento, o Arduino UNO, decide sozinho com uma regra local mais simples: prioridade por tipo de VE, fila de um lugar e verde exclusivo para a aproximação do VE. Ele cumpre os mesmos invariantes de segurança (I1 a I4). O VE é identificado por rádio (ESP-NOW), sem rede nem servidor, e o notebook só observa. Ver `05` §2.

> **O que o texto pode e não pode afirmar.** Pode: o protótipo demonstra a
> camada V2I por rádio, a atuação segura em hardware real e a latência dessa
> cadeia (H3). **Não pode** dizer que "o modelo validado em simulação é o mesmo
> que roda no protótipo" — a versão anterior deste parágrafo afirmava isso, e
> deixou de ser verdade quando a equipe adotou a arquitetura já montada na
> bancada em vez de remontá-la. A equipe preferiu adaptar o sistema ao hardware
> pronto. O motor continua sendo avaliado onde os dados estatísticos sempre
> estiveram, na Frente A.

## 4. Objetivos

**Geral:** desenvolver e validar um modelo de controle dinâmico de semáforos que priorize veículos de emergência, reduzindo seu tempo de travessia, e **quantificar o custo que essa priorização impõe ao fluxo transversal**.

> **Redação alterada em 2026-09-10, pela decisão de P18.** A formulação anterior
> dizia *"sem degradar de forma **inaceitável** o fluxo transversal"*, e a palavra
> nunca foi definida. O orientador decidiu que o trabalho **não declara teto
> numérico** e trata o custo transversal qualitativamente, na discussão. Um
> objetivo que promete um critério inexistente é mais frágil na arguição do que um
> que promete medição — então "sem degradar de forma inaceitável" (promessa sem
> régua) foi substituído por "quantificar o custo" (promessa que os dados
> cumprem). O trade-off deixa de ser ressalva e passa a ser objetivo declarado.
> Ver P18 em `09-pendencias-e-decisoes.md`.

**Específicos:**

1. Modelar uma malha urbana arterial simulada com 4 a 8 cruzamentos semaforizados.
2. Implementar o algoritmo de detecção e preempção com integração Python + TraCI.
3. Implementar a camada de identificação V2I (radar + RFID no protótipo físico).
4. Persistir eventos e métricas em PostgreSQL para auditoria e análise.
5. Disponibilizar dashboard web de monitoramento em tempo real.
6. Comparar estatisticamente o modelo proposto com o baseline de temporização fixa.
7. Demonstrar o funcionamento fim-a-fim no protótipo físico de 4 semáforos.

## 5. Hipóteses de pesquisa

| ID | Hipótese | Como será testada |
| --- | --- | --- |
| H1 | A fusão radar + V2I reduz em **no mínimo 25%** o tempo total de travessia do VE, em cenários de saturação **moderada a intensa**, em relação à temporização estática | Comparação pareada por seed, baseline vs. proposto. O cenário `leve` é medido e discutido, mas **sem meta numérica** |
| H2 | É possível mitigar em **no mínimo 15%** o impacto negativo nas vias transversais com compensação dinâmica de ciclo pós-evento | Três braços: baseline / preempção sem compensação / preempção com compensação. Mitigação = fração do **acréscimo** de espera transversal causado pela preempção, em `moderado` e `intenso` (P17) |
| H3 | A infraestrutura em borda sustenta latência operacional **fim-a-fim inferior a 200 ms** | Da **leitura da tag no veículo** até o **UNO decidir atuar** (`PREEMP_INI`), os dois instantes carimbados no relógio do notebook, medida no **protótipo**, em **100 passagens** (as do RNF05), critério sobre o **p95** (`05` §4.3; n decidido pelo grupo em 2026-10-06) |
| **H4** | Uma política aprendida para escolher entre VEs em conflito **reduz o tempo de travessia do VE mais prejudicado**, em cenários com múltiplos VEs, em relação ao desempate determinístico de E8 | Braço `PREEMPCAO_ML` contra `PREEMPCAO`, pareado por seed, nos cenários com múltiplos VEs. Mesmo rigor de H1: Wilcoxon pareado, Cliff's δ e IC 95% por bootstrap |

> **H4 formulada em 2026-09-10, antes de qualquer treino** (P19). O critério de
> otimização escolhido é **minimax**: minimizar o tempo do VE mais prejudicado.
> As alternativas foram consideradas e recusadas — a soma dos tempos aceitaria
> sacrificar sistematicamente um VE, e o atraso total da rede poderia atrasar uma
> ambulância para favorecer o tráfego de fundo, contradizendo a premissa do
> trabalho. O custo transversal continua **medido e reportado**, como o objetivo
> geral promete, mas não entra na troca.
>
> **H4 não tem meta percentual, e isso é correto** — diferente de H1 e H2, cujos
> números vêm do pré-projeto. É hipótese **comparativa direcional**, avaliada por
> significância e tamanho de efeito. Inventar um percentual agora seria fabricar
> régua.
>
> Fica registrado também que **veredito nulo é veredito**: se a política aprendida
> não superar a heurística, isso é reportado com tamanho de efeito e intervalo de
> confiança, não escondido.
>
> **Escopo da escolha aprendida, desde 2026-09-29 (P20).** A precedência entre
> VEs de **criticidade** diferente é regra declarada, não aprendida — o nível mais
> crítico vence nos dois braços. Os braços `PREEMPCAO` e `PREEMPCAO_ML` só podem
> diferir nas disputas entre VEs de **mesmo nível**. O enunciado de H4 não muda,
> mas a análise é estratificada por `mesmo_nivel` e declara quantas disputas o
> modelo de fato decidiu (`07` §3).

> **Decisões P1 e P2 tomadas em 2026-08-24** (ver `09-pendencias-e-decisoes.md`):
>
> - **H1 é condicionada à saturação.** A Tabela 1 do próprio pré-projeto mostra 8,3% em fluxo leve; nenhuma meta única sobrevive aos quatro cenários. Meta: ≥ 25% em `moderado` e `intenso`.
>
> **Saturação medida, a partir do Bloco 3** (2026-08-25, ver `04` §5 e `09`): os
> cenários operam a v/c de **0,18** (`leve`), **0,42** (`moderado`) e **0,73**
> (`intenso`). Os dois cenários em que a meta de H1 se aplica ficam, portanto, em
> saturação moderada e moderada-alta. Os nomes dos cenários são rótulos do ponto
> experimental; a caracterização do regime é o v/c medido, e é ele que vai no
> texto.
> - **RNF01 e H3 medem coisas diferentes e coexistem.** RNF01 (< 100 ms) é a latência de *decisão* — do estado recebido à emissão do comando, software puro. H3 (< 200 ms) é a latência *fim-a-fim* — da detecção física à atuação, incluindo rede. Instrumentar as duas separadamente em `metrica_latencia`, reportando p95 e p99 de ambas.

> **Decisões de 2026-08-31** (ver `09-pendencias-e-decisoes.md`):
>
> - **H2 passa de "em até 15%" para "em no mínimo 15%".** A redação antiga era um
>   teto, não uma meta: sob ela, a mitigação de −1,0% a +0,6% medida no piloto do
>   Bloco 4 **cumpriria** a hipótese literalmente. `≥ 15%` é simétrico com H1 e é a
>   única leitura sob a qual H2 pode ser rejeitada. **O denominador foi fixado em
>   2026-10-01 (P17):** os 15% incidem sobre o *acréscimo* de espera transversal
>   que a preempção causou, em `moderado` e `intenso`.
> - **A evidência de H3 vem do protótipo, com 100 passagens** (decisão do grupo
>   de 2026-10-06; antes eram 5 repetições). Na simulação `t_atuacao` é o mesmo
>   passo de `t_decisao` — não há atuação física a cronometrar —, então o número
>   de H3 só existe na bancada. Com n = 100 o p95 é estimável: os 200 ms são
>   verificados sobre ele, e mín/mediana/máx vão ao lado, com o n.
> - **A meta de H1 no cenário `intenso` não foi atingida no piloto** (18,1% contra
>   25%). A equipe decidiu **corrigir o mecanismo antes de mexer na hipótese**;
>   reformular H1 é contingência, e passa pelo orientador. Ver P16.

## 6. Requisitos funcionais (do pré-projeto)

| Código | Requisito | Critério de aceitação |
| --- | --- | --- |
| RF01 | Identificar veículos de emergência | Detectar VE em até 500 m do cruzamento |
| RF02 | Priorizar automaticamente a rota emergencial | Alterar semáforos em até 3 s a partir da detecção, medidos **da detecção até o início da atuação** (decisão P14) |
| RF03 | Liberar corredores prioritários | Garantir passagem contínua (VE não para em cruzamento priorizado) |
| RF04 | Exibir o estado dos semáforos | Atualização em tempo real no dashboard |
| RF05 | Registrar eventos no banco | Registro automático de logs de priorização |
| RF06 | Monitorar localização das viaturas | Visualização contínua no dashboard |
| RF07 | Recalcular a priorização | Ajuste dinâmico quando a rota do VE muda |

> **Decisão P20 (2026-09-29) — o que "identificar" quer dizer no RF01.**
> Identificar um VE tem dois fatores: **identidade** (a tag reconhecida, de
> veículo ativo) e **estado** (uma ocorrência aberta pela central de despacho
> para aquele veículo). Um VE sem ocorrência — uma ambulância voltando para a
> base, por exemplo — é reconhecido, mas **não** recebe prioridade. A âncora é o
> CTB, art. 29, VII, que só concede prioridade ao VE *"quando em serviço de
> urgência"*. O RNF05 continua medindo apenas o primeiro fator, a identificação
> da tag.
>
> **Na bancada, só o primeiro fator existe** (decisão de 2026-10-05). O UNO
> decide sem consultar ocorrência, e o VE do protótipo é tratado como em serviço.
> P20 vale no motor, na API e na simulação.

> **Decisão P14 (2026-08-25) — onde termina a medição do RF02.** O requisito
> original não dizia até que ponto contar os 3 s, e as duas leituras possíveis
> davam resultados opostos. Adotada a leitura **"até o início da atuação"**: o
> marco é o instante em que o semáforo visivelmente muda — o amarelo —, carimbado
> como `t_atuacao` na chegada do `ACK` do atuador. *(Na bancada, desde
> 2026-10-05, o marco equivalente é o `EV,PREEMP_INI` do UNO, `05` §4.3.)*
>
> A alternativa, medir até o **verde final** na fase alvo, faria o RF02 absorver
> o **RF03** (garantir passagem contínua, que é justamente "o VE não para") e
> ainda embutir o verde mínimo no número. Verde mínimo é o invariante de
> segurança **I4**, não latência do sistema: sob essa leitura, um cruzamento que
> acabou de abrir o verde para a transversal seria classificado como "lento" por
> estar obedecendo a uma regra de segurança. Os dois requisitos medem coisas
> diferentes e continuam separados — RF02 mede *reação*, RF03 mede *resultado*.
>
> Esta leitura precisa aparecer **explicitamente** na definição do RF02 no texto
> do TCC. Deixá-la implícita é convidar a pergunta na arguição sem ter a resposta
> preparada.

## 7. Requisitos não funcionais

| Código | Categoria | Requisito |
| --- | --- | --- |
| RNF01 | Desempenho | Tempo de resposta da decisão < 100 ms |
| RNF02 | Disponibilidade | Operação contínua 24/7 |
| RNF03 | Escalabilidade | Suportar expansão da malha |
| RNF04 | Segurança | Comunicação criptografada |
| RNF05 | Confiabilidade | Precisão mínima de 95% na identificação do VE |
| RNF06 | Usabilidade | Dashboard intuitivo para operadores |
| RNF07 | Manutenibilidade | Código modular e documentado |

Como cada um vira teste executável: ver `06-testes-e-validacao.md`.

## 8. Escopo — o que **não** será feito

Registrar isso evita que o agente "melhore" o projeto para fora do prazo:

- ❌ Versão mobile do dashboard (decisão documentada no pré-projeto: operação em estação fixa).
- ⚠️ ~~Treinamento de modelo de machine learning preditivo.~~ **DEIXOU DE ESTAR FORA DE ESCOPO em 2026-09-10.** O orientador confirmou que a banca espera aprendizado de máquina, e indicou onde: um modelo para decidir **qual VE é priorizado** quando há mais de uma emergência simultânea — hoje o desempate determinístico da etapa E8. Isso **revoga a decisão P3** de 2026-08-24 e abre a pendência **P19** (`09-pendencias-e-decisoes.md`), onde estão o desenho a definir, o impacto no cronograma e o que precisa sair do escopo em troca.
  - O que **continua** verdadeiro da decisão P3: o restante do sistema — detecção, seleção de fase, transição segura, compensação — segue sendo **agente reativo com otimização determinística baseada em conhecimento**, técnica clássica de IA coberta por Russell & Norvig. O ML entra em **um** ponto delimitado, não substitui o motor.
  - Q-learning tabular para a política de compensação (E7) **continua fora de escopo**, como trabalho futuro descrito.
  - **O que o modelo não decide (P20, 2026-09-29):** se há emergência de fato (ocorrência ativa, regra determinística) e qual emergência importa mais (criticidade da ocorrência, regra acima do modelo). O ML escolhe só entre VEs de mesmo nível de criticidade.
- ❌ Integração com sistemas reais da CET, SAMU ou Corpo de Bombeiros. A **central de despacho** que abre e encerra ocorrências (P20) é **simulada** — painel do dashboard ou endpoint da API.
- ❌ Detecção acústica de sirene. Considerada e recusada em P20: a emergência é declarada pela central, não inferida do ambiente. A chave do giroflex no veículo fica como trabalho futuro.
- ❌ Radar físico. **Decisão P7, 2026-08-24:** no protótipo, o RFID-RC522 **emula** a função do conjunto radar + V2I, e isso é declarado explicitamente no texto. A validação da fusão de sensores ocorre exclusivamente em ambiente simulado. Sem sensor adicional (HC-SR04 descartado — ampliaria escopo sem sustentar nenhuma das três hipóteses).
- ❌ Autenticação multi-tenant, gestão de usuários, RBAC completo. Um login simples basta.
- ❌ Alta disponibilidade real em AWS (multi-AZ, auto-scaling). A infra em nuvem é **descrita** como arquitetura-alvo e, se houver tempo, demonstrada em instância única.

## 9. Glossário

| Termo | Significado |
| --- | --- |
| **VE** | Veículo de emergência (ambulância, viatura policial, bombeiro) |
| **Preempção** | Interrupção do ciclo semafórico normal para conceder verde à aproximação do VE |
| **Fase** | Combinação de movimentos que recebem verde simultaneamente sem conflito |
| **Ciclo** | Sequência completa de fases de um cruzamento |
| **All-red** | Intervalo em que todos os acessos ficam vermelhos, para limpeza do cruzamento |
| **Min green** | Tempo mínimo que um verde deve permanecer antes de poder ser truncado |
| **V2I** | Vehicle-to-Infrastructure — comunicação do veículo com a infraestrutura viária |
| **TLS** | Traffic Light System — identificador de um cruzamento semaforizado no SUMO |
| **TraCI** | Traffic Control Interface — API de controle em tempo real do SUMO |
| **Baseline** | Cenário de controle: semáforos de temporização fixa, sem preempção |
| **Compensação** | Ajuste de ciclo após a passagem do VE para dissipar filas nas transversais |
| **Ocorrência** | Atendimento em curso de um VE, aberto pela central de despacho e encerrado ao fim. Sem ocorrência ativa, o VE não recebe prioridade (P20) |
| **Criticidade** | Nível da ocorrência — 1 `RISCO_VIDA`, 2 `RISCO_COLETIVO`, 3 `URGENCIA`. Decide a precedência entre VEs antes de qualquer outro critério (P20) |

## 10. Stakeholders

CET, SAMU, Corpo de Bombeiros, forças policiais, operadores de centros de monitoramento urbano, desenvolvedores/administradores do sistema. Eles definem os perfis de uso do dashboard, não são usuários reais deste TCC.
