"""Gravador do UNO em pedaços pequenos — contra um bootloader STK500 de mentira.

O defeito que motivou o gravador (os bytes 60..63 de cada página corrompidos na
fronteira do pacote USB, `context/09`, 2026-10-06) só existe na placa. Aqui se
prova o resto: o protocolo, os pedaços de no máximo 16 bytes e a releitura que
reprova uma gravação errada.
"""

from __future__ import annotations

import pytest

from bridge.gravar_uno import PAGINA, PEDACO, GravacaoError, Gravador, ler_hex, paginas


class BootloaderFalso:
    """O bootloader do UNO do outro lado do cabo, com a flash em memória.

    Args:
        corromper: Endereço cujo byte a "flash" grava trocado.
        mudo: Não responde à sincronização.
    """

    def __init__(self, *, corromper: int | None = None, mudo: bool = False) -> None:
        self.dtr = True
        self.flash = bytearray(b"\xff" * 32768)
        self.maior_escrita = 0
        self.saiu = False
        self._corromper = corromper
        self._mudo = mudo
        self._entrada = bytearray()
        self._saida = bytearray()
        self._endereco = 0

    # -- a interface de serial.Serial que o gravador usa -----------------------

    def write(self, dados: bytes) -> int:
        self.maior_escrita = max(self.maior_escrita, len(dados))
        self._entrada += dados
        self._processar()
        return len(dados)

    def flush(self) -> None:
        pass

    def read(self, n: int) -> bytes:
        dados, self._saida = bytes(self._saida[:n]), self._saida[n:]
        return dados

    def reset_input_buffer(self) -> None:
        self._saida.clear()

    # -- o protocolo ------------------------------------------------------------

    def _responder(self, dados: bytes = b"") -> None:
        self._saida += bytes([0x14]) + dados + bytes([0x10])

    def _processar(self) -> None:
        while self._entrada:
            comando = self._entrada[0]
            if comando == 0x30 and len(self._entrada) >= 2:
                del self._entrada[:2]
                if not self._mudo:
                    self._responder()
            elif comando == ord("U") and len(self._entrada) >= 4:
                self._endereco = (self._entrada[1] | self._entrada[2] << 8) * 2
                del self._entrada[:4]
                self._responder()
            elif comando == ord("d") and len(self._entrada) >= 4:
                tamanho = self._entrada[1] << 8 | self._entrada[2]
                if len(self._entrada) < 5 + tamanho:
                    return
                dados = bytearray(self._entrada[4 : 4 + tamanho])
                inicio = self._endereco
                if self._corromper is not None and inicio <= self._corromper < inicio + tamanho:
                    dados[self._corromper - inicio] ^= 0xFF
                self.flash[inicio : inicio + tamanho] = dados
                del self._entrada[: 5 + tamanho]
                self._responder()
            elif comando == ord("t") and len(self._entrada) >= 5:
                tamanho = self._entrada[1] << 8 | self._entrada[2]
                inicio = self._endereco
                del self._entrada[:5]
                self._responder(bytes(self.flash[inicio : inicio + tamanho]))
            elif comando == ord("Q") and len(self._entrada) >= 2:
                del self._entrada[:2]
                self.saiu = True
                self._responder()
            else:
                return


def _hex(memoria: dict[int, int]) -> str:
    """Intel HEX de 16 bytes por linha, como o avr-gcc gera."""
    linhas = []
    enderecos = sorted(memoria)
    for i in range(0, len(enderecos), 16):
        bloco = enderecos[i : i + 16]
        corpo = bytes([len(bloco), bloco[0] >> 8, bloco[0] & 0xFF, 0])
        corpo += bytes(memoria[a] for a in bloco)
        linhas.append(":" + (corpo + bytes([(-sum(corpo)) & 0xFF])).hex().upper())
    return "\n".join([*linhas, ":00000001FF"]) + "\n"


PROGRAMA = {a: (a * 7 + 3) & 0xFF for a in range(300)}  # 3 páginas, a última incompleta


def test_ler_hex_ida_e_volta() -> None:
    assert ler_hex(_hex(PROGRAMA)) == PROGRAMA


def test_hex_com_checksum_errado_e_recusado() -> None:
    texto = _hex({0: 1, 1: 2}).replace(":02000000", ":02000001", 1)
    with pytest.raises(GravacaoError, match="checksum"):
        ler_hex(texto)


def test_paginas_completam_com_ff() -> None:
    lista = paginas(PROGRAMA)
    assert [inicio for inicio, _ in lista] == [0, 128, 256]
    assert all(len(dados) == PAGINA for _, dados in lista)
    assert lista[-1][1][300 - 256 :] == b"\xff" * (PAGINA - 44)


def test_grava_em_pedacos_pequenos_e_confere() -> None:
    placa = BootloaderFalso()
    gravador = Gravador(placa, pausa_s=0)
    gravador.sincronizar()

    total = gravador.gravar(PROGRAMA)

    assert total == 3 * PAGINA
    assert bytes(placa.flash[:300]) == bytes(PROGRAMA[a] for a in range(300))
    # Nenhuma escrita chega perto dos 64 bytes de um pacote USB.
    assert placa.maior_escrita <= PEDACO
    assert placa.saiu


def test_releitura_que_nao_confere_reprova_a_gravacao() -> None:
    placa = BootloaderFalso(corromper=0xBC)  # o byte 60 da segunda página
    gravador = Gravador(placa, pausa_s=0)
    gravador.sincronizar()

    with pytest.raises(GravacaoError, match="0x00bc"):
        gravador.gravar(PROGRAMA)


def test_bootloader_mudo_e_erro_claro() -> None:
    gravador = Gravador(BootloaderFalso(mudo=True), pausa_s=0)
    with pytest.raises(GravacaoError, match="não respondeu"):
        gravador.sincronizar(tentativas=2)
