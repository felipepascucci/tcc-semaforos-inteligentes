-- db/schema.sql — DDL do banco, GERADO. Não edite à mão.
--
-- Anexo do TCC (context/03 §3). A fonte da verdade operacional são as
-- migrations Alembic; este arquivo é o retrato do banco depois de
-- `alembic upgrade head`, mantido em sincronia para o capítulo 4.
--
-- Regenerar:
--   docker compose exec -T db pg_dump -s -U tcc semaforo
--
-- Gerado de: PostgreSQL 16 (serviço `db` do docker-compose)
-- Revisão Alembic: 9d3e6b1f4a27

--
-- PostgreSQL database dump
--

\restrict pJVPAarVvE8FrPGo8V4bJcF0MtrYHgcCAt9tkJDO4a8DKYsNBqTlDpzDOeub9Kf

-- Dumped from database version 16.15
-- Dumped by pg_dump version 16.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: estado_sinal; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.estado_sinal AS ENUM (
    'VERDE',
    'AMARELO',
    'VERMELHO'
);


--
-- Name: modo_controle; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.modo_controle AS ENUM (
    'FIXO',
    'PREEMPCAO',
    'PREEMPCAO_COMPENSADA',
    'PREEMPCAO_ML'
);


--
-- Name: status_execucao; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.status_execucao AS ENUM (
    'SUCESSO',
    'FALHA',
    'TIMEOUT',
    'CONFLITO_ADIADO',
    'ABORTADO_SEGURANCA'
);


--
-- Name: status_operacao; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.status_operacao AS ENUM (
    'ATIVO',
    'INATIVO',
    'MANUTENCAO',
    'FALHA'
);


--
-- Name: tipo_veiculo; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.tipo_veiculo AS ENUM (
    'AMBULANCIA',
    'BOMBEIRO',
    'POLICIA'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: deteccao; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.deteccao (
    id_deteccao bigint NOT NULL,
    id_correlacao uuid NOT NULL,
    origem character varying(20) NOT NULL,
    fk_dispositivo integer,
    fk_veiculo integer,
    uid_bruto character varying(32),
    reconhecido boolean NOT NULL,
    rssi smallint,
    sequencia integer,
    recebido_em timestamp with time zone DEFAULT now() NOT NULL,
    autorizado boolean DEFAULT false NOT NULL,
    fk_ocorrencia integer
);


--
-- Name: deteccao_id_deteccao_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.deteccao_id_deteccao_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: deteccao_id_deteccao_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.deteccao_id_deteccao_seq OWNED BY public.deteccao.id_deteccao;


--
-- Name: dispositivo_iot; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dispositivo_iot (
    id_dispositivo integer NOT NULL,
    codigo character varying(50) NOT NULL,
    tipo character varying(30) NOT NULL,
    fk_semaforo integer,
    token_hash character varying(128) NOT NULL,
    ultimo_contato timestamp with time zone,
    firmware_versao character varying(20),
    status public.status_operacao DEFAULT 'ATIVO'::public.status_operacao NOT NULL
);


--
-- Name: dispositivo_iot_id_dispositivo_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.dispositivo_iot_id_dispositivo_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dispositivo_iot_id_dispositivo_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.dispositivo_iot_id_dispositivo_seq OWNED BY public.dispositivo_iot.id_dispositivo;


--
-- Name: estado_semaforo_amostra; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.estado_semaforo_amostra (
    id_amostra bigint NOT NULL,
    fk_execucao integer NOT NULL,
    fk_semaforo integer NOT NULL,
    t_simulacao numeric(10,2) NOT NULL,
    fase_anterior integer,
    fase integer NOT NULL,
    estado public.estado_sinal NOT NULL,
    em_preempcao boolean DEFAULT false NOT NULL,
    fila_total integer DEFAULT 0 NOT NULL,
    duracao_fase_anterior_s numeric(8,2)
);


--
-- Name: estado_semaforo_amostra_id_amostra_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.estado_semaforo_amostra_id_amostra_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: estado_semaforo_amostra_id_amostra_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.estado_semaforo_amostra_id_amostra_seq OWNED BY public.estado_semaforo_amostra.id_amostra;


--
-- Name: execucao_simulacao; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.execucao_simulacao (
    id_execucao integer NOT NULL,
    nome_cenario character varying(50) NOT NULL,
    modo public.modo_controle NOT NULL,
    seed integer NOT NULL,
    duracao_s integer NOT NULL,
    arquivo_rede character varying(120) NOT NULL,
    versao_codigo character varying(40),
    parametros jsonb NOT NULL,
    exemplar boolean DEFAULT false NOT NULL,
    iniciada_em timestamp with time zone DEFAULT now() NOT NULL,
    finalizada_em timestamp with time zone
);


--
-- Name: execucao_simulacao_id_execucao_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.execucao_simulacao_id_execucao_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: execucao_simulacao_id_execucao_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.execucao_simulacao_id_execucao_seq OWNED BY public.execucao_simulacao.id_execucao;


--
-- Name: fase_semaforo; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.fase_semaforo (
    id_fase integer NOT NULL,
    fk_semaforo integer NOT NULL,
    indice_fase integer NOT NULL,
    descricao character varying(80) NOT NULL,
    movimentos text[] NOT NULL,
    duracao_base integer NOT NULL,
    verde_min integer DEFAULT 7 NOT NULL,
    verde_max integer DEFAULT 60 NOT NULL
);


--
-- Name: fase_semaforo_id_fase_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.fase_semaforo_id_fase_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: fase_semaforo_id_fase_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.fase_semaforo_id_fase_seq OWNED BY public.fase_semaforo.id_fase;


--
-- Name: log_prioridade; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.log_prioridade (
    id_log integer NOT NULL,
    fk_veiculo integer,
    fk_semaforo integer NOT NULL,
    fk_metrica integer,
    fk_execucao integer,
    id_correlacao uuid NOT NULL,
    timestamp_inicio timestamp with time zone NOT NULL,
    timestamp_fim timestamp with time zone,
    ganho_tempo_segundos integer,
    status_execucao public.status_execucao NOT NULL,
    motivo character varying(200),
    fase_anterior integer,
    fase_aplicada integer
);


--
-- Name: log_prioridade_id_log_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.log_prioridade_id_log_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: log_prioridade_id_log_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.log_prioridade_id_log_seq OWNED BY public.log_prioridade.id_log;


--
-- Name: metrica_latencia; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.metrica_latencia (
    id_latencia bigint NOT NULL,
    id_correlacao uuid NOT NULL,
    fk_log integer,
    t_deteccao timestamp with time zone NOT NULL,
    t_decisao timestamp with time zone,
    t_atuacao timestamp with time zone,
    latencia_decisao_ms integer GENERATED ALWAYS AS (((EXTRACT(epoch FROM (t_decisao - t_deteccao)) * (1000)::numeric))::integer) STORED,
    latencia_total_ms integer,
    ambiente character varying(20) NOT NULL
);


--
-- Name: metrica_latencia_id_latencia_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.metrica_latencia_id_latencia_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: metrica_latencia_id_latencia_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.metrica_latencia_id_latencia_seq OWNED BY public.metrica_latencia.id_latencia;


--
-- Name: metrica_simulacao; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.metrica_simulacao (
    id_metrica integer NOT NULL,
    id_execucao integer,
    tempo_medio_resposta numeric(8,2) NOT NULL,
    tempo_espera numeric(8,2) NOT NULL,
    percentual_reducao numeric(5,2) NOT NULL,
    latencia_ia numeric(8,2) NOT NULL,
    cenario_simulado character varying(50) NOT NULL,
    criado_em timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: metrica_simulacao_id_metrica_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.metrica_simulacao_id_metrica_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: metrica_simulacao_id_metrica_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.metrica_simulacao_id_metrica_seq OWNED BY public.metrica_simulacao.id_metrica;


--
-- Name: metrica_via_transversal; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.metrica_via_transversal (
    id_metrica_tv integer NOT NULL,
    fk_execucao integer NOT NULL,
    fk_semaforo integer NOT NULL,
    tempo_espera_medio numeric(8,2) NOT NULL,
    fila_maxima integer NOT NULL,
    veiculos_processados integer NOT NULL,
    janela character varying(20) NOT NULL
);


--
-- Name: metrica_via_transversal_id_metrica_tv_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.metrica_via_transversal_id_metrica_tv_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: metrica_via_transversal_id_metrica_tv_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.metrica_via_transversal_id_metrica_tv_seq OWNED BY public.metrica_via_transversal.id_metrica_tv;


--
-- Name: ocorrencia; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ocorrencia (
    id_ocorrencia integer NOT NULL,
    fk_veiculo integer NOT NULL,
    criticidade smallint NOT NULL,
    descricao character varying(200),
    origem character varying(20) DEFAULT 'CENTRAL'::character varying NOT NULL,
    aberta_em timestamp with time zone DEFAULT now() NOT NULL,
    encerrada_em timestamp with time zone,
    CONSTRAINT ck_ocorrencia_criticidade_na_escala CHECK (((criticidade >= 1) AND (criticidade <= 3))),
    CONSTRAINT ck_ocorrencia_encerra_depois_de_abrir CHECK (((encerrada_em IS NULL) OR (encerrada_em >= aberta_em)))
);


--
-- Name: ocorrencia_id_ocorrencia_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ocorrencia_id_ocorrencia_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ocorrencia_id_ocorrencia_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ocorrencia_id_ocorrencia_seq OWNED BY public.ocorrencia.id_ocorrencia;


--
-- Name: pedido_simulacao; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pedido_simulacao (
    id_pedido integer NOT NULL,
    nome_cenario character varying(50) NOT NULL,
    modo public.modo_controle NOT NULL,
    seed integer NOT NULL,
    duracao_s integer,
    status character varying(12) DEFAULT 'PENDENTE'::character varying NOT NULL,
    fk_execucao integer,
    mensagem character varying(200),
    resumo jsonb,
    criado_em timestamp with time zone DEFAULT now() NOT NULL,
    iniciado_em timestamp with time zone,
    finalizado_em timestamp with time zone,
    velocidade smallint,
    CONSTRAINT ck_pedido_simulacao_duracao_positiva CHECK (((duracao_s IS NULL) OR (duracao_s > 0))),
    CONSTRAINT ck_pedido_simulacao_status_conhecido CHECK (((status)::text = ANY ((ARRAY['PENDENTE'::character varying, 'RODANDO'::character varying, 'CONCLUIDA'::character varying, 'FALHA'::character varying])::text[]))),
    CONSTRAINT ck_pedido_simulacao_velocidade_conhecida CHECK (((velocidade IS NULL) OR (velocidade = ANY (ARRAY[1, 2, 5, 10]))))
);


--
-- Name: pedido_simulacao_id_pedido_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pedido_simulacao_id_pedido_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pedido_simulacao_id_pedido_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pedido_simulacao_id_pedido_seq OWNED BY public.pedido_simulacao.id_pedido;


--
-- Name: semaforo; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.semaforo (
    id_semaforo integer NOT NULL,
    codigo_externo character varying(50) NOT NULL,
    descricao character varying(120),
    latitude numeric(10,8) NOT NULL,
    longitude numeric(11,8) NOT NULL,
    estado_atual public.estado_sinal DEFAULT 'VERMELHO'::public.estado_sinal NOT NULL,
    tempo_ciclo integer NOT NULL,
    status_operacao public.status_operacao DEFAULT 'ATIVO'::public.status_operacao NOT NULL,
    atualizado_em timestamp with time zone DEFAULT now() NOT NULL,
    criado_em timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: semaforo_id_semaforo_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.semaforo_id_semaforo_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: semaforo_id_semaforo_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.semaforo_id_semaforo_seq OWNED BY public.semaforo.id_semaforo;


--
-- Name: tag_rfid; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tag_rfid (
    id_tag integer NOT NULL,
    uid character varying(32) NOT NULL,
    fk_veiculo integer NOT NULL,
    ativo boolean DEFAULT true NOT NULL,
    criado_em timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: tag_rfid_id_tag_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tag_rfid_id_tag_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tag_rfid_id_tag_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tag_rfid_id_tag_seq OWNED BY public.tag_rfid.id_tag;


--
-- Name: veiculo_emergencia; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.veiculo_emergencia (
    id_veiculo integer NOT NULL,
    placa character varying(7) NOT NULL,
    tipo public.tipo_veiculo NOT NULL,
    identificacao character varying(60),
    status_operacional public.status_operacao DEFAULT 'ATIVO'::public.status_operacao NOT NULL,
    criado_em timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: veiculo_emergencia_id_veiculo_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.veiculo_emergencia_id_veiculo_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: veiculo_emergencia_id_veiculo_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.veiculo_emergencia_id_veiculo_seq OWNED BY public.veiculo_emergencia.id_veiculo;


--
-- Name: deteccao id_deteccao; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.deteccao ALTER COLUMN id_deteccao SET DEFAULT nextval('public.deteccao_id_deteccao_seq'::regclass);


--
-- Name: dispositivo_iot id_dispositivo; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dispositivo_iot ALTER COLUMN id_dispositivo SET DEFAULT nextval('public.dispositivo_iot_id_dispositivo_seq'::regclass);


--
-- Name: estado_semaforo_amostra id_amostra; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.estado_semaforo_amostra ALTER COLUMN id_amostra SET DEFAULT nextval('public.estado_semaforo_amostra_id_amostra_seq'::regclass);


--
-- Name: execucao_simulacao id_execucao; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execucao_simulacao ALTER COLUMN id_execucao SET DEFAULT nextval('public.execucao_simulacao_id_execucao_seq'::regclass);


--
-- Name: fase_semaforo id_fase; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fase_semaforo ALTER COLUMN id_fase SET DEFAULT nextval('public.fase_semaforo_id_fase_seq'::regclass);


--
-- Name: log_prioridade id_log; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.log_prioridade ALTER COLUMN id_log SET DEFAULT nextval('public.log_prioridade_id_log_seq'::regclass);


--
-- Name: metrica_latencia id_latencia; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.metrica_latencia ALTER COLUMN id_latencia SET DEFAULT nextval('public.metrica_latencia_id_latencia_seq'::regclass);


--
-- Name: metrica_simulacao id_metrica; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.metrica_simulacao ALTER COLUMN id_metrica SET DEFAULT nextval('public.metrica_simulacao_id_metrica_seq'::regclass);


--
-- Name: metrica_via_transversal id_metrica_tv; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.metrica_via_transversal ALTER COLUMN id_metrica_tv SET DEFAULT nextval('public.metrica_via_transversal_id_metrica_tv_seq'::regclass);


--
-- Name: ocorrencia id_ocorrencia; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ocorrencia ALTER COLUMN id_ocorrencia SET DEFAULT nextval('public.ocorrencia_id_ocorrencia_seq'::regclass);


--
-- Name: pedido_simulacao id_pedido; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pedido_simulacao ALTER COLUMN id_pedido SET DEFAULT nextval('public.pedido_simulacao_id_pedido_seq'::regclass);


--
-- Name: semaforo id_semaforo; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.semaforo ALTER COLUMN id_semaforo SET DEFAULT nextval('public.semaforo_id_semaforo_seq'::regclass);


--
-- Name: tag_rfid id_tag; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tag_rfid ALTER COLUMN id_tag SET DEFAULT nextval('public.tag_rfid_id_tag_seq'::regclass);


--
-- Name: veiculo_emergencia id_veiculo; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.veiculo_emergencia ALTER COLUMN id_veiculo SET DEFAULT nextval('public.veiculo_emergencia_id_veiculo_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: deteccao pk_deteccao; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.deteccao
    ADD CONSTRAINT pk_deteccao PRIMARY KEY (id_deteccao);


--
-- Name: dispositivo_iot pk_dispositivo_iot; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dispositivo_iot
    ADD CONSTRAINT pk_dispositivo_iot PRIMARY KEY (id_dispositivo);


--
-- Name: estado_semaforo_amostra pk_estado_semaforo_amostra; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.estado_semaforo_amostra
    ADD CONSTRAINT pk_estado_semaforo_amostra PRIMARY KEY (id_amostra);


--
-- Name: execucao_simulacao pk_execucao_simulacao; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execucao_simulacao
    ADD CONSTRAINT pk_execucao_simulacao PRIMARY KEY (id_execucao);


--
-- Name: fase_semaforo pk_fase_semaforo; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fase_semaforo
    ADD CONSTRAINT pk_fase_semaforo PRIMARY KEY (id_fase);


--
-- Name: log_prioridade pk_log_prioridade; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.log_prioridade
    ADD CONSTRAINT pk_log_prioridade PRIMARY KEY (id_log);


--
-- Name: metrica_latencia pk_metrica_latencia; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.metrica_latencia
    ADD CONSTRAINT pk_metrica_latencia PRIMARY KEY (id_latencia);


--
-- Name: metrica_simulacao pk_metrica_simulacao; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.metrica_simulacao
    ADD CONSTRAINT pk_metrica_simulacao PRIMARY KEY (id_metrica);


--
-- Name: metrica_via_transversal pk_metrica_via_transversal; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.metrica_via_transversal
    ADD CONSTRAINT pk_metrica_via_transversal PRIMARY KEY (id_metrica_tv);


--
-- Name: ocorrencia pk_ocorrencia; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ocorrencia
    ADD CONSTRAINT pk_ocorrencia PRIMARY KEY (id_ocorrencia);


--
-- Name: pedido_simulacao pk_pedido_simulacao; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pedido_simulacao
    ADD CONSTRAINT pk_pedido_simulacao PRIMARY KEY (id_pedido);


--
-- Name: semaforo pk_semaforo; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.semaforo
    ADD CONSTRAINT pk_semaforo PRIMARY KEY (id_semaforo);


--
-- Name: tag_rfid pk_tag_rfid; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tag_rfid
    ADD CONSTRAINT pk_tag_rfid PRIMARY KEY (id_tag);


--
-- Name: veiculo_emergencia pk_veiculo_emergencia; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.veiculo_emergencia
    ADD CONSTRAINT pk_veiculo_emergencia PRIMARY KEY (id_veiculo);


--
-- Name: dispositivo_iot uq_dispositivo_iot_codigo; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dispositivo_iot
    ADD CONSTRAINT uq_dispositivo_iot_codigo UNIQUE (codigo);


--
-- Name: execucao_simulacao uq_execucao_simulacao_nome_cenario_modo_seed; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execucao_simulacao
    ADD CONSTRAINT uq_execucao_simulacao_nome_cenario_modo_seed UNIQUE (nome_cenario, modo, seed);


--
-- Name: fase_semaforo uq_fase_semaforo_fk_semaforo_indice_fase; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fase_semaforo
    ADD CONSTRAINT uq_fase_semaforo_fk_semaforo_indice_fase UNIQUE (fk_semaforo, indice_fase);


--
-- Name: semaforo uq_semaforo_codigo_externo; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.semaforo
    ADD CONSTRAINT uq_semaforo_codigo_externo UNIQUE (codigo_externo);


--
-- Name: tag_rfid uq_tag_rfid_uid; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tag_rfid
    ADD CONSTRAINT uq_tag_rfid_uid UNIQUE (uid);


--
-- Name: veiculo_emergencia uq_veiculo_emergencia_placa; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.veiculo_emergencia
    ADD CONSTRAINT uq_veiculo_emergencia_placa UNIQUE (placa);


--
-- Name: idx_amostra_exec_t; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_amostra_exec_t ON public.estado_semaforo_amostra USING btree (fk_execucao, t_simulacao);


--
-- Name: idx_deteccao_uid_tempo; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_deteccao_uid_tempo ON public.deteccao USING btree (uid_bruto, recebido_em DESC);


--
-- Name: idx_log_correlacao; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_log_correlacao ON public.log_prioridade USING btree (id_correlacao);


--
-- Name: idx_log_execucao_semaforo; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_log_execucao_semaforo ON public.log_prioridade USING btree (fk_execucao, fk_semaforo);


--
-- Name: idx_log_inicio; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_log_inicio ON public.log_prioridade USING btree (timestamp_inicio DESC);


--
-- Name: idx_metrica_exec; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_metrica_exec ON public.metrica_simulacao USING btree (id_execucao);


--
-- Name: idx_pedido_status_criado; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pedido_status_criado ON public.pedido_simulacao USING btree (status, criado_em);


--
-- Name: uq_ocorrencia_aberta_por_veiculo; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_ocorrencia_aberta_por_veiculo ON public.ocorrencia USING btree (fk_veiculo) WHERE (encerrada_em IS NULL);


--
-- Name: deteccao fk_deteccao_fk_dispositivo; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.deteccao
    ADD CONSTRAINT fk_deteccao_fk_dispositivo FOREIGN KEY (fk_dispositivo) REFERENCES public.dispositivo_iot(id_dispositivo);


--
-- Name: deteccao fk_deteccao_fk_ocorrencia; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.deteccao
    ADD CONSTRAINT fk_deteccao_fk_ocorrencia FOREIGN KEY (fk_ocorrencia) REFERENCES public.ocorrencia(id_ocorrencia);


--
-- Name: deteccao fk_deteccao_fk_veiculo; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.deteccao
    ADD CONSTRAINT fk_deteccao_fk_veiculo FOREIGN KEY (fk_veiculo) REFERENCES public.veiculo_emergencia(id_veiculo);


--
-- Name: dispositivo_iot fk_dispositivo_iot_fk_semaforo; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dispositivo_iot
    ADD CONSTRAINT fk_dispositivo_iot_fk_semaforo FOREIGN KEY (fk_semaforo) REFERENCES public.semaforo(id_semaforo);


--
-- Name: estado_semaforo_amostra fk_estado_semaforo_amostra_fk_execucao; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.estado_semaforo_amostra
    ADD CONSTRAINT fk_estado_semaforo_amostra_fk_execucao FOREIGN KEY (fk_execucao) REFERENCES public.execucao_simulacao(id_execucao) ON DELETE CASCADE;


--
-- Name: estado_semaforo_amostra fk_estado_semaforo_amostra_fk_semaforo; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.estado_semaforo_amostra
    ADD CONSTRAINT fk_estado_semaforo_amostra_fk_semaforo FOREIGN KEY (fk_semaforo) REFERENCES public.semaforo(id_semaforo);


--
-- Name: fase_semaforo fk_fase_semaforo_fk_semaforo; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fase_semaforo
    ADD CONSTRAINT fk_fase_semaforo_fk_semaforo FOREIGN KEY (fk_semaforo) REFERENCES public.semaforo(id_semaforo) ON DELETE CASCADE;


--
-- Name: log_prioridade fk_log_prioridade_fk_execucao; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.log_prioridade
    ADD CONSTRAINT fk_log_prioridade_fk_execucao FOREIGN KEY (fk_execucao) REFERENCES public.execucao_simulacao(id_execucao);


--
-- Name: log_prioridade fk_log_prioridade_fk_metrica; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.log_prioridade
    ADD CONSTRAINT fk_log_prioridade_fk_metrica FOREIGN KEY (fk_metrica) REFERENCES public.metrica_simulacao(id_metrica);


--
-- Name: log_prioridade fk_log_prioridade_fk_semaforo; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.log_prioridade
    ADD CONSTRAINT fk_log_prioridade_fk_semaforo FOREIGN KEY (fk_semaforo) REFERENCES public.semaforo(id_semaforo);


--
-- Name: log_prioridade fk_log_prioridade_fk_veiculo; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.log_prioridade
    ADD CONSTRAINT fk_log_prioridade_fk_veiculo FOREIGN KEY (fk_veiculo) REFERENCES public.veiculo_emergencia(id_veiculo);


--
-- Name: metrica_latencia fk_metrica_latencia_fk_log; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.metrica_latencia
    ADD CONSTRAINT fk_metrica_latencia_fk_log FOREIGN KEY (fk_log) REFERENCES public.log_prioridade(id_log);


--
-- Name: metrica_simulacao fk_metrica_simulacao_id_execucao; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.metrica_simulacao
    ADD CONSTRAINT fk_metrica_simulacao_id_execucao FOREIGN KEY (id_execucao) REFERENCES public.execucao_simulacao(id_execucao) ON DELETE CASCADE;


--
-- Name: metrica_via_transversal fk_metrica_via_transversal_fk_execucao; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.metrica_via_transversal
    ADD CONSTRAINT fk_metrica_via_transversal_fk_execucao FOREIGN KEY (fk_execucao) REFERENCES public.execucao_simulacao(id_execucao) ON DELETE CASCADE;


--
-- Name: metrica_via_transversal fk_metrica_via_transversal_fk_semaforo; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.metrica_via_transversal
    ADD CONSTRAINT fk_metrica_via_transversal_fk_semaforo FOREIGN KEY (fk_semaforo) REFERENCES public.semaforo(id_semaforo);


--
-- Name: ocorrencia fk_ocorrencia_fk_veiculo; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ocorrencia
    ADD CONSTRAINT fk_ocorrencia_fk_veiculo FOREIGN KEY (fk_veiculo) REFERENCES public.veiculo_emergencia(id_veiculo);


--
-- Name: pedido_simulacao fk_pedido_simulacao_fk_execucao; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pedido_simulacao
    ADD CONSTRAINT fk_pedido_simulacao_fk_execucao FOREIGN KEY (fk_execucao) REFERENCES public.execucao_simulacao(id_execucao) ON DELETE SET NULL;


--
-- Name: tag_rfid fk_tag_rfid_fk_veiculo; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tag_rfid
    ADD CONSTRAINT fk_tag_rfid_fk_veiculo FOREIGN KEY (fk_veiculo) REFERENCES public.veiculo_emergencia(id_veiculo) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict pJVPAarVvE8FrPGo8V4bJcF0MtrYHgcCAt9tkJDO4a8DKYsNBqTlDpzDOeub9Kf

