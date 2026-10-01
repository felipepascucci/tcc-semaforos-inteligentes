"""Migrations e seeds contra um banco de verdade.

O ciclo `upgrade → downgrade → upgrade` é o teste que pega a classe de erro mais
comum em migration de Postgres com ENUM: o `DROP TABLE` não remove o tipo, e o
segundo `upgrade` morre no `CREATE TYPE`.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.models import Base
from db.seeds.carregar import aplicar, carregar_dados, coordenadas_da_grade, resumo

RAIZ = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.banco

TABELAS_ESPERADAS = 13  # 12 do Bloco 1 + `ocorrencia` (P20)
ENUMS_ESPERADOS = {
    "estado_sinal",
    "tipo_veiculo",
    "status_operacao",
    "status_execucao",
    "modo_controle",
}
INDICES_ESPERADOS = {
    "idx_log_correlacao",
    "idx_log_execucao_semaforo",
    "idx_log_inicio",
    "idx_amostra_exec_t",
    "idx_deteccao_uid_tempo",
    "idx_metrica_exec",
    "uq_ocorrencia_aberta_por_veiculo",
}


def _configuracao(url: str) -> Config:
    configuracao = Config(str(RAIZ / "alembic.ini"))
    configuracao.set_main_option("script_location", str(RAIZ / "db" / "migrations"))
    os.environ["ALEMBIC_DATABASE_URL"] = url
    return configuracao


def test_schema_tem_as_13_tabelas_de_context_03(engine: Engine) -> None:
    consulta = text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
    )
    with engine.connect() as conexao:
        no_banco = {linha[0] for linha in conexao.execute(consulta)}

    assert len(no_banco) == TABELAS_ESPERADAS
    assert no_banco == set(Base.metadata.tables)


def test_os_cinco_enums_nativos_existem(engine: Engine) -> None:
    consulta = text("SELECT typname FROM pg_type WHERE typtype = 'e'")
    with engine.connect() as conexao:
        assert {linha[0] for linha in conexao.execute(consulta)} == ENUMS_ESPERADOS


def test_indices_de_context_03_secao_3_3(engine: Engine) -> None:
    consulta = text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
    with engine.connect() as conexao:
        no_banco = {linha[0] for linha in conexao.execute(consulta)}
    assert no_banco >= INDICES_ESPERADOS


def test_correcoes_de_p4_estao_no_banco(engine: Engine) -> None:
    """As três correções obrigatórias de P4, verificadas no schema real."""
    consulta = text(
        "SELECT table_name, column_name, numeric_precision, numeric_scale "
        "FROM information_schema.columns WHERE table_schema = 'public'"
    )
    with engine.connect() as conexao:
        colunas = {
            (linha[0], linha[1]): (linha[2], linha[3]) for linha in conexao.execute(consulta)
        }

    # longitude precisa de 3 dígitos inteiros: -46,63 não cabe em (10,8).
    assert colunas[("semaforo", "longitude")] == (11, 8)
    assert colunas[("semaforo", "latitude")] == (10, 8)
    # 999,99 é apertado demais para cenário intenso.
    assert colunas[("metrica_simulacao", "tempo_medio_resposta")] == (8, 2)
    # fk_metrica estava só no §4.2 do pré-projeto; P4 unificou incluindo.
    assert ("log_prioridade", "fk_metrica") in colunas


def test_estado_semaforo_amostra_esta_na_forma_de_p5(engine: Engine) -> None:
    """P5: a tabela guarda transições, e por isso tem os campos da fase anterior."""
    consulta = text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'estado_semaforo_amostra'"
    )
    with engine.connect() as conexao:
        colunas = {linha[0] for linha in conexao.execute(consulta)}

    assert {"fase_anterior", "duracao_fase_anterior_s", "t_simulacao"} <= colunas


def test_ciclo_upgrade_downgrade_upgrade(engine: Engine, url_banco_efemero: str) -> None:
    """Os tipos ENUM sobrevivem ao DROP TABLE; o downgrade precisa removê-los."""
    configuracao = _configuracao(url_banco_efemero)

    tipos_enum = text("SELECT typname FROM pg_type WHERE typtype = 'e'")

    command.downgrade(configuracao, "base")
    with engine.connect() as conexao:
        restantes = {linha[0] for linha in conexao.execute(tipos_enum)}
    assert restantes & ENUMS_ESPERADOS == set(), "tipos ENUM sobraram após o downgrade"

    command.upgrade(configuracao, "head")
    with engine.connect() as conexao:
        consulta = text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
        )
        assert conexao.execute(consulta).scalar_one() == TABELAS_ESPERADAS


# --- seeds ------------------------------------------------------------------


def test_grade_da_malha_respeita_o_espacamento_declarado() -> None:
    """500 m entre cruzamentos consecutivos, com a convergência dos meridianos.

    Ignorar o cosseno da latitude deformaria a grade em ~8% em São Paulo.
    """
    malha = carregar_dados()["malha_sumo"]
    cruzamentos = coordenadas_da_grade(malha)

    assert len(cruzamentos) == malha["linhas"] * malha["colunas"] == 8
    assert [c[0] for c in cruzamentos][:2] == ["CRUZ_01", "CRUZ_02"]

    metros_por_grau_lat = 111_320.0
    passo_lat = abs(float(cruzamentos[4][2]) - float(cruzamentos[0][2])) * metros_por_grau_lat
    assert passo_lat == pytest.approx(malha["espacamento_m"], rel=0.01)


def test_seeds_criam_o_cadastro_de_context_03_secao_5(sessao: Session) -> None:
    criados = aplicar(sessao, carregar_dados())
    sessao.commit()

    # 8 TLS da malha + 1 cruzamento do protótipo (P13: UM cruzamento, 4 fases —
    # não quatro semáforos PROTO_S1..S4).
    assert criados["semaforo"] == 9
    assert criados["fase_semaforo"] == 4
    assert criados["veiculo"] == 3
    assert criados["tag"] == 2
    assert criados["dispositivo"] == 2


def test_seeds_sao_idempotentes(sessao: Session) -> None:
    dados = carregar_dados()
    aplicar(sessao, dados)
    sessao.commit()
    antes = resumo(sessao)

    criados = aplicar(sessao, dados)
    sessao.commit()

    assert sum(criados.values()) == 0
    assert resumo(sessao) == antes


def test_tags_placeholder_nao_autorizam_preempcao(sessao: Session) -> None:
    """Uma tag placeholder ativa seria uma credencial válida pública."""
    from app.models import TagRfid

    aplicar(sessao, carregar_dados())
    sessao.commit()

    for tag in sessao.query(TagRfid).all():
        assert tag.uid.startswith("PLACEHOLDER")
        assert tag.ativo is False


def test_prototipo_tem_um_cruzamento_com_quatro_fases(sessao: Session) -> None:
    """A correção de P13 em context/03 §5, verificada no dado."""
    from app.repositories.cadastro import buscar_semaforo_por_codigo, fases_de

    aplicar(sessao, carregar_dados())
    sessao.commit()

    proto = buscar_semaforo_por_codigo(sessao, "PROTO_CRUZ_01")
    assert proto is not None
    assert proto.tempo_ciclo == 24  # 4 x (3 + 2 + 1)

    fases = fases_de(sessao, proto.id_semaforo)
    assert [f.indice_fase for f in fases] == [1, 2, 3, 4]
    # Sob split phasing cada fase serve uma única aproximação.
    assert all(len(f.movimentos) == 1 for f in fases)
    # verde_s == verde_min_s: na bancada a preempção nunca trunca verde.
    assert all(f.duracao_base == f.verde_min == 3 for f in fases)

    assert buscar_semaforo_por_codigo(sessao, "PROTO_S1") is None
