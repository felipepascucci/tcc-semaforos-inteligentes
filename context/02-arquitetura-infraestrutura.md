# 02 — Arquitetura da Infraestrutura

## 1. Camadas

O pré-projeto define uma arquitetura híbrida **Edge + Nuvem**. Mapeamento concreto para este TCC:

| Camada conceitual | O que é na prática | Onde roda |
| --- | --- | --- |
| **Dispositivo / Veículo** | NodeMCU emissor + RC522 (lê a tag da rua, envia por ESP-NOW) | Bancada, no carrinho |
| **Borda (Edge)** | NodeMCU receptor + Arduino UNO, que **decide** e atua; LCD 16x2 | Bancada, no cruzamento |
| **Observação local** | Processo `bridge` (só escuta o UNO) + instância local do backend | Notebook junto ao protótipo |
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
| Testes backend | pytest, pytest-asyncio, httpx, testcontainers, **hypothesis** | — |
| Testes frontend | Vitest + Testing Library | — |
| Container | Docker + Docker Compose | — |
| Firmware | Arduino IDE 2.3.10 / PlatformIO | — |
| Configuração | **PyYAML**, **python-dotenv** | — |
| Observabilidade | structlog | — |
| Driver do banco | psycopg | 3.x |
| Qualidade | ruff, mypy | — |

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

**Sobre `libsumo`:** é ~10x mais rápido que `traci` porque roda no mesmo processo, mas não permite múltiplos clientes nem GUI. Estratégia: usar `traci` no desenvolvimento (com `sumo-gui`, para gravar vídeo da demonstração) e `libsumo` nas 50 execuções em lote. A camada de adaptador deve abstrair os dois atrás da mesma interface.

> **Implementado em `backend/adapters/sumo/cliente.py`** (Bloco 3), com uma
> ressalva descoberta ao exercitá-lo: o **instalador Windows do SUMO não traz o
> módulo Python do `libsumo`** — só os bindings Java/C#/C++. O módulo vem do pip,
> o que esbarra na regra de não instalar cliente do SUMO por lá. Registrado como
> **P15**, para decidir antes do Bloco 8; o caminho `traci` funciona hoje e
> paraleliza por processo.
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
  frontend:   # Vite dev server (dev) ou nginx (prod) — perfil "frontend"
  adminer:    # inspeção do banco em dev — perfil "dev"
```

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
SERIAL_PORT_VEICULO=COM4             # NodeMCU emissor, só na medição de H3
LOG_LEVEL=INFO
```

> **Sem Wi-Fi desde 2026-10-05.** `WIFI_SSID`, `WIFI_PASSWORD`,
> `BACKEND_URL_DISPOSITIVO` e o `secrets.h` gerado saíram: os NodeMCUs se falam
> por ESP-NOW e não acessam rede nem backend (`05` §5). O `.env.example` é
> ajustado na entrega 5.7.

## 5. Rede do protótipo

**Não há rede** (decisão de 2026-10-05). Os dois NodeMCUs se falam por
**ESP-NOW**: rádio de 2,4 GHz direto, MAC a MAC, sem roteador nem ponto de
acesso. O notebook se liga ao UNO só por USB.

```
[NodeMCU emissor] --ESP-NOW--> [NodeMCU receptor] --serial 9600--> [Arduino UNO R3] --USB--> [Notebook]
   (veículo)                       (cruzamento)                                                ├── bridge (só escuta)
                                                                                               ├── backend :8000
                                                                                               ├── postgres :5432
                                                                                               └── frontend :5173
```

O MAC do receptor está fixo no sketch do emissor (`40:91:51:58:A8:E1`). Trocar
a placa receptora exige regravar o emissor.

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

**Ser explícito no texto do TCC:** UID de tag Mifare S50 é clonável; num sistema real seria necessário criptografia assimétrica com certificados por veículo (padrão IEEE 1609.2). Reconhecer essa limitação vale mais na banca do que fingir que não existe. Anotar como trabalho futuro.

## 7. Observabilidade

- **Logs estruturados** (JSON) com `structlog`, campos obrigatórios: `timestamp`, `nivel`, `evento`, `id_correlacao`, `id_semaforo`, `id_veiculo`.
- **`id_correlacao`** — gerado na detecção e propagado por todo o fluxo até a atuação. É o que permite reconstruir uma priorização completa nos relatórios de validação. Sem ele, o item 6 do escopo (relatórios de validação) fica inviável.
- **Métricas de latência** gravadas em `metrica_latencia` a cada priorização, com os três carimbos: `t_deteccao`, `t_decisao`, `t_atuacao`.
- **Health check** em `/health` retornando estado de banco, adaptadores e da porta serial da bancada.

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

Deixar claro no texto que a implementação local em Docker é **equivalente funcional** da arquitetura-alvo, e que a migração é uma troca de provedor de infraestrutura, não de arquitetura. Diagrama obrigatório em `docs/diagramas/infraestrutura.drawio`.

## 9. Estratégia de branches

`main` sempre funcional (é o que roda na apresentação). Trabalho em `feat/<sprint>-<assunto>`. Antes de qualquer demonstração, tag `v-demo-YYYYMMDD`.

Regra prática: **congelar o código 5 dias antes da apresentação.** O que estiver quebrado nessa data fica de fora, e o repositório volta para a última tag que rodava.
