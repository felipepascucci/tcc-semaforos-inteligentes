# 09 — Pendências e Decisões Abertas

Este arquivo lista contradições e lacunas identificadas na leitura dos documentos entregues. Itens marcados `DECISÃO DO GRUPO` **não devem ser resolvidos pelo agente de código**: exigem escolha da equipe, e alguns exigem consulta ao orientador.

Ao resolver um item, mover para a seção "Decisões tomadas" no fim do arquivo, com data e justificativa.

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

---

## P12 — Ordem das sprints alterada · `REGISTRO`

`08-roadmap-e-convencoes.md` §1 antecipa o banco de dados (Sprint 5 do texto) porque a Sprint 2 já precisa persistir. Registrar a alteração no capítulo de metodologia, com a justificativa — mudança de plano justificada é normal em processo iterativo e demonstra maturidade; mudança silenciosa parece descuido.

---

## Decisões tomadas

| Data | Item | Decisão | Justificativa |
| --- | --- | --- | --- |
| 2026-08-24 | **P1** — meta de redução (20% vs 30%) | H1 reformulada e **condicionada à saturação**: *"redução ≥ 25% no tempo total de travessia do VE em cenários de saturação moderada a intensa"*. O cenário `leve` é analisado e discutido separadamente, sem meta numérica. | A Tabela 1 do próprio pré-projeto mostra 8,3% em fluxo leve — nenhuma meta única sobrevive aos quatro cenários. Condicionar à saturação é fisicamente coerente (com a via livre há pouco tempo perdido a recuperar) e mais defensável que uma meta única. |
| 2026-08-24 | **P2** — latência (100 ms vs 200 ms) | **Duas métricas distintas, ambas instrumentadas e ambas mantidas no texto.** RNF01 = *latência de decisão* (< 100 ms): do estado recebido à emissão do comando, software puro, medida com `perf_counter()`. H3 = *latência fim-a-fim* (< 200 ms): de `t_deteccao` a `t_atuacao`, incluindo rede e atuação física. | Não são o mesmo número medindo a mesma coisa; o conflito era aparente. A tabela `metrica_latencia` já prevê os três carimbos (`t_deteccao`, `t_decisao`, `t_atuacao`), então a separação sai de graça. Reportar p95 e p99 de ambas, nunca só a média. |
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
| 2026-08-24 | **Cliente TraCI não vem do pip** (Bloco 0) | O `pyproject.toml` **não** declara extra `sim`. `traci` e `libsumo` são importados de `%SUMO_HOME%/tools`, acrescentado ao `sys.path` pelo `conftest.py` da raiz. | Instalar `traci` pelo pip cria uma segunda cópia do cliente, que pode divergir da versão do binário instalado. A divergência não falha alto: ela aparece como comportamento sutilmente diferente do TraCI, que é a classe de bug mais cara de diagnosticar neste projeto. Usar o cliente que acompanha o binário elimina a classe inteira. |
