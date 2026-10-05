# 07 — Resultados e Análise

## 1. Aviso crítico sobre os números já escritos no pré-projeto

O capítulo 5 do pré-projeto ("RESULTADOS") apresenta tabelas com valores concretos: tempos de 420/385 s, 680/510 s, 950/665 s, latências de 42/68/94 ms, 1.250 intervenções em 120 h de simulação, 50 execuções, zero colisões.

**Esses números ainda não foram produzidos por execução real.** Eles são, hoje, valores esperados/ilustrativos.

Regras que decorrem disso, e que não podem ser flexibilizadas:

1. **Nenhum desses valores entra no código.** Nada de constantes, mocks ou fallbacks que reproduzam essas tabelas.
2. **O pipeline de análise gera as tabelas do zero** a partir dos CSVs de execução. As tabelas do TCC serão substituídas pelo que o pipeline produzir.
3. **Se os resultados reais divergirem dos esperados, o texto muda — não os dados.** Uma redução de 18% medida honestamente e discutida é um bom TCC. Um número inventado é fraude acadêmica e, na prática, é detectável: a banca pode pedir para rodar.
4. Se algum valor for mantido como "resultado esperado" na fundamentação, precisa estar **explicitamente rotulado como estimativa preliminar**, separado do capítulo de resultados.

Ver `09-pendencias-e-decisoes.md` item P6.

> **Formato confirmado pela equipe em 2026-08-31.** As tabelas do capítulo 5 do
> pré-projeto migram para uma seção **"Resultados esperados"**, dentro da
> metodologia, rotulada explicitamente como **estimativa preliminar do
> pré-projeto**. O capítulo 5 passa a ser preenchido inteiramente pela saída de
> `analysis/gerar_resultados_tcc.py`. A migração **não depende do Bloco 8** e pode
> ser feita já — fazê-la agora é o que impede um número não medido de sobreviver
> por esquecimento até a versão entregue.

> **T2 e a latência fim-a-fim (2026-08-31).** A linha `SIMULACAO` de T2 traz a
> latência de **decisão** (RNF01); a de `HARDWARE`, a **fim-a-fim** (H3). Na
> simulação `t_atuacao` é o mesmo passo de `t_decisao` — não há atuação física a
> cronometrar —, então a comparação simulação × hardware do §6 item 4 é entre
> grandezas diferentes e precisa ser apresentada como tal, com o n de cada uma
> declarado (a de hardware tem n = 5; ver `06` §6).

## 2. Pipeline de análise

```
analysis/
├── data/                       # CSVs gerados pelas execuções (gitignored, regeneráveis)
├── carregar.py                 # leitura e validação dos CSVs
├── estatistica.py              # testes de hipótese, tamanho de efeito, IC
├── tabelas.py                  # gera tabelas em Markdown + LaTeX
├── figuras.py                  # gera gráficos em PDF/PNG
├── gerar_relatorio_validacao.py
├── gerar_resultados_tcc.py     # ⭐ ponto de entrada: gera tudo do capítulo 5
└── saida/                      # tabelas e figuras prontas para o TCC
```

Um comando reproduz o capítulo inteiro:

```bash
python -m analysis.gerar_resultados_tcc --dados analysis/data/ --saida analysis/saida/
```

## 3. Método estatístico

### 3.1 Desenho

Comparação **pareada por seed**: cada seed gera o mesmo tráfego de fundo nos três modos. Isso remove a variabilidade entre cenários de tráfego e aumenta muito o poder do teste. É a razão de o §7 de `04-simulacao-trafego.md` insistir em reutilizar os arquivos de rota.

Unidade de análise: **a execução** (n = 50 por célula cenário × modo), não o veículo individual. Tratar cada VE como observação independente inflaria artificialmente o n e produziria p-valores enganosamente pequenos — VEs da mesma execução compartilham o mesmo tráfego e não são independentes. Este erro é comum e a banca pode pegá-lo.

### 3.2 Testes

| Situação | Teste | Observação |
| --- | --- | --- |
| Diferença pareada, dados normais | t pareado | Verificar normalidade das **diferenças** com Shapiro-Wilk |
| Diferença pareada, não normais | Wilcoxon signed-rank | Padrão para tempos de viagem, que são assimétricos |
| Três modos simultâneos | Friedman + post-hoc de Nemenyi | Quando comparar FIXO vs PREEMPCAO vs COMPENSADA |
| Proporções (taxa de sucesso) | Qui-quadrado ou Fisher | Para taxa de priorização bem-sucedida |

**Recomendação:** tempos de viagem raramente são normais. Reportar Wilcoxon como teste principal e o t pareado como secundário, ou testar normalidade e escolher com critério documentado. Não escolher o teste *depois* de ver qual dá p menor.

### 3.3 O que reportar sempre

Para cada comparação, os quatro juntos:

1. **Estatística descritiva** — mediana e IQR (mais robustos que média e desvio, dada a assimetria).
2. **Teste de hipótese** — estatística e p-valor, com α = 0,05.
3. **Tamanho de efeito** — Cliff's delta (não paramétrico) ou d de Cohen. **Isto é obrigatório.** Com n = 50, quase tudo dá significativo; o tamanho do efeito é o que diz se importa na prática.
4. **Intervalo de confiança de 95%** para a diferença — preferencialmente por bootstrap.

Uma redução de 2 s pode ser estatisticamente significativa e operacionalmente irrelevante. Reportar só o p-valor esconde exatamente isso, e é o tipo de coisa que um arguidor atento questiona.

### 3.3.1 H4 é estratificada por nível de criticidade (P20)

Os braços `PREEMPCAO` e `PREEMPCAO_ML` só podem decidir diferente quando os VEs
em disputa têm a **mesma** criticidade — entre níveis diferentes, a regra de
criticidade decide nos dois braços, igual. Comparar H4 sobre todas as disputas
diluiria o efeito do modelo com casos em que ele não atuou, pelo mesmo mecanismo
que P17 suspeita na métrica de H2.

A análise de H4 reporta, portanto: (1) quantas disputas houve e **quantas eram de
mesmo nível** (coluna `mesmo_nivel` de `conflitos_por_execucao.csv`), que é o n
de escolhas em que o modelo de fato atuou; (2) o teste pareado sobre o tempo do VE
mais prejudicado, com a unidade de análise do §3.1. Declarar o denominador é o que
impede a pergunta "quantas vezes o modelo decidiu alguma coisa?" de ficar sem
resposta na arguição.

### 3.4 Correção para múltiplas comparações

São 4 cenários × várias métricas. Aplicar **Holm-Bonferroni** e reportar p bruto e p ajustado. Mencionar a correção no texto — mostra rigor metodológico.

## 4. Tabelas a gerar

### T1 — Tempo de deslocamento do VE por cenário e modo

| Cenário | Modo | n | Mediana (s) | IQR | Redução vs. FIXO | p (Wilcoxon) | Cliff's δ | IC 95% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

Substitui a "Tabela 1" do pré-projeto, com muito mais informação.

### T2 — Latência do sistema

| Ambiente | Modo | n decisões | Mín | Mediana | Média | p95 | p99 | Máx |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

Duas linhas de ambiente: `SIMULACAO` e `HARDWARE`. A comparação entre os dois é interessante por si só e rende discussão.

### T3 — Impacto nas vias transversais (H2)

| Cenário | Modo | Espera média transversal (s) | Fila máxima | Throughput | Δ vs. FIXO | p |
| --- | --- | --- | --- | --- | --- | --- |

É aqui que H2 é aceita ou rejeitada. Precisa dos três modos. A espera é a média da hora inteira por veículo transversal, e a mitigação é a fração do acréscimo `(PREEMPCAO − COMPENSADA) / (PREEMPCAO − FIXO)`, avaliada em `moderado` e `intenso` (P17).

### T4 — Taxa de sucesso da priorização

| Cenário | Priorizações solicitadas | Sucesso | Conflito adiado | Timeout | Abortado |
| --- | --- | --- | --- | --- | --- |

### T5 — Segurança

| Cenário | Modo | Colisões | Violações I1–I5 | Teleportes |
| --- | --- | --- | --- | --- |

Todos devem ser zero. Se não forem, isso é o achado mais importante do trabalho e precisa ser discutido, não escondido.

### T6 — Verificação das hipóteses

| Hipótese | Critério | Resultado medido | Veredito |
| --- | --- | --- | --- |
| H1 | Redução ≥ 25% em `moderado` e `intenso` (decisão P1) | — | ACEITA / REJEITADA / PARCIAL |
| H1 (exploratório) | Cenário `leve` — sem meta, apenas medido e discutido | — | n/a |
| H2 | Mitigação **≥ 15% do acréscimo** de espera transversal causado pela preempção, `(preempcao − compensada) / (preempcao − fixo)`, sobre a espera média da hora, em `moderado` e `intenso` (P17, 2026-10-01) | — | ACEITA / REJEITADA |
| H3 | Latência **fim-a-fim** < 200 ms, sobre o **máximo** de 5 repetições de bancada (n declarado) | — | — |
| RNF01 | Latência de **decisão** < 100 ms (p95) | — | — |
| H4 | `PREEMPCAO_ML` reduz o tempo do VE mais prejudicado em relação a `PREEMPCAO`, nos cenários com múltiplos VEs — **direcional, sem meta percentual** (P19); n de disputas de mesmo nível declarado (P20, §3.3.1) | — | FAVORÁVEL / NULO |

A linha de H4 faltava nesta tabela desde que a hipótese foi formulada (P19,
2026-09-10); acrescentada em 2026-09-29. "NULO" é veredito legítimo — P19 o
declarou antes de qualquer treino.

As linhas de H3 e RNF01 são métricas distintas — ver decisão P2. Reportar as duas separadamente, com p95 **e** p99.

"PARCIAL" é um veredito legítimo e provavelmente o mais realista: H1 pode se confirmar em fluxo intenso e não em fluxo leve — o que faz todo sentido físico, já que com a via livre há pouco tempo a economizar. Essa discussão é justamente o que dá substância ao capítulo.

## 5. Figuras a gerar

| Fig. | Conteúdo | Tipo |
| --- | --- | --- |
| F1 | Tempo de viagem do VE por modo, agrupado por cenário | Boxplot |
| F2 | Distribuição de latência de decisão | Histograma + CDF, com linhas em 100 e 200 ms |
| F3 | Perfil espaço-temporal do VE (posição × tempo), baseline vs. proposto | Linha |
| F4 | Fila na transversal ao longo do tempo, com marcação do evento de preempção | Série temporal, 3 modos |
| F5 | Redução percentual vs. nível de saturação | Dispersão + linha de tendência |
| F6 | Diagrama de fases de um cruzamento durante uma preempção | Gantt |

F3 é a figura mais didática do trabalho: mostra visualmente o VE do baseline "escadinhando" (parando em cada cruzamento) contra a reta contínua do modelo proposto. Vale investir tempo nela.

F6 é a que prova visualmente que as transições foram seguras — amarelo e all-red aparecem em toda troca.

**Padrão das figuras:** vetorial (PDF), fonte serifada compatível com o TCC, tamanho de fonte legível quando reduzida à largura da página, escala de cinza distinguível (o TCC pode ser impresso em preto e branco), eixos rotulados com unidade.

## 6. Estrutura do capítulo de resultados

1. **Caracterização das execuções** — quantas, quais válidas, ambiente computacional.
2. **Verificação de premissas** — saturação obtida vs. pretendida, ausência de gridlock/teleporte.
3. **Desempenho do VE (H1)** — T1, F1, F3, F5.
4. **Latência (H3)** — T2, F2, comparação simulação vs. hardware.
5. **Impacto transversal (H2)** — T3, F4.
6. **Segurança** — T5, F6.
6b. **Priorização entre VEs (H4)** — disputas por nível de criticidade, escolhas de fato decididas pelo modelo, e a comparação `PREEMPCAO_ML` × `PREEMPCAO` (§3.3.1).
7. **Validação no protótipo físico** — checklist, comparação qualitativa com a simulação.
8. **Discussão** — por que os resultados são o que são; limitações; ameaças à validade.
9. **Síntese das hipóteses** — T6.

## 7. Ameaças à validade (seção obrigatória)

Antecipar isto na discussão desarma boa parte das perguntas da banca:

- **Validade interna:** parâmetros do modelo de car-following (Krauss) não calibrados com dados reais de São Paulo; `speedFactor` do VE é uma escolha de modelagem que influencia diretamente o ganho medido.
- **Validade externa:** malha sintética, não uma região real; resultados não são transferíveis diretamente para um corredor específico da cidade.
- **Validade de construção:** o RFID do protótipo substitui radar + V2I reais; a latência medida em bancada, com ESP-NOW a centímetros e sem outros transmissores, não representa uma rede urbana com interferência e múltiplos saltos. **O protótipo não roda o motor de decisão** (`00` §3, 2026-10-05): ele demonstra a cadeia V2I e a atuação segura com uma regra local, e a latência de H3 é a dessa cadeia, não a do motor. A latência dos dois conversores USB-serial entra na medida de H3 e não se cancela (`05` §4.3). **E a criticidade dos VEs na simulação é atribuída pelo cenário, seguindo o tipo** (P20), e não por ocorrências reais com a distribuição de gravidade de uma central de despacho; e a própria central é simulada.
- **Validade de conclusão:** n = 50 por célula é adequado para efeitos médios a grandes, mas pode não detectar efeitos pequenos; a correção para múltiplas comparações reduz o poder.
- **Comportamento humano:** o SUMO não modela motoristas cedendo passagem ao ouvir a sirene — comportamento que, no mundo real, já produz parte do ganho atribuído aqui ao sistema. Isso **superestima** o benefício marginal da preempção e precisa ser dito.

O último item é o mais honesto e o mais forte. Um trabalho que reconhece o próprio viés de superestimação transmite muito mais domínio do que um que apresenta ganhos sem ressalva.
