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

> **Implementado no Bloco 9 (2026-10-07).** Os
> módulos são `carregar.py`, `estatistica.py`, `tabelas.py`, `figuras.py`,
> `analise_h4.py` (entrega 10.8) e `gerar_resultados_tcc.py`. A entrada padrão é
> `analysis/data/bloco8/`. A saída tem `resultados.md` (T1 a T6 em Markdown),
> `tabelas/T*.tex` (`booktabs`), `comparacoes.csv` (toda comparação, com p bruto
> e de Holm), `figuras/F*.pdf` e `h4.md`.
>
> **`gerar_relatorio_validacao.py` existe desde 2026-10-08** (a versão anterior
> desta nota dizia que ele não seria feito, o que era um corte de escopo):
> `python -m analysis.gerar_relatorio_validacao --rodar-testes --banco` escreve
> `docs/relatorios/validacao_AAAAMMDD.md` com as nove seções de `06` §5. Ver
> `06` §5.
> Rodado sobre os CSV do piloto (`d081473`, código antigo), o pipeline reproduz
> os números já registrados (31,7% em `moderado`, 18,1% em `intenso`, mitigação
> de +3,7%). Isso só confere as fórmulas, e nenhum número do piloto vai ao texto.
>
> **F3, F4 e F6 precisam de séries no tempo, que o lote não grava.** Elas vêm de
> `python -m sim.controlador.traco --cenario intenso --seed 1 --saida
> analysis/data/bloco8_traco`, que roda a mesma (cenário, seed) nos três braços
> com o laço do executor (`decidir_e_aplicar`) e grava a posição dos VEs e a fila
> das transversais a cada segundo, e as transições de sinal. O pipeline confere
> o tempo de cada VE do traço contra o `ve_por_execucao.csv` do lote e declara se
> conferem. O cruzamento (`CRUZ_01`) e o VE (o primeiro da execução) das figuras
> foram fixados no código **antes** de ver as figuras.

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
mesmo nível** (coluna `mesmo_nivel` de `conflitos_por_execucao.csv`); (2) dessas,
no braço `PREEMPCAO_ML`, **quantas o modelo de fato decidiu**
(`decidida_pelo_modelo`) e **em quantas ele escolheu diferente do E8**
(`modelo_divergiu_do_e8`), as duas instrumentadas na entrega 10.7; (3) o teste
pareado sobre o tempo do VE mais prejudicado, com a unidade de análise do §3.1.

O item (2) existe porque mesmo nível não basta: a guarda de oscilação, o timeout
de E6 e os pedidos pela mesma fase desviam parte das disputas antes do modelo.
E um episódio em que o modelo concordou com o E8 em todo passo decorreu igual
nos dois braços no que dependeu do modelo. Declarar o denominador é o que
impede a pergunta "quantas vezes o modelo decidiu alguma coisa?" de ficar sem
resposta na arguição.

### 3.4 Correção para múltiplas comparações

São 4 cenários × várias métricas. Aplicar **Holm-Bonferroni** e reportar p bruto e p ajustado. Mencionar a correção no texto — mostra rigor metodológico.

> **Família de Holm do Bloco 9: o capítulo inteiro.** Toda comparação de T1, de
> T3 e a de H4 entram juntas, que é a leitura mais conservadora.

### 3.5 Regras de veredito do pipeline · **confirmadas pelo grupo em 2026-10-08** (escritas antes dos dados do Bloco 8)

Escritas no código (`analysis/gerar_resultados_tcc.py` e `analise_h4.py`) antes de
haver dado do Bloco 8, pelo mesmo motivo do critério de P16: a regra tem de
preceder o resultado. O `git log` é a prova da ordem: as regras entraram em
`b547976` (2026-10-08 00:23), os dados em `6f769ba` (2026-10-08 16:10), e
nenhum dos arquivos de veredito (`gerar_resultados_tcc.py`, `analise_h4.py`,
`estatistica.py`, `tabelas.py`) mudou entre os dois commits.

> **A confirmação veio depois dos dados, e isso fica declarado.** O cabeçalho
> pedia a confirmação "antes dos dados do Bloco 8"; ela só foi dada pelo Felipe
> em 2026-10-08, com o capítulo 5 já gerado. As regras confirmadas são as
> mesmas que produziram o capítulo, sem nenhuma alteração. O que a ordem dos
> commits garante é que a regra não foi escolhida pelo resultado; o que ela não
> garante é que o grupo a tenha lido antes de ver os números. Registro em `09`.

| Item | Regra |
| --- | --- |
| Estatística | Wilcoxon bilateral (principal), t pareado (secundário), Shapiro-Wilk das diferenças só informado. Cliff's δ = P(braço > base) − P(braço < base), cortes de Romano et al. (2006). IC 95% por bootstrap percentil das seeds, 10.000 reamostras, semente fixa |
| H1 | Por cenário, a redução do braço `PREEMPCAO` contra o `FIXO` é a média sobre as seeds de `(FIXO − braço) / FIXO`, com os VEs pareados por id. O cenário atinge se a redução for ≥ 25% **e** o p de Holm for < 0,05. `moderado` e `intenso` atingem: ACEITA; um: PARCIAL; nenhum: REJEITADA |
| H2 | A mitigação de P17, com as médias entre as seeds, ≥ 15% em `moderado` **e** em `intenso`: ACEITA; senão, REJEITADA. IC e p de `COMPENSADA × PREEMPCAO` ao lado, sem entrar na regra |
| H4 | Por execução, a média, sobre os pares de VEs que chegaram nos dois braços, do maior tempo do par (o minimax da rotulagem). FAVORÁVEL com p de Holm < 0,05 e mediana das diferenças e δ negativos. Um efeito significativo **contra** o modelo é reportado como DESFAVORÁVEL, valor que a T6 não previa |
| RNF01 | O pior p95 da latência de decisão entre as execuções com motor, < 100 ms |

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

> **A simulação não tem como preencher esta tabela como está (Bloco 9, 2026-10-07).**
> As colunas viriam de `log_prioridade`, que a simulação não grava, e o lote não
> conta pedidos de priorização nem timeouts de E6. O pipeline gera uma **T4
> adaptada** com o que o lote registra: VEs que completaram a rota e quantos não
> pararam (o critério do RF03), episódios de disputa entre VEs (um VE adiado em
> cada) e abortos, que o executor só faz por violação de invariante.
>
> **T4 adaptada confirmada pelo grupo em 2026-10-08**, contra instrumentar o lote
> e rodá-lo de novo. Como as regras de §3.5, a versão adaptada foi escrita antes
> dos dados (`b547976`) e confirmada depois deles. O texto do TCC precisa dizer
> que a T4 do pré-projeto foi adaptada e por quê.

### T5 — Segurança

| Cenário | Modo | Colisões | Violações I1–I5 | Teleportes |
| --- | --- | --- | --- | --- |

Todos devem ser zero. Se não forem, isso é o achado mais importante do trabalho e precisa ser discutido, não escondido.

### T6 — Verificação das hipóteses

| Hipótese | Critério | Resultado medido | Veredito |
| --- | --- | --- | --- |
| H1 | Redução ≥ 25% em `moderado` e `intenso` (decisão P1) | moderado: 35,0% [34,4%; 35,7%], p Holm < 0,001; intenso: 28,1% [27,3%; 29,0%], p Holm < 0,001 | ACEITA |
| H1 (exploratório) | Cenário `leve` — sem meta, apenas medido e discutido | leve: 40,5% [39,8%; 41,2%], p Holm < 0,001 | n/a |
| H2 | Mitigação **≥ 15% do acréscimo** de espera transversal causado pela preempção, `(preempcao − compensada) / (preempcao − fixo)`, sobre a espera média da hora, em `moderado` e `intenso` (P17, 2026-10-01) | moderado: +1,3% [-5,2%; 7,6%]; intenso: +7,4% [3,3%; 11,2%] | REJEITADA |
| H3 | Latência **fim-a-fim** < 200 ms no **p95** de 100 passagens de bancada, com mín/mediana/máx e o n (decisão de 2026-10-06; antes, o máximo de 5 repetições) | **p95 31,6 ms**, n = 100, mín 0,1 / mediana 24,9 / máx 46,3 ms, com o emissor no USB (2026-10-07). Sensibilidade sem as 2 amostras de carimbo atrasado: n = 98, p95 33,0 ms. Fonte: `analysis/data/resumo_bancada_2026-10-07.md` | ACEITA |
| RNF01 | Latência de **decisão** < 100 ms (p95) | pior p95 entre as execuções: 0,199 ms | ATENDE |
| H4 | `PREEMPCAO_ML` reduz o tempo do VE mais prejudicado em relação a `PREEMPCAO`, nos cenários com múltiplos VEs — **direcional, sem meta percentual** (P19); n de disputas de mesmo nível declarado (P20, §3.3.1) | mediana da diferença -4,6 s [-11,0; 2,6], δ -0,22, p Holm 0,174 | NULO |

**Preenchida em 2026-10-08** com o texto da T6 de `analysis/saida/resultados.md`,
copiado por script e não digitado: `python -m analysis.gerar_resultados_tcc`
sobre `analysis/data/bloco8/` (650 execuções de `85b1803`, `context/09`). O n de
disputas de mesmo nível da H4 está em `analysis/saida/h4.md` (529 no
`PREEMPCAO`, 560 no `PREEMPCAO_ML`). A H3 é a da bancada, de 2026-10-07.

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
