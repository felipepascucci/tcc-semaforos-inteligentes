# 02 — Arquitetura da Infraestrutura

## 1. Camadas

O pré-projeto define uma arquitetura híbrida **Edge + Nuvem**. Mapeamento concreto para este TCC:

| Camada conceitual | O que é na prática | Onde roda |
| --- | --- | --- |
| **Dispositivo / Veículo** | NodeMCU emissor + RC522 (lê a tag da rua, envia por ESP-NOW), um por carrinho: ambulância, bombeiro e polícia | Bancada, nos 3 carrinhos |
| **Borda (Edge)** | NodeMCU receptor + Arduino UNO, que **decide** e atua; LCD 16x2 | Bancada, no cruzamento |
| **Observação local** | Processo `bridge` (escuta o UNO e lhe leva a lista da Central) + instância local do backend | Notebook junto ao protótipo |
| **Nuvem** | PostgreSQL, API, dashboard, análise histórica | Docker local; AWS como arquitetura-alvo documentada |
| **Simulação** | SUMO + controlador TraCI | Mesma máquina do backend |

A justificativa acadêmica da separação: decisões críticas de preempção acontecem na borda (latência < 200 ms, funciona sem rede nem notebook); persistência, análise histórica e relatórios acontecem na nuvem (tolera latência, precisa de durabilidade).

> **Camadas revistas em 2026-10-05**, com a adoção da arquitetura montada na
> bancada (`05` §2). Antes, a borda era o notebook (`bridge` + backend), e o UNO
> só executava comandos. Agora a borda é o próprio controlador do cruzamento, e
> o notebook observa.

## 2. Stack fixa

Não introduzir dependência fora desta lista sem registrar em `09-pendencias-e-decisoes.md`.

| Camada | Tecnologia | Versão |
| --- | --- | --- |
| Linguagem backend | Python | 3.11+ |
| API | FastAPI + Uvicorn | FastAPI 0.11x |
| ORM / migrations | SQLAlchemy 2.x + Alembic | — |
| Validação | Pydantic | v2 |
| Banco | PostgreSQL | 16 |
| Simulador | Eclipse SUMO | 1.19+ |
| Cliente do simulador | TraCI (`libsumo` opcional) | pacote `traci` |
| Serial | pyserial | 3.5 |
| Frontend | React + TypeScript + Vite | React 18 |
| Estilo | TailwindCSS | 3.x |
| Mapa | Leaflet + react-leaflet | — |
| Gráficos | Recharts | — |
| Análise | pandas, numpy, scipy, matplotlib | — |
| Esquema elétrico (desde 2026-10-10) | **schemdraw**, sobre o matplotlib, no extra `analysis` | 0.23 |
| Testes backend | pytest, pytest-asyncio, httpx, testcontainers, **hypothesis**, **ziglang** | — |
| Testes frontend | Vitest + Testing Library | — |
| Container | Docker + Docker Compose | — |
| Firmware | Arduino IDE 2.3.10 (equipe) / **arduino-cli** 1.5 · core `arduino:avr` 1.8.8 · `LiquidCrystal I2C` 1.1.2 (Frank de Brabander) · `SoftwareSerial` (vem com o core, sem instalação; desde 2026-10-06, para o receptor no A0) | — |
| Configuração | **PyYAML**, **python-dotenv** | — |
| Observabilidade | structlog | — |
| Driver do banco | psycopg | 3.x |
| Qualidade | ruff, mypy | — |
| Autenticação do dashboard | **PyJWT** (HS256); senha em PBKDF2 do `hashlib` | 2.x |
| Proxy reverso / TLS do dashboard | **nginx** (imagem `nginx:1.27-alpine`) | 1.27 |

> **As quatro últimas linhas e o `hypothesis` foram acrescentados durante os
> Blocos 0 a 2**, cada um com a decisão registrada em
> `09-pendencias-e-decisoes.md`, conforme a regra do §4.8 de `08`. Os motivos, em
> uma linha cada: `PyYAML` porque `parametros.yaml` precisa de um parser e a
> biblioteca padrão não traz um; `python-dotenv` porque `alembic`, `db/seeds`,
> `sim/` e `bridge/` rodam **fora** do compose e não recebem as variáveis pelo
> `environment:` do Docker; `hypothesis` porque `06` §3 a recomenda nominalmente
> para o property-based testing de I1 — e é dependência **só de teste**;
> `psycopg` já estava implícita na `DATABASE_URL` do §4; `structlog` já constava
> do §7 deste arquivo; `ruff` e `mypy` já constavam do §3 de `08`.
>
> **`httpx` passou a dependência de runtime no Bloco 6 (2026-10-05).** Já estava
> na stack, para teste. O backend o usa para ler `GET /estado` da ponte, e o
> executor para transmitir o estado ao vivo. Registrado em `09`.
>
> **Acrescentados no Bloco 7 (2026-10-05)**, registrados em `09`: o **`PyJWT`**,
> para o token do login do operador (o §6 já pedia "JWT simples"), e o
> **nginx**, que o §3 e o §6 já previam. No frontend, além de React, Vite, TS,
> Tailwind, Leaflet, react-leaflet, Recharts, Vitest e Testing Library, entram
> só os pacotes de apoio que essas ferramentas exigem: `@vitejs/plugin-react`,
> `postcss` e `autoprefixer` (Tailwind 3), `jsdom` (ambiente do Vitest),
> `@testing-library/user-event` e `@testing-library/jest-dom`, e os tipos
> `@types/react`, `@types/react-dom` e `@types/leaflet`. As versões ficam
> fixadas em `frontend/package.json`. **react-leaflet fica na 4.x**, a última
> compatível com React 18, e o **TypeScript na 5.x**. Não há biblioteca de rotas:
> a aba fica no `#` da URL.
>
> **Acrescentados no Bloco 5 (2026-10-05)**, registrados em `09`: o
> **`arduino-cli`**, para compilar o firmware do UNO sem a IDE, com o core e a
> biblioteca do LCD fixados na versão acima; e o **`ziglang`**, dependência
> **só de teste**, que traz um compilador C++ dentro do `.venv` e permite rodar o
> núcleo do firmware no PC contra o dublê (`05` §3.7). Sem ele, esse teste é
> pulado; sem o `arduino-cli`, o de compilação para a placa.

**Sobre `libsumo`:** é ~10x mais rápido que `traci` porque roda no mesmo processo, mas não permite múltiplos clientes nem GUI. Estratégia original: usar `traci` no desenvolvimento (com `sumo-gui`, para gravar vídeo da demonstração) e `libsumo` nas execuções em lote. A camada de adaptador deve abstrair os dois atrás da mesma interface. **Revista em P15 (2026-10-01): o lote também roda com `traci`**, com processos em paralelo.

> **Implementado em `backend/adapters/sumo/cliente.py`** (Bloco 3), com uma
> ressalva descoberta ao exercitá-lo: o **instalador Windows do SUMO não traz o
> módulo Python do `libsumo`** — só os bindings Java/C#/C++. O módulo vem do pip,
> o que esbarra na regra de não instalar cliente do SUMO por lá. Registrado como
> **P15**, **fechada em 2026-10-01**: o lote do Bloco 8 roda com `traci` e
> `--paralelo 6` (~6 h para as 600, medido no piloto), e o `libsumo` não é
> instalado pelo pip. `--libsumo` continua implementado, sem ser o padrão.
>
> **`sumolib`** também é usado (leitura do `.net.xml` em `adapters/sumo/topologia.py`
> e `sim/rede/detectores.py`). Vem de `%SUMO_HOME%/tools`, como o `traci`, então
> não é dependência nova nem exceção à lista acima.

## 3. Serviços (docker-compose)

```yaml
services:
  db:         # postgres:16-alpine, volume nomeado, healthcheck
  migracoes:  # one-shot: alembic upgrade head + seeds, depois sai
  backend:    # FastAPI, depends_on db healthy + migracoes concluído
  frontend:   # build estático do Vite servido por nginx, HTTPS em :8443
  adminer:    # inspeção do banco em dev — perfil "dev"
```

> **`frontend` (Bloco 7, 2026-10-05).** Dockerfile em dois estágios: `node`
> compila o build do Vite, e o `nginx` o serve em **https://localhost:8443**, com
> proxy reverso de `/api` (REST e WebSocket, `wss`) para o `backend`. O serviço
> está no compose **padrão**, sem perfil, então `docker compose up` sobe o
> dashboard junto, como pede a Definition of Done. O certificado autoassinado é
> gerado na primeira subida, num volume (`certificados`). Para desenvolver o
> frontend com recarga a quente, `npm run dev` no host (:5173), cujo proxy
> repassa `/api` ao backend da porta 8000.

> **`migracoes` (acrescentado em 2026-08-25).** Serviço de vida curta que cria o
> schema e aplica os seeds antes de o `backend` subir
> (`condition: service_completed_successfully`). Existe para que
> `docker compose up` entregue um sistema utilizável a partir de um clone limpo,
> que é o que a Definition of Done do `CLAUDE.md` pede. As duas operações são
> idempotentes: subir de novo não duplica nada.
>
> **Consequência para o §6 deste arquivo:** em desenvolvimento, `migracoes` e
> `backend` usam o **mesmo** usuário `tcc`, então a separação "usuário da
> aplicação sem privilégio de DDL" não vale no compose local. A separação
> continua sendo o desenho correto e permanece descrita no §6 como alvo — o
> serviço já está isolado justamente para que ganhar credencial própria seja uma
> mudança de uma linha. Decisão registrada em `09-pendencias-e-decisoes.md`.

Fora do compose (rodam no host, precisam de USB e display):

- `sim/` — precisa do binário SUMO e, para gravar a demo, de GUI.
- `bridge/` — precisa de acesso a `/dev/ttyUSB0` (Linux) ou `COM3` (Windows).

Documentar em `README.md` como rodar os dois localmente apontando para o backend do compose.

## 4. Variáveis de ambiente

`.env.example` versionado; `.env` **nunca** commitado.

```
DATABASE_URL=postgresql+psycopg://tcc:senha@localhost:5432/semaforo
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:5173
PERFIL_PARAMETROS=simulacao          # ou "hardware"
SUMO_HOME=/usr/share/sumo
SUMO_BINARY=sumo                     # ou sumo-gui
SERIAL_PORT=COM3                     # UNO
SERIAL_BAUDRATE=9600                 # a do NodeMCU receptor; o UNO tem uma UART só
SERIAL_PORT_VEICULO=COM4             # NodeMCU emissor no USB, só na medição de H3
PONTE_URL=http://localhost:8001      # o backend lê GET /estado da ponte (vazio desliga)
PONTE_URL_CONTEINER=http://host.docker.internal:8001   # a mesma, vista do compose
BACKEND_URL=http://localhost:8000    # para onde o executor e o atendente transmitem
LOG_LEVEL=INFO
OPERADOR_USUARIO=operador            # login do dashboard (Bloco 7)
OPERADOR_SENHA_HASH=pbkdf2_sha256:…  # python -m app.services.autenticacao
JWT_SEGREDO=…                        # ≥ 32 caracteres; o backend não sobe com menos
DASHBOARD_PORT=8443                  # porta HTTPS do nginx no host (opcional)
```

> **As três variáveis do login têm padrão de desenvolvimento no compose** (senha
> `operador`), como `POSTGRES_PASSWORD`, para um clone limpo subir sem passo
> manual. Trocar antes da apresentação.

> **Sem Wi-Fi desde 2026-10-05.** `WIFI_SSID`, `WIFI_PASSWORD`,
> `BACKEND_URL_DISPOSITIVO` e o `secrets.h` gerado saíram: os NodeMCUs se falam
> por ESP-NOW e não acessam rede nem backend (`05` §5). O `.env.example` é
> ajustado na entrega 5.7.

## 5. Rede do protótipo

**Não há rede** (decisão de 2026-10-05). Os NodeMCUs (os três emissores e o
receptor, desde 2026-10-08) se falam por **ESP-NOW**: rádio de 2,4 GHz direto, MAC a MAC, sem roteador nem ponto de
acesso. O notebook se liga ao UNO só por USB.

```
[3 NodeMCU emissores] -ESP-NOW-> [NodeMCU receptor] --serial 9600, A0--> [Arduino UNO R3] <--USB--> [Notebook]
   (veículo)                       (cruzamento)                                                ├── bridge (escuta; leva a Central)
                                                                                               ├── backend :8000
                                                                                               ├── postgres :5432
                                                                                               └── frontend :8443 (nginx, HTTPS)
```

O MAC do receptor está fixo no sketch dos emissores (`40:91:51:58:A8:E1`).
Trocar a placa receptora exige regravar os três.

Rede da faculdade, SSID 2,4 GHz e IP fixo do backend deixaram de ser
preocupação: nada na bancada usa Wi-Fi.

## 6. Segurança (RNF04)

Escopo realista para TCC, com honestidade sobre o que é demonstração:

| Item | Implementação |
| --- | --- |
| API ↔ dashboard | HTTPS via reverse proxy (nginx + certificado autoassinado em dev) |
| Autenticação dashboard | JWT simples, um perfil `operador` |
| Dispositivo → API | Header `X-Device-Token` com token pré-compartilhado por dispositivo, validado contra `dispositivo_iot.token_hash` |
| Anti-replay | Campo `sequencia` monotônico + janela de deduplicação de 2 s por UID |
| Autorização de tag | UID precisa existir em `tag_rfid` com `ativo = true`. UID desconhecido → HTTP 403 e log de tentativa |
| Banco | Usuário da aplicação sem privilégio de DDL; migrations com usuário separado. **Em desenvolvimento ainda não vale:** o serviço `migracoes` e o `backend` compartilham o usuário `tcc` (ver nota do §3) |
| Segredos | `.env` fora do Git. *(O `secrets.h` dos NodeMCUs saiu em 2026-10-05: não há credencial de Wi-Fi)* |

> **Na bancada (desde 2026-10-05), as linhas de dispositivo → API, anti-replay
> e autorização de tag não se aplicam:** nenhum dispositivo chama a API. O que
> existe em troca, e precisa ser declarado como limitação: o **ESP-NOW está sem
> criptografia** nos sketches. Qualquer ESP8266 que conheça o MAC do receptor
> pode mandar `RUA3,AMBULANCIA` e preemptar o cruzamento. O ESP-NOW suporta
> chave por par (CCMP), e ativá-la é o primeiro item de trabalho futuro de
> segurança, ao lado dos certificados abaixo.

> **Implementado no Bloco 7 (2026-10-05)** — as duas primeiras linhas da tabela:
>
> - **HTTPS.** O nginx do serviço `frontend` termina o TLS (TLS 1.2 e 1.3) com
>   certificado autoassinado gerado na primeira subida, e repassa ao backend
>   pela rede interna do Docker. O navegador fala só HTTPS e `wss`. **A porta
>   8000 do backend continua exposta em HTTP**, para os processos do host (o
>   executor e o atendente transmitem por ela) e para o Swagger local; o
>   Swagger também está no HTTPS, em `/docs`.
> - **Login.** `POST /auth/login` confere a credencial do operador, lida do
>   ambiente, e devolve um JWT HS256 válido por 8 h. A senha fica como
>   PBKDF2-SHA256 com sal, 600 mil iterações, nunca em claro. O token protege
>   as escritas do operador (`01` §7). Os `GET` e o WebSocket ficam abertos,
>   por decisão da equipe: o dashboard só mostra a tela depois do login, mas a
>   leitura pela API não exige token.
> - **Limitações a declarar:** sem limite de tentativas no login; sem revogação
>   de token (trocar `JWT_SEGREDO` derruba todas as sessões); o token fica no
>   `localStorage` do navegador; `/simulacoes/transmissao` aceita transmissão
>   sem autenticação de quem alcança a porta 8000; certificado autoassinado,
>   que o navegador recusa até o operador aceitar a exceção.

**Ser explícito no texto do TCC:** UID de tag Mifare S50 é clonável; num sistema real seria necessário criptografia assimétrica com certificados por veículo (padrão IEEE 1609.2). Reconhecer essa limitação vale mais na banca do que fingir que não existe. Anotar como trabalho futuro.

## 7. Observabilidade

- **Logs estruturados** (JSON) com `structlog`, campos obrigatórios: `timestamp`, `nivel`, `evento`, `id_correlacao`, `id_semaforo`, `id_veiculo`.
- **`id_correlacao`** — gerado na detecção e propagado por todo o fluxo até a atuação. É o que permite reconstruir uma priorização completa nos relatórios de validação. Sem ele, o item 6 do escopo (relatórios de validação) fica inviável.
- **Métricas de latência** gravadas em `metrica_latencia` a cada priorização, com os três carimbos: `t_deteccao`, `t_decisao`, `t_atuacao`.
- **Health check** em `/health` retornando estado de banco, adaptadores e da porta serial da bancada.

> **Implementado no Bloco 6** (`app/logs.py`, `app/api/v1/health.py`). Os seis
> campos saem em toda linha, nulos quando não se aplicam. O `id_correlacao` é
> amarrado ao contexto do fluxo (`structlog.contextvars`). O `/health` traz
> `banco`, `ponte`, `uno_respondendo` (a última `ST` tem menos de 2 s) e
> `simulacao_ao_vivo`. **Só o banco decide o `estado`**: bancada e simulação são
> opcionais. O antigo `watchdog_serial` saiu com a redefinição de I6 (`01` §6).

## 8. Arquitetura-alvo em AWS (documental)

Descrever no TCC, implantar somente se sobrar tempo:

| Componente | Serviço AWS | Justificativa |
| --- | --- | --- |
| API | ECS Fargate ou EC2 t3.small | Contêiner já pronto |
| Banco | RDS PostgreSQL Multi-AZ | Durabilidade e failover |
| Dashboard | S3 + CloudFront | Estático, baixo custo |
| Ingestão IoT | AWS IoT Core (MQTT) | Substituiria o POST HTTP direto |
| Borda | AWS IoT Greengrass | Formalizaria o nó de borda |
| Logs/métricas | CloudWatch | Auditoria |
| Segredos | Secrets Manager | Substitui `.env` |

Deixar claro no texto que a implementação local em Docker é **equivalente funcional** da arquitetura-alvo, e que a migração é uma troca de provedor de infraestrutura, não de arquitetura. Diagrama obrigatório em `docs/diagramas/infraestrutura.puml` (desde 2026-10-08, em PlantUML e não no draw.io; o segundo diagrama do arquivo, `infraestrutura_aws`, é esta tabela).

## 9. Estratégia de branches

`main` sempre funcional (é o que roda na apresentação). Trabalho em `feat/<sprint>-<assunto>`. Antes de qualquer demonstração, tag `v-demo-YYYYMMDD`.

Regra prática: **congelar o código 5 dias antes da apresentação.** O que estiver quebrado nessa data fica de fora, e o repositório volta para a última tag que rodava.
