"""Relatório de validação — entregável 6 do escopo (`context/06` §5).

    python -m analysis.gerar_relatorio_validacao --rodar-testes --banco
    python -m analysis.gerar_relatorio_validacao --banco          # XML já gravados
    python -m analysis.gerar_relatorio_validacao --data 20261008  # nome do arquivo

Escreve `docs/relatorios/validacao_AAAAMMDD.md` com as nove seções obrigatórias
de `context/06` §5, nesta ordem: identificação, ambiente, matriz de execuções,
rastreabilidade requisito → teste → resultado, invariantes, latências, casos de
falha, checklist do protótipo e anexos.

**Nenhum número do relatório é digitado à mão.** Cada um sai de uma destas
fontes, todas versionadas ou no banco:

* os resultados das suítes, nos XML do JUnit em `analysis/data/validacao/`
  (`--rodar-testes` roda as suítes e regrava os XML antes de gerar);
* os CSV do Bloco 8 (`analysis/data/bloco8/`) e o log do lote;
* os CSV da bancada (`latencia_bancada.csv`, `deteccoes_bancada.csv`,
  `telemetria_bancada.csv`), julgados pelos mesmos módulos do checklist
  (`analysis.checklist_bancada`) e do resumo (`analysis.resumo_bancada`);
* o próprio `context/`: a tabela de rastreabilidade de `06` §2, o checklist de
  `06` §6 e os registros de falha de `09`, lidos dos arquivos e não copiados;
* o git (versões e o hash dos arquivos de parâmetros no commit dos dados);
* com `--banco`, o PostgreSQL (`execucao_simulacao.parametros`,
  `metrica_latencia`, e os itens 9 e 15 do checklist).

O que a fonte não tem, o relatório diz que não tem: um requisito sem teste sai
SEM_TESTE, um ambiente sem dado sai "—". Nada é preenchido no lugar.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from importlib import metadata
from itertools import pairwise
from pathlib import Path
from typing import Final

from adapters.terminal import saida_utf8
from analysis import checklist_bancada as checklist
from analysis.resumo_bancada import (
    BYTES_CARIMBO_ATRASADO,
    CSV_DETECCOES,
    CSV_LATENCIA,
    LIMIAR_H3_MS,
    PASSAGENS_PREVISTAS,
    TAXA_MINIMA_RNF05,
    AmostraH3,
    ler_amostras,
    ler_leituras,
)
from bridge.protocolo import TipoEvento
from bridge.registro import CSV_TELEMETRIA_PADRAO
from bridge.verificar import FOLGA_MS, violacoes
from sim.controlador.coletor import percentil

RAIZ: Final = Path(__file__).resolve().parents[1]
DADOS_BLOCO8: Final = RAIZ / "analysis" / "data" / "bloco8"
PASTA_JUNIT: Final = RAIZ / "analysis" / "data" / "validacao"
SAIDA_PADRAO: Final = RAIZ / "docs" / "relatorios"
CONTEXTO: Final = RAIZ / "context"

#: A sessão da ponte das 100 passagens de RNF05 e H3 (`06` §6, itens 4 e 7b). É
#: o endereço da medição, não um resultado; o mesmo de
#: `analysis.gerar_resultados_tcc.SESSAO_H3`, conferido por teste.
SESSAO_H3: Final = "2026-10-07T16:18:08.177357+00:00"

#: As rodadas do item 5 do checklist (tag fora do mapa), `06` §6 e `09`: as duas
#: primeiras sem veredito, a terceira a registrada. O item 5 só é julgado nelas;
#: em outra sessão a tag fora do mapa não passou, e a janela não teria sentido.
SESSOES_ITEM_5: Final = (
    "2026-10-08T00:25:27.959038+00:00",
    "2026-10-08T00:28:01.131486+00:00",
    "2026-10-08T00:32:44.495549+00:00",
)

#: RF02: da detecção ao início da atuação, em até 3 s (decisão P14).
LIMITE_RF02_MS: Final = 3000.0

#: RNF01: p95 da latência de decisão abaixo disto.
ORCAMENTO_RNF01_MS: Final = 100.0

#: RNF02 na bancada: o item 12 pede 30 min contínuos.
SOAK_BANCADA_MIN: Final = 30.0

#: I5: nenhum acesso em vermelho por mais que isto (`01` §6).
VERMELHO_MAX_MS: Final = 120_000

#: Os XML do JUnit que o relatório lê, e o comando que grava cada um.
SUITES: Final = {
    "pytest_padrao.xml": "python -m pytest (suíte padrão, com os testes de banco)",
    "pytest_sumo.xml": "python -m pytest -m sumo",
    "vitest.xml": "npx vitest run (frontend)",
}

#: Arquivos que fixam o comportamento do motor e da simulação. O hash de cada
#: um é tirado **no commit dos dados** do Bloco 8, com `git show`.
ARQUIVOS_DE_PARAMETROS: Final = (
    "backend/config/parametros.yaml",
    "backend/config/parametros.hardware.yaml",
    "backend/config/politica_desempate.yaml",
    "sim/config/cenarios.yaml",
    "sim/config/mapa_fases.yaml",
    "sim/demanda/veiculos.typ.xml",
    "sim/rede/malha.nod.xml",
    "sim/rede/malha.edg.xml",
    "sim/rede/malha.con.xml",
    "sim/rede/malha.tll.xml",
    "sim/rede/malha.typ.xml",
)

#: Pacotes cuja versão vai para a seção de ambiente.
PACOTES: Final = (
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "alembic",
    "psycopg",
    "pydantic",
    "pyjwt",
    "httpx",
    "pyyaml",
    "structlog",
    "pyserial",
    "numpy",
    "scipy",
    "pandas",
    "matplotlib",
    "pytest",
    "hypothesis",
    "testcontainers",
    "ruff",
    "mypy",
)

#: Os casos de falha de `context/09` que vão para a seção 7, cada um pelo
#: começo do texto da coluna "Item" da tabela de decisões. O texto é lido do
#: arquivo, não copiado: um registro que mudar em `09` muda aqui. Um teste
#: confere que cada chave casa com exatamente uma linha.
FALHAS_EM_09: Final = (
    "**I4 verificado por transição, não por par**",
    "**`ESTENDER_VERDE` conta a partir de agora**",
    "**E7 passa a ser executada, e não só calculada**",
    "**`queue.xml` sai do padrão; `summary` agregado a 60 s**",
    "**Cada execução do lote limpa os CSV da própria pasta antes de rodar**",
    "**O pareamento da análise é por VE, não por execução**",
    "**Removida a linha `leve/PREEMPCAO/seed=42` de `execucao_simulacao`**",
    "**P16 resolvida pelo mecanismo, sem tocar em H1**",
    "**Defeito de posição do VE dentro do cruzamento, corrigido**",
    "**Firmware do UNO reescrito preservando o comportamento**",
    "**Achado da primeira captura na bancada, antes de gravar o firmware novo**",
    "**Gravação do UNO por `python -m bridge.gravar_uno`, e não pelo `arduino-cli upload`**",
    "**Linha pela metade seguida de 100 ms de silêncio é descartada**",
    "**O boot publica a `ST` do all-red; o roteiro exige all-red de pelo menos 1 s**",
    "**O `millis()` do dublê do UNO trunca, como o da placa**",
    "**Saída dos `python -m` em UTF-8**",
    "**`versao_do_codigo()` marca árvore suja**",
    "**Rodada de RNF05 e H3 feita; duas leituras repostas**",
    "**Carimbo atrasado: as amostras ficam, e o resumo ganha uma linha de sensibilidade**",
    "**Checklist: dois ajustes no script depois da rodada, sem mudar limite**",
    "**Item 5 do checklist feito, com dois desvios do roteiro declarado**",
    "**A abertura do COM5 reinicia o emissor, e o lixo do boot suja a primeira linha da sessão**",
    "**Bloco 8 rodado: 650 execuções, 0 descarte**",
    "**Um carrinho por tipo: a bancada ganha os emissores do bombeiro e da polícia**",
    '**Item 15 do checklist: lista da Central `000` no BOOT sai "sem veredito"**',
    "**RF03 não é cumprido ao pé da letra no Bloco 8**",
    "**Quatro arquivos de teste de `06` §2 não existiam**",
)

#: A evidência de cada invariante nas suítes. A bancada (I1 a I4 e I6) tem a
#: sua: o firmware contra o dublê e o verificador da telemetria.
TESTES_DOS_INVARIANTES: Final = {
    "I1": (
        "backend/tests/core/test_seguranca.py",
        "backend/tests/core/test_invariantes_property.py",
        "tests/firmware/test_firmware_uno.py",
        "bridge/tests/test_verificar.py",
    ),
    "I2": (
        "backend/tests/core/test_seguranca.py",
        "backend/tests/core/test_invariantes_property.py",
        "tests/firmware/test_firmware_uno.py",
        "bridge/tests/test_verificar.py",
    ),
    "I3": (
        "backend/tests/core/test_seguranca.py",
        "backend/tests/core/test_invariantes_property.py",
        "tests/firmware/test_firmware_uno.py",
        "bridge/tests/test_verificar.py",
    ),
    "I4": (
        "backend/tests/core/test_seguranca.py",
        "backend/tests/core/test_invariantes_property.py",
        "tests/firmware/test_firmware_uno.py",
        "bridge/tests/test_verificar.py",
    ),
    "I5": ("backend/tests/core/test_seguranca.py", "backend/tests/core/test_motor.py"),
    "I6": ("tests/firmware/test_firmware_uno.py", "bridge/tests/test_verificar.py"),
}

PASSOU, FALHOU, XFAIL, PULADO = "PASSOU", "FALHOU", "XFAIL", "PULADO"
SEM_TESTE = "SEM TESTE"


# ---------------------------------------------------------------------------
# Resultados das suítes (JUnit)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CasoDeTeste:
    """Um `<testcase>` de um XML do JUnit."""

    suite: str
    classe: str
    nome: str
    desfecho: str
    propriedades: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Execucao:
    """Um XML do JUnit: quando rodou e os casos."""

    arquivo: str
    instante: str
    casos: tuple[CasoDeTeste, ...]


def ler_junit(caminho: Path) -> Execucao:
    """Lê um XML do JUnit do pytest ou do Vitest.

    Desfechos: falha e erro viram `FALHOU`; o `skipped` do tipo `pytest.xfail`,
    `XFAIL` (uma falha esperada continua sendo falha do requisito); outro
    `skipped`, `PULADO`. Um `xpass` estrito vem como falha, e é falha.
    """
    raiz = ET.parse(caminho).getroot()
    suites = [raiz] if raiz.tag == "testsuite" else list(raiz.iter("testsuite"))
    instante = next((s.get("timestamp", "") for s in suites if s.get("timestamp")), "")
    casos = []
    for suite in suites:
        for caso in suite.iter("testcase"):
            if caso.find("failure") is not None or caso.find("error") is not None:
                desfecho = FALHOU
            elif (pulado := caso.find("skipped")) is not None:
                desfecho = XFAIL if pulado.get("type") == "pytest.xfail" else PULADO
            else:
                desfecho = PASSOU
            propriedades = {p.get("name", ""): p.get("value", "") for p in caso.iter("property")}
            casos.append(
                CasoDeTeste(
                    caminho.name,
                    caso.get("classname", ""),
                    caso.get("name", ""),
                    desfecho,
                    propriedades,
                )
            )
    return Execucao(caminho.name, instante, tuple(casos))


def ler_suites(pasta: Path) -> list[Execucao]:
    """Os XML de `SUITES` que existirem em `pasta`."""
    return [ler_junit(pasta / nome) for nome in SUITES if (pasta / nome).is_file()]


def casos_do_arquivo(casos: Iterable[CasoDeTeste], arquivo: str) -> list[CasoDeTeste]:
    """Os casos de um arquivo de teste, como `06` §2 o nomeia.

    * `test_x.py` casa com qualquer módulo `test_x` (o pytest põe o caminho
      pontuado em `classname`);
    * `pasta/test_x.py` só com o módulo daquele caminho;
    * `frontend/src/...` (com `*` e `(x)`) com o caminho do arquivo do Vitest,
      que vem relativo a `frontend/`.
    """
    if arquivo.endswith(".py"):
        modulo = arquivo[: -len(".py")]
        if "/" in modulo:
            pontuado = modulo.replace("/", ".")
            return [c for c in casos if c.classe == pontuado or c.classe.startswith(pontuado + ".")]
        return [c for c in casos if modulo in c.classe.split(".")]
    padrao = re.escape(arquivo.removeprefix("frontend/"))
    padrao = padrao.replace(r"\*", "[^/]*").replace(r"\(x\)", "x?")
    return [c for c in casos if re.fullmatch(padrao, c.classe)]


@dataclass(frozen=True)
class Placar:
    """Quantos casos de cada desfecho."""

    passou: int = 0
    falhou: int = 0
    xfail: int = 0
    pulado: int = 0

    @classmethod
    def de(cls, casos: Iterable[CasoDeTeste]) -> Placar:
        contagem = Counter(c.desfecho for c in casos)
        return cls(contagem[PASSOU], contagem[FALHOU], contagem[XFAIL], contagem[PULADO])

    @property
    def total(self) -> int:
        return self.passou + self.falhou + self.xfail + self.pulado

    @property
    def status(self) -> str:
        if self.total == 0:
            return SEM_TESTE
        if self.falhou:
            return FALHOU
        if self.xfail:
            return f"{FALHOU} (falha esperada, xfail)"
        if self.passou == 0:
            return "NÃO EXECUTADO"
        return PASSOU

    def texto(self) -> str:
        partes = [f"{self.passou}/{self.total} passaram"]
        if self.falhou:
            partes.append(f"{self.falhou} falharam")
        if self.xfail:
            partes.append(f"{self.xfail} xfail")
        if self.pulado:
            partes.append(f"{self.pulado} pulados")
        return ", ".join(partes)


# ---------------------------------------------------------------------------
# context/: tabelas lidas dos arquivos
# ---------------------------------------------------------------------------


def _celulas(linha: str) -> list[str]:
    return [celula.strip() for celula in linha.strip().strip("|").split("|")]


def tabela_da_secao(texto: str, titulo: str) -> list[list[str]]:
    """As linhas de dados da primeira tabela depois do título `titulo`."""
    inicio = texto.index(titulo)
    linhas: list[list[str]] = []
    cabecalho_visto = False
    for linha in texto[inicio:].splitlines()[1:]:
        if linha.startswith("|"):
            if not cabecalho_visto:
                cabecalho_visto = True
                continue
            if re.fullmatch(r"\|[\s:|-]+\|", linha.strip()):
                continue
            linhas.append(_celulas(linha))
        elif cabecalho_visto:
            break
    return linhas


@dataclass(frozen=True)
class Requisito:
    """Uma linha de `06` §2."""

    codigo: str
    caso: str
    criterio: str
    arquivo: str

    @property
    def arquivos_de_teste(self) -> list[str]:
        """Os arquivos de teste citados, sem o que é evidência de bancada."""
        return [a for a in re.findall(r"`([^`]+)`", self.arquivo) if "test" in a]

    @property
    def bancada(self) -> bool:
        return "checklist" in self.arquivo.lower() or "bancada" in self.arquivo.lower()


def ler_rastreabilidade(caminho: Path = CONTEXTO / "06-testes-e-validacao.md") -> list[Requisito]:
    """A tabela de rastreabilidade de `06` §2."""
    texto = caminho.read_text(encoding="utf-8")
    return [Requisito(*linha[:4]) for linha in tabela_da_secao(texto, "## 2. Casos de teste")]


@dataclass(frozen=True)
class ItemChecklist:
    """Uma linha de `06` §6."""

    item: str
    verificacao: str
    ok: str


def ler_checklist(caminho: Path = CONTEXTO / "06-testes-e-validacao.md") -> list[ItemChecklist]:
    texto = caminho.read_text(encoding="utf-8")
    return [
        ItemChecklist(*linha[:3])
        for linha in tabela_da_secao(texto, "## 6. Checklist de aceitação")
    ]


@dataclass(frozen=True)
class RegistroDe09:
    """Uma linha da tabela de decisões de `09`."""

    data: str
    item: str
    decisao: str
    justificativa: str


def ler_registros_de_09(
    chaves: Sequence[str] = FALHAS_EM_09,
    caminho: Path = CONTEXTO / "09-pendencias-e-decisoes.md",
) -> list[RegistroDe09]:
    """As linhas de `09` cujo "Item" começa por cada chave, na ordem das chaves.

    Raises:
        ValueError: se uma chave não casar com exatamente uma linha.
    """
    texto = caminho.read_text(encoding="utf-8")
    linhas = tabela_da_secao(texto, "## Decisões tomadas")
    registros = []
    for chave in chaves:
        achadas = [linha for linha in linhas if linha[1].startswith(chave)]
        if len(achadas) != 1:
            raise ValueError(f"{len(achadas)} linhas de 09 para {chave!r}")
        registros.append(RegistroDe09(*achadas[0][:4]))
    return registros


def ler_equipe(caminho: Path = CONTEXTO / "00-visao-geral.md") -> list[str]:
    """Os nomes da equipe, da tabela de identificação de `00` §1."""
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if linha.startswith("| Equipe |"):
            return [nome.strip() for nome in _celulas(linha)[1].split("),")]
    return []


# ---------------------------------------------------------------------------
# Git, SUMO e ambiente
# ---------------------------------------------------------------------------


def _rodar(*comando: str, cwd: Path = RAIZ) -> str | None:
    try:
        resultado = subprocess.run(comando, cwd=cwd, capture_output=True, check=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return resultado.stdout.decode("utf-8", errors="replace").strip()


#: O que não conta para `-suja`: os dados e a documentação, que a própria geração
#: do relatório regrava (os XML do JUnit e o `.md`). A mesma regra de
#: `sim.controlador.executor.FORA_DA_VERSAO`.
FORA_DA_VERSAO: Final = (
    ":(exclude)analysis/data",
    ":(exclude)docs",
    ":(exclude)context",
    ":(exclude)*.md",
)


def git_head() -> str:
    """O commit do repositório, com `-suja` se há código modificado fora dele."""
    head = _rodar("git", "rev-parse", "HEAD") or "—"
    status = _rodar("git", "status", "--porcelain", "--", ".", *FORA_DA_VERSAO)
    return f"{head}-suja" if status else head


def hash_no_commit(commit: str, arquivo: str) -> str | None:
    """sha256 do arquivo como ele está no commit, ou `None` se não estiver."""
    try:
        conteudo = subprocess.run(
            ["git", "show", f"{commit}:{arquivo}"],
            cwd=RAIZ,
            capture_output=True,
            check=True,
            timeout=60,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return hashlib.sha256(conteudo).hexdigest()


def versao_do_sumo() -> str:
    try:
        from sim.ambiente import executavel

        saida = _rodar(executavel("sumo"), "--version")
    except Exception:  # SUMO ausente não impede o relatório
        saida = None
    return saida.splitlines()[0] if saida else "—"


def _memoria_total_bytes() -> int | None:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Estado(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        estado = Estado()
        estado.dwLength = ctypes.sizeof(Estado)
        if ctypes.WinDLL("kernel32").GlobalMemoryStatusEx(ctypes.byref(estado)):
            return int(estado.ullTotalPhys)
        return None
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        for linha in meminfo.read_text(encoding="ascii").splitlines():
            if linha.startswith("MemTotal:"):
                return int(linha.split()[1]) * 1024
    return None


def ambiente() -> list[tuple[str, str]]:
    """O que a máquina e as ferramentas dizem de si, no momento da geração."""
    memoria = _memoria_total_bytes()
    linhas = [
        ("Sistema operacional", platform.platform()),
        ("Processador", platform.processor() or platform.machine()),
        ("Núcleos lógicos", str(os.cpu_count() or "—")),
        ("Memória", "—" if memoria is None else f"{memoria / 2**30:.1f} GiB"),
        ("Python", platform.python_version()),
        ("SUMO", versao_do_sumo()),
        ("Node.js", _rodar("node", "--version") or "—"),
        ("Docker", _rodar("docker", "--version") or "—"),
        ("arduino-cli", (_rodar("arduino-cli", "version") or "—").splitlines()[0]),
    ]
    nucleos = _rodar("arduino-cli", "core", "list")
    if nucleos:
        for linha in nucleos.splitlines()[1:]:
            partes = linha.split()
            if len(partes) >= 2:
                linhas.append((f"Núcleo Arduino {partes[0]}", partes[1]))
    for pacote in PACOTES:
        try:
            linhas.append((pacote, metadata.version(pacote)))
        except metadata.PackageNotFoundError:
            linhas.append((pacote, "não instalado"))
    return linhas


# ---------------------------------------------------------------------------
# Bloco 8
# ---------------------------------------------------------------------------


def _csv(caminho: Path) -> list[dict[str, str]]:
    if not caminho.is_file():
        return []
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


@dataclass(frozen=True)
class Lote:
    """O que o Bloco 8 deixou versionado."""

    execucoes: list[dict[str, str]]
    descartes: list[dict[str, str]]
    planejadas: int | None
    latencias: list[dict[str, str]]

    @property
    def versoes(self) -> list[str]:
        return sorted({linha["versao_codigo"] for linha in self.execucoes})


def ler_lote(pasta: Path = DADOS_BLOCO8) -> Lote:
    """Os CSV do lote e o número planejado, da primeira linha do log."""
    planejadas = None
    log = pasta / "lote_bloco8.log"
    if log.is_file():
        with log.open(encoding="utf-8", errors="replace") as arquivo:
            primeira = arquivo.readline()
        if casamento := re.match(r"lote: (\d+) execuções", primeira):
            planejadas = int(casamento[1])
    return Lote(
        execucoes=_csv(pasta / "execucoes.csv"),
        descartes=_csv(pasta / "descartes.csv"),
        planejadas=planejadas,
        latencias=_csv(pasta / "latencias.csv"),
    )


# ---------------------------------------------------------------------------
# Bancada
# ---------------------------------------------------------------------------


@dataclass
class Bancada:
    """A telemetria gravada, já separada por sessão e trecho."""

    sessoes: dict[str, list[checklist.Linha]]

    def partes(self, sessao: str) -> list[checklist.Trecho]:
        return checklist.trechos(self.sessoes[sessao])

    def todas_as_partes(self) -> list[checklist.Trecho]:
        return [parte for sessao in sorted(self.sessoes) for parte in self.partes(sessao)]


def ler_bancada(caminho: Path = CSV_TELEMETRIA_PADRAO) -> Bancada:
    return Bancada(checklist.ler_sessoes(caminho) if caminho.is_file() else {})


@dataclass(frozen=True)
class InvariantesDaBancada:
    """I1 a I6 sobre toda a telemetria gravada."""

    sts: int
    mudancas_de_luz: int
    achados: dict[str, int]
    vermelho_mais_longo_ms: int
    timeouts: int
    timeouts_ok: int
    emergencias: int
    fins_por_duracao: int


def invariantes_da_bancada(bancada: Bancada) -> InvariantesDaBancada:
    """Conta as violações de I1 a I4 e I6, e o maior vermelho (I5), sessão a sessão.

    I2, I3 e I4 são os achados de `bridge.verificar.violacoes`, com a mesma
    folga do checklist (60 ms). I1 é a `ST` com verde nos dois eixos. I6 é o
    critério do item 11: todo `TIMEOUT` a 30 s do `PREEMP_INI` que abriu a
    emergência, com a volta pelo eixo oposto.
    """
    achados: Counter[str] = Counter()
    sts = mudancas = vermelho_max = 0
    timeouts = timeouts_ok = emergencias = fins = 0
    for sessao in sorted(bancada.sessoes):
        partes = bancada.partes(sessao)
        for trecho in partes:
            seq = [(st.t_dispositivo_ms, st.estado) for st in trecho.sts]
            sts += len(seq)
            achados["I1"] += sum(1 for st in trecho.sts if st.viola_i1)
            for achado in violacoes(seq, folga_ms=FOLGA_MS):
                rotulo = achado.split(":")[0]
                if rotulo != "I1":  # I1 já vem da ST, uma por estado, não por transição
                    achados[rotulo if rotulo in {"I2", "I3", "I4"} else "I2"] += 1
            mudancas += sum(1 for a, b in pairwise(seq) if a[1] != b[1])
            vermelho_max = max(vermelho_max, _vermelho_mais_longo(seq))
            emergencias += len(trecho.eventos(TipoEvento.PREEMP_INI))
            fins += len(trecho.eventos(TipoEvento.PREEMP_FIM))
        resultado = checklist.item_11(partes)
        timeouts += len(resultado.detalhes)
        timeouts_ok += sum(1 for d in resultado.detalhes if d.endswith("— ok"))
    return InvariantesDaBancada(
        sts, mudancas, dict(achados), vermelho_max, timeouts, timeouts_ok, emergencias, fins
    )


def _vermelho_mais_longo(seq: Sequence[tuple[int, str]]) -> int:
    """O maior intervalo, em ms do UNO, em que uma aproximação ficou vermelha."""
    maior = 0
    for i in range(4):
        desde: int | None = None
        for ms, estado in seq:
            if estado[i] == "R":
                desde = ms if desde is None else desde
            elif desde is not None:
                maior = max(maior, ms - desde)
                desde = None
    return maior


def maior_sessao_sem_reinicio_min(bancada: Bancada) -> float:
    """A maior duração, no relógio do notebook, de um trecho sem reinício do UNO."""
    maior = 0.0
    for sessao in bancada.sessoes:
        for trecho in bancada.partes(sessao):
            com_st = [linha.t for linha in trecho.linhas if linha.st is not None]
            if len(com_st) > 1:
                maior = max(maior, (com_st[-1] - com_st[0]).total_seconds() / 60.0)
    return maior


# ---------------------------------------------------------------------------
# Banco (opcional)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DoBanco:
    """O que o relatório lê do PostgreSQL."""

    snapshots: dict[str, int]
    execucoes_da_versao: int
    latencias: list[tuple[str, int, float, float, float, float, float]]


def ler_banco(url: str, versoes: Sequence[str]) -> DoBanco:
    import psycopg

    with psycopg.connect(url) as conexao:
        linhas = conexao.execute(
            "SELECT parametros FROM execucao_simulacao WHERE versao_codigo = ANY(%s)",
            (list(versoes),),
        ).fetchall()
        latencias = conexao.execute(
            "SELECT ambiente::text, count(*), "
            "min(coalesce(latencia_decisao_ms, latencia_total_ms)), "
            "avg(coalesce(latencia_decisao_ms, latencia_total_ms)), "
            "percentile_disc(0.95) WITHIN GROUP "
            "(ORDER BY coalesce(latencia_decisao_ms, latencia_total_ms)), "
            "percentile_disc(0.99) WITHIN GROUP "
            "(ORDER BY coalesce(latencia_decisao_ms, latencia_total_ms)), "
            "max(coalesce(latencia_decisao_ms, latencia_total_ms)) "
            "FROM metrica_latencia GROUP BY 1 ORDER BY 1"
        ).fetchall()
    snapshots: Counter[str] = Counter(
        hashlib.sha256(
            json.dumps(linha[0], sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        for linha in linhas
    )
    return DoBanco(
        dict(snapshots),
        len(linhas),
        [(str(a), int(n), *(float(v) for v in valores)) for a, n, *valores in latencias],
    )


# ---------------------------------------------------------------------------
# Formatação
# ---------------------------------------------------------------------------


def _n(valor: float, casas: int = 1) -> str:
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(fracao: float) -> str:
    return f"{_n(100.0 * fracao)}%"


def _tabela(cabecalho: Sequence[str], linhas: Iterable[Sequence[str]]) -> list[str]:
    def limpo(celula: str) -> str:
        return str(celula).replace("|", "\\|").replace("\n", " ")

    corpo = [[limpo(c) for c in linha] for linha in linhas]
    # O pandoc reparte a largura das colunas no PDF pelo número de traços da
    # linha separadora: proporcional ao conteúdo, com piso e teto, para "#" não
    # sair tão largo quanto o texto do checklist.
    tracos = [
        min(max(len(str(titulo)), *(len(linha[i]) for linha in corpo), 3), TETO_DA_COLUNA)
        for i, titulo in enumerate(cabecalho)
    ]
    saida = [
        "| " + " | ".join(cabecalho) + " |",
        "| " + " | ".join("-" * n for n in tracos) + " |",
    ]
    saida += ["| " + " | ".join(linha) + " |" for linha in corpo]
    return [*saida, ""]


#: Teto de traços de uma coluna no separador (ver `_tabela`).
TETO_DA_COLUNA: Final = 60


def _estatisticas(valores: Sequence[float], casas: int = 3) -> list[str]:
    return [
        str(len(valores)),
        _n(min(valores), casas),
        _n(statistics.fmean(valores), casas),
        _n(percentil(valores, 95), casas),
        _n(percentil(valores, 99), casas),
        _n(max(valores), casas),
    ]


# ---------------------------------------------------------------------------
# Seções
# ---------------------------------------------------------------------------


@dataclass
class Entradas:
    """Tudo o que o relatório lê, carregado uma vez."""

    data: date
    suites: list[Execucao]
    lote: Lote
    bancada: Bancada
    amostras_h3: list[AmostraH3]
    leituras: dict[str, list[checklist.LeituraEmissor]]
    rastreabilidade: list[Requisito]
    checklist_06: list[ItemChecklist]
    falhas: list[RegistroDe09]
    equipe: list[str]
    banco: DoBanco | None = None
    url_banco: str | None = None
    ambiente: list[tuple[str, str]] = field(default_factory=list)
    head: str = "—"
    sumo: str = "—"

    @property
    def casos(self) -> list[CasoDeTeste]:
        return [caso for suite in self.suites for caso in suite.casos]


def secao_identificacao(e: Entradas) -> list[str]:
    commit_dados = e.lote.versoes[0] if len(e.lote.versoes) == 1 else None
    versoes_bancada = sorted({a.versao_codigo for a in e.amostras_h3 if a.sessao == SESSAO_H3})
    linhas = [
        "## 1. Identificação",
        "",
        *_tabela(
            ("Campo", "Valor"),
            [
                ("Data da geração", e.data.isoformat()),
                ("Código que gerou o relatório (`git rev-parse HEAD`)", f"`{e.head}`"),
                (
                    "Código das 650 execuções do Bloco 8 (`execucoes.csv`)",
                    ", ".join(f"`{v}`" for v in e.lote.versoes) or "—",
                ),
                (
                    "Código da ponte nas 100 passagens de H3",
                    ", ".join(f"`{v}`" for v in versoes_bancada) or "—",
                ),
                ("Versão do SUMO (na geração)", e.sumo),
            ],
        ),
        "> O lote não grava a versão do SUMO. A linha acima é a do SUMO instalado quando",
        "> o relatório foi gerado, e só vale para o Bloco 8 se ele não foi trocado depois",
        "> (`docs/plano-desenvolvimento.md`, Bloco 0, registra a instalação da 1.27.1).",
        "",
        "### Hash dos parâmetros",
        "",
    ]
    if commit_dados is None:
        linhas += ["Sem um commit único nos dados do Bloco 8: hash não calculado.", ""]
    else:
        commit_limpo = commit_dados.removesuffix("-suja")
        linhas.append(
            f"sha256 de cada arquivo como está no commit dos dados (`{commit_limpo}`), "
            "e se continua igual no `HEAD`:"
        )
        linhas.append("")
        tabela = []
        for arquivo in ARQUIVOS_DE_PARAMETROS:
            no_commit = hash_no_commit(commit_limpo, arquivo)
            atual = hash_no_commit("HEAD", arquivo)
            mudou = no_commit is not None and no_commit != atual
            commits = _rodar("git", "log", "--format=%h %s", f"{commit_limpo}..HEAD", "--", arquivo)
            tabela.append(
                (
                    f"`{arquivo}`",
                    "—" if no_commit is None else f"`{no_commit[:16]}`",
                    "—" if no_commit is None else ("mudou" if mudou else "igual"),
                    "<br>".join(f"`{c}`" for c in (commits or "").splitlines()) if mudou else "",
                )
            )
        linhas += _tabela(
            ("Arquivo", "sha256 (16 primeiros)", "No HEAD", "Commits que o mudaram depois"), tabela
        )
    if e.banco is not None:
        linhas.append(
            f"No banco, `execucao_simulacao.parametros` das {e.banco.execucoes_da_versao} "
            f"execuções de {', '.join(f'`{v}`' for v in e.lote.versoes)}: "
            f"{len(e.banco.snapshots)} snapshot(s) distinto(s) — "
            + "; ".join(f"`{h[:16]}` em {n}" for h, n in sorted(e.banco.snapshots.items()))
            + " (sha256 do JSON com chaves ordenadas)."
        )
        linhas.append("")
    return linhas


def secao_ambiente(e: Entradas) -> list[str]:
    return [
        "## 2. Ambiente de teste",
        "",
        "A máquina e as ferramentas onde o relatório e as suítes rodaram. O log do lote",
        "não registra a máquina; o lote rodou num worktree no mesmo notebook (`09`,",
        '"Bloco 8 rodado").',
        "",
        *_tabela(("Item", "Versão / valor"), e.ambiente),
    ]


def secao_matriz(e: Entradas) -> list[str]:
    lote = e.lote
    contagem = Counter((linha["cenario"], linha["modo"]) for linha in lote.execucoes)
    seeds = sorted({int(linha["seed"]) for linha in lote.execucoes})
    por_tipo = Counter(linha["tipo"] for linha in lote.descartes)
    motivos = Counter((linha["tipo"], linha["detalhe"]) for linha in lote.descartes)
    linhas = [
        "## 3. Matriz de execuções",
        "",
        f"- Planejadas (primeira linha de `lote_bloco8.log`): "
        f"{'—' if lote.planejadas is None else lote.planejadas}",
        f"- Válidas (`execucoes.csv`): {len(lote.execucoes)}",
        f"- Seeds: {seeds[0]}..{seeds[-1]} ({len(seeds)})" if seeds else "- Seeds: —",
        f"- Registros em `descartes.csv`: {len(lote.descartes)}"
        + (
            " (" + ", ".join(f"{tipo}: {n}" for tipo, n in sorted(por_tipo.items())) + ")"
            if por_tipo
            else ""
        ),
        "",
        *_tabela(
            ("Cenário", "Modo", "Execuções válidas"),
            [(c, m, str(n)) for (c, m), n in sorted(contagem.items())],
        ),
    ]
    if motivos:
        linhas += ["Motivo de cada registro de `descartes.csv`:", ""]
        linhas += _tabela(
            ("Tipo", "Motivo", "Registros"),
            [(tipo, detalhe, str(n)) for (tipo, detalhe), n in sorted(motivos.items())],
        )
        linhas += [
            "`REEXECUCAO` não é execução reprovada: é a remoção, registrada, das linhas que",
            "uma corrida interrompida deixou no banco, antes de rodar tudo de novo (`06` §4).",
            f"Reprovadas por `validar_execucao()` (`DESCARTE` ou `FALHA`): "
            f"{por_tipo.get('DESCARTE', 0) + por_tipo.get('FALHA', 0)}.",
            "",
        ]
    if lote.planejadas is not None and lote.planejadas != len(lote.execucoes):
        linhas += [
            f"> **Atenção:** {lote.planejadas - len(lote.execucoes)} execuções planejadas "
            "não estão entre as válidas.",
            "",
        ]
    return linhas


@dataclass(frozen=True)
class EvidenciaDeBancada:
    texto: str
    atende: bool | None


def evidencia_de_bancada(codigo: str, e: Entradas) -> EvidenciaDeBancada | None:
    """O dado gravado na bancada que sustenta o requisito, julgado pelo critério de `06`."""
    h3 = [a.latencia_total_ms for a in e.amostras_h3 if a.sessao == SESSAO_H3]
    if codigo == "RF02" and h3:
        maximo = max(h3)
        return EvidenciaDeBancada(
            f"Bancada, item 7: maior latência das {len(h3)} passagens de H3 = "
            f"{_n(maximo)} ms (limite {_n(LIMITE_RF02_MS, 0)} ms)",
            maximo < LIMITE_RF02_MS,
        )
    if codigo == "H3" and h3:
        p95 = percentil(h3, 95)
        return EvidenciaDeBancada(
            f"Bancada, item 7b: p95 = {_n(p95)} ms em n = {len(h3)} (limite "
            f"{_n(LIMIAR_H3_MS, 0)} ms)",
            p95 < LIMIAR_H3_MS and len(h3) >= PASSAGENS_PREVISTAS,
        )
    if codigo == "RNF05":
        leituras = [x for x in ler_leituras(CSV_DETECCOES) if x.sessao == SESSAO_H3]
        if leituras:
            chegaram = sum(1 for x in leituras if x.chegou)
            taxa = chegaram / len(leituras)
            return EvidenciaDeBancada(
                f"Bancada, item 4: {chegaram} de {len(leituras)} leituras chegaram ao UNO com "
                f"a rua certa ({_pct(taxa)}; mínimo {_pct(TAXA_MINIMA_RNF05)}), emissor no USB",
                taxa >= TAXA_MINIMA_RNF05 and len(leituras) >= PASSAGENS_PREVISTAS,
            )
    if codigo == "RNF02" and e.bancada.sessoes:
        minutos = maior_sessao_sem_reinicio_min(e.bancada)
        return EvidenciaDeBancada(
            f"Bancada, item 12: maior operação contínua sem reinício do UNO = "
            f"{_n(minutos)} min (pedido: {_n(SOAK_BANCADA_MIN, 0)} min, relógio de parede)",
            minutos >= SOAK_BANCADA_MIN,
        )
    if codigo == "RF03" and e.lote.execucoes:
        return _evidencia_rf03()
    return None


def _evidencia_rf03() -> EvidenciaDeBancada:
    """VEs sem parada no braço `PREEMPCAO`, e quanto esperam os que param.

    A espera é `tempo_espera_s` de `ve_por_execucao.csv` (mediana dos VEs com
    ao menos uma parada), ao lado da mediana do `FIXO` do mesmo cenário: o
    tamanho das paradas que sobram, que a contagem sozinha não mostra.
    """
    ves = _csv(DADOS_BLOCO8 / "ve_por_execucao.csv")
    partes = []
    todos_sem_parada = True
    for cenario in sorted({v["cenario"] for v in ves}):
        do_braco = [v for v in ves if v["cenario"] == cenario and v["modo"] == "PREEMPCAO"]
        if not do_braco:
            continue
        sem = sum(1 for v in do_braco if int(v["paradas"]) == 0)
        todos_sem_parada &= sem == len(do_braco)
        pararam = [float(v["tempo_espera_s"]) for v in do_braco if int(v["paradas"]) > 0]
        fixo = [
            float(v["tempo_espera_s"])
            for v in ves
            if v["cenario"] == cenario and v["modo"] == "FIXO"
        ]
        espera = (
            f"; espera mediana de quem parou {_n(statistics.median(pararam))} s" if pararam else ""
        )
        base = f", no FIXO {_n(statistics.median(fixo))} s" if fixo else ""
        partes.append(
            f"{cenario} {sem}/{len(do_braco)} ({_pct(sem / len(do_braco))}{espera}{base})"
        )
    return EvidenciaDeBancada(
        "Bloco 8, braço PREEMPCAO, VEs sem nenhuma parada: " + "; ".join(partes),
        todos_sem_parada,
    )


def _status_final(placar: Placar, evidencia: EvidenciaDeBancada | None) -> str:
    if placar.total == 0 and evidencia is None:
        return SEM_TESTE
    partes = []
    if placar.total:
        partes.append(placar.status)
    if evidencia is not None and evidencia.atende is not None:
        partes.append(PASSOU if evidencia.atende else FALHOU)
    if any(p.startswith(FALHOU) for p in partes):
        return next(p for p in partes if p.startswith(FALHOU))
    if SEM_TESTE in partes and evidencia is None:
        return SEM_TESTE
    if partes and all(p == PASSOU for p in partes):
        return PASSOU
    return partes[0] if partes else SEM_TESTE


def secao_rastreabilidade(e: Entradas) -> list[str]:
    casos = e.casos
    linhas_tabela = []
    resumo: Counter[str] = Counter()
    for req in e.rastreabilidade:
        por_arquivo = []
        todos: list[CasoDeTeste] = []
        for arquivo in req.arquivos_de_teste:
            do_arquivo = casos_do_arquivo(casos, arquivo)
            todos += do_arquivo
            placar = Placar.de(do_arquivo)
            por_arquivo.append(
                f"`{arquivo}`: "
                + ("**não encontrado nas suítes**" if placar.total == 0 else placar.texto())
            )
        placar = Placar.de(todos)
        # O que um teste grava com `record_property` (o RSS do soak, por exemplo).
        por_arquivo += [
            f"`{caso.nome}` gravou: "
            + ", ".join(f"{nome} = {valor}" for nome, valor in caso.propriedades.items())
            for caso in todos
            if caso.propriedades
        ]
        evidencia = evidencia_de_bancada(req.codigo, e)
        status = _status_final(placar, evidencia)
        resumo[status.split(" (")[0]] += 1
        linhas_tabela.append(
            (
                req.codigo,
                req.caso,
                "<br>".join(por_arquivo) or "—",
                "—" if evidencia is None else evidencia.texto,
                f"**{status}**",
            )
        )
    return [
        "## 4. Rastreabilidade requisito → teste → resultado",
        "",
        "A tabela de `context/06` §2, lida do arquivo, com o resultado de cada arquivo de",
        "teste nas suítes (seção 4.1) e, onde `06` §2 aponta a bancada ou o Bloco 8, o",
        "dado gravado julgado pelo critério declarado. Um requisito é PASSOU só se tudo",
        "o que o sustenta passou; uma falha esperada (`xfail`) continua sendo FALHOU.",
        "",
        *_tabela(
            ("Req.", "Caso de teste", "Testes", "Evidência gravada", "Resultado"), linhas_tabela
        ),
        "Resumo: " + ", ".join(f"{k}: {v}" for k, v in sorted(resumo.items())) + ".",
        "",
        "### 4.1 Suítes",
        "",
        *_tabela(
            ("Arquivo", "Comando", "Rodou em", "Resultado"),
            [
                (
                    f"`{s.arquivo}`",
                    SUITES.get(s.arquivo, "—"),
                    s.instante or "—",
                    Placar.de(s.casos).texto(),
                )
                for s in e.suites
            ]
            or [("—", "nenhum XML em `analysis/data/validacao/`", "—", "—")],
        ),
        *_falhas_das_suites(e.suites),
    ]


def _falhas_das_suites(suites: Sequence[Execucao]) -> list[str]:
    falhas = [c for s in suites for c in s.casos if c.desfecho in (FALHOU, XFAIL)]
    if not falhas:
        return []
    return [
        "Casos que falharam (inclusive os esperados):",
        "",
        *_tabela(
            ("Suíte", "Caso", "Desfecho"),
            [(c.suite, f"`{c.classe}::{c.nome}`", c.desfecho) for c in falhas],
        ),
    ]


def secao_invariantes(e: Entradas) -> list[str]:
    execucoes = e.lote.execucoes
    violacoes_sim = sum(int(linha["violacoes"]) for linha in execucoes)
    colisoes = sum(int(linha["colisoes"]) for linha in execucoes)
    teleportes = sum(int(linha["teleportes"]) for linha in execucoes)
    b = invariantes_da_bancada(e.bancada)
    simulacao = (
        f"{violacoes_sim} em {len(execucoes)} execuções (contagem conjunta de I1 a I5)"
        if execucoes
        else "—"
    )
    bancada_texto = {
        "I1": f"{b.achados.get('I1', 0)} `ST` com verde nos dois eixos, de {b.sts}",
        "I2": f"{b.achados.get('I2', 0)} em {b.mudancas_de_luz} mudanças de luz",
        "I3": f"{b.achados.get('I3', 0)} em {b.mudancas_de_luz} mudanças de luz",
        "I4": f"{b.achados.get('I4', 0)} em {b.mudancas_de_luz} mudanças de luz",
        "I5": (
            f"maior vermelho contínuo de uma aproximação: {_n(b.vermelho_mais_longo_ms / 1000)} s "
            f"(limite {_n(VERMELHO_MAX_MS / 1000, 0)} s)"
        ),
        "I6": (
            f"{b.timeouts_ok} de {b.timeouts} `TIMEOUT` a 30 s com volta pelo eixo oposto "
            f"(critério do item 11); {b.emergencias} `PREEMP_INI` e {b.fins_por_duracao} "
            "`PREEMP_FIM` na telemetria"
        ),
    }
    linhas_tabela = []
    for inv in ("I1", "I2", "I3", "I4", "I5", "I6"):
        placar = Placar.de(
            caso
            for arquivo in TESTES_DOS_INVARIANTES[inv]
            for caso in casos_do_arquivo(e.casos, arquivo)
        )
        linhas_tabela.append(
            (
                inv,
                simulacao if inv != "I6" else "não se aplica (I6 é do firmware, `01` §6)",
                bancada_texto[inv] if e.bancada.sessoes else "—",
                placar.texto() if placar.total else "—",
            )
        )
    return [
        "## 5. Invariantes de segurança",
        "",
        "Simulação: o `VerificadorSeguranca` em todo passo das execuções do Bloco 8",
        "(`violacoes` de `execucoes.csv`; o lote não separa por invariante). Bancada: toda",
        "a telemetria gravada (`telemetria_bancada.csv`, todas as sessões), com",
        "`bridge.verificar.violacoes` e a folga de 60 ms do checklist. Testes: os casos dos",
        "arquivos que exercitam cada invariante, nas suítes da seção 4.1.",
        "",
        *_tabela(
            ("Invariante", "Simulação (Bloco 8)", "Bancada (telemetria)", "Testes"), linhas_tabela
        ),
        f"Ainda na simulação: {colisoes} colisões e {teleportes} teleportes nas mesmas execuções.",
        "",
    ]


def secao_latencias(e: Entradas) -> list[str]:
    cabecalho = (
        "Ambiente",
        "Grandeza",
        "n",
        "Mín (ms)",
        "Média (ms)",
        "p95 (ms)",
        "p99 (ms)",
        "Máx (ms)",
    )
    linhas_tabela: list[Sequence[str]] = []
    por_modo: dict[str, list[float]] = {}
    for linha in e.lote.latencias:
        por_modo.setdefault(linha["modo"], []).append(float(linha["latencia_ms"]))
    for modo, valores in por_modo.items():
        linhas_tabela.append(
            ("SIMULACAO", f"decisão, {modo} (exemplares)", *_estatisticas(valores))
        )
    com_motor = [linha for linha in e.lote.execucoes if linha["modo"] != "FIXO"]
    if com_motor:
        linhas_tabela.append(
            (
                "SIMULACAO",
                f"decisão, pior execução entre {len(com_motor)}",
                "—",
                "—",
                _n(max(float(x["latencia_media_ms"]) for x in com_motor), 3),
                _n(max(float(x["latencia_p95_ms"]) for x in com_motor), 3),
                _n(max(float(x["latencia_p99_ms"]) for x in com_motor), 3),
                _n(max(float(x["latencia_max_ms"]) for x in com_motor), 3),
            )
        )
    h3 = [a for a in e.amostras_h3 if a.sessao == SESSAO_H3]
    if h3:
        linhas_tabela.append(
            (
                "HARDWARE",
                "fim a fim (H3), sessão das 100 passagens",
                *_estatisticas([a.latencia_total_ms for a in h3], 1),
            )
        )
        sem_atraso = [a.latencia_total_ms for a in h3 if not a.carimbo_atrasado]
        if len(sem_atraso) != len(h3):
            linhas_tabela.append(
                (
                    "HARDWARE",
                    f"fim a fim, sem carimbo atrasado (≥ {BYTES_CARIMBO_ATRASADO} bytes)",
                    *_estatisticas(sem_atraso, 1),
                )
            )
    if len(e.amostras_h3) != len(h3):
        linhas_tabela.append(
            (
                "HARDWARE",
                "fim a fim, todas as sessões de `latencia_bancada.csv`",
                *_estatisticas([a.latencia_total_ms for a in e.amostras_h3], 1),
            )
        )
    linhas = [
        "## 6. Latências",
        "",
        "Percentis pelo posto mais próximo. A simulação mede a latência de **decisão**",
        "(RNF01, `motor.avaliar()` cronometrado); a bancada, a latência **fim a fim** de H3",
        "(da leitura da tag ao `PREEMP_INI`). São grandezas diferentes (decisão P2).",
        "",
        *_tabela(cabecalho, linhas_tabela),
    ]
    if not e.lote.latencias:
        linhas += [
            "> `latencias.csv` (uma linha por decisão, só nas execuções exemplares) não está",
            "> no git (`09`, 2026-08-26) e não foi encontrado: as linhas por modo ficam de fora.",
            "",
        ]
    else:
        linhas += [
            "As linhas por modo vêm de `latencias.csv`, que fica fora do git por tamanho",
            "(`09`, 2026-08-26) e só tem as execuções exemplares; a linha da pior execução",
            "vem de `execucoes.csv`, versionado, e cobre todas.",
            "",
        ]
    if e.banco is not None:
        linhas += ["### 6.1 `metrica_latencia`, no banco", ""]
        linhas += _tabela(
            ("Ambiente", "n", "Mín (ms)", "Média (ms)", "p95 (ms)", "p99 (ms)", "Máx (ms)"),
            [(amb, str(n), *(_n(v, 3) for v in valores)) for amb, n, *valores in e.banco.latencias]
            or [("—", "0", "—", "—", "—", "—", "—")],
        )
        linhas += [
            "O lote não grava `metrica_latencia` (a simulação fica nos CSV); as linhas de",
            "`HARDWARE` são as amostras de H3 que o backend gravou com a bancada no ar.",
            "",
        ]
    return linhas


def secao_falhas(e: Entradas) -> list[str]:
    linhas = [
        "## 7. Casos de falha observados e corrigidos",
        "",
        'Lidos de `context/09` (tabela "Decisões tomadas"), em ordem de data. O texto é',
        "o do registro, sem resumo: o que quebrou, o que foi feito e por quê.",
        "",
    ]
    for n, registro in enumerate(sorted(e.falhas, key=lambda r: r.data), 1):
        titulo = registro.item.split("**")[1] if "**" in registro.item else registro.item
        linhas += [
            f"### 7.{n} {titulo} ({registro.data})",
            "",
            f"**Registro:** {registro.item}",
            "",
            f"**O que foi feito:** {registro.decisao}",
            "",
            f"**Por quê:** {registro.justificativa}",
            "",
        ]
    return linhas


def secao_checklist(e: Entradas) -> list[str]:
    veredito_por_item: dict[str, Counter[str]] = {}
    matriz: list[tuple[str, list[checklist.Resultado]]] = []
    for sessao in sorted(e.bancada.sessoes):
        resultados = checklist.avaliar(
            e.bancada.sessoes[sessao],
            e.url_banco,
            e.leituras.get(sessao, []) if sessao in SESSOES_ITEM_5 else None,
        )
        matriz.append((sessao, resultados))
        for r in resultados:
            veredito_por_item.setdefault(r.item, Counter())[_veredito(r.ok)] += 1
    linhas = [
        "## 8. Checklist de aceitação do protótipo físico",
        "",
        "Os itens de `context/06` §6, lidos do arquivo, com o registro de cada um (data,",
        "executor e resultado). Na última coluna, o que `analysis.checklist_bancada` diz",
        "de cada item em **todas** as sessões gravadas"
        + (", com o banco (itens 9 e 15)." if e.url_banco else ", sem o banco."),
        "Os itens 4, 7 e 7b são julgados por `analysis.resumo_bancada` (seção 4); 6, 8, 13",
        "e 14 são observação.",
        "",
    ]
    linhas += _tabela(
        ("#", "Verificação e registro", "OK", "Pelo dado, por sessão"),
        [
            (
                item.item,
                item.verificacao,
                item.ok,
                ", ".join(
                    f"{veredito}: {n}"
                    for veredito, n in sorted(veredito_por_item[item.item].items())
                )
                if item.item in veredito_por_item
                else _pelo_resumo(item.item, e),
            )
            for item in e.checklist_06
        ],
    )
    if matriz:
        itens = list(dict.fromkeys(r.item for _, resultados in matriz for r in resultados))
        itens.sort(key=lambda item: [i.item for i in e.checklist_06].index(item))
        linhas += ["### 8.1 Veredito por sessão", ""]
        linhas += _tabela(
            ("Sessão (UTC)", *itens),
            [
                (
                    sessao_curta(sessao),
                    *(
                        _veredito(por_item[item].ok) if item in por_item else "não julgado"
                        for item in itens
                    ),
                )
                for sessao, resultados in matriz
                for por_item in [{r.item: r for r in resultados}]
            ],
        )
        linhas += [
            '"Não julgado": o item 5 só é julgado nas rodadas dele, e o 9 só com o banco.',
            "",
        ]
        nao_atende = [
            (sessao, r) for sessao, resultados in matriz for r in resultados if r.ok is False
        ]
        if nao_atende:
            linhas += ['Toda célula "não atende", com o que o dado mostra:', ""]
            for sessao, r in nao_atende:
                linhas.append(f"- Sessão `{sessao}`, item {r.item} ({r.titulo}):")
                linhas += [f"  - {detalhe}" for detalhe in r.detalhes]
            linhas.append("")
    linhas += [
        "### 8.2 Assinaturas",
        "",
        "Declaramos que o checklist acima foi executado nas datas registradas em cada item.",
        "",
    ]
    for nome in e.equipe:
        nome_limpo = nome if nome.endswith(")") else nome + ")"
        linhas += [f"- {nome_limpo}: ______________________________  Data: ____/____/______", ""]
    return linhas


def sessao_curta(sessao: str) -> str:
    """`2026-10-07T18:18:37.223864+00:00` como `2026-10-07 18:18:37Z`.

    Até o segundo, as sessões gravadas não se repetem, e o identificador inteiro
    não cabe numa coluna do PDF. O inteiro continua nos detalhes do "não atende".
    """
    return f"{sessao[:10]} {sessao[11:19]}Z"


#: Os itens que `analysis.resumo_bancada` julga, e o requisito de cada um.
ITENS_DO_RESUMO: Final = {"4": "RNF05", "7": "RF02", "7b": "H3"}


def _pelo_resumo(item: str, e: Entradas) -> str:
    if item not in ITENS_DO_RESUMO:
        return "—"
    evidencia = evidencia_de_bancada(ITENS_DO_RESUMO[item], e)
    if evidencia is None:
        return "—"
    return f"{_veredito(evidencia.atende)} (sessão das 100 passagens, `resumo_bancada`)"


def _veredito(ok: bool | None) -> str:
    return {True: "atende", False: "não atende", None: "sem veredito"}[ok]


def secao_anexos() -> list[str]:
    dados = RAIZ / "analysis" / "data"
    arquivos = sorted(
        [
            *dados.glob("*.log"),
            *dados.glob("checklist_bancada_*.md"),
            *dados.glob("resumo_bancada_*.md"),
            DADOS_BLOCO8 / "lote_bloco8.log",
        ]
    )
    tabela = []
    for caminho in arquivos:
        if caminho.is_file():
            conteudo = caminho.read_bytes()
            tabela.append(
                (
                    f"`{caminho.relative_to(RAIZ).as_posix()}`",
                    f"{len(conteudo) / 1024:.1f} KiB",
                    f"`{hashlib.sha256(conteudo).hexdigest()[:16]}`",
                )
            )
    return [
        "## 9. Anexos",
        "",
        "Logs e relatórios gravados, versionados no repositório (sha256, 16 primeiros):",
        "",
        *_tabela(("Arquivo", "Tamanho", "sha256"), tabela),
        "A anexar, com a maquete pronta:",
        "",
        "- fotos da bancada montada (os três carrinhos, o cruzamento e o LCD);",
        "- capturas do dashboard durante uma simulação e durante a bancada;",
        "- vídeo de backup da demonstração (`context/08` §6).",
        "",
    ]


def gerar(e: Entradas) -> str:
    """O relatório inteiro, em Markdown."""
    linhas = [
        f"# Relatório de validação — {e.data.isoformat()}",
        "",
        "Entregável 6 do escopo (`context/06` §5). Gerado por",
        "`python -m analysis.gerar_relatorio_validacao`"
        + (" com `--banco`" if e.url_banco else "")
        + "; nenhum número foi digitado à mão.",
        "",
    ]
    for secao in (
        secao_identificacao,
        secao_ambiente,
        secao_matriz,
        secao_rastreabilidade,
        secao_invariantes,
        secao_latencias,
        secao_falhas,
        secao_checklist,
    ):
        linhas += secao(e)
    linhas += secao_anexos()
    return "\n".join(linhas).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Linha de comando
# ---------------------------------------------------------------------------


def rodar_suites(pasta: Path) -> None:
    """Roda as três suítes e grava os XML do JUnit em `pasta`."""
    pasta.mkdir(parents=True, exist_ok=True)
    comandos: list[tuple[list[str], Path]] = [
        ([sys.executable, "-m", "pytest", f"--junitxml={pasta / 'pytest_padrao.xml'}"], RAIZ),
        (
            [
                sys.executable,
                "-m",
                "pytest",
                "-m",
                "sumo",
                f"--junitxml={pasta / 'pytest_sumo.xml'}",
            ],
            RAIZ,
        ),
        (
            [
                "npx",
                "vitest",
                "run",
                "--reporter=default",
                "--reporter=junit",
                f"--outputFile.junit={pasta / 'vitest.xml'}",
            ],
            RAIZ / "frontend",
        ),
    ]
    for comando, cwd in comandos:
        print("$", " ".join(comando), flush=True)
        subprocess.run(
            comando, cwd=cwd, check=False, shell=sys.platform == "win32" and comando[0] == "npx"
        )


def carregar(
    data: date,
    pasta_junit: Path = PASTA_JUNIT,
    url_banco: str | None = None,
    com_ambiente: bool = True,
) -> Entradas:
    lote = ler_lote()
    entradas = Entradas(
        data=data,
        suites=ler_suites(pasta_junit),
        lote=lote,
        bancada=ler_bancada(),
        amostras_h3=list(ler_amostras(CSV_LATENCIA)),
        leituras=checklist.ler_leituras(CSV_DETECCOES),
        rastreabilidade=ler_rastreabilidade(),
        checklist_06=ler_checklist(),
        falhas=ler_registros_de_09(),
        equipe=ler_equipe(),
        url_banco=url_banco,
    )
    if url_banco is not None:
        entradas.banco = ler_banco(url_banco, lote.versoes)
    if com_ambiente:
        entradas.ambiente = ambiente()
        entradas.head = git_head()
        entradas.sumo = versao_do_sumo()
    return entradas


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada: `python -m analysis.gerar_relatorio_validacao`."""
    saida_utf8()
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument("--data", default=None, help="AAAAMMDD; padrão: hoje")
    analisador.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    analisador.add_argument("--junit", type=Path, default=PASTA_JUNIT)
    analisador.add_argument(
        "--rodar-testes", action="store_true", help="roda as suítes e regrava os XML antes"
    )
    analisador.add_argument(
        "--banco", action="store_true", help="lê o PostgreSQL (DATABASE_URL do .env)"
    )
    analisador.add_argument(
        "--pdf", action="store_true", help=f"gera também o PDF, pela imagem {IMAGEM_PANDOC}"
    )
    opcoes = analisador.parse_args(argv)

    data = (
        date.today()
        if opcoes.data is None
        else date(int(opcoes.data[:4]), int(opcoes.data[4:6]), int(opcoes.data[6:8]))
    )
    if opcoes.rodar_testes:
        rodar_suites(opcoes.junit)
    url = checklist._url_do_banco() if opcoes.banco else None
    relatorio = gerar(carregar(data, opcoes.junit, url))
    destino = opcoes.saida / f"validacao_{data.strftime('%Y%m%d')}.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(relatorio.encode("utf-8"))
    mostrado = destino.relative_to(RAIZ).as_posix() if destino.is_relative_to(RAIZ) else destino
    print(f"relatório: {mostrado}")
    if opcoes.pdf:
        pdf = gerar_pdf(destino)
        print(f"PDF: {pdf.relative_to(RAIZ).as_posix() if pdf.is_relative_to(RAIZ) else pdf}")
    return 0


# ---------------------------------------------------------------------------
# PDF, pela imagem Docker do pandoc (decisão de 2026-10-08, `context/09`)
# ---------------------------------------------------------------------------

#: A imagem que gera o PDF. Versão fixada: outra versão do pandoc ou do LaTeX
#: pode paginar diferente.
IMAGEM_PANDOC: Final = "pandoc/latex:3.11"

#: O cabeçalho LaTeX e o filtro Lua que o PDF usa (`analysis/pdf/`).
PASTA_PDF: Final = RAIZ / "analysis" / "pdf"


def markdown_para_pdf(texto: str) -> str:
    """O Markdown do relatório como o pandoc o recebe para o PDF.

    Só duas trocas, e só no PDF: o `<br>` das células (que o LaTeX descarta, e
    juntaria os itens) vira `; `, e o `☑` do checklist, que nenhuma fonte da
    imagem tem, vira `OK`. O `.md` versionado não muda.
    """
    return texto.replace("<br>", "; ").replace("☑", "OK")


def comando_pandoc(pasta: str, entrada: str, saida: str) -> list[str]:
    """O `docker run` do pandoc, com a pasta de trabalho montada em `/data`."""
    return [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{pasta}:/data",
        IMAGEM_PANDOC,
        f"/data/{entrada}",
        "-o",
        f"/data/{saida}",
        "--pdf-engine=lualatex",
        "-H",
        "/data/cabecalho.tex",
        "--lua-filter=/data/quebrar_codigo.lua",
        "-V",
        "lang=pt-BR",
        "-V",
        "geometry:landscape,a4paper,margin=1.5cm",
    ]


def gerar_pdf(markdown: Path) -> Path:
    """Gera `<relatório>.pdf` ao lado do `.md`, numa pasta temporária montada no contêiner."""
    import shutil
    import tempfile

    destino = markdown.with_suffix(".pdf")
    with tempfile.TemporaryDirectory(prefix="relatorio_pdf_") as temporaria:
        pasta = Path(temporaria)
        (pasta / "relatorio.md").write_bytes(
            markdown_para_pdf(markdown.read_text(encoding="utf-8")).encode("utf-8")
        )
        for arquivo in ("cabecalho.tex", "quebrar_codigo.lua"):
            shutil.copyfile(PASTA_PDF / arquivo, pasta / arquivo)
        resultado = subprocess.run(
            comando_pandoc(str(pasta), "relatorio.md", "relatorio.pdf"),
            capture_output=True,
            check=False,
        )
        avisos = resultado.stderr.decode("utf-8", errors="replace").strip()
        if resultado.returncode != 0 or not (pasta / "relatorio.pdf").is_file():
            raise RuntimeError(f"o pandoc falhou (código {resultado.returncode}):\n{avisos}")
        if "Missing character" in avisos:
            raise RuntimeError(f"o PDF perderia caracteres:\n{avisos}")
        shutil.copyfile(pasta / "relatorio.pdf", destino)
    return destino


if __name__ == "__main__":
    raise SystemExit(main())
