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

from app.models import Base, ModoControle
from db.seeds.carregar import aplicar, carregar_dados, coordenadas_da_grade, resumo

RAIZ = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.banco

TABELAS_ESPERADAS = 14  # 12 do Bloco 1 + `ocorrencia` (P20) + `pedido_simulacao` (Bloco 6)
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


def test_schema_tem_as_14_tabelas_de_context_03(engine: Engine) -> None:
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


def test_modo_controle_tem_os_bracos_do_orm(engine: Engine) -> None:
    """O braço `PREEMPCAO_ML` (10.7) entrou por migration, não só no ORM."""
    consulta = text("SELECT unnest(enum_range(NULL::modo_controle))::text")
    with engine.connect() as conexao:
        no_banco = [linha[0] for linha in conexao.execute(consulta)]
    assert no_banco == [modo.value for modo in ModoControle]


def test_downgrade_do_braco_ml_recusa_apagar_execucao(
    engine: Engine, url_banco_efemero: str
) -> None:
    """Voltar o schema não pode levar execuções do braço junto, em silêncio."""
    configuracao = _configuracao(url_banco_efemero)
    with engine.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO execucao_simulacao "
                "(nome_cenario, modo, seed, duracao_s, arquivo_rede, parametros) "
                "VALUES ('multiplas_emergencias', 'PREEMPCAO_ML', 900, 60, 'teste', '{}')"
            )
        )
    try:
        with pytest.raises(RuntimeError, match="PREEMPCAO_ML"):
            command.downgrade(configuracao, "e5a17c3d8b42")
    finally:
        with engine.begin() as conexao:
            conexao.execute(text("DELETE FROM execucao_simulacao WHERE seed = 900"))

    command.downgrade(configuracao, "e5a17c3d8b42")
    try:
        with engine.connect() as conexao:
            restantes = [
                linha[0]
                for linha in conexao.execute(
                    text("SELECT unnest(enum_range(NULL::modo_controle))::text")
                )
            ]
        assert restantes == ["FIXO", "PREEMPCAO", "PREEMPCAO_COMPENSADA"]
    finally:
        command.upgrade(configuracao, "head")


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

    # 8 TLS da malha + 1 cruzamento do protótipo (UM cruzamento — não quatro
    # semáforos PROTO_S1..S4 — com as 2 fases do ciclo da bancada).
    assert criados["semaforo"] == 9
    assert criados["fase_semaforo"] == 2
    assert criados["veiculo"] == 3
    assert criados["tag"] == 2
    assert criados["dispositivo"] == 3


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


def _verificar_prototipo_da_bancada(sessao: Session) -> None:
    """O cadastro de `context/03` §5 desde 2026-10-05."""
    from app.models import DispositivoIot
    from app.repositories.cadastro import buscar_semaforo_por_codigo, fases_de

    proto = buscar_semaforo_por_codigo(sessao, "PROTO_CRUZ_01")
    assert proto is not None
    assert proto.tempo_ciclo == 12  # 2 x (3 + 2 + 1)

    fases = fases_de(sessao, proto.id_semaforo)
    assert [f.indice_fase for f in fases] == [1, 2]
    assert [sorted(f.movimentos) for f in fases] == [
        ["PRINCIPAL_A", "PRINCIPAL_B"],
        ["TRANSVERSAL_A", "TRANSVERSAL_B"],
    ]
    assert [f.descricao for f in fases] == ["Eixo principal (S1+S2)", "Eixo transversal (S3+S4)"]
    # verde_s == verde_min_s: na bancada a preempção nunca trunca verde.
    assert all(f.duracao_base == f.verde_min == 3 for f in fases)

    assert buscar_semaforo_por_codigo(sessao, "PROTO_S1") is None

    dispositivos = {d.codigo: d for d in sessao.query(DispositivoIot).all()}
    assert set(dispositivos) == {"EMISSOR_VE_01", "RECEPTOR_CRUZ_01", "CTRL_PROTO_01"}
    # O emissor vai no veículo; os outros dois ficam no cruzamento.
    assert dispositivos["EMISSOR_VE_01"].fk_semaforo is None
    assert dispositivos["RECEPTOR_CRUZ_01"].fk_semaforo == proto.id_semaforo
    assert dispositivos["CTRL_PROTO_01"].fk_semaforo == proto.id_semaforo


def test_prototipo_tem_um_cruzamento_com_duas_fases_e_tres_placas(sessao: Session) -> None:
    """A bancada como está montada (decisão de 2026-10-05), verificada no dado."""
    aplicar(sessao, carregar_dados())
    sessao.commit()
    _verificar_prototipo_da_bancada(sessao)


def test_tags_da_bancada_nao_entram_em_tag_rfid(sessao: Session) -> None:
    """As tags reais identificam ruas, não veículos (`context/05` §1)."""
    from app.models import TagRfid

    aplicar(sessao, carregar_dados())
    sessao.commit()

    uids = {tag.uid for tag in sessao.query(TagRfid).all()}
    assert uids.isdisjoint({"F39BD606", "1BD2308E", "B7EF8FA0", "97ABAFA0"})


def test_banco_semeado_antes_de_2026_10_05_e_corrigido_pela_migration(
    sessao: Session, url_banco_efemero: str
) -> None:
    """Os seeds não apagam nada; quem leva o banco antigo ao desenho novo é a migration."""
    configuracao = _configuracao(url_banco_efemero)
    command.downgrade(configuracao, "3f9c2a71d5e8")

    # O cadastro como era: split phasing de P13 e o leitor no cruzamento.
    antigos = carregar_dados()
    antigos["prototipo"]["semaforo"]["tempo_ciclo"] = 24
    antigos["prototipo"]["fases"] = [
        {
            "indice_fase": i,
            "descricao": f"Aproximação S{i}",
            "movimentos": [f"M{i}"],
            "modulos": f"S{i}",
        }
        for i in range(1, 5)
    ]
    antigos["dispositivos"] = [
        {
            "codigo": "LEITOR_CRUZ_01",
            "tipo": "LEITOR_RFID",
            "semaforo": "PROTO_CRUZ_01",
            "token_dev": "x",
        },
        {
            "codigo": "CTRL_PROTO_01",
            "tipo": "CONTROLADOR_SEMAFORO",
            "semaforo": "PROTO_CRUZ_01",
            "token_dev": "y",
        },
    ]
    aplicar(sessao, antigos)
    sessao.commit()
    sessao.close()

    command.upgrade(configuracao, "head")
    aplicar(sessao, carregar_dados())
    sessao.commit()

    _verificar_prototipo_da_bancada(sessao)
