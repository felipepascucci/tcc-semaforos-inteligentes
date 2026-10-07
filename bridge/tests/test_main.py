"""Argumentos de `python -m bridge.main` — sobretudo as guardas da medição de H3."""

from __future__ import annotations

import pytest

from bridge.latencia import CSV_DESFECHOS_PADRAO, CSV_PADRAO
from bridge.main import _argumentos


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
