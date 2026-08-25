"""Carga de `parametros.yaml` — a fronteira entre o disco e o domínio.

Isto **não** vive em `core/` de propósito. Ler arquivo é I/O, e a regra de
`context/01` §1 é que o núcleo seja puro: testável com `pytest` sem SUMO
instalado, sem hardware ligado e sem arquivo nenhum no lugar certo.

O perfil `hardware` é uma **sobreposição**: `parametros.hardware.yaml` traz só as
chaves que mudam na bancada, e as demais são herdadas do perfil de simulação.
Manter os dois arquivos completos convidaria à divergência silenciosa — alguém
mudaria `raio_deteccao_m` num e esqueceria o outro.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from core.excecoes import ConfiguracaoInvalidaError
from core.parametros import Parametros

DIRETORIO_PADRAO = Path(__file__).resolve().parents[1] / "config"

ARQUIVO_SIMULACAO = "parametros.yaml"
ARQUIVO_HARDWARE = "parametros.hardware.yaml"

PERFIS = ("simulacao", "hardware")


def _ler_yaml(caminho: Path) -> dict[str, Any]:
    if not caminho.is_file():
        raise ConfiguracaoInvalidaError(f"arquivo de parâmetros não encontrado: {caminho}")
    with caminho.open(encoding="utf-8") as arquivo:
        dados = yaml.safe_load(arquivo)
    if not isinstance(dados, dict):
        raise ConfiguracaoInvalidaError(f"{caminho} não contém um mapeamento YAML")
    return dados


def carregar_dicionario(perfil: str | None = None, diretorio: Path | None = None) -> dict[str, Any]:
    """Lê os parâmetros do perfil pedido, já mesclados.

    Args:
        perfil: `"simulacao"` ou `"hardware"`. Quando omitido, usa a variável de
            ambiente `PERFIL_PARAMETROS`, com `"simulacao"` como padrão.
        diretorio: Onde estão os YAML. Padrão: `backend/config/`.

    Returns:
        O dicionário de parâmetros.

    Raises:
        ConfiguracaoInvalidaError: se o perfil for desconhecido ou o arquivo
            não existir.
    """
    perfil = perfil or os.getenv("PERFIL_PARAMETROS", "simulacao")
    if perfil not in PERFIS:
        raise ConfiguracaoInvalidaError(
            f"perfil desconhecido: {perfil!r} (esperado um de {', '.join(PERFIS)})"
        )

    base = diretorio or DIRETORIO_PADRAO
    dados = _ler_yaml(base / ARQUIVO_SIMULACAO)

    if perfil == "hardware":
        sobreposicao = _ler_yaml(base / ARQUIVO_HARDWARE)
        dados = {**dados, **sobreposicao}
        # Na bancada `verde_s` é a duração do verde de cada fase; o perfil de
        # simulação não tem esse conceito separado da duração base da fase.
        if "verde_s" in sobreposicao:
            dados.setdefault("verde_min_s", sobreposicao["verde_s"])

    return dados


def carregar(perfil: str | None = None, diretorio: Path | None = None) -> Parametros:
    """Carrega e valida os parâmetros do perfil pedido.

    Args:
        perfil: `"simulacao"` ou `"hardware"`.
        diretorio: Onde estão os YAML.

    Returns:
        Os parâmetros validados, prontos para o motor.
    """
    return Parametros.de_dicionario(carregar_dicionario(perfil, diretorio))


def snapshot(perfil: str | None = None, diretorio: Path | None = None) -> Mapping[str, Any]:
    """Dicionário cru dos parâmetros, para gravar em `execucao_simulacao`.

    A coluna `parametros` guarda o snapshot exato usado na execução. Sem ele não
    há reprodutibilidade e o resultado não é defensável (`context/03` §4.3) —
    saber que a execução usou `K = 0.7` só é possível se o valor foi registrado
    junto do resultado.
    """
    return carregar_dicionario(perfil, diretorio)
