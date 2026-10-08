"""As faixas de seed reservadas, lidas do `cenarios.yaml` de verdade (sem banco)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.simulacoes import RegrasSimulacao, SeedReservadaError

CENARIOS = Path(__file__).resolve().parents[3] / "sim" / "config" / "cenarios.yaml"


def test_cada_faixa_reservada_tem_o_seu_uso() -> None:
    regras = RegrasSimulacao.de_arquivo(CENARIOS)

    faixas = regras.faixas()
    assert [(inicio, fim) for inicio, fim, _ in faixas] == [(1, 50), (101, 105), (201, 250)]
    assert all(uso for _, _, uso in faixas)


@pytest.mark.parametrize("seed", [201, 240, 241, 250])
def test_seeds_do_treino_do_modelo_sao_recusadas_com_o_motivo(seed: int) -> None:
    regras = RegrasSimulacao.de_arquivo(CENARIOS)

    with pytest.raises(SeedReservadaError, match="modelo de ML"):
        regras.validar("moderado", seed)


def test_regras_montadas_sem_uso_continuam_valendo() -> None:
    """O atendente e os testes montam as regras à mão, só com as faixas."""
    regras = RegrasSimulacao(frozenset({"leve"}), ((1, 50),))

    assert regras.faixas() == [(1, 50, "")]
    with pytest.raises(SeedReservadaError, match=r"\(1\.\.50\)"):
        regras.validar("leve", 7)
