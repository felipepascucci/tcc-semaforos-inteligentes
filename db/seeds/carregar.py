"""Carga dos seeds — `context/03` §5.

Idempotente por chave natural: rodar duas vezes não duplica nada e não sobrescreve
alteração feita à mão no banco. Uso::

    python -m db.seeds.carregar          # aplica
    python -m db.seeds.carregar --resumo # só mostra o que existe hoje

As coordenadas dos 8 TLS da malha são **derivadas** da geometria declarada do
cenário (grade 2x4, ~500 m), não digitadas uma a uma: se a geometria mudar no
Bloco 3, muda-se o `dados.yaml` e a grade inteira acompanha.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from app.models import DispositivoIot, FaseSemaforo, Semaforo, TagRfid, VeiculoEmergencia
from app.repositories.sessao import criar_engine, criar_fabrica_sessao, sessao_de

ARQUIVO_DADOS = Path(__file__).with_name("dados.yaml")

#: Metros por grau de latitude. Constante o bastante em escala urbana.
METROS_POR_GRAU_LAT = 111_320.0


def _metros_por_grau_lon(latitude_graus: float) -> float:
    """Metros por grau de longitude na latitude dada.

    Os meridianos convergem em direção aos polos, então um grau de longitude
    encolhe com o cosseno da latitude. Ignorar isso deformaria a grade em ~8%
    na latitude de São Paulo — visível no mapa do dashboard.
    """
    return METROS_POR_GRAU_LAT * math.cos(math.radians(latitude_graus))


def carregar_dados() -> dict[str, Any]:
    """Lê `dados.yaml`."""
    with ARQUIVO_DADOS.open(encoding="utf-8") as arquivo:
        return yaml.safe_load(arquivo)


def coordenadas_da_grade(config: dict[str, Any]) -> list[tuple[str, str, Decimal, Decimal]]:
    """Deriva (código, descrição, latitude, longitude) dos cruzamentos da malha.

    Returns:
        Uma tupla por cruzamento, na ordem linha-a-linha (CRUZ_01..CRUZ_08).
    """
    origem = config["origem"]
    lat0, lon0 = float(origem["latitude"]), float(origem["longitude"])
    passo_m = float(config["espacamento_m"])
    prefixo = config["prefixo_codigo"]

    passo_lat = passo_m / METROS_POR_GRAU_LAT
    passo_lon = passo_m / _metros_por_grau_lon(lat0)

    cruzamentos: list[tuple[str, str, Decimal, Decimal]] = []
    numero = 0
    for linha in range(int(config["linhas"])):
        for coluna in range(int(config["colunas"])):
            numero += 1
            codigo = f"{prefixo}_{numero:02d}"
            descricao = f"Malha SUMO — arterial {linha + 1}, transversal {coluna + 1}"
            latitude = Decimal(f"{lat0 - linha * passo_lat:.8f}")
            longitude = Decimal(f"{lon0 + coluna * passo_lon:.8f}")
            cruzamentos.append((codigo, descricao, latitude, longitude))
    return cruzamentos


def _hash_token(codigo: str, token_dev: str) -> str:
    """Hash SHA-256 do token do dispositivo.

    O token real vem da variável de ambiente ``TOKEN_<CODIGO>``. O valor de
    desenvolvimento do YAML é fallback e precisa ser trocado antes da
    apresentação (`context/02` §6) — por isso o aviso em stderr.
    """
    # `or None` trata variável definida como string vazia igual a ausente. Sem
    # isso, um `TOKEN_CTRL_PROTO_01=` esquecido no .env viraria o hash da string
    # vazia — um token válido que qualquer um adivinha.
    token = os.getenv(f"TOKEN_{codigo}") or None
    if token is None:
        token = token_dev
        print(
            f"  aviso: {codigo} usando token de DESENVOLVIMENTO "
            f"(defina TOKEN_{codigo} para trocar)",
            file=sys.stderr,
        )
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _obter_ou_criar(sessao: Session, modelo: type, chave: dict[str, Any], **campos: Any) -> tuple:
    """Busca por chave natural; cria se não existir.

    Returns:
        (instância, criada) — `criada` diz se houve INSERT.
    """
    existente = sessao.query(modelo).filter_by(**chave).one_or_none()
    if existente is not None:
        return existente, False
    instancia = modelo(**chave, **campos)
    sessao.add(instancia)
    sessao.flush()
    return instancia, True


def aplicar(sessao: Session, dados: dict[str, Any]) -> dict[str, int]:
    """Aplica os seeds e devolve a contagem do que foi criado."""
    criados = {"semaforo": 0, "fase_semaforo": 0, "veiculo": 0, "tag": 0, "dispositivo": 0}

    # --- 8 TLS da malha SUMO ------------------------------------------------
    malha = dados["malha_sumo"]
    ciclo_provisorio = int(malha["tempo_ciclo_provisorio_s"])
    for codigo, descricao, latitude, longitude in coordenadas_da_grade(malha):
        _, novo = _obter_ou_criar(
            sessao,
            Semaforo,
            {"codigo_externo": codigo},
            descricao=descricao,
            latitude=latitude,
            longitude=longitude,
            tempo_ciclo=ciclo_provisorio,
        )
        criados["semaforo"] += novo
    # As fases destes 8 vêm do .net.xml no Bloco 3, não daqui.

    # --- cruzamento do protótipo + as 2 fases do ciclo da bancada -----------
    proto = dados["prototipo"]
    cfg_semaforo = proto["semaforo"]
    semaforo_proto, novo = _obter_ou_criar(
        sessao,
        Semaforo,
        {"codigo_externo": cfg_semaforo["codigo_externo"]},
        descricao=cfg_semaforo["descricao"],
        latitude=Decimal(str(cfg_semaforo["latitude"])),
        longitude=Decimal(str(cfg_semaforo["longitude"])),
        tempo_ciclo=int(cfg_semaforo["tempo_ciclo"]),
    )
    criados["semaforo"] += novo

    padrao = proto["fase_padrao"]
    for fase in proto["fases"]:
        _, novo = _obter_ou_criar(
            sessao,
            FaseSemaforo,
            {"fk_semaforo": semaforo_proto.id_semaforo, "indice_fase": fase["indice_fase"]},
            descricao=f"{fase['descricao']} ({fase['modulos']})",
            movimentos=list(fase["movimentos"]),
            duracao_base=int(padrao["duracao_base_s"]),
            verde_min=int(padrao["verde_min_s"]),
            verde_max=int(padrao["verde_max_s"]),
        )
        criados["fase_semaforo"] += novo

    # --- veículos -----------------------------------------------------------
    por_placa: dict[str, VeiculoEmergencia] = {}
    for veiculo in dados["veiculos"]:
        instancia, novo = _obter_ou_criar(
            sessao,
            VeiculoEmergencia,
            {"placa": veiculo["placa"]},
            tipo=veiculo["tipo"],
            identificacao=veiculo["identificacao"],
        )
        por_placa[veiculo["placa"]] = instancia
        criados["veiculo"] += novo

    # --- tags RFID (placeholder e INATIVAS; as da bancada são de rua) -------
    for tag in dados["tags"]:
        _, novo = _obter_ou_criar(
            sessao,
            TagRfid,
            {"uid": tag["uid"]},
            fk_veiculo=por_placa[tag["placa"]].id_veiculo,
            ativo=bool(tag["ativo"]),
        )
        criados["tag"] += novo

    # --- dispositivos de borda ---------------------------------------------
    for dispositivo in dados["dispositivos"]:
        # O emissor vai no veículo e não tem cruzamento.
        codigo_semaforo = dispositivo.get("semaforo")
        fk_semaforo = (
            None
            if codigo_semaforo is None
            else sessao.query(Semaforo).filter_by(codigo_externo=codigo_semaforo).one().id_semaforo
        )
        _, novo = _obter_ou_criar(
            sessao,
            DispositivoIot,
            {"codigo": dispositivo["codigo"]},
            tipo=dispositivo["tipo"],
            fk_semaforo=fk_semaforo,
            token_hash=_hash_token(dispositivo["codigo"], dispositivo["token_dev"]),
        )
        criados["dispositivo"] += novo

    return criados


def resumo(sessao: Session) -> dict[str, int]:
    """Contagem atual de cada cadastro."""
    return {
        "semaforo": sessao.query(Semaforo).count(),
        "fase_semaforo": sessao.query(FaseSemaforo).count(),
        "veiculo": sessao.query(VeiculoEmergencia).count(),
        "tag": sessao.query(TagRfid).count(),
        "dispositivo": sessao.query(DispositivoIot).count(),
    }


def main() -> int:
    analisador = argparse.ArgumentParser(description="Carrega os seeds do banco.")
    analisador.add_argument(
        "--resumo", action="store_true", help="não altera nada; só conta o que já existe"
    )
    argumentos = analisador.parse_args()

    fabrica = criar_fabrica_sessao(criar_engine())
    with sessao_de(fabrica) as sessao:
        if argumentos.resumo:
            for tabela, quantidade in resumo(sessao).items():
                print(f"  {tabela:<16} {quantidade}")
            return 0

        criados = aplicar(sessao, carregar_dados())

    print("seeds aplicados (linhas criadas nesta execução):")
    for tabela, quantidade in criados.items():
        print(f"  {tabela:<16} {quantidade}")
    print("\nlembretes:")
    print("  - tags estão como PLACEHOLDER e INATIVAS; as da bancada são de rua e não entram")
    print("  - fases dos 8 TLS da malha vêm do .net.xml no Bloco 3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
