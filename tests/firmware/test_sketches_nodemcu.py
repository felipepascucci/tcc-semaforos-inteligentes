"""Sketches dos NodeMCUs versionados como estão — entrega 5.6, `context/05` §5.

A decisão de 2026-10-05 é que eles **não mudam**. Em `firmware/nodemcu/` entra
só um cabeçalho de comentário, e estes testes impedem as duas derivas
possíveis: alguém "consertar" o código, ou o cabeçalho deixar de dizer o que o
código faz.

Desde 2026-10-08 a bancada tem três carrinhos, um por tipo (`context/09`). Os
emissores do bombeiro e da polícia são o sketch da ambulância com **uma** linha
trocada, a do tipo; o resto vale para os três.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from bridge.protocolo import LeituraVeiculo, interpretar_leitura_veiculo

RAIZ = Path(__file__).resolve().parents[2]
ORIGINAIS = RAIZ / "docs" / "hardware"
FIRMWARE = RAIZ / "firmware" / "nodemcu"

# Emissor -> tipo gravado nele. Todos vêm de docs/hardware/veiculo_ambulancia.ino.
EMISSORES = {
    "veiculo_ambulancia": "AMBULANCIA",
    "veiculo_bombeiro": "BOMBEIRO",
    "veiculo_policia": "POLICIA",
}
SKETCHES = (*EMISSORES, "nodeMCU_semaforo")
ORIGINAL_DO_EMISSOR = "veiculo_ambulancia"
LINHA_DO_TIPO = 'String tipoVeiculoAtual = "{}"; '

_CABECALHO = re.compile(rb"\A/\*.*?\*/\n\n", re.DOTALL)


def _versionado(nome: str) -> bytes:
    return (FIRMWARE / nome / f"{nome}.ino").read_bytes()


def _partes(nome: str) -> tuple[str, bytes]:
    """(cabeçalho, corpo) do sketch versionado."""
    conteudo = _versionado(nome)
    casamento = _CABECALHO.match(conteudo)
    assert casamento is not None, f"{nome}: sem cabeçalho /* ... */ no início"
    return casamento[0].decode("utf-8"), conteudo[casamento.end() :]


def _mapa_do_codigo(codigo: str) -> dict[str, str]:
    pares = re.findall(r'uidTag == "([0-9A-F]+)"\)\s*\{\s*ruaDetectada = "(RUA[1-4])"', codigo)
    return dict(pares)


def _original(nome: str) -> bytes:
    """O sketch da equipe de que `nome` deriva, com o tipo do emissor trocado."""
    if nome not in EMISSORES:
        return (ORIGINAIS / f"{nome}.ino").read_bytes()
    original = (ORIGINAIS / f"{ORIGINAL_DO_EMISSOR}.ino").read_bytes()
    da_ambulancia = LINHA_DO_TIPO.format("AMBULANCIA").encode()
    assert original.count(da_ambulancia) == 1
    return original.replace(da_ambulancia, LINHA_DO_TIPO.format(EMISSORES[nome]).encode())


@pytest.mark.parametrize("nome", SKETCHES)
def test_corpo_e_o_sketch_da_equipe_byte_a_byte(nome: str) -> None:
    """Para os emissores, a única linha que pode diferir do original é a do tipo."""
    _, corpo = _partes(nome)
    assert corpo == _original(nome)


@pytest.mark.parametrize("nome", SKETCHES)
def test_cabecalho_documenta_o_mac_do_receptor(nome: str) -> None:
    cabecalho, _ = _partes(nome)
    assert "40:91:51:58:A8:E1" in cabecalho


@pytest.mark.parametrize("nome", EMISSORES)
def test_mac_do_cabecalho_e_o_do_codigo_do_emissor(nome: str) -> None:
    _, corpo = _partes(nome)
    bytes_mac = re.search(rb"enderecoReceptor\[\] = \{([^}]*)\}", corpo)
    assert bytes_mac is not None
    mac = ":".join(f"{int(b, 16):02X}" for b in bytes_mac[1].decode().split(","))
    assert mac == "40:91:51:58:A8:E1"


@pytest.mark.parametrize(("nome", "tipo"), EMISSORES.items())
def test_tipo_do_veiculo_do_cabecalho_e_o_do_codigo(nome: str, tipo: str) -> None:
    cabecalho, corpo = _partes(nome)
    assert LINHA_DO_TIPO.format(tipo).encode() in corpo
    assert f"{tipo}, fixo no código" in cabecalho


def test_um_emissor_por_tipo_de_veiculo() -> None:
    """Os três tipos que o UNO aceita (`05` §3.2), cada um no seu carrinho."""
    assert sorted(EMISSORES.values()) == ["AMBULANCIA", "BOMBEIRO", "POLICIA"]
    for nome in EMISSORES:
        assert (FIRMWARE / nome / f"{nome}.ino").is_file()


@pytest.mark.parametrize("nome", EMISSORES)
def test_mapa_uid_rua_do_cabecalho_e_do_contexto_e_o_do_codigo(nome: str) -> None:
    cabecalho, corpo = _partes(nome)
    do_codigo = _mapa_do_codigo(corpo.decode("utf-8"))
    do_cabecalho = dict(re.findall(r"\*\s+([0-9A-F]{8}) -> (RUA[1-4])", cabecalho))
    contexto = (RAIZ / "context" / "05-integracao-hardware.md").read_text(encoding="utf-8")
    do_contexto = dict(re.findall(r"\| `([0-9A-F]{8})` \| `(RUA[1-4])` \|", contexto))

    assert len(do_codigo) == 4
    assert do_cabecalho == do_codigo
    assert do_contexto == do_codigo


@pytest.mark.parametrize("nome", SKETCHES)
def test_pinagem_documentada(nome: str) -> None:
    cabecalho, _ = _partes(nome)
    assert "Pinagem" in cabecalho


@pytest.mark.parametrize("nome", EMISSORES)
def test_pinos_do_rc522_no_cabecalho_sao_os_do_codigo(nome: str) -> None:
    cabecalho, corpo = _partes(nome)
    assert b"#define RST_PIN D3" in corpo
    assert b"#define SS_PIN  D8" in corpo
    assert "RST    -> D3" in cabecalho
    assert "SDA/SS -> D8" in cabecalho


@pytest.mark.parametrize("nome", EMISSORES)
def test_linha_impressa_pelo_emissor_e_a_que_a_ponte_interpreta(nome: str) -> None:
    """O `t_deteccao` de H3 depende de a ponte reconhecer essa linha (`05` §4.3)."""
    _, corpo = _partes(nome)
    assert b'Serial.println("Tag " + uidTag + " lida -> Enviando " + ruaDetectada);' in corpo
    for uid, rua in _mapa_do_codigo(corpo.decode("utf-8")).items():
        # O que o sketch imprime para esta tag, com o "\r\n" do println.
        linha = f"Tag {uid} lida -> Enviando {rua}\r\n".encode("ascii")
        assert interpretar_leitura_veiculo(linha) == LeituraVeiculo(uid, int(rua[-1]))


def test_receptor_repassa_rua_virgula_veiculo_a_9600() -> None:
    _, corpo = _partes("nodeMCU_semaforo")
    assert b"Serial.begin(9600);" in corpo
    repasse = (
        b'Serial.print(ruaDinamica);\n  Serial.print(",");\n  Serial.println(veiculoDinamico);'
    )
    assert repasse in corpo
