# 09 — Pendências e Decisões Abertas

Este arquivo lista contradições e lacunas identificadas na leitura dos documentos entregues. Itens marcados `DECISÃO DO GRUPO` **não devem ser resolvidos pelo agente de código**: exigem escolha da equipe, e alguns exigem consulta ao orientador.

Ao resolver um item, mover para a seção "Decisões tomadas" no fim do arquivo, com data e justificativa.

---

## Itens que dependem do orientador · orientação de **2026-08-31**

Levantados na preparação da orientação de 31/08/2026. São os únicos itens abertos
que a equipe **não** pode fechar sozinha — os demais são trabalho de engenharia ou
de redação.

**Respondidos na orientação, registrados em 2026-09-10.** A tabela fica como
histórico; o que cada resposta gerou está no item correspondente.

| Item | O que se perguntou | Resposta |
| --- | --- | --- |
| **P3** | A banca espera aprendizado de máquina? | ⚠️ **Sim.** E veio com sugestão concreta: usar ML para **priorizar entre múltiplos VEs** em cenários com mais de uma emergência simultânea. Abre **P19** e **revoga a decisão P3 de 2026-08-24** |
| **P18** | Declarar teto numérico para a degradação transversal? | ✅ **Não** — tratamento qualitativo. Objetivo geral reescrito. Ver P18 |
| **P11 (1) e (2)** | Referências para o fluxo de saturação e para os cortes de v/c | 🕓 **Ele ficou de devolver as referências.** Aprovou o método: medir na simulação e justificar o valor medido. Ver P11 |
| ~~**P11 (3)**~~ | ~~Enquadramento em fluxo interrompido~~ | ✅ **Confirmado pela equipe em 2026-08-31**, antes da orientação. Resta **declarar** a distinção no texto |
| ~~**P16**~~ | ~~Reformular H1, se a correção do mecanismo não levantar o número~~ | ✅ **Contingência não acionada** — a correção levantou (`intenso` 18,1% → 31,2%). H1 fica como está |

> **O item 4 da pauta era o de menor risco técnico e virou o de maior impacto.**
> A resposta a P3 não confirma o que a equipe havia decidido — ela o inverte, e
> com isso muda o escopo declarado do trabalho. Ver **P19**.

---

## P4 — Tabelas novas no banco precisam entrar no texto · `AÇÃO DA EQUIPE`

`03-banco-de-dados.md` adiciona: `fase_semaforo`, `tag_rfid`, `dispositivo_iot`, `deteccao`, `execucao_simulacao`, `estado_semaforo_amostra`, `metrica_latencia`, `metrica_via_transversal`.

O capítulo 4 do TCC precisa ser reescrito para incluí-las, e o DER regerado.

**Correções obrigatórias no texto atual:**
- `longitude DECIMAL(10,8)` → `DECIMAL(11,8)`. A definição atual **não comporta** a longitude de São Paulo (-46,63...): faltam dígitos inteiros. É um erro objetivo.
- `metrica_simulacao.tempo_medio_resposta DECIMAL(5,2)` → `DECIMAL(8,2)`. O limite de 999,99 é apertado demais para tempos de deslocamento em cenário intenso.
- `log_prioridade` no §4.1 não menciona `fk_metrica`, mas o §4.2 menciona. **Unificado incluindo o campo** — o DDL de `03-banco-de-dados.md` §3.1 é a referência; o texto do §4.1 é que precisa ganhar a coluna.

O código já implementa a versão corrigida. O que falta é a atualização do documento acadêmico.

---

## P6 — Números do capítulo 5 são esperados, não medidos · `AÇÃO DA EQUIPE — ALTA PRIORIDADE`

Ver `07-resultados-e-analise.md` §1. As tabelas 1 e 2, as 1.250 intervenções, as 120 h de simulação e o "100% de uptime" ainda não correspondem a execuções reais.

**Encaminhamento:** enquanto os dados reais não existirem, mover essas tabelas para uma seção "Resultados esperados" dentro da metodologia, claramente rotulada como estimativa. O capítulo 5 passa a ser preenchido pela saída de `analysis/gerar_resultados_tcc.py`.

**Este é o item de maior risco acadêmico do projeto.** Resolver cedo.

### Decisão da equipe, 2026-08-31 · **formato fechado; a redação continua ABERTA**

**O encaminhamento acima fica confirmado como o formato oficial.** As tabelas do
capítulo 5 do pré-projeto (420/385 s, 680/510 s, 950/665 s, latências de 42/68/94
ms, 1.250 intervenções em 120 h, "100% de uptime") migram para uma seção
**"Resultados esperados"** dentro da metodologia, rotulada explicitamente como
**estimativa preliminar do pré-projeto**, e o capítulo 5 passa a ser inteiramente
preenchido pela saída de `analysis/gerar_resultados_tcc.py`.

O que resta é execução de redação, e ela **depende do Bloco 8** para o conteúdo
final — mas a migração das tabelas para a metodologia **não depende**, e pode ser
feita já. Fazê-la agora elimina o risco de um número não medido sobreviver por
esquecimento até a versão entregue, que é exatamente como esse tipo de erro chega
à banca.

---

## P8 — Pino D3 (GPIO 0) no RST do RC522 · `VERIFICAÇÃO TÉCNICA`

GPIO 0 é pino de boot do ESP8266. Se o RC522 puxar essa linha para baixo durante o reset, o NodeMCU entra em modo de gravação em vez de executar o sketch.

**Ação:** testar boot com o RC522 conectado. Se falhar, remanejar RST para D0 (GPIO 16) e atualizar a tabela de pinagem em `05-integracao-hardware.md` §1 e no documento do protótipo.

**Status:** hardware disponível na bancada; verificar no **Bloco 5** (Sprint 4, camada IoT), antes de gravar o firmware definitivo.

---

## P9 — Alimentação do LCD I2C em 5 V com GPIO de 3,3 V · `VERIFICAÇÃO TÉCNICA`

Ver `05-integracao-hardware.md` §1C. Operação fora de especificação. Decidir entre alimentar o LCD em 3,3 V (contraste menor) ou usar conversor de nível, e documentar a escolha.

**Status:** hardware disponível; verificar no **Bloco 5** (Sprint 4), junto com P8.

---

## P11 — Fonte de dados de fluxo "típicos de zonas arteriais" · `AÇÃO DA EQUIPE`

A metodologia menciona "dados de fluxo típicos de zonas arteriais" sem citar fonte. Os valores (300–1200 veíc./h) precisam de referência.

**Opções:** manual da CET-SP, Highway Capacity Manual (HCM), ou dados abertos de contagem volumétrica da CET. Sem referência, a calibração da demanda fica sem sustentação metodológica e é um alvo fácil na arguição.

**Bloqueia:** a redação da metodologia, não o código. ~~Mas precisa estar resolvido antes de a Sprint 1 (malha) ser considerada fechada~~ — **deixou de bloquear a Sprint 1 / Bloco 3** com o encaminhamento abaixo, que mede o fluxo de saturação em vez de adotá-lo da literatura.

### Encaminhamento definido em 2026-08-25 · **item continua ABERTO**

A justificativa passa a sustentar o **método**, não cada número solto. Os fluxos
**300 / 700 / 1200 veíc./h permanecem inalterados** — vêm do pré-projeto e já
estão no texto entregue; alterá-los custaria reescrever a metodologia. O que se
acrescenta é a conversão deles em grau de saturação:

```
capacidade_por_faixa = fluxo_de_saturacao × (verde / ciclo)
v/c = fluxo_do_cenario / capacidade_da_aproximacao
```

**O `fluxo_de_saturacao` é MEDIDO na própria malha, não adotado da literatura.**
A malha simulada tem um fluxo de saturação próprio, que emerge dos parâmetros de
car-following do SUMO (`accel`, `decel`, `tau`, `minGap`, `length`); adotar um
valor de manual e aplicá-lo a uma malha que na verdade escoa outro produziria um
v/c errado com aparência de rigor.

O método é o de campo, aplicado à simulação: satura uma aproximação, mantém o
verde, descarta os primeiros veículos (*start-up lost time*) e calcula
`3600 / headway médio` do trecho saturado. Implementado em
`sim/calibracao/fluxo_saturacao.py`; a classificação, em
`sim/calibracao/cenarios.py` (entrega 3.0 do plano), com verificação por medição
de v/c na malha completa em 3.4.

A cadeia fica: **medição do fluxo de saturação → capacidade → v/c derivado → v/c
medido na malha completa**. Todo elo é código versionado, como o `CLAUDE.md`
exige. A literatura entra como **faixa de plausibilidade**, não como fonte do
número.

**Ressalva a declarar no texto.** Calibrar os cenários pela capacidade do próprio
simulador tem um quê de circular. A resposta é que o objetivo não é provar que o
SUMO é realista, e sim caracterizar o regime de operação do experimento — e a
comparação com a literatura é a guarda contra o modelo estar grosseiramente fora
de esquadro. Valor medido muito longe do reportado para via urbana significa
parâmetro errado em `veiculos.typ.xml`, e é isso que se corrige.

**Alerta metodológico — fluxo interrompido × ininterrupto.** Os limiares de
veíc./h/faixa que circulam para classificar trânsito (leve até ~700–800,
moderado até ~1400, intenso acima disso) são de **fluxo ininterrupto**: rodovias
e vias expressas, onde o HCM classifica por densidade e a capacidade fica em
1800–2200 veíc./h/faixa. Este trabalho é **fluxo interrompido** — arterial urbana
semaforizada —, tratado em capítulo separado do HCM, com nível de serviço medido
por *atraso de controle* e capacidade reduzida pela razão de verde.

O tamanho do erro, agora que há medição: a capacidade da nossa aproximação
arterial é **1.652 veíc./h** para duas faixas, contra os ~4.000 que os limiares
de rodovia sugeririam. Sob a régua errada, os 1.200 veíc./h do cenário `intenso`
pareceriam tráfego folgado, longe da capacidade — quando a medição mostra a
aproximação operando a **73%** dela. Não é um ajuste de rótulo: é a diferença
entre descrever uma via que escoa livremente e uma que está perto de saturar, e
com ela vai junto a condição de saturação em que H1 é formulada (decisão P1).

### Resultado da medição, em 2026-08-25 (Bloco 3)

A cadeia foi executada. Os números abaixo saíram de código versionado e estão em
`analysis/data/fluxo_saturacao.csv` e `analysis/data/calibracao_cenarios.csv`.

| Aproximação | Faixas | Fluxo de saturação medido | Capacidade |
| --- | --- | --- | --- |
| arterial | 2 | 1.807 e 1.697 veíc./h/faixa (média 1.752) | 1.652 veíc./h |
| transversal | 1 | 1.573 veíc./h/faixa | 741 veíc./h |

| Cenário | Fluxo arterial | v/c | Classificação | Fluxo transversal **derivado** |
| --- | --- | --- | --- | --- |
| `leve` | 300 | 0,18 | leve | 135 |
| `moderado` | 700 | 0,42 | moderado | 314 |
| `intenso` | 1.200 | **0,73** | **moderado** | 539 |
| `multiplas_emergencias` | 700 | 0,42 | moderado | 314 |

**ACHADO — o cenário `intenso` opera no topo da faixa moderada.** Com a
capacidade medida, 1.200 veíc./h numa aproximação de duas faixas dá v/c = 0,73,
**abaixo do limiar de 0,75** que o `04` §5 usa para a faixa `intenso`.

Isso não invalida H1: a decisão P1 condiciona a meta a "saturação moderada a
intensa", e 0,42 e 0,73 são dois pontos distintos dentro dessa faixa. O que ficou
descompassado foi o **nome** do cenário em relação à sua classificação medida.
**Resolvido em 2026-08-25 (ver tabela de decisões): mantêm-se os fluxos e os
nomes dos cenários; o que muda é a caracterização, que passa a ser a medida.**

**O que ainda falta, e é `AÇÃO DA EQUIPE`:**

1. Uma referência para a **faixa de plausibilidade** do fluxo de saturação em via
   urbana, com autor, edição, ano e capítulo. Não é mais a fonte do número —
   serve para confrontar o valor medido e sustentar a afirmação de que a malha
   opera em regime compatível com o de uma arterial real. Candidatas: Boletins
   Técnicos da CET-SP, o Manual de Estudos de Tráfego do DNIT, ou o HCM.
2. Uma referência para o **enquadramento por grau de saturação** — a ideia de que
   faixas de v/c correspondem a níveis de serviço. É o que justifica os cortes de
   40% e 75% do `04` §5.
3. Confirmar com o **Prof. Marco Gomes** o enquadramento em fluxo interrompido —
   convém levar junto com a decisão P3, que também espera conversa com ele.
4. **Escrever a metodologia com a caracterização medida** (decisão de 2026-08-25):
   a tabela dos cenários traz o v/c ao lado do nome, a demanda transversal é
   declarada como derivada, e o texto evita dizer "tráfego intenso" onde o dado
   diz 0,73 — o cenário `intenso` é descrito como *saturação moderada-alta*.
5. **Declarar as duas simplificações do modelo de demanda**: tráfego de fundo
   passante (sem conversões, logo as conversões permissivas à esquerda não são
   exercitadas) e composição de 5% de ônibus, que é premissa declarada e não
   medida.
6. **Declarar a calibração de `tau`** em `veiculos.typ.xml`: qual era o problema,
   qual foi o critério fixado antes do ajuste e qual o valor medido depois. É o
   ponto do trabalho mais exposto à crítica de circularidade, e a defesa é a
   transparência do procedimento.

> **O que mudou com a decisão de medir.** Antes, P11 exigia um número da
> literatura para *entrar* no cálculo, e sem ele o Bloco 3 não fechava. Agora
> exige uma referência para *conferir* um número que o próprio experimento
> produz. O Bloco 3 deixa de estar bloqueado por bibliografia: a calibração roda,
> a tabela sai, e a citação entra depois como validação. **P11 continua aberta**,
> mas passou de bloqueio de execução a pendência de redação.

### Estado em 2026-08-31 · **item continua ABERTO**

Os itens **1 e 2** — a referência para a faixa de plausibilidade e a referência
para o enquadramento por grau de saturação — foram levados à orientação. **Estado
em 2026-09-10: o orientador aprovou o método e ficou de devolver as referências.**

O que ele aprovou é o que importava mais: **medir o fluxo de saturação na própria
malha e justificar o valor medido** é caminho válido, e a referência entra para
confrontar o número, não para fornecê-lo. Isso confirma o encaminhamento de
2026-08-25 e remove o risco de a calibração inteira ter de ser refeita sobre um
valor de manual.

**P11 continua aberta, mas mudou de natureza:** deixou de ser pergunta e passou a
ser espera. O que falta é receber as citações e escrevê-las. Se elas não
chegarem, o item volta a ser risco — sem referência, a faixa de plausibilidade e
os cortes de v/c ficam sem lastro bibliográfico, e são alvo fácil na arguição.
**Cobrar na próxima orientação se não vierem.**

O item **3 saiu da pauta: o enquadramento em fluxo interrompido foi confirmado
pela equipe em 2026-08-31.** Não é matéria de opinião — a malha é uma arterial
urbana semaforizada, e isso *é* fluxo interrompido por definição; a capacidade
medida (1.652 veíc./h na aproximação arterial, contra os ~4.000 que a régua de
rodovia sugeriria) confirma a ordem de grandeza. **O que continua pendente é
declarar a distinção no texto**, com a aritmética explícita, porque é o ponto em
que a arguição pode aplicar a régua errada e reclassificar o cenário `intenso`
como tráfego folgado. A referência que sustenta a afirmação vem dos itens 1 e 2.

O item **4 fica confirmado pela equipe**: o cenário `intenso` é descrito no texto
como **saturação moderada-alta (v/c ≈ 0,73)**, os fluxos e os nomes dos cenários
não mudam, e a tabela da metodologia traz o v/c medido ao lado do nome. Isso
reafirma, sem alterar, a decisão de 2026-08-25.

Os itens **5 e 6** seguem como redação pendente da equipe, sem dependência
externa.

---

## P15 — `libsumo` para Python não vem com o SUMO no Windows · `DECISÃO DO GRUPO — Bloco 8`

Descoberto no Bloco 3, ao exercitar a opção `--libsumo` do executor.

O `context/02` §2 prevê a estratégia: `traci` no desenvolvimento (com GUI, para
gravar a demonstração) e **`libsumo` nas 600 execuções em lote**, por ser ~10x
mais rápido. O adaptador implementa as duas atrás da mesma interface, como o
plano pede em 3.6 — mas o **instalador Windows do SUMO 1.27.1 não traz o módulo
Python do `libsumo`**. Ele entrega os bindings Java, C# e C++
(`libsumo-1.27.1.jar`, `libsumocpp.dll`), e `%SUMO_HOME%/tools` contém apenas
`traci`.

O módulo Python existe, mas vem do **pip** — e é aí que está a decisão: a regra
registrada em 2026-08-24 é justamente **não instalar cliente do SUMO pelo pip**,
porque uma segunda cópia pode divergir da versão do binário e a divergência
aparece como comportamento sutilmente diferente, que é a classe de bug mais cara
deste projeto.

**As três saídas, para decidir antes do Bloco 8:**

1. **`pip install libsumo==1.27.1`**, fixado na mesma versão do binário. O risco
   da regra original fica mitigado pela fixação exata, e é preciso refixar sempre
   que o SUMO for atualizado. É a opção que preserva o ganho de desempenho.
2. **Rodar o lote com `traci` e paralelismo de processos.** Funciona hoje, sem
   dependência nova. O ganho perdido é menor do que os "10x" nominais sugerem:
   o adaptador lê o estado por **assinaturas**, então são ~4 chamadas por passo,
   e não dezenas — o custo de IPC que o `libsumo` elimina é justamente o das
   chamadas.
3. **Medir antes de decidir:** cronometrar uma execução de 3.600 s nos dois
   clientes e escolher com o número na mão. Custa uma hora e transforma a escolha
   em evidência.

**Recomendação: 3, depois 2 ou 1 conforme o resultado.** O lote são 600 execuções
— se `traci` der conta na janela de tempo disponível, não há por que abrir
exceção à regra de não instalar cliente pelo pip.

**Não bloqueia o Bloco 3:** a interface está implementada e testada no caminho
`traci`; o caminho `libsumo` está implementado e falha com mensagem que explica
exatamente isto.

### Medição do Bloco 4 (2026-08-26) · **item continua ABERTO, mas sem urgência**

A opção 3 ("medir antes de decidir") saiu de graça: o piloto do Bloco 4 são 60
execuções de 3.600 s, e rodá-las **é** a medição.

| Cenário | Tempo de parede por execução (`traci`, 1 processo) |
| --- | --- |
| `leve` | ~1 min |
| `moderado` | ~2 min |
| `intenso` | ~4 min |

Com `--paralelo 6` em 8 núcleos físicos, as **60 execuções levaram ~35 min**.
Extrapolando para a matriz do Bloco 8 — que tem a mesma proporção de cenários —,
as **600 levariam ~6 h**: uma noite de máquina.

**Consequência para a decisão.** A opção 2 (rodar com `traci` e paralelismo de
processos) **cabe na janela de tempo disponível**. O ganho que o `libsumo`
traria deixa de ser a diferença entre viável e inviável, e passa a ser
conveniência — o que enfraquece bastante o argumento para abrir exceção à regra
de não instalar cliente do SUMO pelo pip. Some-se a razão já registrada: o
adaptador lê o estado por assinaturas, ~4 chamadas de IPC por passo, e é
justamente o IPC que o `libsumo` elimina.

**Recomendação atualizada: opção 2.** Manter `--libsumo` implementado e
exercitável, para o caso de a máquina de execução mudar, e não instalar o pacote.
Formalizar a escolha antes do Bloco 8.

---

## P16 — H1 não atinge a meta em `intenso` · ✅ **RESOLVIDA em 2026-08-31**

> **Resolvida corrigindo o mecanismo, sem tocar em H1.** A remedição nas seeds do
> piloto mede **31,2%** no `intenso` contra os 18,1% de antes, e a pior seed
> passou de 13,0% para 27,9% — acima da meta. A contingência de reformular H1
> **não foi acionada**, e a hipótese fica como está.
>
> | Cenário | Piloto (2026-08-26) | Remedição (2026-08-31) | Meta ≥ 25% |
> | --- | ---: | ---: | :---: |
> | `intenso` | 18,1% (13,0 – 25,1) | **31,2%** (27,9 – 33,6) | **atinge** |
> | `moderado` | 31,7% | 34,3% | atinge |
> | `leve` | 39,0% | 40,4% | — |
> | `multiplas_emergencias` | 24,6% | 28,1% | — |
>
> Paradas do VE no `intenso`: **2,76 → 0,08**. Segurança intocada: zero colisão,
> zero teleporte, zero violação de I1 a I5 nas 60 execuções; p95 de decisão
> 0,144 ms.
>
> **A comparação é pareada de verdade.** A remedição usou as **mesmas seeds
> 1..5** do piloto, e os baselines `FIXO` saíram idênticos aos dele (538,0 ·
> 451,3 · 490,2 · 315,3 s, e paradas 6,28 · 5,56 · 5,68 · 3,22). O braço de
> controle não foi tocado pela alteração, que vive em E3 e só atua sob preempção
> — então toda a diferença é atribuível à correção, e não a tráfego diferente.
>
> **O preço está medido e vai para o texto.** O custo transversal no `intenso`
> subiu de **+24,6% para +43,6%**; `moderado` de +18,6% para +19,7%;
> `multiplas_emergencias` de +15,7% para +18,3%. Era o resultado declarado no
> critério antes de medir, e é o trade-off central do trabalho: o corredor abre
> mais cedo porque precisa esvaziar a fila, e quem paga é a transversal.
> **Consequência para P17:** o custo que E7 deveria mitigar quase dobrou no
> `intenso`, o que aumenta a pressão sobre a compensação em vez de aliviá-la.
>
> Evidência: `docs/relatorios/remedicao_p16/piloto_20260831.md` (seeds 1..5,
> código `d63f774`) e `docs/relatorios/calibracao_p16/piloto_20260831.md`
> (seeds 101..105, a corrida de calibração). Dados em
> `analysis/data/remedicao_p16/` e `analysis/data/calibracao_p16/`.
>
> **O que não muda:** `analysis/data/execucoes.csv` continua sendo o piloto de
> 2026-08-26, preservado como está. Os números do capítulo 5 virão do Bloco 8,
> rodado com o código corrigido.

O registro abaixo é o histórico do problema, mantido porque a arguição pode
perguntar como ele foi encontrado e resolvido.

Achado do **piloto do Bloco 4** (2026-08-26, 60 execuções de 3.600 s, 5 seeds ×
4 cenários × 3 modos). Números em `docs/relatorios/piloto_20260826.md`, gerados
por `python -m analysis.relatorio_piloto` a partir de `analysis/data/`.

| Cenário | Regime medido | Redução da travessia do VE | Meta ≥ 25% |
| --- | --- | ---: | :---: |
| `leve` | v/c 0,18 | 39,0% | sem meta |
| `moderado` | v/c 0,42 | **31,7%** | atinge |
| `intenso` | v/c 0,73 | **18,1%** | **não atinge** |
| `multiplas_emergencias` | v/c 0,42, 2 VEs | 24,6% | sem meta |

**É exatamente o risco que o Bloco 4 foi antecipado para expor** — o `08` §6
chama "resultados reais não confirmam H1" de risco mais subestimado do projeto —
e ele apareceu com meses de margem, não na última semana.

**O que o dado diz.** A dispersão entre as seeds do `intenso` é grande: 13,0% na
pior, 25,1% na melhor. Não é um teto do método; é dependência do tráfego
encontrado. As paradas do VE contam a mesma história: caem de 6,28 para 2,76 no
`intenso` (contra 5,68 → 0,76 no `moderado`), ou seja, **o corredor verde não se
fecha por inteiro quando a fila à frente não dissipa a tempo**. O VE alcança o
cruzamento com verde e ainda assim para, porque há veículos parados adiante.

**As saídas, para a equipe decidir:**

1. **Ajustar o modelo.** Antecipar mais a preempção em regime saturado —
   `tempo_antecipacao_margem_s` é fixo em 5 s e não depende da fila medida, que o
   motor já recebe em `EstadoSemaforo.fila_por_acesso`. É trabalho de engenharia,
   cabe no prazo, e tem a vantagem de atacar a causa. Exige remedir.
2. **Reformular H1 declarando a faixa em que a meta vale.** A decisão P1 já
   condicionou a meta à saturação; esta seria a mesma manobra, um degrau mais
   fina — e o `intenso` mede v/c 0,73, que a própria classificação põe em
   `moderado`. Custa uma conversa com o **Prof. Marco Gomes** e a reescrita da
   hipótese.
3. **As duas.** Ajustar o modelo primeiro, remedir, e só então decidir se a
   formulação precisa mudar.

**Recomendação: 3.** Reformular a hipótese sem antes tentar corrigir o mecanismo
seria ajustar a régua ao resultado, que é o que o `CLAUDE.md` proíbe. Tentar
primeiro, e reformular só se o teto for real, é a ordem defensável na arguição.

**Não é bloqueante para o Bloco 5** (camada IoT), que não depende disto. É
bloqueante para o **Bloco 8**: rodar as 600 execuções antes de decidir significa
rodá-las de novo depois.

### Decisão da equipe, 2026-08-31 · **item continua ABERTO até a remedição**

**Adotada a opção 3, começando pela 1: corrigir o mecanismo primeiro.** A
reformulação de H1 fica como contingência, acionada só se a correção não levantar
o número — e, nesse caso, com conversa com o orientador (ver a tabela de itens que
dependem dele, no topo deste arquivo).

**A hipótese de trabalho a atacar** é a que o piloto sustenta:
`tempo_antecipacao_margem_s` é fixo em 5 s e não consulta a fila, que o motor já
recebe em `EstadoSemaforo.fila_por_acesso`. Em regime saturado o corredor abre a
tempo mas não **esvazia** a tempo, e o VE chega ao verde com veículos parados
adiante — é o que as paradas residuais mostram (2,76 no `intenso` contra 0,76 no
`moderado`).

**Três guardas metodológicas, fixadas antes de mexer no código:**

1. **Critério declarado antes do ajuste**, como no precedente do `tau`
   (2026-08-25): escrever qual é o problema, qual é a mudança e qual o resultado
   esperado **antes** de medir o resultado. O valor que vale para o TCC é o medido
   depois, nunca o alvo.
2. **Regra de parada.** O conjunto de parâmetros é congelado antes da remedição, e
   a remedição roda a matriz inteira do piloto. Varrer parâmetros até um deles
   passar de 25% é ajustar a régua com passos pequenos — é o mesmo defeito, só
   mais difícil de enxergar.
3. **Calibrar fora das seeds do Bloco 8.** As seeds do piloto (1..5) são um
   subconjunto das 50 do Bloco 8. Ajustar o mecanismo olhando para elas e depois
   reportar o resultado final sobre 1..50 contamina 5 das 50 — o modelo teria sido
   afinado sobre parte da amostra que o valida. **A calibração deve usar seeds
   fora do intervalo 1..50** (por exemplo 101..105), e a remedição de aceitação,
   as seeds do piloto. Custa nada e torna as 600 execuções inteiramente
   fora-da-amostra. `AÇÃO DA EQUIPE — confirmar antes de começar.`

**Se, depois da correção, o `intenso` continuar abaixo de 25%:** vale a opção 2
(reformular H1 declarando a faixa), e aí a tentativa registrada é o que torna a
reformulação defensável em vez de oportunista.

### Critério do ajuste, declarado **antes** de mexer no código · 2026-08-31

Este bloco é commitado **antes** da alteração, de propósito: o `git log` é o que
prova que o critério precede o resultado. É o mesmo procedimento da calibração de
`tau` (2026-08-25).

**Diagnóstico, com a aritmética explícita.** No cenário `intenso` a arterial
recebe 1.200 veíc./h em duas faixas, ou 600 veíc./h/faixa. O ciclo fixo é de 70 s
com 30 s de verde por eixo, logo a arterial fica 40 s no vermelho e acumula
`600 × 40/3600 ≈ 6,7` veículos por faixa. Dissipar essa fila leva
`6,7 × 2,13 ≈ 14 s`, ao headway de saturação medido.

A janela de E3 hoje é `amarelo (3) + all-red (2) + MARGEM (5) = 10 s`, mais o
verde mínimo residual. O verde alvo abre 5 s depois da decisão, e o VE chega 10 s
depois dela — **5 s de verde contra os ~14 s de que a fila precisa**. O corredor
abre a tempo e não esvazia a tempo, que é exatamente o que as paradas residuais
mostram (2,76 no `intenso` contra 0,76 no `moderado`).

**A mudança.** E3 passa a somar à janela o tempo estimado de dissipação da fila
**no acesso pelo qual o VE vai entrar**:

```
T_ANTECIPACAO = amarelo + all_red + verde_min_residual + MARGEM + T_dissipacao

T_dissipacao  = min( (fila_no_acesso / faixas_do_acesso) * headway_saturacao_s,
                     preempcao_timeout_s - tempo_transicao_segura_s )
```

**A correção não introduz nenhum parâmetro livre**, e isso é o principal
argumento de defesa dela:

| Grandeza | De onde vem |
| --- | --- |
| `fila_no_acesso` | Já chega ao motor em `EstadoSemaforo.fila_por_acesso`, dos detectores E2 |
| `faixas_do_acesso` | Geometria da rede, lida pelo carregador de topologia |
| `headway_saturacao_s` | **Medido** em `analysis/data/fluxo_saturacao.csv` — 1,9926 e 2,1213 na arterial, 2,2891 na transversal; adotada a média das faixas medidas, **2,13 s** |
| Teto de `T_dissipacao` | **Derivado** de `preempcao_timeout_s`: antecipar mais do que a preempção sobrevive faria o corredor cair na cara do VE |

Nenhum número é escolhido para caber no resultado. Mexer em `tau`, `minGap`,
`length`, `accel` ou `decel` obriga a remedir a saturação e **também** a atualizar
`headway_saturacao_s`, que passa a integrar a mesma cadeia de dependência.

**Simplificação declarada: o tempo perdido na partida não entra.** O modelo de
campo somaria um *start-up lost time* ao tempo de dissipação, mas a medição de
`sim/calibracao/fluxo_saturacao.py` devolveu **0,000 s** para ele nas três faixas
— os primeiros veículos da janela cruzam já em movimento. Somar um valor de
manual aqui seria introduzir justamente o número sem lastro que P11 existe para
evitar. A consequência é que a antecipação fica **conservadora em ~2 s**, ou seja,
o erro é para o lado de **não** inflar H1.

**Resultado esperado, declarado antes de medir:**

1. **H1 melhora.** As paradas residuais do VE no `intenso` devem cair das 2,76
   atuais em direção às 0,76 do `moderado`, e a redução da travessia deve subir
   dos 18,1%. *Não* se declara aqui que ela chegará a 25% — isso é o que a
   medição vai dizer.
2. **H2 piora.** A preempção passa a começar antes e segura a transversal por
   mais tempo, então o custo transversal medido (+24,6% no `intenso`) deve
   aumentar. **Isso precisa ser medido e reportado, não escondido** — é o
   trade-off central do trabalho, e é o que dá substância à discussão do
   capítulo 5.
3. **Segurança inalterada.** I1 a I5 não são tocados. A antecipação maior aumenta
   a pressão sobre I5, que já tem guarda no motor e cede a vez à fase faminta;
   espera-se zero violação, e violação seria motivo de reverter, não de afrouxar
   o invariante.

**Regra de parada — uma tentativa deste mecanismo.** Se a redução no `intenso`
não atingir 25%, **não se varre parâmetro**: aciona-se a opção 2 (reformular H1),
com o orientador. Corrigir um defeito de implementação encontrado no caminho não
conta como nova tentativa; mudar a fórmula atrás de um número melhor conta, e é
o que fica proibido.

**Onde se mede.** Matriz completa do piloto nas **seeds 101..105**, fora do
intervalo 1..50 do Bloco 8. As seeds 1..5 só depois, como remedição de aceitação.

#### Emenda à fórmula, na implementação (mesmo dia, antes de medir)

O critério acima aplicava o teto a `T_dissipacao`. **Está errado, e a correção é
de defeito, não de número:** capar só a parcela da fila não cumpre a intenção
declarada ("antecipar mais do que a preempção sobrevive faria o corredor cair na
cara do VE"). Com o teto na parcela, o pior caso somava
`5 + verde_min_residual (≤ 7) + 5 + 40 = 57 s` de antecipação contra um
`preempcao_timeout_s` de 45 s — exatamente o cenário que o teto existia para
impedir. O teto passa a valer sobre a **antecipação total**:

```
T_ANTECIPACAO = min( amarelo + all_red + verde_min_residual + MARGEM + T_dissipacao,
                     preempcao_timeout_s - tempo_transicao_segura_s )
```

No perfil de simulação o teto é `45 − 5 = 40 s`, e ele quase nunca morde: o pior
caso previsto no `intenso` é de ~31 s. É rede de segurança, não botão de ajuste.
Coberto por `test_janela_nao_passa_do_teto_derivado_do_timeout`, e
`Parametros.validar()` passou a recusar `preempcao_timeout_s` menor que o tempo
de transição segura, que tornaria o teto negativo e a preempção impossível.

#### Estado da implementação, 2026-08-31

**Código pronto e testado; a medição é o que falta.** `mypy --strict` limpo,
`ruff` limpo, **279 testes** na execução padrão (6 novos). Alterados:
`core/malha.py` (`faixas_por_via`, vindo da rede e não de configuração),
`core/parametros.py` (`headway_saturacao_s`, `tempo_dissipacao_fila_s()`,
`antecipacao_max_s`), `core/priorizacao/deteccao.py` (`fila_por_faixa()` e o novo
argumento de `dentro_da_janela`), `core/priorizacao/motor.py`,
`adapters/sumo/topologia.py` e `backend/config/parametros.yaml`.

Duas regressões cobrem o defeito de P16 — uma em E3 isolado e outra no motor
inteiro, esta última mudando **só a fila** entre as duas metades do teste.

**A medição não pôde ser feita na sessão em que o código foi escrito:** uma
política de Controle de Aplicativo do Windows bloqueia o lançamento do binário do
SUMO no ambiente do agente. Ela roda na máquina da equipe, com:

```bash
python -m sim.controlador.lote --seeds 101..105 --paralelo 6 \
    --sem-banco --saida analysis/data/calibracao_p16
python -m analysis.relatorio_piloto --dados analysis/data/calibracao_p16
```

`--sem-banco` e o `--saida` separado são obrigatórios: sem eles a calibração
entraria em `analysis/data/execucoes.csv` e em `execucao_simulacao` junto com as
60 execuções do piloto, e o Bloco 9 leria os dois conjuntos como se fossem o
mesmo experimento. As seeds 101..105 são pontos novos, então a guarda de
`PontoJaConsolidadoError` **não** protegeria contra isso.

---

## P17 — E7 não entrega a mitigação de H2 · `DECISÃO DO GRUPO — ANTES DO BLOCO 8`

Mesmo piloto. A compensação **roda** — o defeito de no-op foi corrigido no
Bloco 3 e tem teste de regressão —, mas o efeito medido sobre a espera das vias
transversais é indistinguível de zero, e negativo em dois cenários:

| Cenário | Espera `FIXO` | `PREEMPCAO` | `PREEMPCAO_COMPENSADA` | Custo | Mitigação |
| --- | ---: | ---: | ---: | ---: | ---: |
| `leve` | 18,91 s | 18,60 s | 18,74 s | -1,6% | -0,7% |
| `moderado` | 15,24 s | 18,08 s | 17,97 s | +18,6% | +0,6% |
| `intenso` | 16,35 s | 20,37 s | 20,57 s | +24,6% | **-1,0%** |
| `multiplas_emergencias` | 15,23 s | 17,63 s | 17,61 s | +15,7% | +0,1% |

Meta de H2: mitigar **em no mínimo 15%** (enunciado corrigido em 2026-08-31, ver
abaixo; o piloto foi gerado sob a redação antiga, "em até 15%"). Medido: entre
−1,0% e +0,6%.

**O custo que H2 existe para mitigar é real e está medido** (+18,6% no
`moderado`, +24,6% no `intenso`) — o que falta é a mitigação.

**Duas causas prováveis, nenhuma verificada ainda:**

1. **`ganho_compensacao_k` (0,7) e `n_ciclos_compensacao` (2) nunca foram
   calibrados contra dado real.** O `01` §5.3 os declara como ponto de partida
   ("começar em K = 0.7"), e ponto de partida foi o que ficou. Dois ciclos de 70 s
   são 140 s de compensação para uma preempção que trava a transversal por
   dezenas de segundos — pode simplesmente ser curto demais.
2. **A métrica pode estar diluindo o efeito.** `tempo_espera_medio_transversal_s`
   é a média sobre **todos** os veículos transversais da hora inteira, e a
   compensação atua nos ~140 s seguintes a cada evento. Com um VE a cada 10 min,
   o sinal fica sobre uma fração pequena da amostra. Medir a espera **na janela
   de compensação**, ou a fila máxima por acesso (que os detectores E2 já
   coletam e o coletor já acumula), poderia mostrar um efeito que a média
   esconde.

**Encaminhamento sugerido, nesta ordem:** verificar (2) antes de mexer em (1) —
se a métrica estiver diluindo, calibrar `K` contra ela seria calibrar contra
ruído. Só depois varrer `K` e `n_ciclos_compensacao`.

**E há um item de redação junto.** "Mitigar em até 15% o impacto negativo" admite
duas leituras, e elas divergem: fração da **espera transversal** (o que a coluna
*Mitigação* mede) ou fração do **acréscimo** que a preempção causou (a coluna
*Mitigação do acréscimo*). O relatório do piloto imprime as duas de propósito.
**Qual vale precisa ser declarado no texto antes do Bloco 8** — escolher depois
de ver qual dá o número melhor é o oposto de método.

### Decisão parcial da equipe, 2026-08-31 · **item continua ABERTO**

**Resolvido: o enunciado de H2 passa de "em até 15%" para "em no mínimo 15%"
(≥ 15%).** A redação antiga não enunciava meta nenhuma: "mitigar em **até** 15%" é
um teto, e sob ele os −1,0% a +0,6% medidos no piloto **cumpririam** a hipótese
literalmente, o que a esvazia. `≥ 15%` é a leitura que a equipe sempre teve em
mente, é simétrica com a de H1 (`≥ 25%`) e é a única sob a qual H2 pode ser
rejeitada — hipótese que não pode falhar não é hipótese. Propagado para
`00-visao-geral.md` §5, `07-resultados-e-analise.md` T6 (que trazia `≤ 15%`, o
inverso do pretendido) e a docstring de `core/priorizacao/compensacao.py`.

**Continua aberto: qual é o denominador.** Trocar "até" por "no mínimo" fixa o
sentido da desigualdade, não a grandeza sobre a qual os 15% incidem. As duas
leituras seguem de pé e continuam divergindo:

| Leitura | Fórmula | Medido no piloto (`moderado`) |
| --- | --- | ---: |
| Fração da **espera transversal** | `(preempcao − compensada) / preempcao` | +0,6% |
| Fração do **acréscimo** causado pela preempção | `(preempcao − compensada) / (preempcao − fixo)` | +3,7% |

**Recomendação da leitura, para a equipe confirmar: a segunda.** O enunciado diz
"mitigar o **impacto negativo** nas vias transversais", e o impacto negativo *é* o
acréscimo — a espera que existiria sem preempção nenhuma não é impacto do sistema
e não cabe a E7 mitigar. Sob a primeira leitura, um cenário com espera de base
alta tornaria a meta aritmeticamente inalcançável mesmo com E7 devolvendo o
acréscimo inteiro.

**Declarar agora não é escolher pelo resultado**, e é importante que isso fique
registrado: **nenhuma das duas leituras atinge os 15%** no piloto (+0,6% contra
+3,7% no `moderado`; ambas negativas no `intenso`). A escolha não salva o número,
então fazê-la antes de calibrar `K` é gratuito do ponto de vista metodológico — e
depois da calibração deixaria de ser.

**Ressalva sobre o `leve`.** A leitura pelo acréscimo é instável quando o
acréscimo é próximo de zero ou negativo: no `leve` o custo medido é −1,6% e a
"mitigação do acréscimo" sai como +44,2%, número sem significado. O texto precisa
declarar que a métrica de H2 só se aplica onde a preempção **de fato** custa
alguma coisa — o que é coerente com H2 existir para mitigar um custo.

**Continua aberto também: a métrica pode estar diluindo o efeito** (causa 2 acima)
e `K`/`n_ciclos_compensacao` seguem sem calibração. Verificar a métrica **antes**
de calibrar, pela razão já registrada.

### O que a correção de P16 mudou aqui · 2026-08-31

**O alvo de P17 cresceu.** A correção de P16 antecipa a preempção pelo tempo de
dissipação da fila, e quem paga é a transversal. Medido nas mesmas seeds:

| Cenário | Custo antes de P16 | Custo depois de P16 | Mitigação de E7 |
| --- | ---: | ---: | ---: |
| `intenso` | +24,6% | **+43,6%** | −0,6% |
| `moderado` | +18,6% | +19,7% | −0,8% |
| `multiplas_emergencias` | +15,7% | +18,3% | +1,2% |
| `leve` | −1,6% | +0,2% | +2,4% |

Duas consequências:

1. **P17 ficou mais urgente, não menos.** O custo que H2 existe para mitigar
   quase dobrou no `intenso`, e a mitigação continua indistinguível de zero. O
   trabalho agora tem um ganho maior em H1 **e** um custo maior em H2, e a
   discussão do capítulo 5 precisa apresentar os dois juntos — reportar só o
   ganho seria omissão.
2. **A janela de compensação mudou de tamanho**, o que reforça o encaminhamento
   já registrado de checar a métrica antes de calibrar `K`: a preempção agora
   dura mais por evento, então a fração da hora em que a compensação atua também
   mudou. Calibrar contra a média horária sem verificar isso continua sendo
   calibrar contra ruído.

Reapareceu a instabilidade da leitura pelo acréscimo quando o acréscimo é ~0: no
`leve`, "mitigação do acréscimo" deu **+1347,1%**. É exatamente a ressalva
declarada acima, e confirma que a métrica de H2 só se aplica onde a preempção de
fato custa algo.

> O `08` §2 é explícito: cortar E7 obriga a **tirar H2 do trabalho**, não a
> deixá-la sem sustentação. Se a calibração não levantar o número, a decisão
> honesta é reportar o custo transversal medido e declarar que a compensação
> proposta não o mitigou de forma mensurável neste experimento — o que é um
> resultado, não um fracasso, desde que dito assim.

---

## P18 — "Degradação inaceitável" não tem limiar declarado · ✅ **RESOLVIDA em 2026-09-10**

> **Decisão do orientador: tratamento qualitativo, sem teto numérico.** É a opção 2
> abaixo, que era a recomendação registrada. O custo transversal é medido,
> reportado e discutido no capítulo 5, sem limiar formal — e o **objetivo geral
> foi reescrito** para não prometer um critério que o trabalho não tem:
>
> | | |
> | --- | --- |
> | Antes | "…reduzindo seu tempo de travessia, **sem degradar de forma inaceitável** o fluxo transversal" |
> | Agora | "…reduzindo seu tempo de travessia, e **quantificar o custo que essa priorização impõe** ao fluxo transversal" |
>
> A troca é mais que cosmética: o trade-off sai da condição de ressalva e passa a
> ser **objetivo declarado**. O trabalho promete o que os dados cumprem —
> medir — em vez de um julgamento que ninguém fixou. Não há linha nova em T6,
> porque não há critério a verificar; há uma seção de discussão a escrever.
>
> Aplicado em `00-visao-geral.md` §4. **Nada muda no código nem nas execuções.**

O registro abaixo é o histórico, mantido porque a arguição pode perguntar por que
o objetivo geral foi reescrito no meio do trabalho.

Aberta em 2026-08-31, como consequência direta da correção de P16.

O **objetivo geral** do trabalho (`00-visao-geral.md` §4) é reduzir o tempo de
travessia do VE *"sem degradar de forma **inaceitável** o fluxo transversal"*. A
palavra nunca foi definida, e até agora isso era abstrato: o custo transversal
medido era moderado e ninguém precisava dizer onde ficava a fronteira.

**Deixou de ser abstrato.** A correção de P16 antecipa a preempção pelo tempo de
dissipação da fila, o que resolveu H1 e, no mesmo movimento, quase dobrou o custo
para quem está na transversal:

| Cenário | Antes de P16 | Depois de P16 |
| --- | ---: | ---: |
| `intenso` | +24,6% | **+43,6%** |
| `moderado` | +18,6% | +19,7% |
| `multiplas_emergencias` | +15,7% | +18,3% |
| `leve` | −1,6% | +0,2% |

**A pergunta:** o texto declara um teto numérico para essa degradação, ou trata o
assunto qualitativamente na discussão do capítulo 5?

**Por que precisa ser resolvido antes do Bloco 8.** São 600 execuções para
produzir os dados definitivos. Se houver limiar, ele tem de estar escrito
**antes** delas. Declarar um teto depois de ver os números é escolher a régua
pelo resultado — o mesmo defeito que o projeto evitou em P16 (critério commitado
antes do código) e no enunciado de H2 (denominador declarado enquanto nenhuma
leitura atinge a meta). Fazer diferente aqui abriria exatamente a brecha que as
duas decisões anteriores fecharam.

**As saídas:**

1. **Teto numérico declarado na metodologia.** Torna o objetivo geral
   verificável e dá uma linha nova em T6. O risco é escolher mal: um teto
   apertado reprovaria um sistema que funciona, um teto frouxo não significa
   nada. Se for este o caminho, o valor precisa de justificativa própria — e
   provavelmente da mesma bibliografia de P11.
2. **Tratamento qualitativo, com o objetivo geral reescrito.** O custo é medido,
   reportado e discutido, sem limiar formal. Exige tirar a palavra "inaceitável"
   do objetivo, ou substituí-la por formulação que não prometa um critério que o
   trabalho não tem.

**Recomendação: 2, com a reescrita do objetivo.** Um teto inventado agora seria
um número sem lastro — exatamente o que P11 existe para evitar — e o trabalho não
tem base para fixá-lo. Reportar o trade-off medido e discuti-lo é honesto e é o
que os dados sustentam. Mas **a escolha é do grupo, e vale ouvir o orientador**,
porque é ele que conhece a expectativa da banca sobre um objetivo geral sem
critério numérico.

> **Não confundir com H2.** H2 mede se a **compensação** devolve parte do custo, e
> tem meta própria (≥ 15%, ver P17). P18 é outra coisa: quanto custo é aceitável
> **existir**, mitigado ou não. Um trabalho pode ter H2 rejeitada e ainda assim
> declarar que a degradação ficou dentro do aceitável, e vice-versa.

---

## P19 — Modelo de ML para priorizar entre múltiplos VEs · `DECISÃO DO GRUPO — DEFINE UM BLOCO NOVO`

Aberta em 2026-09-10, pela resposta do orientador a P3. **Revoga a decisão P3 de
2026-08-24**, que reservava a palavra "IA" à caracterização de agente e punha
aprendizado de máquina explicitamente fora de escopo.

**O que o orientador pediu:** um modelo de *machine learning* para decidir, em
cenários com mais de um veículo de emergência simultâneo, **qual deles é
priorizado**. A banca espera ML no trabalho, e este é o ponto onde ele deve
entrar.

### O que isso substitui

A etapa **E8** (`01-arquitetura-sistema.md` §5.2), hoje um desempate
determinístico e lexicográfico:

1. maior prioridade por tipo (`AMBULANCIA > BOMBEIRO > POLICIA`);
2. menor ETA ao cruzamento;
3. preempção já em curso vence, para evitar oscilação.

### Por que a substituição é defensável — e não decorativa

Este é o argumento que vai para o texto, e ele é real: **E8 é míope.** Decide um
cruzamento por vez, num instante, por uma ordem fixa, sem considerar a
consequência sequencial. Priorizar o VE A agora pode custar muito mais ao VE B
adiante, ou formar uma fila que prejudica os dois. A ordem por tipo é uma
convenção declarada, não uma otimização — nada garante que servir a ambulância
primeiro minimize o tempo do conjunto.

Uma política aprendida pode pesar a consequência. **Existe, portanto, uma lacuna
genuína que o ML preenche**, o que é bem diferente de vestir de ML algo que já
funciona. É o que torna a entrega defensável na arguição em vez de parecer
concessão à expectativa da banca.

### O primeiro passo é medir, e o dado não existe

**Ninguém sabe quantos eventos de conflito existem por execução.** `conflito.py`
resolve a disputa e devolve os adiados, mas o coletor **não agrega** e
`execucoes.csv` **não tem coluna** para isso — verificado em 2026-09-10. O
`status_execucao = 'CONFLITO_ADIADO'` está previsto em `log_prioridade`, mas o
lote roda com `--sem-banco` e nada conta o evento no CSV.

Isso importa porque **o paradigma viável depende dessa contagem**, e escolher o
modelo antes de conhecê-la seria projetar no escuro:

| Se houver… | …então |
| --- | --- |
| ~3 conflitos por execução | ~150 eventos em 50 seeds. Não sustenta treino **e** avaliação separados; obriga cenário mais denso |
| ~30 conflitos por execução | ~1.500 eventos. Sustenta tabela Q ou modelo pequeno, com divisão treino/teste por seed |

**Ação imediata, antes de qualquer decisão de modelagem:** instrumentar a
contagem de conflitos no coletor, acrescentar a coluna em `execucoes.csv` e rodar
o cenário `multiplas_emergencias` em algumas seeds. É trabalho de horas e
transforma a escolha do paradigma em evidência — o mesmo procedimento que P15
seguiu ("medir antes de decidir") e que P16 formalizou.

### As decisões de modelagem, para depois da medição

1. **Paradigma.** (a) **Classificador supervisionado com rótulos de oráculo** —
   para cada conflito, simular as duas escolhas e rotular a melhor; treina sobre
   verdade construída, dispensa desenho de recompensa, e a avaliação é direta.
   (b) **Q-learning tabular** — é o que o texto já descreve como trabalho futuro
   (para E7), mas exige discretizar o estado e converge mal com eventos raros.
   (c) **Função de utilidade linear com pesos aprendidos** — mantém a estrutura de
   E8 e aprende os coeficientes em vez de declará-los; é o caminho mais baixo em
   custo e o mais explicável.
2. **O que otimizar.** Soma dos tempos dos dois VEs? O **pior** dos dois
   (minimax, que é o critério mais justo e mais fácil de defender eticamente)?
   Soma ponderada por tipo? **Precisa ser declarado antes de treinar** — é a
   mesma disciplina do denominador de H2 e do critério de P16.
3. **Onde o modelo roda.** `core/` é puro por decisão arquitetural central: é o
   que sustenta a afirmação de que o mesmo motor roda na simulação e no
   protótipo, e `test_arquitetura.py` reprova qualquer import de framework.
   **A saída é treinar fora e exportar a política como dado** — tabela, pesos ou
   árvore pequena — com inferência pura em `core/`. Isso preserva a arquitetura,
   mantém a latência do RNF01 e deixa o modelo auditável na defesa.
4. **Divisão treino/teste por seed**, com o treino **fora** do intervalo 1..50 do
   Bloco 8. Mesma guarda de P16, pela mesma razão: treinar sobre parte da amostra
   que valida o resultado contamina a validação.
5. **Densidade de VEs.** O cenário `multiplas_emergencias` tem ~11 VEs por
   execução de 1 h, em pares. Se os conflitos forem raros, será preciso um cenário
   mais denso para treinar — e isso significa novos arquivos de demanda.

### O que mais precisa mudar no trabalho

- **`00-visao-geral.md` §8** põe "treinamento de modelo de machine learning
  preditivo" explicitamente **fora de escopo**. Contradição direta; tem de ser
  reescrito.
- **A decisão P3** (tabela de decisões tomadas, 2026-08-24) fica **revogada**, com
  a data e o motivo registrados. Mudança de escopo justificada é normal; mudança
  silenciosa parece descuido — é o mesmo princípio de P12.
- **Hipótese nova (H4)** e **braço novo** (`PREEMPCAO_ML`), comparado contra o E8
  determinístico. Sem braço próprio não há como isolar o efeito do modelo.
- **A matriz do Bloco 8 cresce.** Um braço a mais nos cenários com múltiplos VEs,
  mais as execuções de treino.
- **Bibliografia de ML** — Russell & Norvig já cobre aprendizado por reforço; um
  classificador supervisionado pede referência própria.

### Risco a declarar desde já

**O modelo pode não bater o heurístico.** Com dois VEs e um desempate por tipo e
ETA, a margem é estreita. O trabalho precisa estar estruturado para que **um
resultado nulo continue sendo resultado**: relatar que a política aprendida não
superou a heurística, com o tamanho de efeito e o intervalo de confiança, é
contribuição legítima — e é o que o `07` §1 já exige em espírito. O que não pode
acontecer é o modelo entrar sem avaliação, só para satisfazer a expectativa.

### Impacto no cronograma

Hoje é **2026-09-10**. Faltam os Blocos 5 a 9 e a apresentação está estimada
entre nov/2026 e jan/2027. P19 acrescenta um bloco inteiro — instrumentação,
geração de dados, treino, exportação, braço novo, hipótese nova e análise
estatística própria — a um caminho crítico que **já está bloqueado por P17**.

A lista de corte do `08` §2 existe para isto e passa a ser candidata real: o
**dashboard** (itens 2 e 5) é o primeiro a ceder, e vale decidir cedo em vez de
descobrir em dezembro.

### Recomendação

1. **Medir a frequência dos conflitos primeiro** (horas de trabalho).
2. Com o número na mão, escolher o paradigma — a inclinação é pela **opção (c) ou
   (a)**, por custo e explicabilidade, deixando Q-learning como alternativa.
3. **Declarar o objetivo de otimização antes de treinar**, e commitá-lo antes do
   código, como se fez em P16.
4. **Levar a proposta de desenho ao orientador antes de implementar.** Ele pediu
   ML, não um desenho específico; alinhar o desenho evita construir a coisa errada.
5. Decidir, na mesma conversa, **o que sai do escopo** para P19 entrar.

---

## P12 — Ordem das sprints alterada · `REGISTRO`

`08-roadmap-e-convencoes.md` §1 antecipa o banco de dados (Sprint 5 do texto) porque a Sprint 2 já precisa persistir. Registrar a alteração no capítulo de metodologia, com a justificativa — mudança de plano justificada é normal em processo iterativo e demonstra maturidade; mudança silenciosa parece descuido.

---

## Decisões tomadas

| Data | Item | Decisão | Justificativa |
| --- | --- | --- | --- |
| 2026-08-24 | **P1** — meta de redução (20% vs 30%) | H1 reformulada e **condicionada à saturação**: *"redução ≥ 25% no tempo total de travessia do VE em cenários de saturação moderada a intensa"*. O cenário `leve` é analisado e discutido separadamente, sem meta numérica. | A Tabela 1 do próprio pré-projeto mostra 8,3% em fluxo leve — nenhuma meta única sobrevive aos quatro cenários. Condicionar à saturação é fisicamente coerente (com a via livre há pouco tempo perdido a recuperar) e mais defensável que uma meta única. |
| 2026-08-24 | **P2** — latência (100 ms vs 200 ms) | **Duas métricas distintas, ambas instrumentadas e ambas mantidas no texto.** RNF01 = *latência de decisão* (< 100 ms): do estado recebido à emissão do comando, software puro, medida com `perf_counter()`. H3 = *latência fim-a-fim* (< 200 ms): de `t_deteccao` a `t_atuacao`, incluindo rede e atuação física. | Não são o mesmo número medindo a mesma coisa; o conflito era aparente. A tabela `metrica_latencia` já prevê os três carimbos (`t_deteccao`, `t_decisao`, `t_atuacao`), então a separação sai de graça. Reportar p95 e p99 de ambas, nunca só a média. |
| 2026-09-10 | **P3 REVOGADA** — a banca espera ML | A decisão de 2026-08-24 (abaixo) **deixa de valer na parte que excluía aprendizado de máquina**. O orientador confirmou que a banca espera ML e indicou o ponto: decidir **qual VE é priorizado** quando há mais de uma emergência simultânea, hoje o desempate determinístico de E8. Abre **P19**. Continua valendo que o **restante** do motor é agente reativo determinístico — o ML entra em um ponto delimitado, não substitui o motor —, e que Q-learning para E7 segue como trabalho futuro. | A decisão P3 foi tomada em 2026-08-24 com a ressalva expressa de **"comunicar ao orientador — a expectativa do avaliador pesa aqui"**. Comunicada, a expectativa se revelou oposta à suposição. Registrar a revogação com data e motivo é o que separa mudança de escopo justificada de descuido (mesmo princípio de P12); apagar a decisão anterior esconderia que a equipe raciocinou antes de decidir, o que é justamente o que sustenta a defesa. |
| 2026-09-10 | **P18** — teto para a degradação transversal | **Sem teto numérico; tratamento qualitativo**, por decisão do orientador. O objetivo geral foi reescrito: de *"sem degradar de forma inaceitável o fluxo transversal"* para *"quantificar o custo que essa priorização impõe ao fluxo transversal"*. | Um objetivo que promete um critério inexistente é mais frágil na arguição do que um que promete medição. A troca move o trade-off de ressalva para objetivo declarado, e o trabalho passa a prometer exatamente o que os dados cumprem. Sem teto não há linha nova em T6 — há uma seção de discussão a escrever, com o custo medido (+43,6% no `intenso` após P16). Nada muda no código nem nas execuções. |
| 2026-08-24 | **P3** — o que é a "IA" | **Opção 1:** o sistema é descrito como *agente reativo com otimização determinística baseada em conhecimento* — técnica clássica de IA, coberta por Russell & Norvig (já na bibliografia). A palavra "IA" fica reservada à caracterização de agente; o restante do texto usa "algoritmo de decisão". Aprendizado de máquina (ex.: Q-learning tabular para a política de compensação E7) fica como **trabalho futuro explicitamente descrito**. | Baixo risco e custo zero de cronograma, sem sacrificar rigor: o sistema *é* um agente reativo, e chamá-lo pelo nome correto é mais forte na banca do que vestir de ML algo que não treina nada. **Comunicar a decisão ao orientador** — a expectativa do avaliador pesa aqui. |
| 2026-08-24 | **P5** — volume de `estado_semaforo_amostra` | **Opção (b) + (c):** o Postgres recebe apenas **transições de fase**, não amostras periódicas. Além disso, só execuções marcadas como **exemplares** (uma por par cenário × modo, usadas nas figuras) são persistidas; as demais das 600 vivem em CSV sob `analysis/data/`. | Transições permitem reconstruir o histórico completo e verificar I2/I3 e I4 com custo de centenas de milhares de linhas em vez de 173 milhões. CSV cobre a análise em lote sem sobrecarregar o banco numa máquina de estudante. A coluna `t_simulacao` passa a marcar o instante da transição. |
| 2026-08-24 | **P13** — conjunto de fases do protótipo | O protótipo é **um cruzamento com 4 aproximações**, em regime de ***split phasing***: **4 fases, uma aproximação verde por vez**. `PRE,<fase>,<dur_s>` passa a aceitar `fase ∈ 1..4`. Acrescentados `TESTMODE,<0\|1>` e `TEST,<c1><c2><c3><c4>` para acionamento direto **restrito ao modo de bancada**. A matriz de conflito é aplicada **no motor e, independentemente, no firmware**. | Refuta a inferência de 2 fases da v1 do contrato. Sob split phasing a matriz de conflito é total, então I1 vira `contar_verdes() <= 1` — três linhas de guarda no AVR e uma verificação grep-ável na telemetria. O comando direto atende à necessidade de conferir fiação sem abrir brecha para violar I1 em operação: fora do modo de teste é recusado, e mesmo dentro dele a guarda de conflito continua ativa. |
| 2026-08-24 | **Perfil de tempos da bancada** (decorrente de P13) | `parametros.hardware.yaml`: **verde 3 s, amarelo 2 s, all-red 1 s**, com `verde_min_s = verde_s = 3.0`. Ciclo completo de 4 fases = **24 s**. Pior caso da transição de preempção = **6 s**. | Com 4 fases o ciclo a 5 s de verde levava 32 s, lento demais para a banca acompanhar. A 3 s cai para 24 s. Como `verde_s` coincide com o piso de I4, a preempção na bancada nunca trunca verde — aguarda o corrente terminar, o que simplifica o firmware. O caso de truncamento continua exercitado no perfil de simulação (`verde_min_s = 7.0`), que é de onde vêm os dados. |
| 2026-08-24 | **P10** — resistores nos LEDs | **Módulos semáforo já têm resistores integrados** (confirmado pela equipe de hardware). Nenhum resistor externo necessário. Cada módulo acende um LED por vez, então o pior caso é ~80 mA para 4 LEDs simultâneos. | Confortavelmente abaixo do limite de 200 mA do ATmega328P e dos 40 mA por pino. Remove a única restrição elétrica para operação prolongada — o teste de 30 min do checklist pode ser feito sem ressalva. |
| 2026-08-24 | **P7** — radar inexistente no protótipo | **Declarar explicitamente** no TCC que, no protótipo físico, o RFID-RC522 **emula** a função do conjunto radar + V2I, e que a validação da fusão de sensores ocorre exclusivamente em ambiente simulado. Sem HC-SR04. | Custo zero e honesto. A banca vai olhar a bancada e procurar o radar; dizer antes desarma a pergunta. Adicionar um segundo sensor físico ampliaria o escopo sem melhorar nenhuma hipótese — nenhuma das três depende de fusão física. |
| 2026-08-24 | **Dependências fora da stack fixa** (Bloco 0, regra do §4.8 de `08`) | Acrescentadas ao `pyproject.toml`: **PyYAML** (runtime) e **types-PyYAML** (tipagem). As demais adições já estavam sancionadas por outro arquivo do contexto e não constituem exceção: `ruff` e `mypy` (`08` §3), `structlog` (`02` §7), `testcontainers` (`06` §1), `hypothesis` (`06` §3, e nota do plano no Bloco 2), `psycopg` (implícita na `DATABASE_URL` de `02` §4). | `parametros.yaml` é a espinha dorsal da regra "todo número mágico vive em arquivo de configuração" (`08` §4.3), e `mapa_fases.yaml`/`cenarios.yaml` virão no Bloco 3. Ler YAML exige um parser; a biblioteca padrão não traz um. PyYAML é a escolha canônica, sem dependências transitivas. |
| 2026-08-25 | **P14** — onde termina a medição do RF02 | **Leitura (a): o RF02 mede da detecção até o INÍCIO DA ATUAÇÃO.** O amarelo já é a alteração do semáforo, e o marco é o `ACK` do atuador. O `00-visao-geral.md` §6 passa a declarar o ponto final explicitamente; o perfil de tempos de `parametros.hardware.yaml` e o ciclo de 24 s de P13 **ficam inalterados**. | O requisito nasceu "alterar semáforos em até 3 s" — e alterar é o que o amarelo faz; o verde final é *conceder passagem*, que é o RF03, medido separadamente por `waitingCount == 0`. Medir até o verde final faria o RF02 absorver o RF03 e ainda embutir o verde mínimo, que é um invariante de segurança (I4) e não latência do sistema: um cruzamento que acabou de abrir o verde seria "lento" por obedecer a I4. Some-se que a instrumentação já implementa esta leitura — `t_atuacao` é carimbado na chegada do `ACK` (contrato §10), e o Arduino responde `ACK,PRE` ao **iniciar** a transição —, então a alternativa exigiria mudar firmware, perfil de tempos e ponto de medição para piorar a demonstração. **Custo:** declarar a leitura no texto, sob pena de a pergunta aparecer na arguição sem resposta preparada. |
| 2026-08-25 | **Serviço `migracoes` no compose, com usuário único** | Acrescentado um serviço one-shot que roda `alembic upgrade head` e os seeds antes de o `backend` subir. Ele usa o **mesmo** usuário `tcc` da aplicação, contrariando o §6 de `02` ("usuário da aplicação sem privilégio de DDL; migrations com usuário separado") **no ambiente de desenvolvimento**. A separação continua descrita no `02` §6 como arquitetura-alvo. | Antes disso, `docker compose up` entregava um backend com `/health` verde e **zero tabelas** — o schema só existia depois de dois comandos manuais. Cumpria a letra da Definition of Done ("sem passo manual *não documentado*") e não o espírito. Criar o usuário separado de DDL agora custaria script de inicialização, um segundo conjunto de credenciais no `.env` e uma classe nova de erro de permissão para depurar, sem benefício num banco local descartável. Isolar a operação num serviço próprio é o que torna a troca futura uma mudança de uma linha. |
| 2026-08-24 | **Hypothesis** (Bloco 2, regra do §4.8 de `08`) | Acrescentada ao `pyproject.toml` como dependência **só de teste**. Não entra no runtime nem no contêiner do backend. | O `06` §3 a recomenda nominalmente para I1: *"gerar milhares de sequências de comandos aleatórios e verificar que o invariante nunca quebra"*. É a diferença entre afirmar que os casos que pensamos passam e afirmar que não se achou contraexemplo em milhares de tentativas — argumento muito mais forte na banca. Como é dependência de teste, não amplia a superfície do que roda na apresentação. |
| 2026-08-24 | **I5 é responsabilidade do motor** (Bloco 2) | O motor passa a acompanhar, por cruzamento, quando cada fase teve verde pela última vez, e **recusa preemptar** para longe de uma fase perto do teto de `vermelho_max_s`. A guarda não dispara quando a fase pedida é a própria faminta — nesse caso preemptar resolve a starvation. | A tabela de invariantes do `contrato` §9 já atribuía I5 ao motor, mas nada no código a garantia. A máquina de estados sozinha **pode** matar de fome uma aproximação sob uma sequência adversária de extensões de verde; é por isso que a decisão de preemptar precisa consultar o histórico de verdes. Verificado em `test_motor.py`. |
| 2026-08-24 | **I4 verificado por transição, não por par** (Bloco 2) | `core/seguranca.verificar_transicao()` passa a checar I4 sobre uma transição isolada. Um amarelo só pode suceder um verde, então `duracao_fase_anterior_s` de uma transição para `AMARELO` **é** a duração daquele verde. | Furo encontrado por **teste de mutação**: com o verde mínimo sabotado, a violação não era acusada. A checagem antiga só rodava sobre pares consecutivos, e a **primeira** transição de cada execução ficava sem predecessor — justamente a mais exposta a um comando prematuro, logo após a partida do controlador. Registrado como teste de regressão. |
| 2026-08-24 | **python-dotenv** (Bloco 1, regra do §4.8 de `08`) | Acrescentada ao `pyproject.toml`. Usada por `db/migrations/env.py` e, adiante, por `sim/` e `bridge/` — os três rodam **no host**, fora do compose, e portanto não recebem as variáveis pelo `environment:` do Docker. | Sem ela, `alembic upgrade head` só funcionaria com as variáveis exportadas à mão a cada terminal novo, o que contraria a Definition of Done do `CLAUDE.md` ("sem passo manual não documentado"). A alternativa era escrever um parser de `.env` próprio: ~10 linhas que parecem triviais até aparecerem aspas, comentários e valores com `=`. |
| 2026-08-25 | **Caracterização dos cenários passa a ser a medida** (Bloco 3, decorrente de P11) | Os fluxos (300/700/1.200) e os **nomes** dos cenários (`leve`, `moderado`, `intenso`) ficam como estão. O que muda é a **caracterização**: cada cenário passa a ser descrito pelo v/c medido, e não pela faixa que se supunha. O cenário `intenso` é declarado como **"saturação moderada-alta, v/c ≈ 0,73"**. Os limiares de 0,40 e 0,75 permanecem intocados, e a função de classificação continua devolvendo `moderado` para ele — o que é o resultado correto e é o que vai no texto. | Era a única das três saídas que não mexe em nada já entregue **e** descreve o experimento pelo que ele mede. Aumentar o fluxo para ~1.300 contrariaria a regra explícita de manter 300/700/1.200, que já estão no texto; reduzir a razão de verde para inflar o v/c seria ajustar o experimento até o número caber, exatamente o que o `CLAUDE.md` proíbe. **O nome do cenário passa a ser rótulo de identificação do ponto experimental, não afirmação sobre o regime.** Isso precisa aparecer no texto: a tabela da metodologia traz o v/c medido ao lado do nome, e a redação evita dizer "tráfego intenso" onde o dado diz 0,73. H1 continua de pé — P1 pede "moderada a intensa", e os dois cenários em que a meta se aplica medem 0,42 e 0,73. |
| 2026-08-25 | **Rota do VE atravessa os oito cruzamentos** (Bloco 3) | O `04` §3 se contradizia: "grade 2×4 com 4 transversais" (em que cada arterial cruza 4) e "o VE atravessa os 8 cruzamentos". Adotada a leitura que preserva as duas afirmações: a rota é um **"U"** — arterial 1 de oeste a leste (CRUZ_01..04), desce a transversal 4 e volta pela arterial 2 (CRUZ_08..05). 4.500 m, oito cruzamentos, duas conversões à direita. | É a única leitura que fecha com "os 8 cruzamentos" **e** com os ~5 km do pré-projeto, sem mexer na geometria 2×4 que o plano fixa em 3.1. Tem um ganho metodológico de brinde: o corredor **muda de eixo** no meio do percurso (em CRUZ_08 o VE pede a fase transversal, não a arterial), o que exercita E4 de verdade — um corredor que pedisse sempre a mesma fase não provaria que a seleção de fase funciona. Escolha confirmada com a equipe. |
| 2026-08-25 | **Demanda transversal é derivada, não escolhida** (Bloco 3) | Cada aproximação transversal recebe o fluxo que a coloca no **mesmo grau de saturação** da arterial, calculado a partir do fluxo de saturação medido: 135 / 314 / 539 veíc./h nos três cenários. | As alternativas eram piores. Repetir o fluxo nominal da arterial (1.200) numa via de uma faixa daria v/c > 1,5: fila que não dissipa, gridlock e execução inválida por `04` §12. Uma fração fixa declarada ("metade da arterial") seria exatamente o número sem lastro que o encaminhamento de P11 existe para eliminar. Derivar mantém a malha inteira no regime que caracteriza o cenário, que é o que a condição de H1 exige. Escolha confirmada com a equipe. |
| 2026-08-25 | **`tau` calibrado em `veiculos.typ.xml`** (Bloco 3) | `tau` do carro passa de 1,0 s (padrão do SUMO) para **1,6 s**, e o do ônibus para 1,8 s. Critério **declarado antes do ajuste**: levar o headway do carro ao valor correspondente ao centro da faixa de plausibilidade (1.800 veíc./h/faixa a 16,7 m/s ⇒ 2,0 s ⇒ `tau` = 2,0 − 7/16,7 = 1,58). O valor que vale para o TCC é o **medido depois**, não o alvo. | Com `tau = 1,0` a primeira medição deu ~2.400 veíc./h/faixa, fora da faixa de plausibilidade — e não por ruído: no modelo de car-following do SUMO o headway em regime é `tau + (minGap + length)/v`, que com aqueles valores dá exatamente 1,42 s. O modelo reproduzia fielmente um parâmetro irreal. `tau` não era declarado em lugar nenhum do `context/` (o `04` §4 fixa `accel`, `decel`, `sigma`, `length` e `maxSpeed`, não ele), então não houve contradição com o escopo — houve o preenchimento de uma lacuna, pelo procedimento que o próprio plano prescreve para valor fora de esquadro. **Consequência:** mexer em `tau`, `minGap`, `length`, `accel` ou `decel` obriga a remedir a saturação e regerar a tabela de cenários e os arquivos de fluxo, nessa ordem. |
| 2026-08-25 | **`ESTENDER_VERDE` conta a partir de agora** (defeito do Bloco 2, achado no Bloco 3) | `core/priorizacao/fases.py` interpretava `duracao_s` como duração **total** do verde, contada do início dele; passa a contar **a partir do instante do comando**, com o teto de `verde_max` ainda ancorado no início (I5 preservado). | O motor calcula `duracao_s = eta + margem`, que é tempo a partir de agora. Sob a leitura antiga, o comando virava seu oposto assim que o verde já durava mais que o pedido: pedir "segure mais 9 s para o VE passar" fechava o verde imediatamente. Efeito medido antes e depois, mesma seed e mesmo cenário: **6 paradas e 409 s de travessia → 0 parada e 313 s**. Nenhum teste unitário pegava — todos exercitavam extensões a partir de verdes recém-abertos. É a semântica de `PRE,<fase>,<dur_s>` do protocolo serial, então firmware e simulação voltam a concordar. |
| 2026-08-25 | **E7 passa a ser executada, e não só calculada** (defeito do Bloco 2, achado no Bloco 3) | O motor calculava `PlanoCompensacao`, guardava e **nada nunca o aplicava**. Passa a emitir `ESTENDER_VERDE` com o restante da duração planejada a cada fase que abre, enquanto a compensação vigora. O comando sai **sem** `id_veiculo`, e a máquina de estados só marca `em_preempcao` quando há VE associado. | Os braços `PREEMPCAO` e `PREEMPCAO_COMPENSADA` saíam com resultados **idênticos até o último dígito** — E7 era um no-op e H2 não tinha mecanismo nenhum por trás. O `08` §2 é explícito: cortar E7 obriga a tirar H2 do trabalho, não a deixá-la sem sustentação. A distinção por `id_veiculo` importa porque `em_preempcao` viaja para `estado_semaforo_amostra`: sem ela, os dois ciclos de compensação seriam contabilizados como preempção e o custo transversal que H2 mede seria atribuído ao evento errado. Coberto por `test_compensacao_estende_de_fato_o_verde_das_fases`. |
| 2026-08-25 | **Tráfego de fundo é passante, sem conversões** (Bloco 3) | Todo veículo de fundo entra por uma fronteira e sai pela oposta, em linha reta. As únicas conversões do experimento são as duas do VE. | Além da simplicidade, há razão metodológica: sem conversões o fluxo de cada aproximação é exatamente o fluxo declarado do cenário, e o v/c **derivado** e o **medido** passam a medir a mesma coisa — que é o que a verificação de `04` §12 item 4 confronta. Com conversões, a demanda se redistribuiria segundo uma matriz origem-destino que o pré-projeto não fornece, e inventá-la cairia na armadilha que P11 existe para evitar. **Limitação a declarar no texto:** as conversões permissivas à esquerda existem na rede mas não são exercitadas pelo tráfego de fundo. |
| 2026-08-25 | **`queue.xml` sai do padrão; `summary` agregado a 60 s** (Bloco 3) | O SUMO grava `queue` e `summary` a cada passo. Com passo de 0,1 s, a primeira execução completa (3.600 s) produziu **77 MB de `queue.xml`** e 10 MB de `summary.xml`. `queue-output` passa a ser opcional (`--saida-detalhada`) e `summary` passa a agregar a cada 60 s. | Nas 600 execuções do Bloco 8 seriam ~46 GB só de fila, num disco de estudante — e para um dado **redundante**: os detectores E2 já medem fila com agregação de 300 s, e o coletor já acumula a fila máxima por aproximação em memória. É a mesma aritmética de P5 e da latência detalhada: volume bruto não é gratuito, e o que sustenta as hipóteses são os agregados. A saída bruta por execução caiu de ~88 MB para ~1,5 MB. Só apareceu ao rodar a primeira execução de 3.600 s de ponta a ponta — as de verificação, mais curtas, não davam a escala do problema. |
| 2026-08-25 | **`latencias.csv` detalhado só em execução exemplar** (Bloco 3) | Uma linha por decisão apenas nas execuções marcadas como exemplares; as demais gravam só os percentis, em `execucoes.csv`. | Mesma aritmética que levou à decisão P5: são 36.000 decisões por execução, o que daria mais de 20 milhões de linhas nas 600 do Bloco 8. Os percentis — que são o que RNF01 e H3 exigem (`04` §9.3) — vão em toda execução. |
| 2026-08-26 | **`latencias.csv` deixa de ser versionado** | Acrescentado ao `.gitignore`. É o **único** CSV de `analysis/data/` fora do controle de versão; `execucoes.csv`, `ve_por_execucao.csv`, `transversal_por_execucao.csv`, `descartes.csv` e os dois da calibração continuam versionados. | São 13 MB (~1,3 MB comprimidos) mesmo já restrito às execuções exemplares por P5, e o lote **reescreve o arquivo inteiro** a cada corrida — cada reexecução acrescentaria esse peso à história do repositório para sempre, e P16/P17 garantem várias. O que sustenta o texto do TCC são os **percentis** (mín, média, p95, p99, máx), que estão em `execucoes.csv` de toda execução e continuam versionados. O único consumidor do detalhe é a figura **F2** (`07` §5), regenerável rodando as exemplares de novo. **Ressalva registrada:** latência é a única grandeza do experimento que não é reprodutível a partir da seed — é relógio de parede, depende da máquina e da carga —, então regerar F2 dá distribuição equivalente, não idêntica. Se o Bloco 9 precisar de F2 estável entre gerações, a saída é versionar um resumo por quantis (~1.000 linhas por exemplar) em vez das 36.000 amostras. |
| 2026-08-26 | **Removida a linha `leve/PREEMPCAO/seed=42` de `execucao_simulacao`** | Sobra de uma execução de verificação do Bloco 3 (700 s, versão `c8cc3c7`, 477 transições), apagada com as transições em cascata. O banco fica com **60 execuções e 12 exemplares**, um por par cenário x modo. | A linha estava marcada `exemplar`, o que dava **dois** exemplares para o par `leve`/`PREEMPCAO` e violava a decisão P5 — a regra que limita o volume de `estado_semaforo_amostra` e define quais execuções alimentam as figuras do capítulo 5. Não é dado experimental: não pertence a nenhuma matriz (a seed 42 está fora de 1..50), foi produzida por versão anterior do código e com duração fora do protocolo, e não aparece em nenhum CSV de `analysis/data/`. Apagá-la não altera número nenhum do piloto; deixá-la faria o Bloco 8 escolher entre dois exemplares para o mesmo par. |
| 2026-08-26 | **Lote antecipado do Bloco 8 para o Bloco 4** | `sim/controlador/lote.py` foi escrito no Bloco 4, com a CLI que o `04` §7 já especificava. O que muda entre o piloto e o lote completo é o valor de `--seeds` (`1..5` contra `1..50`), e mais nada. | O piloto são 60 execuções de 3.600 s — número que não se roda à mão, e cujo resultado precisa ser tão reprodutível quanto o das 600. Escrever o lote duas vezes (uma versão descartável agora, a definitiva depois) custaria mais do que escrevê-lo uma vez certo, e a versão descartável seria a que produziria o dado que decide se H1 se sustenta. |
| 2026-08-26 | **O lote paraleliza com processos `traci`** (encaminhamento parcial de **P15**) | Cada trabalhador sobe o seu SUMO e fala com ele por `traci`. `--libsumo` continua exposto e implementado; só não é o padrão. **Medido em 8 núcleos físicos, `--paralelo 6`:** as 60 execuções do piloto levaram **~35 min** — ~1 min por execução no `leve`, ~2 min no `moderado`, ~4 min no `intenso`. | Resolve na prática a opção 2 de P15 sem fechar a decisão: **o `traci` dá conta da janela de tempo**. Extrapolando, as 600 do Bloco 8 levariam ~6 h — uma noite de máquina, não uma semana. Isso enfraquece bastante o argumento para abrir exceção à regra de não instalar cliente do SUMO pelo pip. **P15 continua aberta**, mas com o número na mão que a opção 3 pedia. |
| 2026-08-26 | **O pareamento da análise é por VE, não por execução** | `analysis/relatorio_piloto.py` compara os braços sobre a **interseção dos ids de VE presentes nos três**, por (cenário, seed), e declara no relatório quantos VEs a interseção descartou. | Comparar a média de execução tem um viés silencioso e **conservador**, que é o que o faz passar despercebido: o último VE parte perto do fim do horizonte e, no baseline — mais lento —, pode não chegar dentro dos 3.600 s. Ele sai da média do `FIXO` mas fica na da preempção; a média do controle melhora por exclusão justamente do caso difícil, e a redução medida encolhe. No piloto isso valeu de 0 a 5 VEs por cenário. Coberto por teste. |
| 2026-08-26 | **Execução descartada não entra em `analysis/data/`** | `validar_execucao()` roda em toda execução do lote. A reprovada fica na própria pasta de `sim/saida/`, com a evidência bruta; o motivo e o caminho da evidência vão para `analysis/data/descartes.csv`. O mesmo arquivo registra as remoções feitas por `--repetir`. | O `06` §4 manda descartar e registrar. Deixar a linha reprovada no CSV consolidado exigiria que todo consumidor a filtrasse — e o Bloco 9 tem seis tabelas e seis figuras, cada uma um lugar para esquecer o filtro. Manter a evidência bruta no disco é o que permite auditar o descarte depois; o registro é o que separa metodologia de racionalização. |
| 2026-08-26 | **O lote recusa consolidar um ponto que já tem linhas no CSV** | Antes de rodar qualquer coisa, `rodar()` confere se algum ponto da matriz já aparece em `execucoes.csv` e falha com `PontoJaConsolidadoError`. `--repetir MOTIVO` é a autorização explícita: apaga a evidência anterior do CSV **e** do banco, e registra a remoção. | O banco já tinha essa proteção (restrição única em cenário/modo/seed); o CSV não tinha nenhuma — ele simplesmente acrescenta. A assimetria é perigosa porque o CSV é o que alimenta o capítulo 5: uma linha duplicada não falha alto, ela vira **uma seed com peso dobrado na média**. A checagem vem antes das execuções porque descobrir a duplicata na consolidação significaria descobri-la depois de horas de máquina gastas. |
| 2026-08-26 | **Cada execução do lote limpa os CSV da própria pasta antes de rodar** (defeito achado no piloto) | `_limpar_csv_da_pasta()` apaga os quatro CSV da pasta da execução antes de executá-la. | **Não é hipótese: aconteceu.** Quatro pontos tinham sido exercitados num teste curto (400 s) antes do piloto, e `gravar_csv()` **acrescenta** — comportamento certo para o arquivo consolidado, errado para a pasta de uma execução. O `execucoes.csv` do piloto saiu com **64 linhas para 60 execuções**, com as quatro sobras carregando a duração errada. Só apareceu porque a contagem foi conferida; a média não teria denunciado nada. Os quatro pontos foram reexecutados com `--repetir` e o descarte está em `descartes.csv`. Coberto por teste de regressão. |
| 2026-08-24 | **Cliente TraCI não vem do pip** (Bloco 0) | O `pyproject.toml` **não** declara extra `sim`. `traci` e `libsumo` são importados de `%SUMO_HOME%/tools`, acrescentado ao `sys.path` pelo `conftest.py` da raiz. | Instalar `traci` pelo pip cria uma segunda cópia do cliente, que pode divergir da versão do binário instalado. A divergência não falha alto: ela aparece como comportamento sutilmente diferente do TraCI, que é a classe de bug mais cara de diagnosticar neste projeto. Usar o cliente que acompanha o binário elimina a classe inteira. |
| 2026-08-31 | **Enunciado de H2 passa a ser `≥ 15%`** (encaminhamento parcial de **P17**) | "Mitigar em **até** 15% o impacto negativo" vira "mitigar em **no mínimo** 15%". Propagado para `00` §5, `07` T6 (que trazia `≤ 15%`) e a docstring de `core/priorizacao/compensacao.py`. **O denominador continua aberto** — ver P17. | A redação antiga era um teto, não uma meta: sob ela, os −1,0% a +0,6% medidos no piloto **cumpririam** H2 literalmente. Hipótese que não pode falhar não é hipótese, e a banca não precisaria de muito para achar isso. `≥ 15%` é o que a equipe sempre quis dizer, é simétrico com H1 (`≥ 25%`) e é a única forma sob a qual H2 pode ser rejeitada. |
| 2026-08-31 | **P16 — corrigir o mecanismo antes de mexer em H1** | Adotada a opção 3 começando pela 1: ajustar `tempo_antecipacao_margem_s` para consultar a fila que o motor já recebe, remedir a matriz do piloto e só então avaliar se H1 precisa ser reformulada. Reformulação vira contingência, com o orientador. Três guardas fixadas antes do código: critério declarado antes do ajuste, congelamento dos parâmetros antes da remedição, e **calibração em seeds fora de 1..50**. | Reformular a hipótese sem tentar corrigir o mecanismo é ajustar a régua ao resultado, o que o `CLAUDE.md` proíbe; tentar primeiro e reformular só se o teto for real é a ordem defensável na arguição. A guarda das seeds resolve um problema que passaria despercebido: 1..5 é subconjunto de 1..50, e afinar o modelo sobre elas contaminaria 5 das 50 execuções que validam o resultado final. Calibrar em 101..105 custa nada e torna o Bloco 8 inteiramente fora-da-amostra. |
| 2026-08-31 | **P6 — formato dos números do capítulo 5 confirmado** | As tabelas do capítulo 5 do pré-projeto migram para uma seção **"Resultados esperados"** dentro da metodologia, rotulada como estimativa preliminar; o capítulo 5 passa a ser preenchido só pela saída de `analysis/gerar_resultados_tcc.py`. A migração **não** depende do Bloco 8 e pode ser feita já. | É o item de maior risco acadêmico do projeto (`07` §1). Separar fisicamente estimativa de medição, no documento, é o que impede um número não medido de sobreviver por esquecimento até a versão entregue — que é exatamente como esse erro chega à banca. |
| 2026-08-31 | **P16 resolvida pelo mecanismo, sem tocar em H1** | E3 passou a somar à janela de ativação o tempo de dissipação da fila do acesso de entrada, com teto derivado de `preempcao_timeout_s`. Medido nas mesmas seeds do piloto: `intenso` **18,1% → 31,2%**, pior seed 13,0% → 27,9%, paradas do VE 2,76 → 0,08. A contingência de reformular H1 **não foi acionada**. Custo: a espera transversal no `intenso` subiu de +24,6% para +43,6%. | A ordem — tentar o mecanismo antes de mexer na hipótese — foi declarada e **commitada antes do código** (`1ae762e`), e é o que torna o resultado defensável em vez de oportunista. A correção não introduz parâmetro livre: fila dos detectores E2, faixas da geometria da rede, headway de saturação medido, teto derivado. Os baselines `FIXO` idênticos aos do piloto provam que a melhora não vem de tráfego mais fácil. O custo transversal era um dos três resultados **declarados antes de medir** e vai para o texto como trade-off, não como nota de rodapé. |
| 2026-08-31 | **H3 — 5 repetições de bancada** | A evidência de H3 (latência fim-a-fim < 200 ms) vem do protótipo, com **5 repetições** roteirizadas no checklist de aceitação. **Com n = 5 o p95 não é estimável** — o critério passa a ser reportado como **mín / mediana / máx das 5, com o n declarado**, e o limiar de 200 ms verificado sobre o **máximo observado**. | A simulação não tem atuação física: `t_atuacao` é o mesmo passo de `t_decisao`, então o número de H3 só existe na bancada. 5 repetições é o que cabe no roteiro manual. A ressalva do n é obrigatória: chamar de "p95" o percentil de 5 amostras é, na prática, reportar o máximo com nome de percentil, e é o tipo de imprecisão que a banca pega. **Ver a observação sobre aproveitar as 100 leituras do RNF05** (`06` §2) — se a instrumentação de latência entrar nelas, H3 ganha um p95 de verdade sem repetição extra. |
