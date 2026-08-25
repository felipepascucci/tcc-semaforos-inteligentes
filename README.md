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

Pré-requisitos: **Docker Desktop**, **Python 3.11+**, **SUMO 1.19+**, **Node 18+**
(só a partir do Bloco 7).

```powershell
Copy-Item .env.example .env      # ajuste se precisar; .env nunca é commitado

docker compose up -d --build     # db -> migrations + seeds -> backend
curl http://localhost:8000/api/v1/health
```

É só isso. O serviço `migracoes` cria o schema e aplica os seeds antes de o
backend subir, então um clone limpo vira um sistema utilizável com um comando.
As duas operações são idempotentes — subir de novo não duplica nada.

`/api/v1/health` responde `estado: "ok"` quando o banco está acessível, e
`degradado` com HTTP 503 caso contrário. Componentes ainda não implementados são
declarados como `nao_configurado` — nunca como verde falso.

| Serviço | Porta | Perfil | Observação |
| --- | --- | --- | --- |
| `db` (PostgreSQL 16) | 5432 | padrão | volume nomeado `pgdata`, healthcheck `pg_isready` |
| `migracoes` | — | padrão | one-shot: migrations + seeds, depois sai com código 0 |
| `backend` (FastAPI) | 8000 | padrão | `--reload`, `/docs` para a API interativa |
| `adminer` | 8080 | `dev` | `docker compose --profile dev up -d adminer` |
| `frontend` (Vite) | 5173 | `frontend` | só existe a partir do Bloco 7 |

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

## Banco de dados

O `docker compose up` já cuida disso pelo serviço `migracoes`. Os comandos abaixo
servem para rodar **do host**, contra o banco do compose — o caso de quem está
mexendo em migration ou em seed:

```powershell
docker compose up -d db          # o banco precisa estar no ar
alembic upgrade head             # cria as 12 tabelas e os 5 enums
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
docker compose exec -T db pg_dump -s -U tcc semaforo
```

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
2. **P4 / P11 / P12** — correções e registros pendentes no texto do TCC.
   **Abertas.**
3. **P8 / P9** — verificações de bancada (GPIO 0 no RST do RC522, LCD I2C em
   5 V — aguardando peças). **Abertas, resolver no Bloco 5.**

**Resolvidas em 2026-08-24:** P1 (H1 ≥ 25% condicionada à saturação), P2
(latência de decisão e fim-a-fim são métricas distintas), P3 (agente reativo
determinístico; ML como trabalho futuro), P5 (persistir só transições de fase, só
de execuções exemplares), P7 (RFID emula radar+V2I, declarado no texto), P10
(módulos semáforo têm resistores integrados; sem restrição elétrica), P13
(protótipo é um cruzamento de 4 aproximações em split phasing; protocolo passa a
4 fases). Ver [`context/09-pendencias-e-decisoes.md`](context/09-pendencias-e-decisoes.md).
