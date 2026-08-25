"""schema inicial das 12 tabelas

As 12 tabelas de `context/03` §3, com as três correções obrigatórias de P4 já
aplicadas: `longitude` em `DECIMAL(11,8)` (que comporta -46,63 de São Paulo),
`metrica_simulacao.tempo_medio_resposta` em `DECIMAL(8,2)`, e
`log_prioridade.fk_metrica` presente.

`estado_semaforo_amostra` está na forma da decisão P5 — grava **transições** de
fase, não amostras periódicas.

Revision ID: eb4834072797
Revises:
Create Date: 2026-08-24 22:55:33.398339
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "eb4834072797"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Os cinco ENUM nativos de context/03 §3.1.
#
# `create_type=False` é essencial: sem ele o SQLAlchemy emite um CREATE TYPE
# junto de cada CREATE TABLE que usa o tipo, e `status_operacao` aparece em três
# tabelas (semaforo, veiculo_emergencia, dispositivo_iot). O segundo CREATE
# aborta a migration com "type already exists". Os tipos são criados uma única
# vez, explicitamente, no início de upgrade().
ESTADO_SINAL = postgresql.ENUM(
    "VERDE", "AMARELO", "VERMELHO", name="estado_sinal", create_type=False
)
TIPO_VEICULO = postgresql.ENUM(
    "AMBULANCIA", "BOMBEIRO", "POLICIA", name="tipo_veiculo", create_type=False
)
STATUS_OPERACAO = postgresql.ENUM(
    "ATIVO", "INATIVO", "MANUTENCAO", "FALHA", name="status_operacao", create_type=False
)
STATUS_EXECUCAO = postgresql.ENUM(
    "SUCESSO",
    "FALHA",
    "TIMEOUT",
    "CONFLITO_ADIADO",
    "ABORTADO_SEGURANCA",
    name="status_execucao",
    create_type=False,
)
MODO_CONTROLE = postgresql.ENUM(
    "FIXO", "PREEMPCAO", "PREEMPCAO_COMPENSADA", name="modo_controle", create_type=False
)

TIPOS_ENUM = (ESTADO_SINAL, TIPO_VEICULO, STATUS_OPERACAO, STATUS_EXECUCAO, MODO_CONTROLE)


def upgrade() -> None:
    vinculo = op.get_bind()
    for tipo in TIPOS_ENUM:
        tipo.create(vinculo, checkfirst=True)

    op.create_table(
        "execucao_simulacao",
        sa.Column("id_execucao", sa.Integer(), nullable=False),
        sa.Column("nome_cenario", sa.String(length=50), nullable=False),
        sa.Column("modo", MODO_CONTROLE, nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("duracao_s", sa.Integer(), nullable=False),
        sa.Column("arquivo_rede", sa.String(length=120), nullable=False),
        sa.Column("versao_codigo", sa.String(length=40), nullable=True),
        sa.Column("parametros", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("exemplar", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "iniciada_em",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finalizada_em", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id_execucao", name=op.f("pk_execucao_simulacao")),
        sa.UniqueConstraint(
            "nome_cenario",
            "modo",
            "seed",
            name=op.f("uq_execucao_simulacao_nome_cenario_modo_seed"),
        ),
    )
    op.create_table(
        "semaforo",
        sa.Column("id_semaforo", sa.Integer(), nullable=False),
        sa.Column("codigo_externo", sa.String(length=50), nullable=False),
        sa.Column("descricao", sa.String(length=120), nullable=True),
        sa.Column("latitude", sa.Numeric(precision=10, scale=8), nullable=False),
        sa.Column("longitude", sa.Numeric(precision=11, scale=8), nullable=False),
        sa.Column("estado_atual", ESTADO_SINAL, server_default="VERMELHO", nullable=False),
        sa.Column("tempo_ciclo", sa.Integer(), nullable=False),
        sa.Column("status_operacao", STATUS_OPERACAO, server_default="ATIVO", nullable=False),
        sa.Column(
            "atualizado_em",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "criado_em",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id_semaforo", name=op.f("pk_semaforo")),
        sa.UniqueConstraint("codigo_externo", name=op.f("uq_semaforo_codigo_externo")),
    )
    op.create_table(
        "veiculo_emergencia",
        sa.Column("id_veiculo", sa.Integer(), nullable=False),
        sa.Column("placa", sa.String(length=7), nullable=False),
        sa.Column("tipo", TIPO_VEICULO, nullable=False),
        sa.Column("identificacao", sa.String(length=60), nullable=True),
        sa.Column("status_operacional", STATUS_OPERACAO, server_default="ATIVO", nullable=False),
        sa.Column(
            "criado_em",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id_veiculo", name=op.f("pk_veiculo_emergencia")),
        sa.UniqueConstraint("placa", name=op.f("uq_veiculo_emergencia_placa")),
    )
    op.create_table(
        "dispositivo_iot",
        sa.Column("id_dispositivo", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=50), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("fk_semaforo", sa.Integer(), nullable=True),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("ultimo_contato", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("firmware_versao", sa.String(length=20), nullable=True),
        sa.Column("status", STATUS_OPERACAO, server_default="ATIVO", nullable=False),
        sa.ForeignKeyConstraint(
            ["fk_semaforo"], ["semaforo.id_semaforo"], name=op.f("fk_dispositivo_iot_fk_semaforo")
        ),
        sa.PrimaryKeyConstraint("id_dispositivo", name=op.f("pk_dispositivo_iot")),
        sa.UniqueConstraint("codigo", name=op.f("uq_dispositivo_iot_codigo")),
    )
    op.create_table(
        "estado_semaforo_amostra",
        sa.Column("id_amostra", sa.BigInteger(), nullable=False),
        sa.Column("fk_execucao", sa.Integer(), nullable=False),
        sa.Column("fk_semaforo", sa.Integer(), nullable=False),
        sa.Column("t_simulacao", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("fase_anterior", sa.Integer(), nullable=True),
        sa.Column("fase", sa.Integer(), nullable=False),
        sa.Column("estado", ESTADO_SINAL, nullable=False),
        sa.Column("em_preempcao", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("fila_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duracao_fase_anterior_s", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.ForeignKeyConstraint(
            ["fk_execucao"],
            ["execucao_simulacao.id_execucao"],
            name=op.f("fk_estado_semaforo_amostra_fk_execucao"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["fk_semaforo"],
            ["semaforo.id_semaforo"],
            name=op.f("fk_estado_semaforo_amostra_fk_semaforo"),
        ),
        sa.PrimaryKeyConstraint("id_amostra", name=op.f("pk_estado_semaforo_amostra")),
    )
    op.create_index(
        "idx_amostra_exec_t",
        "estado_semaforo_amostra",
        ["fk_execucao", "t_simulacao"],
        unique=False,
    )
    op.create_table(
        "fase_semaforo",
        sa.Column("id_fase", sa.Integer(), nullable=False),
        sa.Column("fk_semaforo", sa.Integer(), nullable=False),
        sa.Column("indice_fase", sa.Integer(), nullable=False),
        sa.Column("descricao", sa.String(length=80), nullable=False),
        sa.Column("movimentos", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("duracao_base", sa.Integer(), nullable=False),
        sa.Column("verde_min", sa.Integer(), server_default="7", nullable=False),
        sa.Column("verde_max", sa.Integer(), server_default="60", nullable=False),
        sa.ForeignKeyConstraint(
            ["fk_semaforo"],
            ["semaforo.id_semaforo"],
            name=op.f("fk_fase_semaforo_fk_semaforo"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id_fase", name=op.f("pk_fase_semaforo")),
        sa.UniqueConstraint(
            "fk_semaforo", "indice_fase", name=op.f("uq_fase_semaforo_fk_semaforo_indice_fase")
        ),
    )
    op.create_table(
        "metrica_simulacao",
        sa.Column("id_metrica", sa.Integer(), nullable=False),
        sa.Column("id_execucao", sa.Integer(), nullable=True),
        sa.Column("tempo_medio_resposta", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("tempo_espera", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("percentual_reducao", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("latencia_ia", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("cenario_simulado", sa.String(length=50), nullable=False),
        sa.Column(
            "criado_em",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["id_execucao"],
            ["execucao_simulacao.id_execucao"],
            name=op.f("fk_metrica_simulacao_id_execucao"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id_metrica", name=op.f("pk_metrica_simulacao")),
    )
    op.create_index("idx_metrica_exec", "metrica_simulacao", ["id_execucao"], unique=False)
    op.create_table(
        "metrica_via_transversal",
        sa.Column("id_metrica_tv", sa.Integer(), nullable=False),
        sa.Column("fk_execucao", sa.Integer(), nullable=False),
        sa.Column("fk_semaforo", sa.Integer(), nullable=False),
        sa.Column("tempo_espera_medio", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("fila_maxima", sa.Integer(), nullable=False),
        sa.Column("veiculos_processados", sa.Integer(), nullable=False),
        sa.Column("janela", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(
            ["fk_execucao"],
            ["execucao_simulacao.id_execucao"],
            name=op.f("fk_metrica_via_transversal_fk_execucao"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["fk_semaforo"],
            ["semaforo.id_semaforo"],
            name=op.f("fk_metrica_via_transversal_fk_semaforo"),
        ),
        sa.PrimaryKeyConstraint("id_metrica_tv", name=op.f("pk_metrica_via_transversal")),
    )
    op.create_table(
        "tag_rfid",
        sa.Column("id_tag", sa.Integer(), nullable=False),
        sa.Column("uid", sa.String(length=32), nullable=False),
        sa.Column("fk_veiculo", sa.Integer(), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "criado_em",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["fk_veiculo"],
            ["veiculo_emergencia.id_veiculo"],
            name=op.f("fk_tag_rfid_fk_veiculo"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id_tag", name=op.f("pk_tag_rfid")),
        sa.UniqueConstraint("uid", name=op.f("uq_tag_rfid_uid")),
    )
    op.create_table(
        "deteccao",
        sa.Column("id_deteccao", sa.BigInteger(), nullable=False),
        sa.Column("id_correlacao", sa.UUID(), nullable=False),
        sa.Column("origem", sa.String(length=20), nullable=False),
        sa.Column("fk_dispositivo", sa.Integer(), nullable=True),
        sa.Column("fk_veiculo", sa.Integer(), nullable=True),
        sa.Column("uid_bruto", sa.String(length=32), nullable=True),
        sa.Column("reconhecido", sa.Boolean(), nullable=False),
        sa.Column("rssi", sa.SmallInteger(), nullable=True),
        sa.Column("sequencia", sa.Integer(), nullable=True),
        sa.Column(
            "recebido_em",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["fk_dispositivo"],
            ["dispositivo_iot.id_dispositivo"],
            name=op.f("fk_deteccao_fk_dispositivo"),
        ),
        sa.ForeignKeyConstraint(
            ["fk_veiculo"], ["veiculo_emergencia.id_veiculo"], name=op.f("fk_deteccao_fk_veiculo")
        ),
        sa.PrimaryKeyConstraint("id_deteccao", name=op.f("pk_deteccao")),
    )
    op.create_index(
        "idx_deteccao_uid_tempo",
        "deteccao",
        ["uid_bruto", sa.literal_column("recebido_em DESC")],
        unique=False,
    )
    op.create_table(
        "log_prioridade",
        sa.Column("id_log", sa.Integer(), nullable=False),
        sa.Column("fk_veiculo", sa.Integer(), nullable=True),
        sa.Column("fk_semaforo", sa.Integer(), nullable=False),
        sa.Column("fk_metrica", sa.Integer(), nullable=True),
        sa.Column("fk_execucao", sa.Integer(), nullable=True),
        sa.Column("id_correlacao", sa.UUID(), nullable=False),
        sa.Column("timestamp_inicio", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("timestamp_fim", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("ganho_tempo_segundos", sa.Integer(), nullable=True),
        sa.Column("status_execucao", STATUS_EXECUCAO, nullable=False),
        sa.Column("motivo", sa.String(length=200), nullable=True),
        sa.Column("fase_anterior", sa.Integer(), nullable=True),
        sa.Column("fase_aplicada", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["fk_execucao"],
            ["execucao_simulacao.id_execucao"],
            name=op.f("fk_log_prioridade_fk_execucao"),
        ),
        sa.ForeignKeyConstraint(
            ["fk_metrica"],
            ["metrica_simulacao.id_metrica"],
            name=op.f("fk_log_prioridade_fk_metrica"),
        ),
        sa.ForeignKeyConstraint(
            ["fk_semaforo"], ["semaforo.id_semaforo"], name=op.f("fk_log_prioridade_fk_semaforo")
        ),
        sa.ForeignKeyConstraint(
            ["fk_veiculo"],
            ["veiculo_emergencia.id_veiculo"],
            name=op.f("fk_log_prioridade_fk_veiculo"),
        ),
        sa.PrimaryKeyConstraint("id_log", name=op.f("pk_log_prioridade")),
    )
    op.create_index("idx_log_correlacao", "log_prioridade", ["id_correlacao"], unique=False)
    op.create_index(
        "idx_log_execucao_semaforo", "log_prioridade", ["fk_execucao", "fk_semaforo"], unique=False
    )
    op.create_index(
        "idx_log_inicio",
        "log_prioridade",
        [sa.literal_column("timestamp_inicio DESC")],
        unique=False,
    )
    op.create_table(
        "metrica_latencia",
        sa.Column("id_latencia", sa.BigInteger(), nullable=False),
        sa.Column("id_correlacao", sa.UUID(), nullable=False),
        sa.Column("fk_log", sa.Integer(), nullable=True),
        sa.Column("t_deteccao", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("t_decisao", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("t_atuacao", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "latencia_decisao_ms",
            sa.Integer(),
            sa.Computed(
                "(EXTRACT(EPOCH FROM (t_decisao - t_deteccao)) * 1000)::INT", persisted=True
            ),
            nullable=False,
        ),
        sa.Column("latencia_total_ms", sa.Integer(), nullable=True),
        sa.Column("ambiente", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(
            ["fk_log"], ["log_prioridade.id_log"], name=op.f("fk_metrica_latencia_fk_log")
        ),
        sa.PrimaryKeyConstraint("id_latencia", name=op.f("pk_metrica_latencia")),
    )


def downgrade() -> None:
    op.drop_table("metrica_latencia")
    op.drop_index("idx_log_inicio", table_name="log_prioridade")
    op.drop_index("idx_log_execucao_semaforo", table_name="log_prioridade")
    op.drop_index("idx_log_correlacao", table_name="log_prioridade")
    op.drop_table("log_prioridade")
    op.drop_index("idx_deteccao_uid_tempo", table_name="deteccao")
    op.drop_table("deteccao")
    op.drop_table("tag_rfid")
    op.drop_table("metrica_via_transversal")
    op.drop_index("idx_metrica_exec", table_name="metrica_simulacao")
    op.drop_table("metrica_simulacao")
    op.drop_table("fase_semaforo")
    op.drop_index("idx_amostra_exec_t", table_name="estado_semaforo_amostra")
    op.drop_table("estado_semaforo_amostra")
    op.drop_table("dispositivo_iot")
    op.drop_table("veiculo_emergencia")
    op.drop_table("semaforo")
    op.drop_table("execucao_simulacao")

    # Os tipos ENUM sobrevivem ao DROP TABLE. Sem removê-los aqui, um
    # `downgrade base` seguido de `upgrade head` falharia no CREATE TYPE — e o
    # ciclo completo é justamente o que o teste de migrations exercita.
    vinculo = op.get_bind()
    for tipo in reversed(TIPOS_ENUM):
        tipo.drop(vinculo, checkfirst=True)
