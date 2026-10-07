"""Construção da malha — entrega 3.1 (`make rede`).

Roda o `netconvert` sobre os cinco arquivos-fonte de `sim/rede/` e produz
`malha.net.xml` e `malha.det.add.xml`. Ambos são **gerados** e ficam fora do Git
(`.gitignore`): versiona-se a entrada, não a saída (`context/04` §12).

    python -m sim.rede.construir              # reconstrói a rede e os detectores
    python -m sim.rede.construir --verificar  # só confere se a saída está em dia
    python -m sim.rede.construir --regenerar-conexoes

**Aviso do netconvert é erro.** O item 1 da validação de `context/04` §12 exige
build sem aviso de conexão inválida, e um aviso que ninguém lê é um aviso que não
existe. Quem quiser ver a rede mesmo assim usa `--permitir-avisos`.

Sobre `--regenerar-conexoes`: `malha.con.xml` é fruto da inferência do próprio
netconvert, conferida e congelada como fonte (ver o cabeçalho do arquivo). Se a
geometria dos nós ou das vias mudar, a inferência precisa rodar de novo — é o que
essa opção faz, reescrevendo o arquivo a partir da rede recém-construída. Fora
esse caso, o arquivo não deve mudar.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from adapters.terminal import saida_utf8
from sim.ambiente import executavel
from sim.rede.detectores import gerar_detectores

DIRETORIO = Path(__file__).resolve().parent

#: Os cinco arquivos-fonte de `context/04` §2, na ordem em que o netconvert os lê.
FONTES = {
    "--node-files": "malha.nod.xml",
    "--edge-files": "malha.edg.xml",
    "--connection-files": "malha.con.xml",
    "--tllogic-files": "malha.tll.xml",
    "--type-files": "malha.typ.xml",
}

REDE = "malha.net.xml"
DETECTORES = "malha.det.add.xml"

#: Opções que precisam ser as mesmas em toda construção, sob pena de a rede mudar
#: de uma máquina para outra.
OPCOES = (
    # Retornos (conversão em U) nos cruzamentos criariam links a mais no
    # semáforo, mudando o comprimento das state strings do `.tll.xml` — e não
    # existem no cenário modelado.
    "--no-turnarounds",
    "true",
    "--tls.default-type",
    "static",
)


class ConstrucaoDeRedeError(RuntimeError):
    """O `netconvert` falhou, ou emitiu avisos com o modo estrito ligado."""


def _avisos(saida_de_erro: str) -> list[str]:
    return [linha for linha in saida_de_erro.splitlines() if linha.startswith("Warning:")]


def _executar_netconvert(destino: Path, prefixo_plano: Path | None = None) -> str:
    argumentos = [executavel("netconvert")]
    for opcao, arquivo in FONTES.items():
        argumentos += [opcao, str(DIRETORIO / arquivo)]
    argumentos += ["--output-file", str(destino), *OPCOES]
    if prefixo_plano is not None:
        argumentos += ["--plain-output-prefix", str(prefixo_plano)]

    resultado = subprocess.run(argumentos, capture_output=True, text=True, timeout=180)
    if resultado.returncode != 0:
        raise ConstrucaoDeRedeError(
            f"netconvert falhou (código {resultado.returncode}):\n{resultado.stderr}"
        )
    return resultado.stderr


def construir(
    *, estrito: bool = True, com_detectores: bool = True, destino: Path | None = None
) -> Path:
    """Constrói `malha.net.xml` a partir dos arquivos-fonte.

    Args:
        estrito: Se `True`, qualquer aviso do netconvert interrompe a construção.
        com_detectores: Se `True`, gera também `malha.det.add.xml`.
        destino: Caminho do `.net.xml`. Padrão: `sim/rede/malha.net.xml`.

    Returns:
        O caminho da rede construída.

    Raises:
        ConstrucaoDeRedeError: se o netconvert falhar ou avisar em modo estrito.
    """
    destino = destino or DIRETORIO / REDE
    erros = _executar_netconvert(destino)

    if avisos := _avisos(erros):
        if estrito:
            raise ConstrucaoDeRedeError(
                "netconvert emitiu avisos (context/04 §12 exige zero):\n  "
                + "\n  ".join(avisos)
            )
        for aviso in avisos:
            print(f"  {aviso}", file=sys.stderr)

    if com_detectores:
        gerar_detectores(destino, destino.with_name(DETECTORES))

    return destino


def regenerar_conexoes() -> Path:
    """Reescreve `malha.con.xml` a partir da inferência do netconvert.

    Preserva o cabeçalho explicativo do arquivo atual — ele documenta por que o
    arquivo é congelado, e perdê-lo a cada regeneração transformaria a decisão em
    folclore oral.

    Returns:
        O caminho de `malha.con.xml`.
    """
    conexoes = DIRETORIO / FONTES["--connection-files"]
    cabecalho = _cabecalho_de(conexoes)

    with tempfile.TemporaryDirectory() as temporario:
        area = Path(temporario)
        _executar_netconvert(area / REDE, prefixo_plano=area / "plano")
        gerado = (area / "plano.con.xml").read_text(encoding="utf-8")

    corpo = gerado[gerado.index("<connections") :]
    conexoes.write_text(cabecalho + corpo, encoding="utf-8")
    return conexoes


def _cabecalho_de(arquivo: Path) -> str:
    """Tudo do arquivo até (exclusive) a tag `<connections`."""
    texto = arquivo.read_text(encoding="utf-8")
    return texto[: texto.index("<connections")]


def verificar() -> list[str]:
    """Confere se a rede gerada está em dia com os arquivos-fonte.

    Reconstrói numa área temporária e compara com o que está no disco. Um
    `.net.xml` velho é a classe de erro mais traiçoeira aqui: tudo roda, os
    números saem, e eles descrevem uma malha que não existe mais.

    Returns:
        Lista de problemas. Vazia significa que está tudo em dia.
    """
    rede = DIRETORIO / REDE
    if not rede.is_file():
        return [f"{rede.name} não existe — rode `python -m sim.rede.construir`"]

    with tempfile.TemporaryDirectory() as temporario:
        referencia = Path(temporario) / REDE
        _executar_netconvert(referencia)
        # O netconvert carimba data e versão no cabeçalho, então a comparação
        # tem de ignorar o comentário inicial.
        if _corpo(referencia) != _corpo(rede):
            return [f"{rede.name} está desatualizado em relação aos arquivos-fonte"]

    detectores = DIRETORIO / DETECTORES
    if not detectores.is_file():
        return [f"{detectores.name} não existe — rode `python -m sim.rede.construir`"]
    return []


def _corpo(rede: Path) -> str:
    texto = rede.read_text(encoding="utf-8")
    return texto[texto.index("<net ") :] if "<net " in texto else texto


def main(argumentos: list[str] | None = None) -> int:
    saida_utf8()
    analisador = argparse.ArgumentParser(description="Constrói a malha SUMO (entrega 3.1).")
    analisador.add_argument(
        "--permitir-avisos",
        action="store_true",
        help="não interrompe quando o netconvert avisa (context/04 §12 pede zero)",
    )
    analisador.add_argument(
        "--sem-detectores", action="store_true", help="não regenera malha.det.add.xml"
    )
    analisador.add_argument(
        "--regenerar-conexoes",
        action="store_true",
        help="reescreve malha.con.xml a partir da inferência (só se a geometria mudou)",
    )
    analisador.add_argument(
        "--verificar",
        action="store_true",
        help="não escreve nada; confere se a rede gerada está em dia",
    )
    opcoes = analisador.parse_args(argumentos)

    if opcoes.verificar:
        problemas = verificar()
        for problema in problemas:
            print(f"  {problema}", file=sys.stderr)
        print("rede em dia com os arquivos-fonte" if not problemas else "rede DESATUALIZADA")
        return 1 if problemas else 0

    if opcoes.regenerar_conexoes:
        print(f"conexões regeneradas: {regenerar_conexoes()}")

    rede = construir(estrito=not opcoes.permitir_avisos, com_detectores=not opcoes.sem_detectores)
    print(f"rede construída: {rede}")
    if not opcoes.sem_detectores:
        print(f"detectores: {rede.with_name(DETECTORES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
