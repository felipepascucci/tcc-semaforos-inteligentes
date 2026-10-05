"""Sketches dos NodeMCUs versionados como estão — entrega 5.6, `context/05` §5.

A decisão de 2026-10-05 é que eles **não mudam**. Em `firmware/nodemcu/` entra
só um cabeçalho de comentário, e estes testes impedem as duas derivas
possíveis: alguém "consertar" o código, ou o cabeçalho deixar de dizer o que o
código faz.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from bridge.protocolo import LeituraVeiculo, interpretar_leitura_veiculo

RAIZ = Path(__file__).resolve().parents[2]
ORIGINAIS = RAIZ / "docs" / "hardware"
FIRMWARE = RAIZ / "firmware" / "nodemcu"

SKETCHES = ("veiculo_ambulancia", "nodeMCU_semaforo")

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


@pytest.mark.parametrize("nome", SKETCHES)
def test_corpo_e_o_sketch_da_equipe_byte_a_byte(nome: str) -> None:
    _, corpo = _partes(nome)
    assert corpo == (ORIGINAIS / f"{nome}.ino").read_bytes()


@pytest.mark.parametrize("nome", SKETCHES)
def test_cabecalho_documenta_o_mac_do_receptor(nome: str) -> None:
    cabecalho, _ = _partes(nome)
    assert "40:91:51:58:A8:E1" in cabecalho


def test_mac_do_cabecalho_e_o_do_codigo_do_emissor() -> None:
    _, corpo = _partes("veiculo_ambulancia")
    bytes_mac = re.search(rb"enderecoReceptor\[\] = \{([^}]*)\}", corpo)
    assert bytes_mac is not None
    mac = ":".join(f"{int(b, 16):02X}" for b in bytes_mac[1].decode().split(","))
    assert mac == "40:91:51:58:A8:E1"


def test_tipo_do_veiculo_do_cabecalho_e_o_do_codigo() -> None:
    cabecalho, corpo = _partes("veiculo_ambulancia")
    assert b'String tipoVeiculoAtual = "AMBULANCIA";' in corpo
    assert "AMBULANCIA, fixo no código" in cabecalho


def test_mapa_uid_rua_do_cabecalho_e_do_contexto_e_o_do_codigo() -> None:
    cabecalho, corpo = _partes("veiculo_ambulancia")
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


def test_pinos_do_rc522_no_cabecalho_sao_os_do_codigo() -> None:
    cabecalho, corpo = _partes("veiculo_ambulancia")
    assert b"#define RST_PIN D3" in corpo
    assert b"#define SS_PIN  D8" in corpo
    assert "RST    -> D3" in cabecalho
    assert "SDA/SS -> D8" in cabecalho


def test_linha_impressa_pelo_emissor_e_a_que_a_ponte_interpreta() -> None:
    """O `t_deteccao` de H3 depende de a ponte reconhecer essa linha (`05` §4.3)."""
    _, corpo = _partes("veiculo_ambulancia")
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
