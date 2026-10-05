# Plano de Desenvolvimento

> Documento irmão: [`contrato-hardware-software.md`](contrato-hardware-software.md) — a especificação da integração com o protótipo físico (pinagem, protocolo serial, requisitos de firmware, invariantes). Leia-o antes de qualquer trabalho em `firmware/`, `bridge/` ou `adapters/hardware/`.

Data-base: **2026-08-24**. Janela de entrega assumida: **3 a 6 meses** → apresentação estimada entre **nov/2026 e jan/2027**, com **congelamento de código 5 dias antes** (regra do `context/02` §9).

Escopo: completo, conforme `context/` (`context/08` §2).

> **Escopo confirmado em 2026-09-10, após a orientação.** Todos os blocos
> previstos seguem como estão, e o **Bloco 10** — priorização aprendida entre
> múltiplos VEs, pedido pelo orientador (P19) — é **acrescentado**. Faltam,
> portanto, os Blocos 5, 6, 7, 10, 8 e 9 — nessa ordem de execução.

---

## Princípio que organiza a ordem

O `context/08` §1 recomenda **5 → 2 → 3 → 1 → 7 → 4 → 6 → 8**. Este plano segue essa lógica com três ajustes justificados:

1. **Bloco 0 de fundação antes de tudo.** O repositório ainda não é um repositório git, não há `docker compose`, nem toolchain, e o SUMO não está instalado. Sem isso a Definition of Done do `CLAUDE.md` é inatingível já na primeira entrega.
2. **Piloto experimental antecipado** (Bloco 4). O `context/08` §6 identifica "resultados reais não confirmam H1" como o risco mais subestimado do projeto, e a mitigação é rodar 5 seeds cedo. Fazemos isso logo após o adaptador TraCI, muito antes do lote completo.
3. ~~**P10 verificado no Bloco 0.**~~ **Não se aplica mais.** Quando este plano foi escrito, P10 (LEDs sem resistor no limite de 200 mA do ATmega328P) era o único pendente com risco de dano físico. A equipe de hardware já o resolveu em 2026-08-24: os módulos semáforo **têm resistores integrados**, pior caso ~80 mA. Ver `context/09`, tabela de decisões tomadas.

---

## Blocos

### Bloco 0 — Fundação · ~3 dias

| # | Entrega |
|---|---|
| 0.1 | `git init`, `.gitignore`, primeiro commit; branch `main` protegida por convenção |
| 0.2 | Esqueleto de diretórios do `CLAUDE.md` (`backend/ sim/ firmware/ bridge/ frontend/ db/ analysis/ docs/`) |
| 0.3 | `pyproject.toml` com ruff (linha 100), mypy strict em `core/`, pytest + marcadores `sumo`/`hardware` |
| 0.4 | `docker-compose.yml` (db, backend, frontend, adminer no perfil `dev`) + `.env.example` |
| 0.5 | Instalação do SUMO 1.19+, `SUMO_HOME` configurado, `netconvert --version` validado |
| 0.6 | ~~**P10** — medir se os módulos semáforo têm resistor embutido~~ · **já resolvida** em `context/09` (módulos com resistor integrado, ~80 mA no pior caso). Nada a fazer |
| 0.7 | `backend/config/parametros.yaml` + `parametros.hardware.yaml` com os valores do `context/01` §5.3 |

**Pronto quando:** `docker compose up` sobe db + backend com `/health` verde; `ruff check` e `pytest` rodam limpos num teste trivial; `netconvert --version` responde.

**Estado: concluído em 2026-08-24.** SUMO 1.27.1 instalado (`winget install EclipseFoundation.SUMO`), `SUMO_HOME` definido pelo instalador; `docker compose up` sobe `db` + `backend` ambos *healthy*, com `/api/v1/health` retornando `estado: "ok"` e `banco: "ok"`; `ruff check`, `ruff format --check`, `mypy` (strict em `backend/core/`) e `pytest` limpos — 19 testes na execução padrão, 3 sob o marcador `sumo`. Duas dependências fora da stack fixa registradas em `context/09` (PyYAML e a decisão de **não** instalar `traci` pelo pip).

---

### Bloco 1 — Banco de dados (Sprint 5) · ~1 semana

| # | Entrega |
|---|---|
| 1.1 | Models SQLAlchemy 2.x de todas as 12 tabelas, com as correções P4 (`longitude DECIMAL(11,8)`, `tempo_medio_resposta DECIMAL(8,2)`, `log_prioridade.fk_metrica`) |
| 1.2 | `estado_semaforo_amostra` na forma da decisão P5 (transições, com `fase_anterior` e `duracao_fase_anterior_s`) e `execucao_simulacao.exemplar` |
| 1.3 | Migration Alembic inicial + enums Postgres + índices do `context/03` §3.3 |
| 1.4 | Repositories com a regra crítica do `context/03` §4.1: **nada de INSERT síncrono dentro do loop**; fila em memória + flush em lote |
| 1.5 | Seeds: 8 TLS da malha + ~~`PROTO_S1..S4`~~ **`PROTO_CRUZ_01` com 4 fases**, 3 VEs, 2 dispositivos IoT. Tags RFID ficam com UID placeholder até a leitura real no Bloco 5 |
| 1.6 | `db/schema.sql` gerado do banco vivo (anexo do TCC) |

> **Correção do item 1.5.** O plano pedia quatro semáforos `PROTO_S1..S4`, o que modela cada módulo como um cruzamento independente. O `context/03` §5 já corrigiu isso por causa de P13: o protótipo é **um** cruzamento com quatro aproximações, logo **uma** linha em `semaforo` e **quatro** em `fase_semaforo`. `S1..S4` seguem existindo como nomes de aproximação no firmware e no protocolo serial. Implementado conforme o `context/`.

**Pronto quando:** `alembic upgrade head` cria tudo do zero, seeds aplicam, e um teste de integração com testcontainers grava e lê um `log_prioridade` completo.

**Estado: concluído em 2026-08-24.** 12 tabelas, 5 enums e os 6 índices do `context/03` §3.3 criados pela migration `eb4834072797`; `alembic check` sem divergência e ciclo `upgrade → downgrade → upgrade` verde (o `downgrade` remove os tipos ENUM, que sobrevivem ao `DROP TABLE`). Seeds idempotentes: 9 semáforos, 4 fases, 3 VEs, 2 tags **inativas**, 2 dispositivos. `db/schema.sql` gerado. Suite: **44 testes** na execução padrão, dos quais 17 de integração sob o marcador `banco` (Postgres efêmero via testcontainers). Uma dependência nova registrada em `context/09` (python-dotenv).

---

### Bloco 2 — Motor de decisão (Sprint 3) · ~2 semanas · **núcleo do TCC**

Python puro. Zero import de `traci`, `pyserial`, `sqlalchemy` ou `fastapi`.

| # | Entrega |
|---|---|
| 2.1 | `core/modelos.py`, `core/comandos.py`, `core/excecoes.py` — dataclasses frozen do `context/01` §5.1 e §9 |
| 2.2 | `core/priorizacao/deteccao.py` — E1/E2/E3. **Distância ao longo da rota, nunca euclidiana** |
| 2.3 | `core/priorizacao/fases.py` — E4/E5, transição segura obrigatória (verde→amarelo→all-red→alvo) |
| 2.4 | `core/priorizacao/compensacao.py` — E7, fórmula com `K` do `parametros.yaml` |
| 2.5 | `core/priorizacao/conflito.py` — E8, desempate por tipo → ETA → preempção em curso |
| 2.6 | `core/priorizacao/motor.py` — `avaliar(EstadoMalha) -> list[Comando]`, síncrono e puro |
| 2.7 | `core/seguranca.py` — I1 a I5 como asserções por passo; violação → `FALLBACK_SEGURO` + incidente registrado |
| 2.8 | `test_arquitetura.py` — teste via AST que falha se `core/` importar framework ou I/O |
| 2.9 | **Property-based (Hypothesis) para I1** — milhares de sequências aleatórias de comandos, invariante verificado em todo estado alcançado |
| 2.10 | `test_desempenho.py` — p95 de `motor.avaliar()` < 100 ms em 10.000 chamadas (RNF01, decisão P2) |

**Pronto quando:** testes de I1–I5 passam; `mypy --strict core/` limpo; suite roda em segundos sem SUMO instalado.

> Hypothesis não consta na stack fixa do `context/02` §2. É dependência **só de teste** e o `context/06` §3 a recomenda nominalmente para I1. Registro a decisão ao introduzi-la.

**Estado: concluído em 2026-08-24.** `core/` com 13 módulos, `mypy --strict` limpo, e o teste de arquitetura via AST reprovando qualquer import de framework, I/O ou camada externa — inclusive `math.dist`, para que E1 não escorregue para distância euclidiana. Suite de **175 testes em ~18 s**, sem SUMO e sem hardware. Latência de decisão medida: **p95 de 0,034 ms** na malha de 8 cruzamentos e 0,070 ms com 32 — contra o orçamento de 100 ms do RNF01.
>
> Três achados registrados em `context/09`: **I5 não estava garantida por ninguém** (o contrato a atribui ao motor, mas o código não a implementava); **I4 escapava da verificação na primeira transição de cada execução**, furo encontrado por teste de mutação; e o **`preempcao_timeout_s` (45 s) é mais apertado que `verde_max_s` (60 s)** no perfil de simulação, então quem calibrar um precisa mexer no outro.
>
> Duas mudanças de forma em `context/01` §5.1, documentadas lá: contêineres imutáveis de verdade (`tuple`/`Mapping`) e os campos `posicao_na_via_m` e `sinal`, sem os quais RF01 e I4 não são verificáveis.

---

### Bloco 3 — Malha SUMO + adaptador TraCI (Sprints 1 e 2) · ~2 semanas

| # | Entrega |
|---|---|
| 3.0 | **Calibração dos cenários.** `sim/calibracao/fluxo_saturacao.py` **mede** o fluxo de saturação da própria malha (marcado `sumo`); `sim/calibracao/cenarios.py` converte os fluxos 300/700/1200 em grau de saturação e gera a tabela da metodologia (puro, testável sem SUMO). **Encaminha P11** |
| 3.1 | `sim/rede/*.xml` — grade 2×4, arterial 60 km/h com ~500 m entre cruzamentos, 4 transversais a 40 km/h; `make rede` chamando `netconvert` |
| 3.2 | Detectores E1/E2/E3 no `.add.xml` — sem eles H2 fica sem evidência |
| 3.3 | `sim/demanda/` — tipos de veículo, 3 arquivos de fluxo, rotas de VE (1 a cada 10 min) |
| 3.4 | **Validação da malha** (`context/04` §12): zero warning no netconvert, zero colisão, `--time-to-teleport -1` sem teleporte, v/c **medido** batendo com o v/c **derivado** em 3.0, dentro de tolerância declarada |

> **Por que 3.0 vem antes de tudo.** O plano original mandava conferir se o v/c
> medido bate com "o cenário pretendido" — mas não dizia de onde sai o
> pretendido. Os percentuais do `context/04` §5 (`<40%`, `40–75%`, `>75%`) estão
> declarados, não calculados. Sem a derivação, uma divergência em 3.4 não teria o
> que ajustar: viraria tentativa e erro até o número ficar bonito, que é
> exatamente o que a regra de ouro do `CLAUDE.md` proíbe.
>
> Os fluxos **300 / 700 / 1200 veíc./h continuam como estão** — vêm do
> pré-projeto e já estão no texto entregue. Eles são entrada da conta, não saída.
> O que 3.0 produz é a **classificação** deles em grau de saturação, que é o que
> permite afirmar "saturação moderada a intensa" (a condição de H1, decisão P1)
> por medição em vez de por decreto.
>
> **O fluxo de saturação é medido, não adotado da literatura** (decisão de
> 2026-08-25). A malha simulada tem um fluxo de saturação próprio, que emerge dos
> parâmetros de car-following do SUMO (`accel`, `decel`, `tau`, `minGap`,
> `length`) — adotar 1900 veíc./h de um manual e aplicá-lo a uma malha que na
> verdade escoa outro valor produziria um v/c errado com aparência de rigor.
>
> O método é o de campo, aplicado à simulação: satura uma aproximação, mantém o
> verde, **descarta os primeiros veículos** (o *start-up lost time*, em que a fila
> ainda está acelerando) e calcula `3600 / headway médio` do trecho saturado.
> Assim o número vem de código versionado, como o `CLAUDE.md` exige, e é
> regenerável.
>
> **Ressalva a declarar no texto — e a banca pode levantar.** Calibrar os
> cenários pela capacidade do próprio simulador tem um quê de circular: é
> natural que os cenários "caibam". A resposta honesta é que o objetivo não é
> provar que o SUMO é realista, e sim **caracterizar o regime de operação do
> experimento** — e a comparação com a faixa reportada na literatura serve
> justamente de guarda contra o modelo estar grosseiramente fora de esquadro. Se
> o valor medido cair muito longe do que se reporta para vias urbanas, o problema
> está nos parâmetros do `veiculos.typ.xml`, e é isso que se corrige.
>
> **Atenção metodológica:** os limiares de veíc./h/faixa que circulam para
> rodovia (capacidade ~1800–2200) valem para **fluxo ininterrupto** e não se
> aplicam aqui. Numa aproximação semaforizada a capacidade é o fluxo de saturação
> multiplicado pela razão de verde — com ciclo de 70 s e 30 s de verde, cerca de
> **metade**. Usar os limiares de rodovia reclassificaria o nosso `intenso` como
> `moderado` e derrubaria a formulação de H1.
| 3.5 | `sim/config/mapa_fases.yaml`, `cenarios.yaml`, `.sumocfg` |
| 3.6 | `adapters/sumo/` — interface única abstraindo `traci` (dev/GUI) e `libsumo` (lote) |
| 3.7 | `sim/controlador/executor.py` — 1 execução, seed explícita, grava `execucao_simulacao` |
| 3.8 | `sim/controlador/coletor.py` — métricas do `context/04` §9 + registro de transições (P5) |

**Pronto quando:** `python -m sim.controlador.executor --cenario leve --modo FIXO --seed 1` produz `tripinfo.xml` e uma linha em `execucao_simulacao`; corredor verde visível na `sumo-gui` no modo `PREEMPCAO`.

**Estado: concluído em 2026-08-25.** Malha 2×4 construída por `make rede` sem
avisos, 8 TLS, 44 vias, 108 detectores (48 E2, 48 E1, 12 E3). O executor roda os
três braços e grava os CSV de `analysis/data/`; `sumo-gui` mostra o corredor.
Suíte: **231 testes** na execução padrão e **21** sob o marcador `sumo`; `ruff`,
`ruff format` e `mypy --strict` limpos.

**Calibração (3.0), com números medidos.** Fluxo de saturação da malha:
**1.752 veíc./h/faixa** na arterial e **1.573** na transversal, ambos dentro da
faixa de plausibilidade declarada. Daí saem as capacidades (1.652 e 741 veíc./h) e
os graus de saturação: `leve` 0,18 · `moderado` 0,42 · `intenso` **0,73**. A
demanda transversal passa a ser **derivada** (135 / 314 / 539 veíc./h), e não
escolhida. A validação da malha (3.4) aprovou: v/c medido 0,186 contra 0,182
derivado, zero colisão, zero teleporte, zero violação de invariante no baseline.

**Efeito medido no corredor** (cenário `leve`, seed 1, 1.500 s, dois VEs):

| Modo | Travessia média do VE | Paradas |
| --- | --- | --- |
| `FIXO` | 490,6 s | 5,5 |
| `PREEMPCAO` | 272,3 s | **0** |
| `PREEMPCAO_COMPENSADA` | 274,1 s | **0** |

Latência de decisão: p95 de **0,05 ms** contra o orçamento de 100 ms do RNF01.

> **Dois defeitos do Bloco 2 só apareceram rodando**, e ambos foram corrigidos
> com teste de regressão (`context/09`):
>
> 1. **`ESTENDER_VERDE` contava do início do verde**, não do instante do comando.
>    O motor pede `eta + margem` para segurar o corredor, e o verde fechava na
>    cara do VE. Efeito da correção, mesma seed: **6 paradas e 409 s → 0 parada e
>    313 s**. Nenhum teste unitário pegava — todos exercitavam extensões a partir
>    de verdes recém-abertos.
> 2. **E7 era um no-op.** O motor calculava o `PlanoCompensacao`, guardava, e nada
>    o aplicava: os braços `PREEMPCAO` e `PREEMPCAO_COMPENSADA` saíam idênticos
>    até o último dígito, e H2 não tinha mecanismo por trás.
>
> **Um achado, já decidido:** o cenário `intenso` mede v/c = 0,73, **abaixo** do
> limiar de 0,75 que o `context/04` §5 usa para essa faixa. Decisão da equipe em
> 2026-08-25: **fluxos e nomes ficam como estão; a caracterização passa a ser a
> medida**, e o cenário é descrito no texto como *saturação moderada-alta*. Os
> limiares não foram tocados — mudar a régua depois de ver o resultado seria o
> oposto de método. H1 continua de pé: os dois cenários em que a meta se aplica
> medem 0,42 e 0,73, dois pontos distintos da faixa que P1 exige.
>
> Também registradas: a rota do VE em "U" pelos oito cruzamentos (o `04` §3 se
> contradizia), a calibração de `tau` em `veiculos.typ.xml` — único parâmetro
> ajustado, por critério declarado antes do ajuste — e a opção por tráfego de
> fundo passante, sem conversões.

**Verificações de fechamento (2026-08-26).** Além da suíte:

| Item | Resultado |
|---|---|
| `executor --cenario leve --modo FIXO --seed 1` (3.600 s) | `tripinfo.xml` + linha em `execucao_simulacao`, fechada |
| Corredor verde na `sumo-gui` (modo `PREEMPCAO`) | roda de ponta a ponta e encerra sem janela órfã |
| Validação da malha nos três cenários de fundo | `leve` 0,186 × 0,182 · `moderado` 0,436 × 0,424 · `intenso` 0,702 × 0,726 — **todos aprovados** |
| `multiplas_emergencias` exercita E8 | **525 passos** com dois VEs disputando CRUZ_02 |
| `docker compose up` | `db` + `migracoes` + `backend` saudáveis, `/health` verde |

> **Duas pendências abertas pelo Bloco 3, nenhuma bloqueante:**
>
> - **P15 — `libsumo` para Python não vem no instalador Windows.** A interface do
>   adaptador abstrai os dois clientes conforme 3.6, mas o caminho `libsumo` não
>   pôde ser exercitado. Decidir antes do Bloco 8; o lote roda com `traci` em
>   paralelo enquanto isso.
> - **`queue.xml` saiu do padrão de saída**: 77 MB por execução (~46 GB nas 600),
>   redundante com os detectores E2. Agora está atrás de `--saida-detalhada`, e a
>   saída bruta por execução caiu para ~1,5 MB.

---

### Bloco 4 — Piloto experimental · ~3 dias · **mitigação do risco nº 1**

5 seeds × 4 cenários × 3 modos = 60 execuções. Objetivo: **conhecer a ordem de grandeza do ganho antes de comprometer o texto**.

Saída: um relatório curto respondendo — a redução em `moderado`/`intenso` chega perto de 25%? Há gridlock? A latência p95 fica sob 100 ms? Se a resposta a qualquer uma for ruim, ajusta-se **o modelo ou o texto** aqui, não na última semana.

**Estado: concluído em 2026-08-26.** 60 execuções de 3.600 s, **zero descartadas**,
em ~35 min de máquina (8 núcleos, `--paralelo 6`). Relatório em
[`relatorios/piloto_20260826.md`](relatorios/piloto_20260826.md), gerado por
`python -m analysis.relatorio_piloto` — nenhum número dele é digitado à mão.

Duas entregas de código, ambas antecipadas do Bloco 8:

| # | Entrega |
|---|---|
| 4.1 | `sim/controlador/lote.py` — a matriz completa em processos paralelos, com `validar_execucao()` em toda execução e descarte documentado em `analysis/data/descartes.csv`. `--seeds 1..5` é o piloto; `--seeds 1..50` é o Bloco 8, e não muda mais nada |
| 4.2 | `analysis/relatorio_piloto.py` — lê `analysis/data/` e escreve o relatório. A seção "o que este piloto obriga a decidir" é **calculada**, e some sozinha quando não há o que decidir |

**As três respostas:**

| Pergunta | Resposta |
|---|---|
| Redução em `moderado`/`intenso` chega a 25%? | **`moderado` sim (31,7%), `intenso` não (18,1%)** |
| Há gridlock? | Não — zero teleporte, zero colisão, zero violação de invariante nas 60 |
| p95 da decisão sob 100 ms? | Sim, com folga de três ordens de grandeza: pior p95 **0,163 ms** |

**Redução da travessia do VE, pareada por veículo:**

| Cenário | Regime medido | `PREEMPCAO` | Dispersão entre seeds | Paradas `FIXO` → `PREEMPCAO` |
|---|---|---:|---|---:|
| `leve` | v/c 0,18 | 39,0% | 36,1% – 44,1% | 5,56 → 0,36 |
| `moderado` | v/c 0,42 | **31,7%** | 28,9% – 33,8% | 5,68 → 0,76 |
| `intenso` | v/c 0,73 | **18,1%** | 13,0% – 25,1% | 6,28 → 2,76 |
| `multiplas_emergencias` | v/c 0,42, 2 VEs | 24,6% | 20,1% – 30,2% | 3,22 → 0,55 |

> **O piloto cumpriu exatamente o papel para o qual foi antecipado: expôs dois
> problemas com meses de margem.** Ambos viraram pendência de decisão da equipe
> em `context/09`, e **os dois bloqueiam o Bloco 8** — rodar as 600 execuções
> antes de decidir significa rodá-las de novo depois.
>
> - **P16 — H1 não atinge a meta em `intenso`** (18,1% contra 25%). A dispersão
>   entre seeds (13,0% a 25,1%) e as paradas residuais (2,76 contra 0,76 no
>   `moderado`) apontam a causa: o corredor não se fecha por inteiro quando a fila
>   à frente não dissipa a tempo. `tempo_antecipacao_margem_s` é fixo em 5 s e não
>   consulta a fila, que o motor já recebe. Recomendação: **tentar corrigir o
>   mecanismo antes de mexer na hipótese** — reformular H1 sem tentar é ajustar a
>   régua ao resultado.
> - **P17 — E7 não entrega a mitigação de H2.** O custo transversal que H2 existe
>   para mitigar está medido e é real (+18,6% no `moderado`, +24,6% no `intenso`);
>   a mitigação medida fica entre −1,0% e +0,6%, contra a meta de 15%. `K` (0,7) e
>   `n_ciclos_compensacao` (2) nunca foram calibrados contra dado real. Antes de
>   calibrar, verificar se a **métrica** não está diluindo o efeito: a média sobre
>   a hora inteira mede uma compensação que dura ~140 s por evento.

**Encaminhamento das duas, em 2026-08-31.** Registrado em `context/09`; nenhuma
das duas está fechada.

| Pendência | O que ficou decidido | O que continua aberto |
|---|---|---|
| **P16** ✅ | **Resolvida em 2026-08-31**, corrigindo o mecanismo e sem tocar em H1. E3 passou a somar o tempo de dissipação da fila do acesso de entrada. Medido nas mesmas seeds do piloto: `intenso` **18,1% → 31,2%**, paradas do VE 2,76 → 0,08 | Nada. A contingência de reformular H1 não foi acionada |
| **P17** | O enunciado de H2 passa de "em até 15%" para **"em no mínimo 15%"** — a redação antiga era um teto, e sob ela a mitigação medida **cumpriria** a hipótese | **Qual é o denominador** (espera transversal × acréscimo), se a métrica dilui o efeito, e a calibração de `K` e `n_ciclos_compensacao` |

> **A guarda das seeds vale explicação.** As 5 seeds do piloto são um subconjunto
> das 50 do Bloco 8. Afinar o mecanismo olhando para elas e depois reportar o
> resultado final sobre 1..50 contaminaria 5 das 50 execuções que validam o
> trabalho — o modelo teria sido calibrado sobre parte da amostra que o valida.
> Calibrar em 101..105 custa nada e mantém o Bloco 8 inteiramente fora-da-amostra.

**Correção de P16, medida em 2026-08-31.** O critério do ajuste foi declarado e
**commitado antes do código** (`1ae762e`); o código veio depois (`d63f774`). A
ordem é verificável no `git log`, e é ela que separa "corrigimos o mecanismo e
medimos" de "mexemos até o número subir".

| Cenário | Piloto | Após a correção | Meta ≥ 25% |
|---|---:|---:|:---:|
| `intenso` | 18,1% (13,0 – 25,1) | **31,2%** (27,9 – 33,6) | **atinge** |
| `moderado` | 31,7% | 34,3% | atinge |
| `leve` | 39,0% | 40,4% | — |
| `multiplas_emergencias` | 24,6% | 28,1% | — |

Paradas do VE no `intenso`: **2,76 → 0,08**. Zero colisão, zero teleporte, zero
violação de I1 a I5 nas 120 execuções das duas corridas.

> **O custo está medido e é o trade-off central do trabalho.** A espera
> transversal no `intenso` subiu de **+24,6% para +43,6%** — o corredor abre mais
> cedo porque precisa esvaziar a fila, e quem paga é a transversal. Era um dos
> três resultados declarados **antes** de medir, e vai para a discussão do
> capítulo 5 junto com o ganho, não como nota de rodapé. **P17 ficou mais
> urgente:** o custo que E7 deveria mitigar quase dobrou, e a mitigação continua
> indistinguível de zero.

**Um defeito do próprio lote, achado e corrigido no piloto.** O `execucoes.csv`
consolidado saiu com **64 linhas para 60 execuções**: quatro pontos exercitados
antes num teste curto tinham deixado CSV na pasta da execução, e `gravar_csv()`
acrescenta em vez de substituir. Os quatro foram reexecutados com `--repetir`, o
descarte está em `descartes.csv`, e há teste de regressão. A lição virou guarda
permanente: o lote agora **recusa** consolidar um ponto que já tem linhas no CSV,
a menos que `--repetir MOTIVO` autorize.

---

### Bloco 5 — Camada IoT (Sprint 4) · ~2 semanas

| # | Entrega |
|---|---|
> **Replanejado em 2026-10-05.** A equipe adotou a arquitetura já montada na
> bancada (`context/05`, `context/09`): ESP-NOW do veículo ao cruzamento, decisão
> no UNO, notebook só escutando. 5.1, 5.2 e 5.7 foram entregues em 2026-10-04
> contra o protocolo de comandos anterior e precisam ser **refeitas**, não
> descartadas: ficam a estrutura, o transporte, a API e o relógio.

| # | Entrega |
|---|---|
| 5.1 | `bridge/protocolo.py` — ✅ **refeito em 2026-10-05**: `ST` e `EV` de `context/05` §4.2, a linha `<RUA>,<VEICULO>` do receptor e da injeção, a linha `Tag … lida` do emissor. Saiu a tradução `Comando` → linha |
| 5.2 | `adapters/hardware/simulado.py` — ✅ **refeito em 2026-10-05** com a regra de `context/05` §3: 2 fases, verde exclusivo, fila por tipo, transição segura, teto de 30 s. 44 testes, Hypothesis para I1–I5, verificação por mutação (4 sabotagens, todas pegas) |
| 5.3 | Firmware UNO reescrito em `firmware/uno/`, conforme `context/05` §3 e §4: decisão local preservada, transição segura, **zero `delay()`** no `loop()`, **zero `String`**, `ST` a 2 Hz e a cada mudança de estado, eventos antes do LCD — ✅ **escrito e compilado em 2026-10-05** (27% da flash, 41% da RAM). O núcleo roda no PC contra o dublê, linha por linha, em cenários fixos e 200 sequências aleatórias; 9 sabotagens, todas pegas (`context/05` §3.7). **Falta** a aceitação na placa: `bridge.verificar` com 16 de 16 |
| 5.4 | ~~**P8**~~ ✅ **2026-10-05** — boot normal com o RC522 no D3 (questionário, 3.3) |
| 5.5 | ~~**P9**~~ ✅ **2026-10-05** — não se aplica: o LCD está no UNO, de 5 V |
| 5.6 | Sketches dos NodeMCUs (emissor e receptor) versionados **como estão** em `firmware/nodemcu/`, com cabeçalho documentando o MAC do receptor, o tipo do veículo e o mapa UID → rua — ✅ **2026-10-05**, com teste que confere o corpo idêntico ao original e o cabeçalho de acordo com o código |
| 5.7 | `bridge/` — ✅ **em parte, 2026-10-05**: só escuta a 9600, `/estado` com histórico, `/health`, `POST /injecao` e `/injecao/bruta`, `bridge.verificar` reescrito (**16 de 16 contra o dublê**), `.env.example` sem Wi-Fi, `parametros.hardware.yaml` com 2 fases. ✅ **H3 também, 2026-10-05**: carimbo no primeiro byte, `--porta-veiculo` e o casamento detecção → decisão que grava `analysis/data/latencia_bancada.csv` (`context/05` §6). O CSV só nasce de medição na bancada |
| 5.8 | ✅ UIDs lidos (identificam ruas, `context/05` §1). ✅ **2026-10-05:** seeds com as 2 fases de `PROTO_CRUZ_01` e os dispositivos `EMISSOR_VE_01`, `RECEPTOR_CRUZ_01` e `CTRL_PROTO_01`; migration de dados para bancos já semeados (`context/03` §5) |
| 5.9 | ~~**P20** na bancada~~ — **não se aplica desde 2026-10-05**: o UNO decide sem consultar ocorrência. P20 segue no motor, na API e na simulação |

> **Pendente de bancada (2026-10-05).** A bancada não está com o Felipe. Tudo o
> que dá para fazer sem a placa está feito; ficam para quando ela chegar a
> aceitação do firmware na placa (`bridge.verificar`, 16 de 16), a medição de H3,
> o checklist de `context/06` §6 e o ensaio da demonstração. O projeto segue
> para o Bloco 6 enquanto isso.

**Pronto quando:**
- o carrinho passa pela tag → o UNO inicia a preempção em < 3 s (RF02) e chega ao verde exclusivo pelo amarelo e pelo all-red;
- `bridge.verificar` passa contra o dublê e contra a placa;
- H3 medida em 5 repetições com o emissor no USB do notebook;
- com a ponte encerrada, o cruzamento continua funcionando.

---

### Bloco 6 — API + WebSocket (Sprint 2 formal) · ~1 semana

Todas as rotas do `context/01` §7, schemas Pydantic v2, WebSocket com throttle de 5 Hz, `X-Device-Token` validado contra `dispositivo_iot.token_hash`, dedup anti-replay de 2 s, `id_correlacao` propagado da detecção à métrica, logs estruturados com structlog.

**Regra do `context/08` §4.5:** endpoint, schema e teste no mesmo commit.

**P20 (2026-09-29) acrescenta:** `POST /ocorrencias`, `POST /ocorrencias/{id}/encerramento` e `GET /ocorrencias?ativas=true`; e o serviço de `/deteccoes` passa a chamar `core/autorizacao.autorizar()` com o que buscou no banco, responder `acao = "SEM_OCORRENCIA"` (HTTP 200) à tag reconhecida sem ocorrência e gravar `deteccao.autorizado` e `fk_ocorrencia`. A tabela, o ORM e o repositório (`abrir_ocorrencia`, `encerrar_ocorrencia`, `ocorrencia_ativa_do_veiculo`) já existem desde a P20.

**Estado em 2026-10-05: implementado, esperando o teste da equipe.** Sete
decisões tomadas antes do código, registradas em `context/09`: o backend lê
`GET /estado` da ponte a 5 Hz; `/deteccoes` fica como contrato do V2I com rede,
e a bancada entra pela leitura da ponte; a aproximação vai em `motivo`;
`metrica_latencia.t_decisao` passa a aceitar nulo (migration `c4d81f2b9a60`);
`POST /simulacoes` grava em `pedido_simulacao` e o atendente do host executa; o
executor transmite ao vivo com `--transmitir`; a API recusa as seeds do
experimento.

| Entrega | Onde |
| --- | --- |
| Todas as rotas de `context/01` §7, mais `GET /simulacoes` e `POST /simulacoes/transmissao` | `backend/app/api/v1/` |
| Schemas Pydantic v2 | `backend/app/schemas/` |
| WebSocket `/api/v1/stream`, throttle de 5 Hz pela borda de subida | `app/services/difusao.py`, `api/v1/ws.py` |
| `X-Device-Token`, anti-replay de 2 s, P20 com `SEM_OCORRENCIA` em 200 | `app/services/deteccoes.py` |
| `id_correlacao` da detecção à métrica (API: detecção → log; bancada: decisão → log → H3) | `app/services/deteccoes.py`, `app/services/bancada.py` |
| structlog com os seis campos de `context/02` §7 | `app/logs.py` |
| Bancada → backend: tradução dos eventos do UNO, gravação, WebSocket | `app/services/bancada.py` |
| Simulação ao vivo e atendente de pedidos | `sim/controlador/transmissor.py`, `sim/controlador/atendente.py`, `sim/rede/georreferencia.py` |

Testes: a suíte padrão passou de 544 para **575**, e a de banco de 31 para
**89**. Conferido também de ponta a ponta com `docker compose up`: a ponte com o
dublê no host, o backend no contêiner lendo-a, a preempção manual pela API e um
pedido de simulação executado pelo atendente com o SUMO e transmissão ao vivo.

---

### Bloco 7 — Dashboard (Sprint 6) · ~2 semanas

React + Vite + TS + Tailwind. Mapa Leaflet, painel de semáforos em tempo real, tela de logs com filtro, painel de métricas com Recharts, login simples. Vitest nos componentes de estado. **Painel "Central" (P20):** abrir ocorrência escolhendo veículo e criticidade, encerrar, e ver quem está em serviço — é a central de despacho simulada.

**Estado em 2026-10-05: implementado, esperando o teste da equipe.** Quatro
decisões tomadas antes do código, registradas em `context/09`: login com PyJWT e
a credencial do operador no ambiente; o token protege só as escritas do
operador; HTTPS pelo nginx com certificado autoassinado; o frontend no compose
padrão, como build estático servido pelo nginx em `https://localhost:8443`.

| Entrega | Onde |
| --- | --- |
| Login do operador (`POST /auth/login`, `GET /auth/sessao`) e as escritas protegidas | `backend/app/services/autenticacao.py`, `app/api/v1/autenticacao.py`, `app/api/dependencias.py` |
| Projeto React + Vite + TS + Tailwind, sem roteador (aba no `#`) | `frontend/` |
| Estado ao vivo do WebSocket, com reconexão | `frontend/src/stream/` |
| Aba "Ao vivo": mapa Leaflet com semáforos e VEs, painel da bancada (S1..S4, regime, rua, fila), lista de semáforos, eventos, preempção manual com o motivo do 409 | `frontend/src/componentes/` |
| Aba "Central" (P20): abrir e encerrar ocorrência, frota e quem está em serviço | `PainelCentral.tsx` |
| Aba "Logs": filtros, paginação e filtro por `id_correlacao` | `TelaLogs.tsx` |
| Aba "Métricas": resumo, priorizações por desfecho, RNF01 e H3 separados, latência ao vivo | `PainelMetricas.tsx` |
| Aba "Simulações": pedir execução e acompanhar os pedidos | `TelaSimulacoes.tsx` |
| nginx com HTTPS e proxy de `/api` e do WebSocket | `frontend/Dockerfile`, `frontend/nginx/` |
| **Revisão após o primeiro teste da equipe:** mapa desenhado da malha SUMO (sem mapa de rua), com ponto de sinal por aproximação | `sim/rede/exportar_mapa.py`, `frontend/src/malha/malha.json`, `MapaMalha.tsx` |
| Tráfego de fundo no mapa | `sim/controlador/transmissor.py`, `executor.py`, mensagem `trafego` |
| Velocidade da simulação escolhida no pedido (1x, 2x, 5x, 10x ou máxima) | migration `e5a17c3d8b42`, `sim/controlador/ritmo.py`, `atendente.py` |
| Reenvio do WebSocket limitado a 5 s; aviso de atendente parado; resumo de cada execução na aba Simulações | `app/services/difusao.py`, `TelaSimulacoes.tsx` |

Testes: 70 no Vitest; no backend, a suíte padrão passou de 575 para **645**, e a
de banco de 89 para **103**; as 23 do SUMO passam. Conferido também de ponta a
ponta com `docker compose up`, a ponte com o dublê e o atendente no host: login,
401 sem token, 409 com o motivo, `wss` pelo nginx, cada aba vista num Chrome
sem janela durante uma simulação a 10x, e o fluxo do operador com digitação e
cliques (login, abrir e encerrar ocorrência, filtro de logs, sair). O ritmo e o tráfego não mudam o
resultado (mesma execução com e sem, `context/06` §2).

---

### Bloco 8 — Lote completo (Sprint 7) · ~1 semana + tempo de máquina

~~`sim/controlador/lote.py`~~ **já existe** (entrega 4.1). O Bloco 8 é rodá-lo com `--seeds 1..50`: 4 cenários × 3 modos × 50 seeds = **600 execuções** de 3600 s. Medido no piloto, com `traci` e 6 processos, isso dá **~6 h** — uma noite de máquina. `libsumo` deixou de ser necessário para caber na janela (ver P15).

> **A matriz cresce com o Bloco 10.** O braço `PREEMPCAO_ML` (entrega 10.7) entra
> nos cenários com múltiplos VEs, então as 600 execuções passam a ser o piso e não
> o total. O acréscimo exato depende de quantos cenários de múltiplas emergências
> existirem depois de 10.2. **Por isso o Bloco 10 executa antes do Bloco 8**: um
> braço acrescentado depois obriga a rodar tudo de novo.

> **Bloqueado pelo Bloco 10.** ~~P16~~ foi resolvida em 2026-08-31 corrigindo o mecanismo, ~~P18~~ em 2026-09-10 sem teto numérico, e ~~P17~~ em 2026-10-01, com `K` e `n_ciclos_compensacao` calibrados e congelados. **P19 / Bloco 10** acrescenta um braço à matriz, com a mesma consequência. As 600 rodam com o código de `d63f774` em diante — o piloto de 2026-08-26 foi produzido pelo código anterior e **não** se mistura com elas.

**Pareamento por seed é inegociável:** gerar as rotas uma vez por (cenário, seed) e reutilizar em **todos** os modos, inclusive no braço de ML. Sem isso a comparação deixa de ser pareada e perde poder estatístico.

`validar_execucao()` do `context/06` §4 roda em toda execução; falha → descarte **documentado** e reexecução com a mesma seed.

---

### Bloco 9 — Análise e artefatos acadêmicos (Sprint 8) · ~2 semanas

`analysis/` completo: Wilcoxon como principal e t pareado como secundário, Cliff's δ obrigatório, IC 95% por bootstrap, Holm-Bonferroni para múltiplas comparações. Tabelas T1–T6 e figuras F1–F6 em PDF vetorial, legíveis em escala de cinza.

`python -m analysis.gerar_resultados_tcc` reproduz o capítulo 5 inteiro com um comando.

Em paralelo: diagramas PlantUML do `context/08` §5, DER via eralchemy2, relatório de validação, checklist assinado do protótipo.

---

### Bloco 10 — Priorização aprendida entre múltiplos VEs (P19) · ~2 a 3 semanas

> **O número é 10, mas a posição na fila é antes do Bloco 8.** O braço novo tem de
> existir quando as 600 execuções rodarem, senão elas precisam ser rodadas duas
> vezes. Não renumerei os Blocos 8 e 9 porque o `context/` os referencia por
> número em dezenas de lugares, e renumerar trocaria uma confusão pequena por
> muitas oportunidades de erro. **Ordem de execução: 5 → 6 → 7 → 10 → 8 → 9.**

Pedido do orientador (P19, 2026-09-10): um modelo de aprendizado de máquina para
decidir **qual VE é priorizado** quando há mais de uma emergência simultânea.
Substitui o desempate determinístico de **E8** — hoje lexicográfico por tipo,
depois ETA, depois preempção em curso.

**Por que é defensável e não decorativo:** E8 é míope. Decide um cruzamento por
vez, sem pesar a consequência sequencial — priorizar o VE A agora pode custar
mais ao VE B adiante, ou formar fila que prejudica os dois. A ordem por tipo é
convenção declarada, não otimização. Há lacuna genuína a preencher.

| # | Entrega |
|---|---|
| 10.1 | **Contagem de conflitos.** ⚠️ **Remedir:** a rota do segundo VE foi estendida em 2026-10-05 (Bloco 7), e numa execução de demonstração as disputas foram de 6 para 10 por execução. A medição abaixo vale para a rota antiga. ✅ **MEDIDA em 2026-09-10: 60 disputas em 10 execuções, 56 decidíveis, 6 por execução.** Abaixo do piso de 100 de P19, o que **torna a 10.2 obrigatória**. A instrumentação também expôs um defeito de E1/E2 anterior ao bloco — o VE recuava ~490 m ao atravessar um cruzamento —, corrigido e coberto por regressão. Evidência e números em `context/09` P19 |
| 10.2 | **Cenário de treino mais denso em VEs — agora obrigatório**, pelo volume medido em 10.1. Novos arquivos de demanda, mesma malha. ~~Precisa defasar a rotação de tipos entre as duas rotas~~ — deixou de valer com a P20 (`tipo` não é mais atributo). Precisa de **volume de disputas de mesmo nível de criticidade**, o domínio do modelo, e de alguns pares de nível misto, só para exercitar a regra. É aqui que criticidade e tipo se desacoplam (`criticidades` em rodízio próprio) |
| 10.3 | ~~Declaração do objetivo de otimização~~ · **já feita** em 2026-09-10: critério **minimax**, minimizar o tempo do VE mais prejudicado. Registrada em P19 e em `context/00` §5 **antes** de existir treino |
| 10.4 | **Rotulagem por bifurcação da simulação** — `saveState`/`loadState` no instante do conflito, rodando as duas escolhas até os VEs liberarem a rota, e rotulando pelo minimax. Com **divisão treino/teste por seed** e o treino **fora** do intervalo 1..50 (guarda de P16). **Só as disputas de mesmo nível** (`mesmo_nivel = 1`) são bifurcadas — as mistas a regra de criticidade decide, e não há rótulo a aprender (P20) |
| 10.5 | Treino offline (regressão logística par a par sobre diferenças, **quatro atributos** desde a P20) e **exportação dos pesos como arquivo versionado** |
| 10.6 | Inferência **pura** em `core/priorizacao/`, sem import de framework: `test_arquitetura.py` continua verde e o RNF01 continua medido. Duas regras ficam **acima** do modelo, nesta ordem: **criticidade** (o nível mais crítico vence, inclusive sobre preempção em curso — P20) e **guarda de oscilação** (no mesmo nível, a preempção em curso vence) |
| 10.7 | Braço `PREEMPCAO_ML` no executor e no lote, comparável contra o E8 determinístico |
| 10.8 | ~~Linha nova em T6~~ (a linha de H4 já está em `context/07` T6 desde a P20) e análise estatística própria de **H4** — mesmo rigor de H1: Wilcoxon pareado, Cliff's δ, IC 95% — **estratificada por `mesmo_nivel`**, com o n de escolhas que o modelo de fato decidiu (`context/07` §3.3.1) |

**Desenho, decidido em 2026-09-10 e anterior a qualquer treino** (justificativas em P19):

```
score = w · (x_A − x_B)      escolhe A se score > 0, senão B

x = (eta_s, velocidade_ms, fila_no_acesso, cruzamentos_restantes)
```

Comparação par a par **sobre diferenças**, com torneio para três ou mais VEs — a
antissimetria fica garantida por construção, e não depende de o modelo aprendê-la.
Critério **minimax**. Rótulos por bifurcação da simulação. `distancia_m` ficou de
fora por redundância com `eta_s`; `preempcao_em_curso` ficou de fora porque não
informa a decisão, **suspende** a decisão — é regra rígida acima do modelo.

> **P20, 2026-09-29: `tipo` saiu do vetor.** Sob o rótulo minimax em tempo, o
> peso de `tipo` não carregaria relevância — o tempo não sabe que a ambulância
> leva uma vida. A relevância virou **criticidade da ocorrência** (1
> `RISCO_VIDA`, 2 `RISCO_COLETIVO`, 3 `URGENCIA`), aplicada como regra **acima**
> do modelo. O modelo decide só entre VEs de mesmo nível.

**Pronto quando:** o braço `PREEMPCAO_ML` roda a matriz inteira; a política vem de
arquivo versionado e não de código; `mypy --strict` e o teste de arquitetura
seguem limpos; e existe uma comparação estatística entre a política aprendida e o
desempate determinístico.

> **Restrição arquitetural, decidida desde já.** O modelo é **treinado fora e
> exportado como dado**. É o que preserva a decisão do `context/01` §1 — o mesmo
> motor roda na simulação e no protótipo —, mantém a latência de decisão dentro do
> RNF01, e deixa a política auditável na defesa. Um `import sklearn` dentro de
> `core/` reprovaria `test_arquitetura.py`, e com razão.

> **Risco a declarar desde já: o modelo pode não bater o heurístico.** Com dois
> VEs e desempate por tipo e ETA, a margem é estreita. O bloco precisa estar
> estruturado para que **resultado nulo continue sendo resultado** — relatar que a
> política aprendida não superou a heurística, com tamanho de efeito e intervalo
> de confiança, é contribuição legítima. O que não pode acontecer é o modelo
> entrar sem avaliação, só para satisfazer a expectativa.

---

## Marcos de verificação

| Marco | O que prova |
|---|---|
| Fim do Bloco 2 | O núcleo do TCC existe e é seguro — invariantes verificados por property-based testing |
| Fim do Bloco 4 | ✅ **2026-08-26.** H1 se sustenta em `moderado` (31,7%) e **não** em `intenso` (18,1%); H2 tem custo medido mas **sem** mitigação (P16 e P17). Zero gridlock, RNF01 com folga de três ordens de grandeza. O marco cumpriu seu papel: os problemas apareceram com margem — e **P16 foi corrigida em 2026-08-31** (`intenso` 31,2%), com quase três meses de folga, que é exatamente o que antecipar o piloto comprou |
| Fim do Bloco 5 | O protótipo físico funciona fim-a-fim, com transição segura, fim da emergência por duração e teto, e H3 medida |
| **Entrega 10.1** | Sabe-se **quantos eventos de conflito entre VEs existem por execução** — é o que define se há dado suficiente para treinar, e nenhuma decisão de modelagem é tomada antes disso |
| Fim do Bloco 10 | Existe uma política aprendida, exportada como dado e comparada estatisticamente contra o desempate determinístico. Veredito favorável **ou** nulo, ambos reportáveis |
| Fim do Bloco 8 | Os dados do capítulo 5 existem e são reprodutíveis |

## Pendências que continuam abertas

> **Atualizado em 2026-10-01.** P11, P15, P16, P18 e P20 estão **fechadas**.
> **P3 foi revogada:** a banca espera aprendizado de máquina, o que abriu **P19**
> e o Bloco 10. **P17 foi calibrada e congelada.** Bloqueia o Bloco 8 só o
> Bloco 10.

- ~~**P16** — H1 abaixo da meta em `intenso`.~~ ✅ **Resolvida em 2026-08-31**
  corrigindo o mecanismo, sem tocar em H1: 18,1% → **31,2%**, paradas do VE
  2,76 → 0,08. Ver o quadro no Bloco 4.
- **P19** (aberta em 2026-09-10) — **acrescenta o Bloco 10 e bloqueia o Bloco 8.**
  O orientador confirmou que a banca espera aprendizado de máquina e indicou
  onde: um modelo para decidir **qual VE é priorizado** quando há mais de uma
  emergência simultânea — hoje o desempate determinístico de E8. Revoga a decisão
  P3. **Nada sai do escopo em troca** (decisão da equipe, 2026-09-10). O desenho
  do modelo ainda não está definido, e a primeira entrega do bloco é medir
  quantos conflitos existem por execução, porque é isso que define o que é
  treinável. Ver Bloco 10 acima e P19 em `context/09`.
- ~~**P18**~~ ✅ **Resolvida em 2026-09-10.** Sem teto numérico: o custo
  transversal é tratado qualitativamente, e o objetivo geral foi reescrito de
  "sem degradar de forma inaceitável" para "quantificar o custo que essa
  priorização impõe". Nada muda no código.
- **P17** — ✅ **decidida em 2026-10-01**; a execução **bloqueia o Bloco 8**. E7 e
  H2 ficam. H2 = mitigação de ≥ 15% do **acréscimo**, em `moderado` e `intenso`,
  sobre a espera média transversal da hora. **Calibrada e congelada em
  2026-10-01:** `K = 1,0`, `n = 3`, pontuação +6,2% (abaixo da meta; nenhuma
  combinação se distinguiu de zero). Veredito no Bloco 8; abaixo de 15%, H2 é
  reportada como rejeitada. **Não bloqueia mais o Bloco 8.**
- ~~**P3**~~ — **revogada em 2026-09-10**: o orientador confirmou que a banca
  espera aprendizado de máquina. Virou P19, acima.
- ~~**P20**~~ ✅ **Decidida em 2026-09-29.** Emergência é estado declarado: a
  preempção exige tag reconhecida **e** ocorrência ativa, aberta pela central de
  despacho (simulada). A relevância entre tipos virou **criticidade da
  ocorrência**, regra acima do modelo de P19, que perde o atributo `tipo`. Núcleo,
  simulação e banco entregues na P20 (PR #8); API, LCD e painel ficam com os
  Blocos 6, 5 e 7 (entregas 5.9 e as notas dos Blocos 6 e 7). Nenhum número
  medido muda. **Fechada em 2026-10-01.**
- **P6** — **formato fechado em 2026-08-31**: as tabelas do capítulo 5 do
  pré-projeto migram para uma seção "Resultados esperados" na metodologia,
  rotulada como estimativa preliminar, e o capítulo 5 passa a vir só de
  `analysis/gerar_resultados_tcc.py`. A migração não depende do Bloco 8 e pode ser
  feita já; o conteúdo final depende.
- **H3** — **n definido em 2026-08-31: 5 repetições de bancada.** A evidência só
  existe no protótipo (na simulação `t_atuacao` é o mesmo passo de `t_decisao`).
  Com n = 5 o p95 não é estimável: reportar mín/mediana/máx com o n declarado e
  verificar os 200 ms sobre o máximo. Fica registrada em `context/06` §6 a opção
  de instrumentar as **100 leituras que o RNF05 já exige**, o que daria a H3 um
  p95 real sem repetição extra.
- ~~**P15**~~ ✅ **Fechada em 2026-10-01.** O lote roda com `traci` e processos
  em paralelo — o piloto mediu ~6 h para as 600 execuções — e `libsumo` **não**
  é instalado pelo pip. `--libsumo` continua implementado, sem ser o padrão.
- ~~**P11**~~ ✅ **Fechada em 2026-10-01.** O método (medir o fluxo de saturação
  na própria malha) foi aprovado pelo orientador. O que resta é redação do
  capítulo de metodologia, listado em `context/09` P11.
- **P4, P12** — ações de redação no texto do TCC. O código já implementa a versão correta; falta a equipe atualizar o documento.
- ~~**P14** — ponto final de medição do RF02.~~ ✅ **Decidida em 2026-08-25:** mede da detecção até o **início da atuação**. O perfil de tempos da bancada e o ciclo de 24 s de P13 ficam inalterados, e o firmware do Bloco 5 já tem contra o que ser escrito.
- ~~**P8, P9**~~ — ✅ fechadas em 2026-10-05 pelo questionário de hardware (P8: boot normal; P9: não se aplica, LCD no UNO).
