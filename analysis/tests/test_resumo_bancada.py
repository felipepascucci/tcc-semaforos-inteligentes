"""Resumo de RNF05 e H3 — `analysis/resumo_bancada.py`.

Os CSV daqui são escritos pelos gravadores da própria ponte, com instantes
fixos escritos à mão: testam a conta, não medem nada.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from analysis.resumo_bancada import gerar_relatorio, ler_amostras, ler_leituras, main
from bridge.latencia import (
    DecisaoCarimbada,
    Desfecho,
    GravadorCsv,
    GravadorDesfechos,
    LeituraCarimbada,
)
from bridge.protocolo import Evento, LeituraVeiculo, TipoEvento
from core.modelos import TipoVeiculo

T0 = datetime(2026, 10, 7, 14, 0, tzinfo=UTC)
UID_DA_RUA = {1: "F39BD606", 2: "1BD2308E", 3: "B7EF8FA0", 4: "97ABAFA0"}


def _medir(pasta: Path, sessao: datetime, passagens: list[tuple[TipoEvento | None, float]]) -> None:
    """Grava as passagens como a ponte gravaria: (decisão ou None, latência em ms)."""
    h3 = GravadorCsv(pasta / "latencia.csv", sessao=sessao, versao_codigo="abc1234")
    todas = GravadorDesfechos(pasta / "deteccoes.csv", sessao=sessao, versao_codigo="abc1234")
    for i, (tipo, latencia_ms) in enumerate(passagens):
        rua = i % 4 + 1
        t = sessao + timedelta(seconds=20 * i)
        leitura = LeituraCarimbada(t, LeituraVeiculo(UID_DA_RUA[rua], rua))
        decisao = (
            None
            if tipo is None
            else DecisaoCarimbada(
                t + timedelta(milliseconds=latencia_ms),
                Evento(i, tipo, rua, TipoVeiculo.AMBULANCIA),
            )
        )
        desfecho = Desfecho(leitura, decisao)
        todas.gravar(desfecho)
        if (amostra := desfecho.amostra) is not None:
            h3.gravar(amostra)


def _relatorio(pasta: Path, *sessoes: datetime) -> str:
    return gerar_relatorio(
        ler_leituras(pasta / "deteccoes.csv"),
        ler_amostras(pasta / "latencia.csv"),
        [sessao.isoformat() for sessao in sessoes],
    )


def test_cem_passagens_com_cinco_perdas_atendem_o_rnf05(tmp_path: Path) -> None:
    passagens: list[tuple[TipoEvento | None, float]] = [
        (TipoEvento.PREEMP_INI, 30.0 + i) for i in range(93)
    ]
    passagens += [(TipoEvento.RENOVADO, 31.0), (TipoEvento.FILA, 32.0)]
    passagens += [(None, 0.0)] * 5
    _medir(tmp_path, T0, passagens)

    relatorio = _relatorio(tmp_path, T0)
    assert "Leituras impressas pelo emissor (denominador): 100" in relatorio
    assert "Viraram evento de decisão com a rua certa: 95 (95.0%)" in relatorio
    assert "SEM_DECISAO: 5" in relatorio
    assert "Critério (≥ 95%): **atende**" in relatorio


def test_seis_perdas_nao_atendem_o_rnf05(tmp_path: Path) -> None:
    passagens = [(TipoEvento.PREEMP_INI, 30.0)] * 94 + [(None, 0.0)] * 6
    _medir(tmp_path, T0, passagens)
    assert "Critério (≥ 95%): **não atende**" in _relatorio(tmp_path, T0)


def test_rodada_incompleta_nao_tem_veredito_do_rnf05(tmp_path: Path) -> None:
    _medir(tmp_path, T0, [(TipoEvento.PREEMP_INI, 30.0)] * 40)
    relatorio = _relatorio(tmp_path, T0)
    assert "Rodada incompleta: 40 de 100" in relatorio
    assert "Critério (≥ 95%)" not in relatorio


def test_h3_usa_o_posto_mais_proximo(tmp_path: Path) -> None:
    """Latências 1..100 ms: p95 é a 95ª medida, sem interpolação."""
    _medir(tmp_path, T0, [(TipoEvento.PREEMP_INI, float(ms)) for ms in range(1, 101)])
    relatorio = _relatorio(tmp_path, T0)
    assert "| 100 | 1.0 ms | 50.0 ms | 50.5 ms | 95.0 ms | 99.0 ms | 100.0 ms |" in relatorio
    assert "Critério (p95 < 200 ms): **atende**" in relatorio
    assert "Atenção" not in relatorio


def test_h3_reprovado_pela_cauda(tmp_path: Path) -> None:
    passagens = [(TipoEvento.PREEMP_INI, 40.0)] * 90 + [(TipoEvento.PREEMP_INI, 250.0)] * 10
    _medir(tmp_path, T0, passagens)
    assert "Critério (p95 < 200 ms): **não atende**" in _relatorio(tmp_path, T0)


def test_sessoes_nao_se_misturam_e_a_padrao_e_a_ultima(tmp_path: Path) -> None:
    antiga, nova = T0, T0 + timedelta(hours=1)
    _medir(tmp_path, antiga, [(None, 0.0)] * 3)
    _medir(tmp_path, nova, [(TipoEvento.PREEMP_INI, 45.0)] * 2)
    saida = tmp_path / "resumo.md"

    main(
        [
            "--deteccoes",
            str(tmp_path / "deteccoes.csv"),
            "--latencia",
            str(tmp_path / "latencia.csv"),
            "--saida",
            str(saida),
        ]
    )

    relatorio = saida.read_text(encoding="utf-8")
    assert nova.isoformat() in relatorio
    assert antiga.isoformat() not in relatorio
    assert "Leituras impressas pelo emissor (denominador): 2" in relatorio
    assert "SEM_DECISAO" not in relatorio


def test_sem_dados_o_relatorio_diz_como_medir(tmp_path: Path) -> None:
    assert "bridge.main" in gerar_relatorio((), (), [])
