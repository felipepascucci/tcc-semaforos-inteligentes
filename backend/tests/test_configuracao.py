"""Carga dos parâmetros — `adapters/configuracao.py` sobre os YAML reais.

`backend/tests/test_parametros.py` confere os **valores** dos arquivos contra
`context/01` §5.3. Aqui se confere o **caminho de carga**: que os arquivos de
verdade atravessam `Parametros.de_dicionario()` sem quebrar, que a sobreposição
do perfil de bancada funciona, e que configuração incoerente falha na carga em
vez de falhar no meio das 600 execuções.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from adapters import configuracao
from core.excecoes import ConfiguracaoInvalidaError
from core.modelos import TipoVeiculo
from core.parametros import Parametros

DIRETORIO_REAL = Path(__file__).resolve().parents[1] / "config"


# ---------------------------------------------------------------------------
# Os arquivos de verdade
# ---------------------------------------------------------------------------


def test_perfil_de_simulacao_carrega_e_valida() -> None:
    """O `parametros.yaml` que alimenta os dados estatísticos precisa carregar."""
    parametros = configuracao.carregar("simulacao")

    assert isinstance(parametros, Parametros)
    assert parametros.raio_deteccao_m == 500.0
    assert parametros.verde_min_s == 7.0
    assert parametros.prioridade_tipo == (
        TipoVeiculo.AMBULANCIA,
        TipoVeiculo.BOMBEIRO,
        TipoVeiculo.POLICIA,
    )


def test_perfil_de_hardware_sobrepoe_apenas_o_que_muda() -> None:
    """A bancada herda o resto do perfil de simulação.

    Manter os dois arquivos completos convidaria à divergência silenciosa:
    alguém mudaria `raio_deteccao_m` num e esqueceria o outro.
    """
    simulacao = configuracao.carregar("simulacao")
    hardware = configuracao.carregar("hardware")

    # O que muda na bancada:
    assert (hardware.verde_min_s, hardware.amarelo_s, hardware.all_red_s) == (3.0, 2.0, 1.0)
    assert hardware.preempcao_timeout_s == 30.0

    # O que é herdado:
    assert hardware.raio_deteccao_m == simulacao.raio_deteccao_m
    assert hardware.ganho_compensacao_k == simulacao.ganho_compensacao_k
    assert hardware.prioridade_tipo == simulacao.prioridade_tipo


def test_carregar_hardware_nao_altera_o_perfil_de_simulacao() -> None:
    """`parametros.yaml` produz os dados do capítulo 5 e não pode ser contaminado."""
    antes = configuracao.carregar("simulacao")
    configuracao.carregar("hardware")
    depois = configuracao.carregar("simulacao")

    assert antes == depois
    assert depois.verde_min_s == 7.0  # e não 3.0, da bancada


def test_ciclo_da_bancada_bate_com_a_decisao_de_2026_10_05() -> None:
    """2 fases x (3 + 2 + 1) = 12 s, calculado a partir do que foi carregado."""
    hardware = configuracao.carregar("hardware")
    dados = configuracao.carregar_dicionario("hardware")

    por_fase = dados["verde_s"] + hardware.amarelo_s + hardware.all_red_s
    assert dados["n_fases_prototipo"] * por_fase == 12.0


def test_bancada_nunca_trunca_verde() -> None:
    """`verde_s == verde_min_s` é o que dispensa o truncamento no firmware."""
    dados = configuracao.carregar_dicionario("hardware")
    assert dados["verde_s"] == configuracao.carregar("hardware").verde_min_s


# ---------------------------------------------------------------------------
# Seleção de perfil
# ---------------------------------------------------------------------------


def test_perfil_vem_da_variavel_de_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERFIL_PARAMETROS", "hardware")
    assert configuracao.carregar().verde_min_s == 3.0


def test_perfil_padrao_e_simulacao(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PERFIL_PARAMETROS", raising=False)
    assert configuracao.carregar().verde_min_s == 7.0


def test_perfil_desconhecido_falha_com_mensagem_util(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERFIL_PARAMETROS", "producao")
    with pytest.raises(ConfiguracaoInvalidaError, match="perfil desconhecido"):
        configuracao.carregar()


def test_arquivo_ausente_falha_na_carga(tmp_path: Path) -> None:
    with pytest.raises(ConfiguracaoInvalidaError, match="não encontrado"):
        configuracao.carregar("simulacao", diretorio=tmp_path)


# ---------------------------------------------------------------------------
# Snapshot para `execucao_simulacao.parametros`
# ---------------------------------------------------------------------------


def test_snapshot_e_serializavel_e_completo() -> None:
    """Sem o snapshot não há reprodutibilidade (`context/03` §4.3).

    O valor vai para uma coluna JSONB, então precisa sobreviver a uma ida e
    volta por JSON — um `Decimal` ou um `date` solto no YAML quebraria a
    gravação no meio da execução, e não na hora de carregar.
    """
    import json

    instantaneo = configuracao.snapshot("simulacao")
    devolta = json.loads(json.dumps(instantaneo))

    assert devolta["raio_deteccao_m"] == 500
    assert devolta["ganho_compensacao_k"] == 1.0
    assert devolta["prioridade_tipo"] == ["AMBULANCIA", "BOMBEIRO", "POLICIA"]


# ---------------------------------------------------------------------------
# Validação: falhar cedo, não no meio das 600 execuções
# ---------------------------------------------------------------------------


def _escrever(diretorio: Path, **alteracoes: object) -> Path:
    with (DIRETORIO_REAL / "parametros.yaml").open(encoding="utf-8") as arquivo:
        dados = yaml.safe_load(arquivo)
    dados.update(alteracoes)
    destino = diretorio / "parametros.yaml"
    destino.write_text(yaml.safe_dump(dados), encoding="utf-8")
    return diretorio


@pytest.mark.parametrize(
    ("alteracao", "trecho_esperado"),
    [
        ({"verde_min_s": 90.0}, "maior que verde_max_s"),
        ({"amarelo_s": 0.0}, "I2 exige amarelo"),
        ({"velocidade_min_estimativa_ms": 0.0}, "divisor do ETA"),
        ({"raio_deteccao_m": 0}, "raio_deteccao_m"),
        ({"vermelho_max_s": 10.0}, "I5 é violável por construção"),
        ({"prioridade_tipo": ["AMBULANCIA", "AMBULANCIA"]}, "tipo repetido"),
        ({"prioridade_tipo": ["HELICOPTERO"]}, "tipo de veículo desconhecido"),
        ({"ganho_compensacao_k": -0.5}, "ganho_compensacao_k não pode ser negativo"),
    ],
)
def test_configuracao_incoerente_falha_na_carga(
    tmp_path: Path, alteracao: dict[str, object], trecho_esperado: str
) -> None:
    """Falhar aqui é barato; falhar no meio de 600 execuções não é."""
    with pytest.raises(ConfiguracaoInvalidaError, match=trecho_esperado):
        configuracao.carregar("simulacao", diretorio=_escrever(tmp_path, **alteracao))


def test_parametro_obrigatorio_ausente_e_apontado_pelo_nome(tmp_path: Path) -> None:
    """A mensagem precisa dizer *qual* chave falta, não só que algo faltou."""
    with (DIRETORIO_REAL / "parametros.yaml").open(encoding="utf-8") as arquivo:
        dados = yaml.safe_load(arquivo)
    del dados["ganho_compensacao_k"]
    (tmp_path / "parametros.yaml").write_text(yaml.safe_dump(dados), encoding="utf-8")

    with pytest.raises(ConfiguracaoInvalidaError, match="ganho_compensacao_k"):
        configuracao.carregar("simulacao", diretorio=tmp_path)


# ---------------------------------------------------------------------------
# Pesos da política de desempate de P19 (entrega 10.6)
# ---------------------------------------------------------------------------


def test_pesos_da_politica_carregam_do_arquivo_versionado() -> None:
    """Os números que o núcleo recebe são os do YAML, na ordem do treino."""
    with (DIRETORIO_REAL / configuracao.ARQUIVO_POLITICA).open(encoding="utf-8") as arquivo:
        dados = yaml.safe_load(arquivo)

    pesos = configuracao.carregar_politica()

    assert pesos.vetor() == tuple(dados["pesos"][nome] for nome in dados["atributos"])


def test_pesos_da_politica_ausentes_falham_na_carga(tmp_path: Path) -> None:
    with pytest.raises(ConfiguracaoInvalidaError, match="não encontrado"):
        configuracao.carregar_politica(diretorio=tmp_path)


@pytest.mark.parametrize(
    ("conteudo", "trecho"),
    [
        ({"atributos": ["eta_s"]}, "não traz"),
        ({"pesos": {"eta_s": 1.0}}, "não traz"),
        (
            {
                "atributos": ["eta_s", "velocidade_ms", "fila_no_acesso", "cruzamentos_restantes"],
                "pesos": {
                    "eta_s": 0.0,
                    "velocidade_ms": 0.0,
                    "fila_no_acesso": 0.0,
                    "cruzamentos_restantes": 0.0,
                },
            },
            "diferem",
        ),
    ],
    ids=["sem-pesos", "sem-atributos", "outro-desenho"],
)
def test_pesos_da_politica_de_outro_formato_falham_na_carga(
    tmp_path: Path, conteudo: dict[str, object], trecho: str
) -> None:
    (tmp_path / configuracao.ARQUIVO_POLITICA).write_text(
        yaml.safe_dump(conteudo), encoding="utf-8"
    )

    with pytest.raises(ConfiguracaoInvalidaError, match=trecho):
        configuracao.carregar_politica(diretorio=tmp_path)
