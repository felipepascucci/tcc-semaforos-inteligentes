# TCC — Controle Dinâmico de Semáforos com Priorização de Veículos de Emergência

Universidade Paulista (UNIP) · Bacharelado em Ciência da Computação · 2026
Orientador: Prof. Marco Gomes
Equipe: Felipe Rafael Tancredi Pascucci · Giovanna Santos da Silva · Isabelle Rosa Moura Ferreira

Um único **motor de decisão** em Python puro, agnóstico ao atuador, validado em
duas frentes: **simulação** (SUMO + TraCI — de onde vêm todos os números do
capítulo 5) e **protótipo físico** (Arduino UNO + NodeMCU + RFID — prova de
viabilidade, sem papel estatístico).

- Escopo, hipóteses e não-escopo: [`context/00-visao-geral.md`](context/00-visao-geral.md)
- Plano de execução por blocos: [`docs/plano-desenvolvimento.md`](docs/plano-desenvolvimento.md)
- Integração com a bancada: [`docs/contrato-hardware-software.md`](docs/contrato-hardware-software.md)

---

## Começando

Pré-requisitos: **Docker Desktop**, **Python 3.11+**, **SUMO 1.19+**. **Node 20+**
só para desenvolver o dashboard: o compose compila o frontend sozinho.

```powershell
Copy-Item .env.example .env      # ajuste se precisar; .env nunca é commitado

docker compose up -d --build     # db -> migrations + seeds -> backend -> dashboard
curl http://localhost:8000/api/v1/health
```

O dashboard fica em **https://localhost:8443**. O certificado é autoassinado: o
navegador avisa na primeira vez, e basta aceitar a exceção. Login de
desenvolvimento: usuário `operador`, senha `operador` (ver "Dashboard", abaixo).

É só isso. O serviço `migracoes` cria o schema e aplica os seeds antes de o
backend subir, então um clone limpo vira um sistema utilizável com um comando.
As duas operações são idempotentes — subir de novo não duplica nada.

`/api/v1/health` responde `estado: "ok"` quando o banco está acessível, e
`degradado` com HTTP 503 caso contrário. Também mostra a ponte da bancada
(`ponte`, `uno_respondendo`) e a simulação ao vivo (`simulacao_ao_vivo`), que são
opcionais e não derrubam o `estado`. O que não está configurado aparece como
`nao_configurado` — nunca como verde falso.

A API está em `http://localhost:8000/docs` (rotas de `context/01` §7) e o
WebSocket em `ws://localhost:8000/api/v1/stream`, com throttle de 5 Hz.

| Serviço | Porta | Perfil | Observação |
| --- | --- | --- | --- |
| `db` (PostgreSQL 16) | 5432 | padrão | volume nomeado `pgdata`, healthcheck `pg_isready` |
| `migracoes` | — | padrão | one-shot: migrations + seeds, depois sai com código 0 |
| `backend` (FastAPI) | 8000 | padrão | `--reload`, `/docs` para a API interativa |
| `adminer` | 8080 | `dev` | `docker compose --profile dev up -d adminer` |
| `frontend` (nginx) | 8443 | padrão | dashboard em HTTPS, proxy de `/api` e do WebSocket |

## Dashboard

React + Vite + TypeScript + Tailwind, com mapa Leaflet e gráficos Recharts
(`context/02` §2). Cinco abas: **Ao vivo** (mapa, bancada, semáforos, eventos,
preempção manual), **Central** (as ocorrências de P20), **Logs**, **Métricas** e
**Simulações**.

No compose, o nginx serve o build em HTTPS e repassa `/api` ao backend, então
dashboard e API ficam na mesma origem. Dois processos rodam **no host**, fora do
compose, e sem eles a tela fica parada:

```powershell
.\.venv\Scripts\python.exe -m bridge.main --simulado      # a bancada, com o dublê do UNO
.\.venv\Scripts\python.exe -m sim.controlador.atendente   # executa os pedidos da aba Simulações
```

**Sem o atendente, o pedido de simulação fica "pendente" para sempre**, e os
CRUZ_01..08 ficam "sem dado ao vivo": só a simulação transmite o estado deles. A
aba Simulações avisa quando um pedido passa de 10 s pendente. O pedido escolhe a
velocidade: 1x é tempo real (3600 s levam 1 h, então ponha uma duração), e
"máxima" roda a ~50x. A velocidade não muda o resultado.

O mapa desenha a malha SUMO a partir de `frontend/src/malha/malha.json`. Se a
rede (`sim/rede/malha.net.xml`) ou o mapa de fases mudarem, regenere-o com
`python -m sim.rede.exportar_mapa`; um teste acusa o arquivo desatualizado.

**Login.** Uma credencial só, a do operador (`context/02` §6), lida do ambiente:
`OPERADOR_USUARIO`, `OPERADOR_SENHA_HASH` e `JWT_SEGREDO`. O compose traz
padrões **só de desenvolvimento** (senha `operador`). Para trocar a senha:

```powershell
docker compose exec backend python -m app.services.autenticacao   # imprime OPERADOR_SENHA_HASH=…
```

Copie a linha para o `.env`, troque também o `JWT_SEGREDO` (32 caracteres ou
mais) e rode `docker compose up -d backend`. **Trocar os dois antes da
apresentação.** O token vale 8 h e protege só as escritas do operador; a leitura
e o WebSocket ficam abertos (decisão do Bloco 7, `context/09`).

**Desenvolvendo o frontend**, com recarga a quente:

```powershell
cd frontend
npm ci
npm run dev          # http://localhost:5173, com /api repassado ao backend da porta 8000
npm test             # Vitest
npm run typecheck    # tsc
```

## Ambiente Python local

O compose cobre o backend, mas `sim/`, `bridge/`, `analysis/` e as ferramentas de
qualidade rodam no host.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"          # acrescente ",analysis" ou ",hardware" conforme o bloco

ruff check . ; ruff format --check .
mypy                             # strict, restrito a backend/core/ (context/08 §3)
pytest                           # `sumo` e `hardware` ficam de fora por padrão
```

Marcadores (`pyproject.toml`, seção `[tool.pytest.ini_options]`):

| Marcador | O que exige | Na execução padrão? |
| --- | --- | --- |
| `sumo` | binário do SUMO e `SUMO_HOME` | não — `pytest -m sumo` |
| `hardware` | a bancada física ligada | não — `pytest -m hardware` |
| `banco` | **Docker rodando** (Postgres efêmero via testcontainers) | sim |
| `lento` | alguns segundos (medição de latência, escala) | sim |

`banco` e `lento` ficam na execução padrão de propósito: o teste de integração
do banco e o de latência do RNF01 são critérios de pronto, e escondê-los atrás de
um marcador seria escondê-los. Para uma rodada rápida sem Docker:

```powershell
pytest -m "not banco and not lento and not sumo and not hardware"
```

## O motor de decisão

O núcleo do trabalho é [backend/core/](backend/core/): Python puro, **sem I/O e
sem framework**, o mesmo algoritmo que roda na simulação e no protótipo. A regra
não depende de disciplina — [test_arquitetura.py](backend/tests/test_arquitetura.py)
reprova via AST qualquer import de framework, I/O ou camada externa dentro de
`core/`, e até o uso de `math.dist` (E1 exige distância **ao longo da rota**,
nunca euclidiana).

Os invariantes de segurança I1–I5 estão em [seguranca.py](backend/core/seguranca.py)
e são verificados por property-based testing: o Hypothesis dirige milhares de
sequências aleatórias de comandos contra a máquina de estados e confere os
invariantes em todo estado alcançado.

## SUMO

Instalação (Windows):

```powershell
winget install --id EclipseFoundation.SUMO --exact
```

O instalador define `SUMO_HOME` e coloca `%SUMO_HOME%\bin` no `PATH` — **abra um
terminal novo** depois de instalar, senão o processo atual continua com o
ambiente antigo.

O cliente Python (`traci`, `libsumo`) **não** é instalado pelo pip: ele vem em
`%SUMO_HOME%\tools`, que o [`conftest.py`](conftest.py) acrescenta ao `sys.path`.
Uma segunda cópia via pip poderia ficar em versão diferente do binário — bug
silencioso e caro de achar.

Verificação: `pytest -m sumo`.

## Simulação

A malha e a demanda são **construídas**, não versionadas prontas. A ordem importa
e não é arbitrária — cada etapa consome o resultado da anterior:

```powershell
make rede         # netconvert + detectores        -> sim/rede/malha.net.xml
make saturacao    # MEDE o fluxo de saturação      -> analysis/data/fluxo_saturacao.csv
make cenarios     # deriva o v/c de cada cenário   -> analysis/data/calibracao_cenarios.csv
make fluxos       # congela a demanda derivada     -> sim/demanda/fluxo_*.rou.xml
make validar      # os quatro itens do context/04 §12
```

`make calibrar` faz as três do meio de uma vez. Sem `make` (o caso do Windows
puro), cada alvo é um `python -m ...` — o Makefile serve de documentação da
ordem, e as receitas estão à vista.

Rodar uma execução:

```powershell
python -m sim.controlador.executor --cenario leve --modo FIXO --seed 1
python -m sim.controlador.executor --cenario intenso --modo PREEMPCAO --seed 3 --gui
make demo         # o corredor verde na sumo-gui
```

| Opção | Para quê |
| --- | --- |
| `--modo` | `FIXO` (baseline, sem intervenção), `PREEMPCAO`, `PREEMPCAO_COMPENSADA` |
| `--seed` | escolhe o arquivo de rotas — **o mesmo nos três modos** (pareamento) |
| `--gui` | roda na `sumo-gui`, para ver o corredor e gravar a demonstração |
| `--libsumo` | ~10x mais rápido, sem GUI — implementado, mas **não** é o modo do lote (P15) |
| `--exemplar` | persiste transições no banco e latências detalhadas (decisão P5) |
| `--sem-banco` | não grava em `execucao_simulacao` |
| `--saida-detalhada` | grava também `queue.xml` — 77 MB por execução, para depurar |

`--libsumo` **não funciona nesta instalação**: o instalador Windows do SUMO não
traz o módulo Python do `libsumo`, só os bindings Java/C#/C++. **P15, fechada em
2026-10-01:** o lote do Bloco 8 roda com `traci` e processos em paralelo (~6 h
para as 600, medido no piloto), e o `libsumo` não é instalado pelo pip. A opção
continua no adaptador para o caso de a máquina de execução mudar.

### Ver o corredor verde

```powershell
.\.venv\Scripts\Activate.ps1
python -m sim.controlador.executor --cenario leve --modo PREEMPCAO --seed 1 `
    --duracao 900 --gui --sem-banco
```

A janela abre e já começa a rodar. Três coisas que ajudam a de fato **ver** o
efeito:

1. **O primeiro VE entra aos 300 s de simulação**, que é o aquecimento declarado
   em `cenarios.yaml` — antes disso a malha só está enchendo. Com o atraso padrão
   de 20 ms por passo, isso é cerca de um minuto de espera. Para pular o
   aquecimento, rode com `--atraso-ms 0` e aumente o campo **Delay (ms)** da
   barra de ferramentas para ~20–50 quando o relógio passar dos 290 s.
2. **Troque o tema de `standard` para `real world`** na caixa da barra de
   ferramentas — no padrão todo veículo é um triângulo e a ambulância fica igual
   a um carro. A `sumo-gui` memoriza a escolha.
3. **Para acompanhar o VE:** botão da lupa (*Locate Vehicle*) → escolha
   `VE_ROTA_VE_CORREDOR_00`; depois botão direito nele → *Start Tracking*.
   Ambulância é vermelha, bombeiro laranja, polícia azul.
4. **O que observar:** o VE entra a oeste em CRUZ_01, e os semáforos vão abrindo
   à frente dele até CRUZ_04; ali ele converte à direita para a transversal e, em
   CRUZ_08, entra na arterial de baixo — repare que nesse cruzamento a fase
   aberta para ele é a **transversal**, não a arterial. Compare rodando o mesmo
   comando com `--modo FIXO`: o VE para 5 a 6 vezes.

Três coisas que valem saber antes de mexer:

- **O `.net.xml` e o `.det.add.xml` são gerados** e ficam fora do Git. Os
  arquivos-fonte (`.nod`, `.edg`, `.con`, `.tll`, `.typ`) é que são versionados.
  `python -m sim.rede.construir --verificar` diz se a rede no disco está em dia.
- **Mexer em `veiculos.typ.xml` obriga a recalibrar.** `tau`, `minGap`, `length`,
  `accel` e `decel` determinam o fluxo de saturação; mudá-los sem rodar
  `make calibrar` faz o v/c descrever uma malha que não é a que roda.
- **As rotas por seed são materializadas**, não sorteadas pelo SUMO. É o que
  garante o pareamento do `context/04` §7, e é verificável com `diff`.

## Banco de dados

O `docker compose up` já cuida disso pelo serviço `migracoes`. Os comandos abaixo
servem para rodar **do host**, contra o banco do compose — o caso de quem está
mexendo em migration ou em seed:

```powershell
docker compose up -d db          # o banco precisa estar no ar
alembic upgrade head             # 14 tabelas (12 + `ocorrencia`, P20, + `pedido_simulacao`, Bloco 6) e 5 enums
python -m db.seeds.carregar      # cadastros mínimos; idempotente
python -m db.seeds.carregar --resumo

docker compose logs migracoes    # o que o serviço one-shot fez na última subida
docker compose down -v           # zera o volume; a próxima subida recria tudo
```

As migrations vivem em [db/migrations/](db/migrations/) e o `alembic.ini` fica na
raiz, para que `alembic upgrade head` funcione sem `-c`. A URL vem sempre do
ambiente, nunca do `.ini`.

[db/schema.sql](db/schema.sql) é **gerado**, para o anexo do TCC. Regenerar
depois de qualquer migration:

```powershell
docker compose exec -T db pg_dump -s -O -x -U tcc semaforo
```

`-O -x` tira dono e permissões: o anexo descreve o schema, não o usuário do
ambiente. O cabeçalho do arquivo (comentários e revisão do Alembic) é mantido à
mão.

Duas coisas nos seeds são deliberadas e não devem surpreender:

- **As tags RFID são placeholder e estão inativas.** Só recebem UID real na
  entrega 5.8. Tag placeholder ativa seria uma credencial válida publicada no
  repositório.
- **Os 8 TLS da malha não têm fases semeadas.** Elas vêm do `.net.xml` e do
  `sim/config/mapa_fases.yaml` no Bloco 3. Suas coordenadas e `tempo_ciclo` são
  provisórios, e o próprio [db/seeds/dados.yaml](db/seeds/dados.yaml) diz quais
  campos são e por quê.

### Sobre a `DATABASE_URL`

É uma variável só, com dois significados conforme onde o processo roda. No host
ela vem do `.env` e aponta para `localhost`; dentro do contêiner, o
`docker-compose.yml` a redefine no `environment:` apontando para o serviço `db`.
Como o ambiente do processo vence o `.env`, os dois casos funcionam sem
configuração extra.

## Rodar `sim/` e `bridge/` no host

Ficam fora do compose de propósito (context/02 §3): `sim/` precisa do binário do
SUMO e de GUI para gravar a demonstração; `bridge/` precisa de acesso a `COM3`.
Ambos usam a `DATABASE_URL` do `.env` e falam com o backend em
`http://localhost:8000`.

A ponte roda a partir da raiz do repositório, só **escuta** o UNO e expõe a
própria API em `http://127.0.0.1:8001` (`/health`, `/estado`, `/injecao`,
documentação em `/docs`). **O backend lê a ponte**, e não o contrário: o
contêiner consulta `GET /estado` a 5 Hz em `http://host.docker.internal:8001`
(`PONTE_URL_CONTEINER` no `.env`), grava os eventos do UNO em `log_prioridade` e
as amostras de H3 em `metrica_latencia`, e os repassa ao WebSocket. Sem ponte no
ar, o backend sobe do mesmo jeito. No Linux, rode a ponte com `--host 0.0.0.0`,
porque o `host-gateway` não alcança o 127.0.0.1 do host.

```powershell
.venv\Scripts\python.exe -m bridge.main             # porta do .env (SERIAL_PORT)
.venv\Scripts\python.exe -m bridge.main --porta COM5
.venv\Scripts\python.exe -m bridge.main --simulado  # sem bancada: dublê do UNO
# Medição de H3: o NodeMCU do veículo no USB do notebook (context/05 §4.3)
.venv\Scripts\python.exe -m bridge.main --porta COM3 --porta-veiculo COM5
# Checklist da bancada: grava cada linha do USB do UNO (context/06 §6)
.venv\Scripts\python.exe -m bridge.main --porta COM3 --porta-veiculo COM5 --telemetria
```

O que a bancada grava fica em `analysis/data/`: `deteccoes_bancada.csv` (RNF05),
`latencia_bancada.csv` (H3) e, com `--telemetria`, `telemetria_bancada.csv`. Os
resultados saem só desses arquivos:

```powershell
.venv\Scripts\python.exe -m analysis.resumo_bancada --sessao <sessão>      # RNF05 e H3
.venv\Scripts\python.exe -m analysis.checklist_bancada --todas --banco     # itens de 06 §6
```

Precisa do extra `hardware` (`pip install -e ".[dev,hardware]"`). A bancada fala
a **9600 baud**: confira `SERIAL_BAUDRATE` no `.env`.

Para conferir a ponte de ponta a ponta (~4 min), noutro terminal, logo depois de
subi-la: `.venv\Scripts\python.exe -m bridge.verificar`. **Com o backend
parado**: o roteiro manda ao UNO a lista da Central ele mesmo, e o backend a
trocaria pela do banco.

O UNO liga **negando todos** (a Central vale na bancada desde 2026-10-06): com o
compose no ar, o backend leva a ele, em até ~1 s, quem tem ocorrência aberta. Aí
`POST /api/v1/semaforos/PROTO_CRUZ_01/preempcao` (`{"rua": 3, "veiculo":
"AMBULANCIA"}`) faz o VE "chegar" pela injeção da ponte, e a decisão do UNO
aparece em `/api/v1/logs/prioridade` — `SEM_OCORRENCIA` se a ambulância não
estiver em serviço na aba Central.

Para apresentar, o roteiro guiado da demonstração (`context/05` §7), com a ponte
no ar, o compose no ar e o dashboard aberto:

```powershell
.venv\Scripts\python.exe -m bridge.demo                 # pede a senha do operador
.venv\Scripts\python.exe -m bridge.demo --sem-carrinho  # plano B: a ponte injeta a ambulância
```

### Simulação ao vivo e pedidos pela API

O executor transmite o estado ao backend a 5 Hz quando pedido; o lote roda sem:

```powershell
python -m sim.controlador.executor --cenario leve --modo PREEMPCAO --seed 1001 `
    --duracao 900 --sem-banco --transmitir --velocidade 5   # padrão: $BACKEND_URL
```

`--velocidade N` roda a N vezes o tempo real, para acompanhar no dashboard; sem
ela, o executor roda o mais rápido que a máquina permite (~50x). Não muda o
resultado. Com `--gui`, o ritmo é o `--atraso-ms` da sumo-gui.

`POST /api/v1/simulacoes` não roda o SUMO (ele está no host, e o backend no
contêiner): grava um pedido, que o **atendente** executa com transmissão ligada:

```powershell
python -m sim.controlador.atendente              # atende até Ctrl+C
python -m sim.controlador.atendente --uma-vez    # atende o que houver e sai
```

As seeds 1..50 (Bloco 8) e 101..105 (calibração) são recusadas pela API e pelo
atendente, e os CSV de uma execução pedida vão para `sim/saida/<ponto>/`, nunca
para `analysis/data/`.

## Firmware

`firmware/uno/semaforo/` é o UNO; `firmware/nodemcu/` são os dois NodeMCUs, como
a equipe de hardware os escreveu (context/05). Para compilar o UNO sem a IDE:

```powershell
arduino-cli core install arduino:avr
arduino-cli lib install "LiquidCrystal I2C"
arduino-cli compile --fqbn arduino:avr:uno firmware/uno/semaforo
```

Para gravar: `.venv\Scripts\python.exe -m bridge.gravar_uno --porta COM3`, com a
ponte fechada. Ele compila, grava em pedaços pequenos e relê a flash inteira.
**Não use o `arduino-cli upload`**: na bancada ele grava errado 4 bytes de cada
página e não percebe (`context/05` §3.7). Com o receptor no A0 (desde
2026-10-06), não é preciso soltar fio nenhum. Os testes de
`tests/firmware/` compilam o núcleo do firmware para o PC (pacote `ziglang`, do
extra `dev`) e o comparam com o dublê.

## Estrutura

```
backend/   API FastAPI + motor de decisão (core/ é puro: sem I/O, sem framework)
sim/       Cenários SUMO + controlador TraCI
firmware/  Sketches Arduino UNO R3 e NodeMCU ESP8266
bridge/    Ponte serial (backend <-> Arduino UNO)
frontend/  Dashboard React
db/        Migrations (Alembic) e seeds
analysis/  Estatística, tabelas e figuras do TCC
docs/      Artefatos entregáveis (plano, contrato, diagramas, relatórios)
context/   Pacote de contexto — fonte da verdade do escopo
```

---

# Pacote de Contexto

Fonte da verdade do escopo, arquitetura e decisões do projeto. Escrito para ser
lido por um agente de código (Claude Code) e pela equipe.

O [`CLAUDE.md`](CLAUDE.md) é lido automaticamente no início de cada sessão e
aponta para os arquivos abaixo. **Mantenha atualizado:** quando uma decisão muda
o sistema, o arquivo correspondente muda **no mesmo commit** (context/08 §4.7).

| Arquivo | Leia quando |
| --- | --- |
| `00-visao-geral.md` | Sempre primeiro. Objetivos, hipóteses, requisitos, escopo e não-escopo, glossário |
| `01-arquitetura-sistema.md` | Qualquer trabalho no backend, no motor de decisão ou nos contratos de API |
| `02-arquitetura-infraestrutura.md` | Docker, dependências, rede, segurança, observabilidade, AWS |
| `03-banco-de-dados.md` | Modelagem, migrations, queries, persistência |
| `04-simulacao-trafego.md` | SUMO, TraCI, cenários, protocolo experimental, coleta de métricas |
| `05-integracao-hardware.md` | Firmware Arduino/ESP8266, protocolo serial, ponte, demonstração |
| `06-testes-e-validacao.md` | Escrever testes, gerar relatório de validação, checklist do protótipo |
| `07-resultados-e-analise.md` | Pipeline estatístico, tabelas e figuras do TCC |
| `08-roadmap-e-convencoes.md` | Planejar a próxima entrega, padrões de código, artefatos acadêmicos |
| `09-pendencias-e-decisoes.md` | **Sempre.** Contradições ainda não resolvidas — não decida sozinho |
| `10-aprendizado-de-maquina.md` | IA e o modelo de ML de P19: onde atuam, como foram treinados e avaliados, estado do Bloco 10, perguntas da banca |

## Estado do documento

Gerado a partir de:

- `Pré_Projeto_TCC_Versao_Final.docx`
- `Protótipo_hardware_documentado_v1.docx`

Tudo que aparece aqui e **não** está nos documentos originais está marcado como
proposta ou pendência. Onde há divergência entre os documentos, o conflito está
registrado em `09-pendencias-e-decisoes.md` — nenhum foi resolvido
silenciosamente.

## Pendências de maior risco

1. **P6** — os números do capítulo 5 ainda não vêm de execução real. Maior risco
   acadêmico. **Aberta.**
2. **P4 / P12** — correções e registros pendentes no texto do TCC. **Abertas.**
3. **P11** — fechada em 2026-10-01 (o método foi aprovado), mas a redação da
   metodologia depende das referências que o orientador ficou de devolver.
4. **P19 / Bloco 10** — o modelo está treinado (10.5); faltam a inferência em
   `core/` (10.6), o braço `PREEMPCAO_ML` (10.7) e a análise de H4 (10.8). Bloqueia
   o Bloco 8.

**Fechadas em 2026-10-05:** P8 (boot normal com o RC522 no D3) e P9 (não se
aplica: o LCD está no UNO, de 5 V). **Bancada, 2026-10-07:** checklist de
`context/06` §6 feito, menos o item 5 (falta uma tag fora das 4 ruas); faltam as
fotos e a versão do pacote `esp8266` (`docs/contrato-hardware-software.md` §15).

**Decidida em 2026-09-29:** P20 — a preempção exige tag reconhecida **e**
ocorrência ativa aberta pela central de despacho (simulada), e a criticidade da
ocorrência decide entre VEs antes do tipo, como regra acima do modelo de P19.

**Revogada em 2026-09-10:** P3 — a banca espera aprendizado de máquina, que entra
para escolher entre VEs em conflito (P19, Bloco 10).

**Resolvidas em 2026-08-24:** P1 (H1 ≥ 25% condicionada à saturação), P2
(latência de decisão e fim-a-fim são métricas distintas), ~~P3~~ (revogada, acima), P5 (persistir só transições de fase, só
de execuções exemplares), P7 (RFID emula radar+V2I, declarado no texto), P10
(módulos semáforo têm resistores integrados; sem restrição elétrica), P13
(protótipo é um cruzamento de 4 aproximações em split phasing; protocolo passa a
4 fases). Ver [`context/09-pendencias-e-decisoes.md`](context/09-pendencias-e-decisoes.md).
