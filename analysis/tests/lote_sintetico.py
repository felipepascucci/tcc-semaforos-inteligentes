"""Uma pasta de lote **sintética**, no formato de `context/04` §10.

Os valores são redondos e artificiais de propósito (`context/08` §4.2): servem
para exercitar o pipeline, e nada aqui se parece com resultado experimental. A
travessia do VE é `400 + seed` no `FIXO` e `280 + seed` com preempção; a espera
transversal é 10, 14 e 13 s mais um décimo da seed; e assim por diante.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pandas as pd

SEEDS = tuple(range(1, 13))

#: Travessia de cada VE por braço, antes de somar a seed.
TRAVESSIA = {"FIXO": 400.0, "PREEMPCAO": 280.0, "PREEMPCAO_COMPENSADA": 290.0}

#: Espera transversal por braço, antes de somar um décimo da seed.
ESPERA = {"FIXO": 10.0, "PREEMPCAO": 14.0, "PREEMPCAO_COMPENSADA": 13.0}

MULTIPLAS = "multiplas_emergencias"
MODOS_MULTIPLAS = ("FIXO", "PREEMPCAO", "PREEMPCAO_ML")


def _execucao(cenario: str, modo: str, seed: int, espera: float) -> dict[str, object]:
    return {
        "id_execucao": -1,
        "cenario": cenario,
        "modo": modo,
        "seed": seed,
        "versao_codigo": "teste00",
        "duracao_s": 3600,
        "aquecimento_s": 300,
        "veiculos_planejados": 1000,
        "veiculos_completos": 1000,
        "ves_completos": 2,
        "tempo_medio_travessia_ve_s": 0.0,
        "paradas_medias_ve": 0.0,
        "tempo_espera_medio_transversal_s": espera,
        "atraso_total_rede_s": 0.0,
        "latencia_media_ms": 0.0 if modo == "FIXO" else 0.05,
        "latencia_p95_ms": 0.0 if modo == "FIXO" else 0.1,
        "latencia_p99_ms": 0.0 if modo == "FIXO" else 0.2,
        "latencia_max_ms": 0.0 if modo == "FIXO" else 1.0,
        "colisoes": 0,
        "teleportes": 0,
        "violacoes": 0,
        "transicoes": 100,
        "eventos_conflito": 0,
        "eventos_conflito_decidiveis": 0,
        "passos_em_conflito": 0,
    }


def _ve(cenario: str, modo: str, seed: int, id_veiculo: str, tempo: float) -> dict[str, object]:
    return {
        "id_execucao": -1,
        "cenario": cenario,
        "modo": modo,
        "seed": seed,
        "id_veiculo": id_veiculo,
        "tipo": "ambulancia",
        "tempo_viagem_s": tempo,
        "tempo_espera_s": 0.0,
        "paradas": 0 if modo != "FIXO" else 3,
        "velocidade_media_ms": 10.0,
        "atraso_s": 0.0,
    }


def _conflito(modo: str, seed: int, *, mesmo_nivel: int, decidida: int, divergiu: int,
              em_curso: str = "") -> dict[str, object]:  # fmt: skip
    return {
        "id_execucao": -1,
        "cenario": MULTIPLAS,
        "modo": modo,
        "seed": seed,
        "t_inicio_s": 400.0,
        "t_fim_s": 410.0,
        "duracao_s": 10.0,
        "passos": 100,
        "id_semaforo": "SEMAFORO_TESTE",
        "n_ves": 2,
        "ids_veiculos": "VE_ROTA_VE_CORREDOR_00|VE_ROTA_VE_TRANSVERSAL_00",
        "tipos": "AMBULANCIA|AMBULANCIA",
        "criticidades": "1|1" if mesmo_nivel else "1|2",
        "etas_s": "20.0|10.0",
        "fases_desejadas": "1|2",
        "mesmo_nivel": mesmo_nivel,
        "decidivel": 0 if em_curso else 1,
        "decidivel_em_algum_passo": 0 if em_curso else 1,
        "preempcao_em_curso": em_curso,
        "decidida_pelo_modelo": decidida,
        "modelo_divergiu_do_e8": divergiu,
    }


def escrever_lote(
    pasta: Path,
    *,
    cenarios: Sequence[str] = ("moderado", "intenso"),
    com_multiplas: bool = True,
    ganho_ml_s: float = 5.0,
    espera: dict[str, float] | None = None,
) -> Path:
    """Escreve os quatro CSV do lote numa pasta e a devolve.

    São `execucoes.csv`, `ve_por_execucao.csv`, `transversal_por_execucao.csv` e
    `conflitos_por_execucao.csv`.

    Args:
        pasta: Onde escrever.
        cenarios: Cenários de um VE (dois VEs por seed, `VE_TESTE_00` e `_01`).
        com_multiplas: Se acrescenta o `multiplas_emergencias` com o braço de ML.
        ganho_ml_s: Quanto o braço de ML encurta o VE mais prejudicado de cada par.
        espera: Espera transversal base por braço; padrão `ESPERA`.
    """
    espera = espera or ESPERA
    execucoes: list[dict[str, object]] = []
    ves: list[dict[str, object]] = []
    filas: list[dict[str, object]] = []
    conflitos: list[dict[str, object]] = []
    for cenario in cenarios:
        for seed in SEEDS:
            for modo, base in TRAVESSIA.items():
                execucoes.append(_execucao(cenario, modo, seed, espera[modo] + seed / 10))
                for indice in range(2):
                    ves.append(_ve(cenario, modo, seed, f"VE_TESTE_0{indice}", base + seed))
                filas.append(
                    {"id_execucao": -1, "cenario": cenario, "modo": modo, "seed": seed,
                     "acesso": "T1_S0", "fila_maxima": 5}
                )  # fmt: skip
                filas.append(
                    {"id_execucao": -1, "cenario": cenario, "modo": modo, "seed": seed,
                     "acesso": "A1_L0", "fila_maxima": 50}
                )  # fmt: skip
    if com_multiplas:
        for seed in SEEDS:
            for modo in MODOS_MULTIPLAS:
                execucoes.append(_execucao(MULTIPLAS, modo, seed, 10.0 + seed / 10))
                corredor = {"FIXO": 330.0, "PREEMPCAO": 250.0, "PREEMPCAO_ML": 250.0 - ganho_ml_s}
                for par in ("00", "01"):
                    ves.append(
                        _ve(MULTIPLAS, modo, seed, f"VE_ROTA_VE_CORREDOR_{par}",
                            corredor[modo] + seed)
                    )  # fmt: skip
                    ves.append(
                        _ve(MULTIPLAS, modo, seed, f"VE_ROTA_VE_TRANSVERSAL_{par}", 150.0 + seed)
                    )
            # O último par incompleto: só o VE da transversal chegou.
            ves.append(_ve(MULTIPLAS, "PREEMPCAO", seed, "VE_ROTA_VE_TRANSVERSAL_02", 150.0))
            conflitos.append(_conflito("PREEMPCAO", seed, mesmo_nivel=1, decidida=0, divergiu=0))
            conflitos.append(
                _conflito("PREEMPCAO", seed, mesmo_nivel=1, decidida=0, divergiu=0,
                          em_curso="VE_ROTA_VE_TRANSVERSAL_00")
            )  # fmt: skip
            conflitos.append(
                _conflito("PREEMPCAO_ML", seed, mesmo_nivel=1, decidida=1,
                          divergiu=int(seed % 2 == 0))
            )  # fmt: skip
            conflitos.append(_conflito("PREEMPCAO_ML", seed, mesmo_nivel=0, decidida=0, divergiu=0))
    pasta.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(execucoes).to_csv(pasta / "execucoes.csv", index=False)
    pd.DataFrame(ves).to_csv(pasta / "ve_por_execucao.csv", index=False)
    pd.DataFrame(filas).to_csv(pasta / "transversal_por_execucao.csv", index=False)
    if conflitos:
        pd.DataFrame(conflitos).to_csv(pasta / "conflitos_por_execucao.csv", index=False)
    return pasta
