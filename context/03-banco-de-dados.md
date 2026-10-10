# 03 — Arquitetura do Banco de Dados

## 1. Regra de compatibilidade com o texto do TCC

O pré-projeto já documenta quatro tabelas: `SEMAFORO`, `VEICULO_EMERGENCIA`, `LOG_PRIORIDADE`, `METRICA_SIMULACAO`, com campos específicos. **Esses nomes e campos são preservados exatamente**, porque já estão no texto entregue. As tabelas adicionais abaixo são extensões necessárias para o sistema funcionar de verdade — e o capítulo 4 do TCC precisa ser atualizado para incluí-las (ver `09-pendencias-e-decisoes.md` item P4).

Nunca renomeie uma coluna existente sem sinalizar que isso exige correção no documento acadêmico.

## 2. Modelo lógico

```
                    ┌──────────────────┐
                    │    SEMAFORO      │
                    └────────┬─────────┘
                             │ 1
                             │
                    ┌────────┴─────────┐
                    │  FASE_SEMAFORO   │  N
                    └──────────────────┘

┌───────────────────┐        ┌──────────────────┐
│ VEICULO_EMERGENCIA│──1:N──▶│    TAG_RFID      │
└─────────┬─────────┘        └──────────────────┘
          │ 1:N              ┌──────────────────┐
          ├─────────────────▶│   OCORRENCIA     │  (P20: no máximo 1 aberta por VE)
          │                  └──────────────────┘
          │
          │ N                ┌──────────────────┐
          │                  │ DISPOSITIVO_IOT  │
          ▼                  └────────┬─────────┘
┌───────────────────┐                 │ 1:N
│  LOG_PRIORIDADE   │◀────────────────┘
└─────────┬─────────┘        ┌──────────────────┐
          │ N:1              │    DETECCAO      │
          ▼                  └──────────────────┘
┌───────────────────┐
│ METRICA_SIMULACAO │
└─────────┬─────────┘
          │ N:1
          ▼
┌───────────────────┐        ┌────────────────────────┐
│ EXECUCAO_SIMULACAO│──1:N──▶│ ESTADO_SEMAFORO_AMOSTRA│
└───────────────────┘        └────────────────────────┘
```

> **`PEDIDO_SIMULACAO` (Bloco 6, 2026-10-05)** fica fora do diagrama acima: é a
> fila dos pedidos de `POST /simulacoes`, e aponta N:1, opcionalmente, para
> `EXECUCAO_SIMULACAO`. É tabela operacional, e não do experimento.

## 3. DDL

Arquivo de referência: `db/schema.sql`. A fonte da verdade operacional são as migrations Alembic; este DDL existe para o anexo do TCC e deve ser mantido em sincronia.

### 3.1 Tabelas do texto original

```sql
CREATE TYPE estado_sinal    AS ENUM ('VERDE', 'AMARELO', 'VERMELHO');
CREATE TYPE tipo_veiculo    AS ENUM ('AMBULANCIA', 'BOMBEIRO', 'POLICIA');
CREATE TYPE status_operacao AS ENUM ('ATIVO', 'INATIVO', 'MANUTENCAO', 'FALHA');
CREATE TYPE status_execucao AS ENUM ('SUCESSO', 'FALHA', 'TIMEOUT', 'CONFLITO_ADIADO', 'ABORTADO_SEGURANCA');
CREATE TYPE modo_controle   AS ENUM ('FIXO', 'PREEMPCAO', 'PREEMPCAO_COMPENSADA',
                                     'PREEMPCAO_ML');  -- braço de H4, migration 9d3e6b1f4a27 (10.7)

CREATE TABLE semaforo (
    id_semaforo     SERIAL PRIMARY KEY,
    codigo_externo  VARCHAR(50)   NOT NULL UNIQUE,  -- id do TLS no SUMO ou do controlador físico
    descricao       VARCHAR(120),
    latitude        DECIMAL(10,8) NOT NULL,
    longitude       DECIMAL(11,8) NOT NULL,
    estado_atual    estado_sinal  NOT NULL DEFAULT 'VERMELHO',
    tempo_ciclo     INT           NOT NULL,
    status_operacao status_operacao NOT NULL DEFAULT 'ATIVO',
    criado_em       TIMESTAMPTZ   NOT NULL DEFAULT now(),
    atualizado_em   TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE TABLE veiculo_emergencia (
    id_veiculo         SERIAL PRIMARY KEY,
    placa              VARCHAR(7)  NOT NULL UNIQUE,   -- padrão Mercosul
    tipo               tipo_veiculo NOT NULL,
    identificacao      VARCHAR(60),                   -- ex.: "SAMU 192 - Unidade 07"
    status_operacional status_operacao NOT NULL DEFAULT 'ATIVO',
    criado_em          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE metrica_simulacao (
    id_metrica           SERIAL PRIMARY KEY,
    id_execucao          INT REFERENCES execucao_simulacao(id_execucao) ON DELETE CASCADE,
    tempo_medio_resposta DECIMAL(8,2) NOT NULL,  -- s, deslocamento do VE
    tempo_espera         DECIMAL(8,2) NOT NULL,  -- s, parado em cruzamentos
    percentual_reducao   DECIMAL(5,2) NOT NULL,
    latencia_ia          DECIMAL(8,2) NOT NULL,  -- ms
    cenario_simulado     VARCHAR(50)  NOT NULL,
    criado_em            TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE log_prioridade (
    id_log               SERIAL PRIMARY KEY,
    fk_veiculo           INT REFERENCES veiculo_emergencia(id_veiculo),
    fk_semaforo          INT NOT NULL REFERENCES semaforo(id_semaforo),
    fk_metrica           INT REFERENCES metrica_simulacao(id_metrica),
    fk_execucao          INT REFERENCES execucao_simulacao(id_execucao),
    id_correlacao        UUID NOT NULL,
    timestamp_inicio     TIMESTAMPTZ NOT NULL,
    timestamp_fim        TIMESTAMPTZ,
    ganho_tempo_segundos INT,
    status_execucao      status_execucao NOT NULL,
    motivo               VARCHAR(200),
    fase_anterior        INT,
    fase_aplicada        INT
);
```

**Nota sobre `DECIMAL(5,2)`:** o texto original usa `DECIMAL(5,2)` em `metrica_simulacao`, o que limita o valor a 999,99. `tempo_medio_resposta` de 950 s cabe, mas fica sem folga; em cenário intenso pode estourar. Ampliado para `DECIMAL(8,2)`. Registrar a correção no TCC.

**Nota sobre `longitude`:** o texto usa `DECIMAL(10,8)` para ambas as coordenadas. Longitude vai de -180 a 180 e precisa de 3 dígitos inteiros — `DECIMAL(10,8)` **não comporta** a longitude de São Paulo (-46,63). Corrigido para `DECIMAL(11,8)`. Este é um erro real do documento e precisa ser corrigido no texto.

### 3.2 Tabelas de extensão

```sql
CREATE TABLE fase_semaforo (
    id_fase       SERIAL PRIMARY KEY,
    fk_semaforo   INT NOT NULL REFERENCES semaforo(id_semaforo) ON DELETE CASCADE,
    indice_fase   INT NOT NULL,
    descricao     VARCHAR(80) NOT NULL,       -- "Eixo Principal A-B"
    movimentos    TEXT[] NOT NULL,            -- movimentos servidos
    duracao_base  INT NOT NULL,
    verde_min     INT NOT NULL DEFAULT 7,
    verde_max     INT NOT NULL DEFAULT 60,
    UNIQUE (fk_semaforo, indice_fase)
);

CREATE TABLE tag_rfid (
    id_tag      SERIAL PRIMARY KEY,
    uid         VARCHAR(32) NOT NULL UNIQUE,   -- normalizado: maiúsculas, sem espaços
    fk_veiculo  INT NOT NULL REFERENCES veiculo_emergencia(id_veiculo) ON DELETE CASCADE,
    ativo       BOOLEAN NOT NULL DEFAULT true,
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE dispositivo_iot (
    id_dispositivo SERIAL PRIMARY KEY,
    codigo         VARCHAR(50) NOT NULL UNIQUE,   -- "CTRL_PROTO_01"
    tipo           VARCHAR(30) NOT NULL,          -- EMISSOR_V2I | RECEPTOR_V2I | CONTROLADOR_SEMAFORO
    fk_semaforo    INT REFERENCES semaforo(id_semaforo),
    token_hash     VARCHAR(128) NOT NULL,
    ultimo_contato TIMESTAMPTZ,
    firmware_versao VARCHAR(20),
    status         status_operacao NOT NULL DEFAULT 'ATIVO'
);

-- P20 (2026-09-29): a emergência é estado declarado pela central de despacho,
-- não propriedade do veículo. Sem ocorrência aberta, a tag é reconhecida mas
-- não preempta. A criticidade é ordinal (1 = mais crítico) e decide E8 antes do tipo.
CREATE TABLE ocorrencia (
    id_ocorrencia  SERIAL PRIMARY KEY,
    fk_veiculo     INT NOT NULL REFERENCES veiculo_emergencia(id_veiculo),
    criticidade    SMALLINT NOT NULL CHECK (criticidade BETWEEN 1 AND 3),
    descricao      VARCHAR(200),
    origem         VARCHAR(20) NOT NULL DEFAULT 'CENTRAL',  -- CENTRAL | OPERADOR
    aberta_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    encerrada_em   TIMESTAMPTZ,
    CHECK (encerrada_em IS NULL OR encerrada_em >= aberta_em)
);

CREATE TABLE deteccao (
    id_deteccao     BIGSERIAL PRIMARY KEY,
    id_correlacao   UUID NOT NULL,
    origem          VARCHAR(20) NOT NULL,          -- V2I_RFID | RADAR_SIM | MANUAL
    fk_dispositivo  INT REFERENCES dispositivo_iot(id_dispositivo),
    fk_veiculo      INT REFERENCES veiculo_emergencia(id_veiculo),
    uid_bruto       VARCHAR(32),
    reconhecido     BOOLEAN NOT NULL,
    autorizado      BOOLEAN NOT NULL DEFAULT false,  -- P20: reconhecido E com ocorrência ativa
    fk_ocorrencia   INT REFERENCES ocorrencia(id_ocorrencia),
    rssi            SMALLINT,
    sequencia       INT,
    recebido_em     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE execucao_simulacao (
    id_execucao      SERIAL PRIMARY KEY,
    nome_cenario     VARCHAR(50) NOT NULL,
    modo             modo_controle NOT NULL,
    seed             INT NOT NULL,
    duracao_s        INT NOT NULL,
    arquivo_rede     VARCHAR(120) NOT NULL,
    versao_codigo    VARCHAR(40),                 -- git rev-parse --short HEAD, com -suja se há código fora do commit
    parametros       JSONB NOT NULL,              -- snapshot de parametros.yaml
    exemplar         BOOLEAN NOT NULL DEFAULT false,  -- P5: se true, grava transições no banco
    iniciada_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finalizada_em    TIMESTAMPTZ,
    UNIQUE (nome_cenario, modo, seed)
);

-- Decisão P5 (2026-08-24): grava apenas TRANSIÇÕES de fase, não amostras periódicas.
-- `t_simulacao` é o instante da transição. `fase_anterior` permite verificar I2/I3/I4
-- (verde->amarelo->all-red->verde, verde mínimo respeitado) sem série temporal densa.
-- Além disso, só execuções marcadas como exemplares (execucao_simulacao.exemplar = true)
-- são persistidas aqui; as demais das 600 vivem em CSV sob analysis/data/.
CREATE TABLE estado_semaforo_amostra (
    id_amostra     BIGSERIAL PRIMARY KEY,
    fk_execucao    INT NOT NULL REFERENCES execucao_simulacao(id_execucao) ON DELETE CASCADE,
    fk_semaforo    INT NOT NULL REFERENCES semaforo(id_semaforo),
    t_simulacao    DECIMAL(10,2) NOT NULL,   -- instante da TRANSIÇÃO
    fase_anterior  INT,                      -- NULL na primeira transição da execução
    fase           INT NOT NULL,
    estado         estado_sinal NOT NULL,
    em_preempcao   BOOLEAN NOT NULL DEFAULT false,
    fila_total     INT NOT NULL DEFAULT 0,
    duracao_fase_anterior_s DECIMAL(8,2)     -- verifica I4 (verde_min) diretamente
);

CREATE TABLE metrica_latencia (
    id_latencia     BIGSERIAL PRIMARY KEY,
    id_correlacao   UUID NOT NULL,
    fk_log          INT REFERENCES log_prioridade(id_log),
    t_deteccao      TIMESTAMPTZ NOT NULL,
    t_decisao       TIMESTAMPTZ,                  -- NULL na bancada (Bloco 6, 2026-10-05)
    t_atuacao       TIMESTAMPTZ,
    latencia_decisao_ms  INT GENERATED ALWAYS AS
        (EXTRACT(EPOCH FROM (t_decisao - t_deteccao)) * 1000)::INT STORED,
    latencia_total_ms    INT,
    ambiente        VARCHAR(20) NOT NULL          -- SIMULACAO | HARDWARE
);

-- Bloco 6 (2026-10-05): POST /simulacoes grava aqui; o atendente do host executa.
-- Demonstração, não experimento: seeds 1..50 e 101..105 são recusadas.
CREATE TABLE pedido_simulacao (
    id_pedido      SERIAL PRIMARY KEY,
    nome_cenario   VARCHAR(50) NOT NULL,
    modo           modo_controle NOT NULL,
    seed           INT NOT NULL,
    duracao_s      INT CHECK (duracao_s IS NULL OR duracao_s > 0),  -- NULL: a de cenarios.yaml
    -- Bloco 7: múltiplo do tempo real em que o atendente roda; NULL é o máximo.
    -- O ritmo fica fora do SUMO e não muda o resultado (migration e5a17c3d8b42).
    velocidade     SMALLINT CHECK (velocidade IS NULL OR velocidade IN (1, 2, 5, 10)),
    status         VARCHAR(12) NOT NULL DEFAULT 'PENDENTE'
                   CHECK (status IN ('PENDENTE', 'RODANDO', 'CONCLUIDA', 'FALHA')),
    fk_execucao    INT REFERENCES execucao_simulacao(id_execucao) ON DELETE SET NULL,
    mensagem       VARCHAR(200),
    resumo         JSONB,                         -- o que o executor mediu; não é capítulo 5
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    iniciado_em    TIMESTAMPTZ,
    finalizado_em  TIMESTAMPTZ
);

CREATE TABLE metrica_via_transversal (
    id_metrica_tv        SERIAL PRIMARY KEY,
    fk_execucao          INT NOT NULL REFERENCES execucao_simulacao(id_execucao) ON DELETE CASCADE,
    fk_semaforo          INT NOT NULL REFERENCES semaforo(id_semaforo),
    tempo_espera_medio   DECIMAL(8,2) NOT NULL,
    fila_maxima          INT NOT NULL,
    veiculos_processados INT NOT NULL,
    janela               VARCHAR(20) NOT NULL     -- PRE_EVENTO | DURANTE | POS_EVENTO
);
```

### 3.3 Índices

```sql
CREATE INDEX idx_log_correlacao        ON log_prioridade (id_correlacao);
CREATE INDEX idx_log_execucao_semaforo ON log_prioridade (fk_execucao, fk_semaforo);
CREATE INDEX idx_log_inicio            ON log_prioridade (timestamp_inicio DESC);
CREATE INDEX idx_amostra_exec_t        ON estado_semaforo_amostra (fk_execucao, t_simulacao);
CREATE INDEX idx_deteccao_uid_tempo    ON deteccao (uid_bruto, recebido_em DESC);
CREATE INDEX idx_metrica_exec          ON metrica_simulacao (id_execucao);
CREATE INDEX idx_pedido_status_criado  ON pedido_simulacao (status, criado_em);

-- P20: no máximo UMA ocorrência aberta por veículo. É o banco, e não o código,
-- que impede duas criticidades concorrentes para o mesmo VE.
CREATE UNIQUE INDEX uq_ocorrencia_aberta_por_veiculo
    ON ocorrencia (fk_veiculo) WHERE encerrada_em IS NULL;
```

**Decisão P5 (2026-08-24) — resolvida.** Amostrar a 10 Hz daria ~173 milhões de linhas; a 1 Hz, ~17 M. Ambas inviáveis numa máquina de estudante. A solução adotada:

1. **Só transições de fase** vão para `estado_semaforo_amostra` — ordem de centenas de milhares de linhas, e suficiente para reconstruir todo o histórico e verificar I2, I3 e I4.
2. **Só execuções exemplares** (`execucao_simulacao.exemplar = true`, uma por par cenário × modo, as que geram as figuras) são persistidas no banco. As demais das 600 ficam em CSV sob `analysis/data/`.

Consequência para o coletor: ele mantém a fase corrente de cada TLS em memória e só enfileira um registro quando ela muda, calculando `duracao_fase_anterior_s` na virada.

## 4. Regras de persistência

1. **Nunca escrever no banco dentro do loop de simulação.** O `traci.simulationStep()` roda a 10 Hz; um `INSERT` síncrono por passo derruba o desempenho e contamina a medição de latência. Use fila em memória + flush em lote a cada 500 registros ou 5 s, com `COPY`/`executemany`.
2. **Latência é medida em memória**, não a partir do banco. O banco recebe o resultado da medição.
3. **Toda execução de simulação grava `versao_codigo` e `parametros`.** Sem isso não há reprodutibilidade e o resultado não é defensável.
4. **`id_correlacao` é gerado na detecção** e propagado até a atuação e a métrica.

## 5. Seeds

`db/seeds/` com dados mínimos para o sistema subir funcional:

- 8 semáforos correspondentes ao TLS da rede SUMO + **1 semáforo do protótipo físico** (`PROTO_CRUZ_01`).
- **2 fases** para `PROTO_CRUZ_01`, as do ciclo da bancada (decisão de 2026-10-05, que revê P13):

  | `indice_fase` | `descricao` | Módulos físicos |
  | --- | --- | --- |
  | 1 | Eixo principal | S1 + S2 |
  | 2 | Eixo transversal | S3 + S4 |

  A emergência abre o verde de **uma** aproximação (S1..S4), que não é fase do
  ciclo. **Decidido no Bloco 6 (2026-10-05):** a aproximação vai em `motivo`, e
  `fase_aplicada` fica nula. Assim `fase_aplicada` continua significando índice
  de `fase_semaforo`, como na simulação. **Aplicado nos seeds em 2026-10-05
  (entrega 5.8)**, com `tempo_ciclo = 12`. Um banco semeado antes dessa data é
  corrigido pela migration `7b2e4d9a1c35`, só de dados: os seeds são
  idempotentes por chave e nunca apagam, então sozinhos deixariam as fases 3 e 4
  e o `LEITOR_CRUZ_01` no lugar. A migration tira as fases 3 e 4, reescreve as
  fases 1 e 2 e o ciclo, e tira o `LEITOR_CRUZ_01`. Se alguma `deteccao` apontar
  para ele, ele fica, marcado `INATIVO`, para não apagar histórico.

  > **Correção de P13 (histórico).** Até 2026-10-05 esta seção pedia 4 fases em
  > *split phasing*, uma por aproximação. O firmware que a equipe de hardware
  > escreveu roda 2 fases, e a equipe decidiu adaptar o sistema a ele.
  >
  > **Correção anterior, ainda válida.** A versão anterior desta seção pedia *"4 semáforos do protótipo (`PROTO_S1..S4`)"*, o que modelava cada módulo como um cruzamento independente. Está errado: o protótipo é **um** cruzamento com quatro aproximações, então é **uma** linha em `semaforo` e **quatro** em `fase_semaforo`. Os identificadores `S1..S4` continuam existindo, mas como nomes de aproximação no firmware e no protocolo serial — não como chaves de `semaforo`.
- 3 veículos de emergência (uma ambulância, um bombeiro, uma viatura) com placas fictícias no padrão Mercosul.
- 2 tags RFID vinculadas a veículos, **com UIDs fictícios**. As tags reais da
  bancada identificam **ruas**, não veículos (`05` §1), e não entram em
  `tag_rfid`: o mapa UID → rua vive no sketch do emissor, e o backend recebe a
  rua já resolvida. `tag_rfid` continua servindo à API e à autorização de P20.
- Dispositivos IoT: `EMISSOR_VE_01` (NodeMCU + RC522, no veículo, tipo
  `EMISSOR_V2I`, **sem** `fk_semaforo`), `RECEPTOR_CRUZ_01` (NodeMCU do
  cruzamento, `RECEPTOR_V2I`) e `CTRL_PROTO_01` (UNO, `CONTROLADOR_SEMAFORO`).
  Substituíram o `LEITOR_CRUZ_01` em 2026-10-05 (entrega 5.8). Em 2026-10-08
  entraram `EMISSOR_VE_02` e `EMISSOR_VE_03`, os carrinhos do bombeiro e da
  polícia (`05` §1); o `01` é o da ambulância. Os seeds só acrescentam, então
  um banco já semeado os ganha na próxima carga, sem migration. Nenhum deles
  chama a API, então `token_hash` não é exercitado pela bancada.
- **Nenhuma ocorrência** — de propósito (P20). O sistema sobe sem VE em
  serviço. *(Desde 2026-10-06 isso vale também na bancada: o UNO liga negando
  todos, e só preempta o tipo com ocorrência aberta pela Central; o roteiro de
  demonstração abre a ocorrência no passo 3, `05` §7.)*

## 6. DER para o TCC

Gerar automaticamente para não haver divergência entre diagrama e schema:

```bash
# opção 1: a partir do banco vivo
docker compose exec db pg_dump -s -U tcc semaforo > docs/schema_dump.sql
# opção 2: diagrama
python -m eralchemy2 -i "$DATABASE_URL" -o docs/diagramas/der.pdf
```

O DER do TCC deve mostrar as entidades e a cardinalidade, destacando as quatro entidades originais (Semáforo, Veículo de Emergência, Log de Prioridade, Métrica de Simulação) e agrupando as extensões em um bloco "entidades de apoio operacional".
