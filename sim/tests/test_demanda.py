"""Geração da demanda — o pareamento por seed, que é regra crítica.

`context/04` §7: *"a execução com `seed=17` no modo `FIXO` e no modo `PREEMPCAO`
precisa ter exatamente o mesmo tráfego"*. Sem isso a comparação deixa de ser
pareada e perde o poder estatístico que justifica 50 seeds em vez de 500.

Estes testes rodam sem SUMO: a geração é determinística por construção,
justamente para não depender do simulador.
"""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from adapters.sumo.adaptador import PARAMETRO_CRITICIDADE
from sim.calibracao import cenarios as calibracao
from sim.demanda import gerar_rotas
from sim.demanda.fluxos import (
    ENTRADAS_ARTERIAIS,
    ENTRADAS_TRANSVERSAIS,
    correntes_do_cenario,
    rotas_de_emergencia,
)
from sim.demanda.gerar_rotas import ARQUIVO_DE_FLUXO, gerar, partidas_de_emergencia

RAIZ = Path(__file__).resolve().parents[2]
DEMANDA = RAIZ / "sim" / "demanda"


# ---------------------------------------------------------------------------
# Correntes de tráfego
# ---------------------------------------------------------------------------


def test_malha_recebe_doze_correntes() -> None:
    """Quatro entradas arteriais e oito transversais — a grade 2x4 inteira."""
    assert len(ENTRADAS_ARTERIAIS) == 4
    assert len(ENTRADAS_TRANSVERSAIS) == 8


def test_correntes_usam_o_fluxo_derivado_na_transversal() -> None:
    """Arterial recebe o fluxo do pré-projeto; transversal, o derivado."""
    linhas, _ = calibracao.calibrar()
    intenso = next(linha for linha in linhas if linha.cenario == "intenso")
    correntes = correntes_do_cenario("intenso", linhas)

    arteriais = [c for c in correntes if c.aproximacao == "arterial"]
    transversais = [c for c in correntes if c.aproximacao == "transversal"]

    assert all(c.fluxo_veic_h == intenso.fluxo_arterial_veic_h for c in arteriais)
    assert all(c.fluxo_veic_h == intenso.fluxo_transversal_veic_h for c in transversais)
    # A transversal tem uma faixa; se recebesse o fluxo nominal da arterial,
    # saturaria e o cenário viraria gridlock.
    assert transversais[0].fluxo_veic_h < arteriais[0].fluxo_veic_h


def test_cenario_desconhecido_falha_alto() -> None:
    linhas, _ = calibracao.calibrar()
    with pytest.raises(KeyError):
        correntes_do_cenario("inexistente", linhas)


def test_apenas_multiplas_emergencias_tem_segundo_ve() -> None:
    """O cenário de conflito é o único com dois VEs, e por rotas que se cruzam."""
    configuracao = calibracao.carregar_configuracao()

    assert len(rotas_de_emergencia(configuracao, "moderado")) == 1

    duas = rotas_de_emergencia(configuracao, "multiplas_emergencias")
    assert len(duas) == 2
    assert duas[0][0] != duas[1][0], "os dois VEs precisam vir por rotas diferentes"
    assert duas[1][1] > 0, "o segundo VE parte depois, para encontrar o primeiro em CRUZ_02"


# ---------------------------------------------------------------------------
# Pareamento por seed
# ---------------------------------------------------------------------------


def test_mesma_seed_gera_arquivo_identico(tmp_path: Path) -> None:
    """A garantia mais importante do protocolo experimental, verificada por `diff`."""
    primeiro = gerar("moderado", 17, destino=tmp_path / "a.rou.xml")
    segundo = gerar("moderado", 17, destino=tmp_path / "b.rou.xml")

    assert primeiro.read_bytes() == segundo.read_bytes()


def test_seeds_diferentes_geram_trafego_diferente(tmp_path: Path) -> None:
    """Se a seed não mudasse nada, rodar 50 delas não teria sentido."""
    uma = gerar("moderado", 1, destino=tmp_path / "1.rou.xml")
    outra = gerar("moderado", 2, destino=tmp_path / "2.rou.xml")

    assert uma.read_bytes() != outra.read_bytes()


def test_ves_partem_nos_mesmos_instantes_em_qualquer_seed(tmp_path: Path) -> None:
    """O VE é o objeto de medida: sua partida não pode variar com a seed.

    A seed varia o tráfego de fundo; o VE entra sempre nos mesmos instantes e
    encontra um trânsito diferente a cada seed. Misturar as duas fontes de
    variação tornaria impossível atribuir a diferença medida ao controle.
    """
    partidas = []
    for seed in (1, 2, 3):
        arquivo = gerar("leve", seed, destino=tmp_path / f"{seed}.rou.xml")
        raiz = ET.parse(arquivo).getroot()
        partidas.append(
            [
                (v.get("id"), v.get("type"), v.get("depart"))
                for v in raiz.findall("vehicle")
                if str(v.get("id")).startswith("VE_")
            ]
        )

    assert partidas[0] == partidas[1] == partidas[2]
    assert partidas[0], "nenhum VE foi gerado"


def test_arquivo_sai_ordenado_por_partida(tmp_path: Path) -> None:
    """O SUMO exige o arquivo ordenado; desordenado, ele recusa ou descarta."""
    arquivo = gerar("leve", 5, destino=tmp_path / "ordem.rou.xml")
    instantes = [
        float(str(v.get("depart"))) for v in ET.parse(arquivo).getroot().findall("vehicle")
    ]

    assert instantes == sorted(instantes)


def test_multiplas_emergencias_reaproveita_a_demanda_de_fundo_do_moderado() -> None:
    """context/04 §5: mesmo fluxo (700); o que muda é a emergência."""
    assert ARQUIVO_DE_FLUXO["multiplas_emergencias"] == ARQUIVO_DE_FLUXO["moderado"]


def test_cenario_de_conflito_gera_ves_pelas_duas_rotas(tmp_path: Path) -> None:
    arquivo = gerar("multiplas_emergencias", 1, destino=tmp_path / "conflito.rou.xml")
    rotas = {
        str(v.get("route"))
        for v in ET.parse(arquivo).getroot().findall("vehicle")
        if str(v.get("id")).startswith("VE_")
    }

    assert rotas == {"ROTA_VE_CORREDOR", "ROTA_VE_TRANSVERSAL"}


def _cruzamentos_da_rota(id_rota: str) -> list[str]:
    """Os cruzamentos semaforizados que a rota atravessa, na ordem."""
    rotas = ET.parse(DEMANDA / "emergencias.rou.xml").getroot()
    vias = next(r for r in rotas.iter("route") if r.get("id") == id_rota).attrib["edges"].split()
    rede = ET.parse(RAIZ / "sim" / "rede" / "malha.net.xml").getroot()
    destino = {e.attrib["id"]: e.attrib["to"] for e in rede.iter("edge") if "to" in e.attrib}
    return [destino[via] for via in vias if destino[via].startswith("CRUZ_")]


def test_rota_secundaria_encontra_o_corredor_e_segue_por_quatro_cruzamentos() -> None:
    """Depois do conflito em CRUZ_02, o segundo VE ainda tem cruzamentos pela frente.

    Bloco 7 (2026-10-05). O CRUZ_08 é comum às duas rotas.
    """
    secundaria = _cruzamentos_da_rota("ROTA_VE_TRANSVERSAL")
    corredor = _cruzamentos_da_rota("ROTA_VE_CORREDOR")

    assert secundaria == ["CRUZ_02", "CRUZ_06", "CRUZ_07", "CRUZ_08"]
    assert corredor == [f"CRUZ_0{i}" for i in (1, 2, 3, 4, 8, 7, 6, 5)]
    assert {"CRUZ_02", "CRUZ_08"} <= set(secundaria) & set(corredor)


# ---------------------------------------------------------------------------
# Criticidade da ocorrência — P20
# ---------------------------------------------------------------------------


def _criticidade(veiculo: ET.Element) -> str | None:
    parametro = veiculo.find(f"param[@key='{PARAMETRO_CRITICIDADE}']")
    return None if parametro is None else parametro.get("value")


def test_todo_ve_gerado_declara_a_criticidade_e_o_fundo_nao(tmp_path: Path) -> None:
    """Sem o parâmetro o adaptador trataria o VE como fora de serviço."""
    arquivo = gerar("multiplas_emergencias", 1, destino=tmp_path / "crit.rou.xml")
    veiculos = ET.parse(arquivo).getroot().findall("vehicle")

    ves = [v for v in veiculos if str(v.get("id")).startswith("VE_")]
    fundo = [v for v in veiculos if not str(v.get("id")).startswith("VE_")]

    assert ves
    assert all(_criticidade(v) is not None for v in ves)
    assert all(_criticidade(v) is None for v in fundo)


def test_criticidade_roda_em_passo_com_o_tipo(tmp_path: Path) -> None:
    """Nos cenários do experimento, cada VE atende a ocorrência típica do tipo.

    É a atribuição que faz o E8 da P20 decidir como o anterior — e, com isso,
    nenhum número já medido mudar.
    """
    esperado = {"ambulancia": "1", "bombeiro": "2", "policia": "3"}
    arquivo = gerar("multiplas_emergencias", 1, destino=tmp_path / "passo.rou.xml")

    pares = {
        (str(v.get("type")), _criticidade(v))
        for v in ET.parse(arquivo).getroot().findall("vehicle")
        if str(v.get("id")).startswith("VE_")
    }

    assert pares == set(esperado.items())


def test_listas_de_tamanhos_diferentes_sao_recusadas() -> None:
    """Com uma criticidade a menos, o rodízio sairia de fase em silêncio."""
    configuracao = copy.deepcopy(calibracao.carregar_configuracao())
    configuracao["emergencias"]["criticidades"] = [1, 2]

    with pytest.raises(ValueError, match="criticidades"):
        list(partidas_de_emergencia(configuracao, "moderado"))


def test_nivel_fora_da_escala_e_recusado() -> None:
    configuracao = copy.deepcopy(calibracao.carregar_configuracao())
    configuracao["emergencias"]["criticidades"] = [1, 2, 7]

    with pytest.raises(ValueError):
        list(partidas_de_emergencia(configuracao, "moderado"))


def test_garantir_regenera_arquivo_em_cache_desatualizado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cache anterior à P20 não pode ser reaproveitado.

    Sem o parâmetro `criticidade`, o adaptador trata todo VE como fora de
    serviço — o lote rodaria inteiro sem preempção nenhuma, e sem erro.
    """
    monkeypatch.setattr(gerar_rotas, "SAIDA", tmp_path)
    caminho = gerar_rotas.caminho_das_rotas("leve", 3)
    caminho.write_text("<routes/>  <!-- gerado por uma versão antiga -->\n", encoding="utf-8")

    devolvido = gerar_rotas.garantir("leve", 3)

    assert devolvido == caminho
    assert caminho.read_text(encoding="utf-8") == gerar_rotas.conteudo("leve", 3)


def test_garantir_nao_reescreve_arquivo_ja_atual(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Arquivo atual fica intocado — nem a data de modificação muda."""
    monkeypatch.setattr(gerar_rotas, "SAIDA", tmp_path)
    caminho = gerar_rotas.garantir("leve", 3)
    antes = caminho.stat().st_mtime_ns

    gerar_rotas.garantir("leve", 3)

    assert caminho.stat().st_mtime_ns == antes


def test_cenario_curto_declara_a_criticidade_do_seu_ve() -> None:
    """`teste_60s.rou.xml` é escrito à mão; sem o parâmetro, a suíte `sumo` perderia o VE."""
    raiz = ET.parse(DEMANDA / "teste_60s.rou.xml").getroot()
    ves = [v for v in raiz.findall("vehicle") if v.get("type") == "ambulancia"]

    assert ves
    assert all(_criticidade(v) == "1" for v in ves)


# ---------------------------------------------------------------------------
# Arquivos de fluxo versionados
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cenario", ["leve", "moderado", "intenso"])
def test_arquivo_de_fluxo_versionado_bate_com_a_calibracao(cenario: str) -> None:
    """Os `fluxo_*.rou.xml` são gerados e congelados — não podem envelhecer.

    Se alguém remedir o fluxo de saturação e esquecer de regerar, metade do lote
    rodaria com uma demanda e metade com outra. Este teste falha antes disso.
    """
    linhas, _ = calibracao.calibrar()
    linha = next(linha for linha in linhas if linha.cenario == cenario)
    proporcao = float(calibracao.carregar_configuracao()["composicao"]["proporcao_onibus"])

    raiz = ET.parse(DEMANDA / f"fluxo_{cenario}.rou.xml").getroot()
    por_id = {str(f.get("id")): float(str(f.get("vehsPerHour"))) for f in raiz.findall("flow")}

    assert por_id["A1_LESTE_carro"] == pytest.approx(
        linha.fluxo_arterial_veic_h * (1 - proporcao), abs=0.01
    )
    assert por_id["T1_SUL_carro"] == pytest.approx(
        linha.fluxo_transversal_veic_h * (1 - proporcao), abs=0.01
    )
