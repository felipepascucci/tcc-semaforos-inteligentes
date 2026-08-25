# Plano de Desenvolvimento

> Documento irmão: [`contrato-hardware-software.md`](contrato-hardware-software.md) — a especificação da integração com o protótipo físico (pinagem, protocolo serial, requisitos de firmware, invariantes). Leia-o antes de qualquer trabalho em `firmware/`, `bridge/` ou `adapters/hardware/`.

Data-base: **2026-08-24**. Janela de entrega assumida: **3 a 6 meses** → apresentação estimada entre **nov/2026 e jan/2027**, com **congelamento de código 5 dias antes** (regra do `context/02` §9).

Escopo: completo, conforme `context/`. Sem cortes preventivos — a lista de corte do `context/08` §2 fica de reserva, acionada só se um marco atrasar.

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

---

### Bloco 4 — Piloto experimental · ~3 dias · **mitigação do risco nº 1**

5 seeds × 4 cenários × 3 modos = 60 execuções. Objetivo: **conhecer a ordem de grandeza do ganho antes de comprometer o texto**.

Saída: um relatório curto respondendo — a redução em `moderado`/`intenso` chega perto de 25%? Há gridlock? A latência p95 fica sob 100 ms? Se a resposta a qualquer uma for ruim, ajusta-se **o modelo ou o texto** aqui, não na última semana.

---

### Bloco 5 — Camada IoT (Sprint 4) · ~2 semanas

| # | Entrega |
|---|---|
| 5.1 | `bridge/protocolo.py` — 100% testável sem hardware, ambos os sentidos |
| 5.2 | `adapters/hardware/simulado.py` — dublê com latência artificial, permite o trio trabalhar sem a bancada |
| 5.3 | Firmware UNO reescrito: máquina de estados `millis()`, **zero `delay()`**, **zero `String`**, watchdog 3 s (I6), timeout de preempção 30 s, telemetria 2 Hz |
| 5.4 | **P8** — testar boot do NodeMCU com RC522 ligado; se falhar, RST → D0 (GPIO 16) e atualizar `context/05` §1 |
| 5.5 | **P9** — decidir LCD em 3,3 V ou conversor de nível; documentar a escolha |
| 5.6 | Firmware NodeMCU: dedup por UID com cooldown 3 s, `sequencia` monotônica, HTTP com timeout, reconexão Wi-Fi com backoff, `secrets.h` gerado por `firmware/gerar_secrets.py` |
| 5.7 | `bridge/main.py` — asyncio, PING 1 s, reconexão serial, `t_atuacao` carimbado **na chegada do ACK** |
| 5.8 | Ler os UIDs reais das tags e atualizar os seeds |

**Pronto quando:** tag aproxima → semáforo físico preempta em < 3 s (RF02); cabo USB desconectado durante preempção → ciclo fixo retomado em < 3 s (I6).

---

### Bloco 6 — API + WebSocket (Sprint 2 formal) · ~1 semana

Todas as rotas do `context/01` §7, schemas Pydantic v2, WebSocket com throttle de 5 Hz, `X-Device-Token` validado contra `dispositivo_iot.token_hash`, dedup anti-replay de 2 s, `id_correlacao` propagado da detecção à métrica, logs estruturados com structlog.

**Regra do `context/08` §4.5:** endpoint, schema e teste no mesmo commit.

---

### Bloco 7 — Dashboard (Sprint 6) · ~2 semanas

React + Vite + TS + Tailwind. Mapa Leaflet, painel de semáforos em tempo real, tela de logs com filtro, painel de métricas com Recharts, login simples. Vitest nos componentes de estado.

Primeiro candidato ao corte se algo atrasar (`context/08` §2, item 2 e 5).

---

### Bloco 8 — Lote completo (Sprint 7) · ~1 semana + tempo de máquina

`sim/controlador/lote.py`: 4 cenários × 3 modos × 50 seeds = **600 execuções** de 3600 s, `libsumo` headless, 4 processos.

**Pareamento por seed é inegociável:** gerar as rotas uma vez por (cenário, seed) e reutilizar nos três modos. Sem isso a comparação deixa de ser pareada e perde poder estatístico.

`validar_execucao()` do `context/06` §4 roda em toda execução; falha → descarte **documentado** e reexecução com a mesma seed.

---

### Bloco 9 — Análise e artefatos acadêmicos (Sprint 8) · ~2 semanas

`analysis/` completo: Wilcoxon como principal e t pareado como secundário, Cliff's δ obrigatório, IC 95% por bootstrap, Holm-Bonferroni para múltiplas comparações. Tabelas T1–T6 e figuras F1–F6 em PDF vetorial, legíveis em escala de cinza.

`python -m analysis.gerar_resultados_tcc` reproduz o capítulo 5 inteiro com um comando.

Em paralelo: diagramas PlantUML do `context/08` §5, DER via eralchemy2, relatório de validação, checklist assinado do protótipo.

---

## Marcos de verificação

| Marco | O que prova |
|---|---|
| Fim do Bloco 2 | O núcleo do TCC existe e é seguro — invariantes verificados por property-based testing |
| Fim do Bloco 4 | **Sabemos se as hipóteses se sustentam**, com tempo de sobra para reagir |
| Fim do Bloco 5 | O protótipo físico funciona fim-a-fim, incluindo o fail-safe |
| Fim do Bloco 8 | Os dados do capítulo 5 existem e são reprodutíveis |

## Pendências que continuam abertas

- **P4, P6, P11, P12** — ações de redação no texto do TCC. O código já implementa a versão correta; falta a equipe atualizar o documento. **P6 é o maior risco acadêmico** e depende do Bloco 8.
- **P8, P9** — resolvidas por teste de bancada no Bloco 5.
- **P3** — decidida (agente reativo determinístico), mas **comunicar ao orientador** antes de fechar a redação dos capítulos 2 e 6.
