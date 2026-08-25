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

**Bloqueia:** a redação da metodologia, não o código. Mas precisa estar resolvido antes de a Sprint 1 (malha) ser considerada fechada — a calibração dos cenários `leve`/`moderado`/`intenso` referencia esses números.

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
| 2026-08-25 | **Serviço `migracoes` no compose, com usuário único** | Acrescentado um serviço one-shot que roda `alembic upgrade head` e os seeds antes de o `backend` subir. Ele usa o **mesmo** usuário `tcc` da aplicação, contrariando o §6 de `02` ("usuário da aplicação sem privilégio de DDL; migrations com usuário separado") **no ambiente de desenvolvimento**. A separação continua descrita no `02` §6 como arquitetura-alvo. | Antes disso, `docker compose up` entregava um backend com `/health` verde e **zero tabelas** — o schema só existia depois de dois comandos manuais. Cumpria a letra da Definition of Done ("sem passo manual *não documentado*") e não o espírito. Criar o usuário separado de DDL agora custaria script de inicialização, um segundo conjunto de credenciais no `.env` e uma classe nova de erro de permissão para depurar, sem benefício num banco local descartável. Isolar a operação num serviço próprio é o que torna a troca futura uma mudança de uma linha. |
| 2026-08-24 | **Hypothesis** (Bloco 2, regra do §4.8 de `08`) | Acrescentada ao `pyproject.toml` como dependência **só de teste**. Não entra no runtime nem no contêiner do backend. | O `06` §3 a recomenda nominalmente para I1: *"gerar milhares de sequências de comandos aleatórios e verificar que o invariante nunca quebra"*. É a diferença entre afirmar que os casos que pensamos passam e afirmar que não se achou contraexemplo em milhares de tentativas — argumento muito mais forte na banca. Como é dependência de teste, não amplia a superfície do que roda na apresentação. |
| 2026-08-24 | **I5 é responsabilidade do motor** (Bloco 2) | O motor passa a acompanhar, por cruzamento, quando cada fase teve verde pela última vez, e **recusa preemptar** para longe de uma fase perto do teto de `vermelho_max_s`. A guarda não dispara quando a fase pedida é a própria faminta — nesse caso preemptar resolve a starvation. | A tabela de invariantes do `contrato` §9 já atribuía I5 ao motor, mas nada no código a garantia. A máquina de estados sozinha **pode** matar de fome uma aproximação sob uma sequência adversária de extensões de verde; é por isso que a decisão de preemptar precisa consultar o histórico de verdes. Verificado em `test_motor.py`. |
| 2026-08-24 | **I4 verificado por transição, não por par** (Bloco 2) | `core/seguranca.verificar_transicao()` passa a checar I4 sobre uma transição isolada. Um amarelo só pode suceder um verde, então `duracao_fase_anterior_s` de uma transição para `AMARELO` **é** a duração daquele verde. | Furo encontrado por **teste de mutação**: com o verde mínimo sabotado, a violação não era acusada. A checagem antiga só rodava sobre pares consecutivos, e a **primeira** transição de cada execução ficava sem predecessor — justamente a mais exposta a um comando prematuro, logo após a partida do controlador. Registrado como teste de regressão. |
| 2026-08-24 | **python-dotenv** (Bloco 1, regra do §4.8 de `08`) | Acrescentada ao `pyproject.toml`. Usada por `db/migrations/env.py` e, adiante, por `sim/` e `bridge/` — os três rodam **no host**, fora do compose, e portanto não recebem as variáveis pelo `environment:` do Docker. | Sem ela, `alembic upgrade head` só funcionaria com as variáveis exportadas à mão a cada terminal novo, o que contraria a Definition of Done do `CLAUDE.md` ("sem passo manual não documentado"). A alternativa era escrever um parser de `.env` próprio: ~10 linhas que parecem triviais até aparecerem aspas, comentários e valores com `=`. |
| 2026-08-24 | **Cliente TraCI não vem do pip** (Bloco 0) | O `pyproject.toml` **não** declara extra `sim`. `traci` e `libsumo` são importados de `%SUMO_HOME%/tools`, acrescentado ao `sys.path` pelo `conftest.py` da raiz. | Instalar `traci` pelo pip cria uma segunda cópia do cliente, que pode divergir da versão do binário instalado. A divergência não falha alto: ela aparece como comportamento sutilmente diferente do TraCI, que é a classe de bug mais cara de diagnosticar neste projeto. Usar o cliente que acompanha o binário elimina a classe inteira. |
