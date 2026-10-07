"""Argumentos de `python -m bridge.main` — sobretudo as guardas da medição de H3."""

from __future__ import annotations

from pathlib import Path

import pytest

from bridge.latencia import CSV_DESFECHOS_PADRAO, CSV_PADRAO
from bridge.main import _argumentos
from bridge.registro import CSV_TELEMETRIA_PADRAO


def test_sem_porta_veiculo_nao_ha_medicao() -> None:
    args = _argumentos([])
    assert args.porta_veiculo is None


def test_porta_veiculo_explicita() -> None:
    args = _argumentos(["--porta", "COM3", "--porta-veiculo", "COM7"])
    assert (args.porta, args.porta_veiculo) == ("COM3", "COM7")
    assert args.csv_h3 == CSV_PADRAO
    assert args.csv_deteccoes == CSV_DESFECHOS_PADRAO


def test_porta_veiculo_sem_valor_vem_do_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERIAL_PORT_VEICULO", "COM9")
    assert _argumentos(["--porta-veiculo"]).porta_veiculo == "COM9"


def test_h3_nao_se_mede_com_o_duble(capsys: pytest.CaptureFixture[str]) -> None:
    """Nenhum número simulado pode chegar a `latencia_bancada.csv`."""
    with pytest.raises(SystemExit):
        _argumentos(["--simulado", "--porta-veiculo", "COM4"])
    assert "bancada" in capsys.readouterr().err


def test_sem_telemetria_nao_ha_registro() -> None:
    assert _argumentos([]).telemetria is None


def test_telemetria_sem_valor_vai_para_o_csv_padrao() -> None:
    assert _argumentos(["--telemetria"]).telemetria == CSV_TELEMETRIA_PADRAO
    assert _argumentos(["--telemetria", "x.csv"]).telemetria == Path("x.csv")


def test_checklist_nao_se_grava_com_o_duble(capsys: pytest.CaptureFixture[str]) -> None:
    """Nenhuma telemetria do dublê pode chegar a `telemetria_bancada.csv`."""
    with pytest.raises(SystemExit):
        _argumentos(["--simulado", "--telemetria"])
    assert "bancada" in capsys.readouterr().err
