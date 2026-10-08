"""Execução da matriz experimental em lote — `context/04` §7.

    python -m sim.controlador.lote --seeds 1..5 --paralelo 4
    python -m sim.controlador.lote --cenarios moderado,intenso --modos FIXO,PREEMPCAO --seeds 1..3

Esta é a **entrega 8.1 antecipada**. O plano a coloca no Bloco 8 (600 execuções),
mas o piloto do Bloco 4 já são 60 — número que não se roda à mão, e cujo
resultado precisa ser reprodutível do mesmo jeito que o do lote completo. O que
muda entre piloto e lote é o valor de `--seeds`, e mais nada.

POR QUE PARALELIZA COM PROCESSOS, E NÃO COM `libsumo`

O `context/02` §2 previa `libsumo` no lote, por rodar no mesmo processo. **O
instalador Windows do SUMO não traz o módulo Python do `libsumo`** (P15,
descoberta do Bloco 3): ele entrega os bindings Java, C# e C++. Enquanto a
decisão de instalar — ou não — o pacote do pip não é tomada, o lote paraleliza
com `traci`, cada processo com seu próprio SUMO.

Isso funciona bem, e o ganho perdido é menor do que os "10x" nominais sugerem: o
adaptador lê o estado por **assinaturas**, então são ~4 chamadas de IPC por
passo, e não dezenas — e é justamente o custo de IPC que o `libsumo` elimina.
Trocar de cliente depois é passar `--libsumo`, porque o adaptador já abstrai os
dois atrás da mesma interface (entrega 3.6).

TRÊS GARANTIAS QUE O LOTE PRECISA DAR

1. **Pareamento por seed** (`context/04` §7, "regra crítica"). Os arquivos de
   rota são gerados **antes** de qualquer processo subir, no processo pai e em
   série. Dois trabalhadores correndo para escrever o mesmo
   `sim/saida/rotas/<cenario>_<seed>.rou.xml` produziriam um arquivo truncado —
   e o pareamento, que é o que dá poder estatístico à comparação, morreria em
   silêncio.

2. **Descarte documentado** (`context/06` §4). `validar_execucao()` roda em toda
   execução. A que reprova **não entra** nos CSV de `analysis/data/`: ela fica na
   própria pasta de saída, com a evidência bruta, e o motivo do descarte vai para
   `analysis/data/descartes.csv`. Descarte silencioso é má prática científica;
   descarte com critério fixado antes e registrado é metodologia.

3. **Exemplar em uma execução por par cenário x modo** (decisão P5). É o que
   limita o volume de `estado_semaforo_amostra` e de `latencias.csv` — sem a
   regra, as 600 execuções dariam mais de 20 milhões de linhas de latência. O
   lote escolhe a menor seed de cada par; a escolha é determinística e não
   depende da ordem em que os processos terminam.

REEXECUTAR UM PONTO EXIGE APAGAR A EVIDÊNCIA ANTERIOR

`execucao_simulacao` tem restrição única em (cenário, modo, seed), o que faz o
banco **recusar** gravar de novo um ponto já registrado. É proposital: a fricção
é o que força o descarte a ser documentado em vez de silencioso. O CSV não tem
restrição nenhuma — ele simplesmente acrescenta —, então o lote impõe a mesma
regra do lado dos arquivos: **antes de rodar qualquer coisa**, recusa a matriz
que inclua ponto já presente em `execucoes.csv`.

`--repetir MOTIVO` é a autorização explícita: apaga a evidência anterior nos dois
lugares e registra a remoção, com o motivo, em `descartes.csv`. A checagem vem
antes das execuções porque descobrir a duplicata na hora de consolidar
significaria descobri-la depois de horas de máquina — e uma linha duplicada num
CSV de 600 não se percebe olhando: ela aparece como uma seed com peso dobrado na
média do capítulo 5, não como erro.
"""

from __future__ import annotations

import argparse
import csv
import time
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from adapters.configuracao import carregar as carregar_parametros
from adapters.terminal import saida_utf8
from sim.controlador import executor
from sim.controlador.coletor import (
    ARQUIVO_CONFLITOS,
    ARQUIVO_EXECUCOES,
    ARQUIVO_LATENCIAS,
    ARQUIVO_TRANSVERSAL,
    ARQUIVO_VE,
    DADOS,
    cabecalho_do_csv,
    exigir_mesmo_cabecalho,
)
from sim.demanda import gerar_rotas
from sim.validacao.execucao import validar_execucao

RAIZ = Path(__file__).resolve().parents[2]

#: Os CSV de `context/04` §10, na ordem em que são consolidados. O de conflitos
#: entrou com a entrega 10.1 e segue as mesmas regras dos demais: consolidação,
#: guarda anti-duplicata e remoção em reexecução.
ARQUIVOS_CSV = (
    ARQUIVO_EXECUCOES,
    ARQUIVO_VE,
    ARQUIVO_TRANSVERSAL,
    ARQUIVO_LATENCIAS,
    ARQUIVO_CONFLITOS,
)

#: Onde o lote registra o que descartou e o que apagou para reexecutar.
ARQUIVO_DESCARTES = "descartes.csv"

CENARIOS_PADRAO = ("leve", "moderado", "intenso", "multiplas_emergencias")


@dataclass(frozen=True, order=True)
class Ponto:
    """Um ponto da matriz experimental.

    Attributes:
        cenario: Cenário de `cenarios.yaml`.
        modo: Braço de comparação.
        seed: Seed do ponto.
        ajustes: Parâmetros que substituem os de `parametros.yaml` neste ponto
            (calibração de P17). Vazio nas execuções normais.
    """

    cenario: str
    modo: str
    seed: int
    ajustes: executor.Ajustes = ()

    def __str__(self) -> str:
        base = f"{self.cenario}/{self.modo}/seed={self.seed}"
        return f"{base}/{self.variante}" if self.ajustes else base

    @property
    def variante(self) -> str:
        """Rótulo dos ajustes; vazio quando o ponto usa `parametros.yaml` puro."""
        return executor.rotulo_dos_ajustes(self.ajustes)

    @property
    def pasta(self) -> Path:
        """Pasta de saída bruta desta execução."""
        return executor.pasta_de_saida(self.cenario, self.modo, self.seed, self.ajustes)

    def destino(self, saida: Path) -> Path:
        """Onde os CSV deste ponto são consolidados.

        Ponto com ajustes vai para uma subpasta com o rótulo deles. Os CSV não
        têm coluna de parâmetro, então duas combinações do mesmo (cenário, modo,
        seed) no mesmo arquivo seriam linhas indistinguíveis.
        """
        return saida / self.variante if self.ajustes else saida


@dataclass(frozen=True)
class Tarefa:
    """O que um processo trabalhador precisa saber para rodar um ponto."""

    ponto: Ponto
    duracao_s: float | None
    exemplar: bool
    persistir: bool


@dataclass(frozen=True)
class ResultadoDoPonto:
    """O que o processo pai recebe de volta de cada ponto.

    Deliberadamente **magro**: não traz as transições nem a série de latências.
    Uma execução de 3.600 s produz dezenas de milhares de transições, e devolvê-las
    ao processo pai custaria pickle e memória para um dado que já está no CSV.

    Attributes:
        ponto: O ponto experimental.
        segundos: Tempo de parede da execução.
        problemas: Saída de `validar_execucao()`. Vazia significa execução válida.
        erro: Mensagem, se a execução levantou exceção. `None` se rodou.
        ves_completos: VEs que completaram a rota.
        tempo_medio_travessia_ve_s: Variável de resposta de H1.
        paradas_medias_ve: Evidência do RF03.
        tempo_espera_medio_transversal_s: Evidência de H2.
        latencia_p95_ms: O número do RNF01.
        colisoes: Colisões observadas.
        teleportes: Teleportes observados.
        violacoes: Violações de invariante.
    """

    ponto: Ponto
    segundos: float
    problemas: tuple[str, ...] = ()
    erro: str | None = None
    ves_completos: int = 0
    tempo_medio_travessia_ve_s: float = 0.0
    paradas_medias_ve: float = 0.0
    tempo_espera_medio_transversal_s: float = 0.0
    latencia_p95_ms: float = 0.0
    colisoes: int = 0
    teleportes: int = 0
    violacoes: int = 0

    @property
    def valida(self) -> bool:
        """Se a execução pode entrar na análise."""
        return self.erro is None and not self.problemas


# ---------------------------------------------------------------------------
# Montagem da matriz
# ---------------------------------------------------------------------------


def analisar_seeds(texto: str) -> tuple[int, ...]:
    """Interpreta `"1..5"`, `"1,3,7"` ou `"1..3,10"`.

    Args:
        texto: Especificação das seeds.

    Returns:
        As seeds, ordenadas e sem repetição.

    Raises:
        ValueError: se um trecho não for inteiro nem faixa `a..b`, ou se a faixa
            estiver invertida.
    """
    seeds: set[int] = set()
    for trecho in texto.split(","):
        pedaco = trecho.strip()
        if not pedaco:
            continue
        if ".." in pedaco:
            inicio_txt, _, fim_txt = pedaco.partition("..")
            inicio, fim = int(inicio_txt), int(fim_txt)
            if fim < inicio:
                raise ValueError(f"faixa de seeds invertida: {pedaco!r}")
            seeds.update(range(inicio, fim + 1))
        else:
            seeds.add(int(pedaco))
    if not seeds:
        raise ValueError(f"nenhuma seed em {texto!r}")
    return tuple(sorted(seeds))


def analisar_ajustes(textos: Sequence[str]) -> executor.Ajustes:
    """Interpreta `["ganho_compensacao_k=1.5", "n_ciclos_compensacao=3"]`.

    Só a forma é conferida aqui; nome e valor são validados por
    `executor.aplicar_ajustes()`, que é quem os aplica.

    Raises:
        ValueError: se algum item não tiver a forma `NOME=VALOR` numérica.
    """
    pares: list[tuple[str, float]] = []
    for texto in textos:
        nome, sinal, valor = texto.partition("=")
        if not sinal or not nome.strip():
            raise ValueError(f"ajuste fora da forma NOME=VALOR: {texto!r}")
        try:
            pares.append((nome.strip(), float(valor)))
        except ValueError:
            raise ValueError(f"valor não numérico em {texto!r}") from None
    return tuple(sorted(pares))


def matriz(
    cenarios: Sequence[str],
    modos: Sequence[str],
    seeds: Sequence[int],
    ajustes: executor.Ajustes = (),
) -> tuple[Ponto, ...]:
    """Produto cartesiano dos três eixos, em ordem estável.

    A ordem é `seed` mais externa, depois cenário, depois modo. Isso agrupa os
    braços de um mesmo (cenário, seed) — que é o conjunto que a comparação
    pareada consome — e faz com que uma interrupção do lote deixe seeds
    **completas** para trás, em vez de um cenário inteiro num modo só.

    **Uma exceção ao produto:** o braço `PREEMPCAO_ML` só entra nos cenários
    com mais de um VE simultâneo (decisão da equipe, 2026-10-07). Com um VE só
    não há disputa, o modelo nunca é consultado, e a execução repetiria a do
    `PREEMPCAO` gastando máquina. O corte é feito aqui, e não por quem chama,
    para que o Bloco 8 continue sendo um comando só.
    """
    com_disputa = {
        cenario: executor.ves_simultaneos(cenario) > 1
        for cenario in cenarios
        if executor.MODO_ML in modos
    }
    return tuple(
        Ponto(cenario, modo, seed, ajustes)
        for seed in seeds
        for cenario in cenarios
        for modo in modos
        if modo != executor.MODO_ML or com_disputa[cenario]
    )


def exemplares(pontos: Iterable[Ponto]) -> frozenset[Ponto]:
    """Um ponto por par (cenário, modo) — decisão P5.

    A menor seed de cada par. A escolha precisa ser determinística e independente
    da ordem de término dos processos: é ela que decide quais execuções gravam
    transições no banco e latência linha a linha no CSV, e portanto quais
    alimentam as figuras do capítulo 5.
    """
    escolhidos: dict[tuple[str, str, executor.Ajustes], Ponto] = {}
    for ponto in pontos:
        chave = (ponto.cenario, ponto.modo, ponto.ajustes)
        atual = escolhidos.get(chave)
        if atual is None or ponto.seed < atual.seed:
            escolhidos[chave] = ponto
    return frozenset(escolhidos.values())


# ---------------------------------------------------------------------------
# O trabalhador — roda num processo próprio, com seu próprio SUMO
# ---------------------------------------------------------------------------


def _limpar_csv_da_pasta(ponto: Ponto) -> None:
    """Apaga os CSV que uma execução anterior deste ponto deixou na pasta.

    `gravar_csv()` **acrescenta** — é o comportamento certo para o arquivo
    consolidado, e o errado para a pasta de uma execução. Sem esta limpeza, rodar
    o mesmo ponto duas vezes deixa duas linhas na pasta, e a consolidação leva as
    duas para `analysis/data/`.

    Não é hipótese: aconteceu no piloto do Bloco 4. Quatro pontos tinham sido
    exercitados antes num teste curto (400 s), e o `execucoes.csv` consolidado
    saiu com **64 linhas para 60 execuções** — as quatro sobras, com a duração
    errada, misturadas às boas. O erro não falha alto: ele vira uma seed com peso
    dobrado na média do capítulo 5.
    """
    for nome in ARQUIVOS_CSV:
        (ponto.pasta / nome).unlink(missing_ok=True)


def executar_ponto(tarefa: Tarefa) -> ResultadoDoPonto:
    """Roda um ponto experimental e devolve o resumo.

    Roda no processo trabalhador. **Nunca levanta**: uma execução que quebra não
    pode derrubar as outras 59 do lote, então a exceção volta em `erro` e o ponto
    é contabilizado como falho no relatório.

    Os CSV vão para a pasta da própria execução, não para `analysis/data/`. O
    processo pai consolida depois, em ordem determinística — se os processos
    escrevessem direto no arquivo compartilhado, as linhas se intercalariam a
    cada `flush` e a ordem mudaria a cada corrida do lote.
    """
    inicio = time.perf_counter()
    ponto = tarefa.ponto
    _limpar_csv_da_pasta(ponto)
    try:
        resultado = executor.executar(
            executor.Opcoes(
                cenario=ponto.cenario,
                modo=ponto.modo,
                seed=ponto.seed,
                duracao_s=tarefa.duracao_s,
                exemplar=tarefa.exemplar,
                persistir=tarefa.persistir,
                diretorio_csv=ponto.pasta,
                ajustes=ponto.ajustes,
            )
        )
    except Exception as erro:  # o lote continua; o ponto entra como falho
        return ResultadoDoPonto(
            ponto=ponto,
            segundos=time.perf_counter() - inicio,
            erro=f"{erro.__class__.__name__}: {erro}",
        )

    # `ves_planejados` fica em None de propósito. Quantos VEs completam a rota
    # depende do braço: o último VE parte perto do fim do horizonte e, no
    # baseline, pode não chegar dentro dos 3.600 s. Exigir um número fixo
    # reprovaria execuções legítimas de `FIXO` — justamente as mais lentas, que
    # são o controle. O pareamento é feito por id de VE na análise, sobre a
    # interseção dos três braços.
    problemas = validar_execucao(
        resultado,
        executor.aplicar_ajustes(carregar_parametros("simulacao"), ponto.ajustes),
        completa=tarefa.duracao_s is None,
    )
    return ResultadoDoPonto(
        ponto=ponto,
        segundos=time.perf_counter() - inicio,
        problemas=tuple(problemas),
        ves_completos=len(resultado.viagens_ve),
        tempo_medio_travessia_ve_s=resultado.tempo_medio_travessia_ve_s,
        paradas_medias_ve=resultado.paradas_medias_ve,
        tempo_espera_medio_transversal_s=resultado.tempo_espera_medio_transversal_s,
        latencia_p95_ms=resultado.latencia_p95_ms,
        colisoes=resultado.colisoes,
        teleportes=resultado.teleportes,
        violacoes=len(resultado.violacoes),
    )


# ---------------------------------------------------------------------------
# Consolidação dos CSV
# ---------------------------------------------------------------------------


class PontoJaConsolidadoError(RuntimeError):
    """A matriz inclui pontos que já têm linhas nos CSV de destino."""


def pontos_ja_no_csv(destino: Path, pontos: Iterable[Ponto]) -> tuple[Ponto, ...]:
    """Quais dos pontos dados já aparecem em `execucoes.csv`.

    A consolidação **acrescenta** linhas. Rodar o mesmo ponto duas vezes sem
    limpar antes duplicaria a evidência em silêncio — e uma linha duplicada num
    CSV de 600 não se percebe olhando: ela aparece como uma seed com peso dobrado
    na média do capítulo 5.
    """
    arquivo = destino / ARQUIVO_EXECUCOES
    if not arquivo.is_file():
        return ()
    procurados = {(ponto.cenario, ponto.modo, ponto.seed): ponto for ponto in pontos}
    with arquivo.open(encoding="utf-8", newline="") as entrada:
        presentes = {
            (linha["cenario"], linha["modo"], int(linha["seed"]))
            for linha in csv.DictReader(entrada)
        }
    return tuple(sorted(procurados[chave] for chave in presentes & set(procurados)))


def remover_dos_csv(destino: Path, pontos: Iterable[Ponto]) -> dict[str, int]:
    """Reescreve os CSV sem as linhas dos pontos dados.

    É a contraparte de `remover_do_banco()`: reexecutar um ponto exige apagar a
    evidência anterior nos dois lugares, e `descartes.csv` — que **não** é
    limpo — fica como o registro de que isso aconteceu.

    Returns:
        Quantas linhas foram removidas de cada arquivo.
    """
    alvos = {(ponto.cenario, ponto.modo, ponto.seed) for ponto in pontos}
    removidas: dict[str, int] = {}

    for nome in ARQUIVOS_CSV:
        arquivo = destino / nome
        if not arquivo.is_file():
            continue
        with arquivo.open(encoding="utf-8", newline="") as entrada:
            leitor = csv.DictReader(entrada)
            campos = leitor.fieldnames or []
            todas = list(leitor)
        mantidas = [
            linha
            for linha in todas
            if (linha["cenario"], linha["modo"], int(linha["seed"])) not in alvos
        ]
        if len(mantidas) == len(todas):
            continue
        with arquivo.open("w", encoding="utf-8", newline="") as saida:
            escritor = csv.DictWriter(saida, fieldnames=campos)
            escritor.writeheader()
            escritor.writerows(mantidas)
        removidas[nome] = len(todas) - len(mantidas)
    return removidas


def _verificar_cabecalhos(pastas: Sequence[Path], destino: Path) -> None:
    """Confere, antes de escrever, que todo CSV parcial casa com o do destino.

    Cada parcial é comparado com o arquivo já existente em `destino` e com o
    primeiro parcial do mesmo nome — o que cobre tanto o destino antigo quanto
    execuções de versões diferentes do código misturadas na mesma matriz.
    """
    for nome in ARQUIVOS_CSV:
        parciais = [pasta / nome for pasta in pastas if (pasta / nome).is_file()]
        for parcial in parciais:
            cabecalho = cabecalho_do_csv(parcial) or []
            exigir_mesmo_cabecalho(destino / nome, cabecalho)
            exigir_mesmo_cabecalho(parciais[0], cabecalho)


def consolidar(pastas: Sequence[Path], destino: Path) -> dict[str, int]:
    """Junta os CSV parciais das execuções válidas num só conjunto.

    Args:
        pastas: Pastas das execuções válidas, **na ordem da matriz**.
        destino: Diretório de saída — normalmente `analysis/data/`.

    Returns:
        Quantas linhas de dados cada arquivo recebeu.

    Raises:
        CabecalhoDivergenteError: se um CSV de `destino` já existe com outro
            cabeçalho, ou se as execuções trazem cabeçalhos diferentes entre si.
            A checagem roda para **todos** os arquivos antes de qualquer escrita,
            para que a falha não deixe a consolidação pela metade.
    """
    destino.mkdir(parents=True, exist_ok=True)
    _verificar_cabecalhos(pastas, destino)
    contagem: dict[str, int] = {}

    for nome in ARQUIVOS_CSV:
        parciais = [pasta / nome for pasta in pastas if (pasta / nome).is_file()]
        if not parciais:
            continue
        alvo = destino / nome
        primeiro = not alvo.is_file()
        linhas = 0
        with alvo.open("a", encoding="utf-8", newline="") as saida:
            for parcial in parciais:
                with parcial.open(encoding="utf-8", newline="") as entrada:
                    cabecalho = entrada.readline()
                    if primeiro:
                        saida.write(cabecalho)
                        primeiro = False
                    for linha in entrada:
                        saida.write(linha)
                        linhas += 1
        contagem[nome] = linhas
    return contagem


def registrar_descartes(
    destino: Path, resultados: Iterable[ResultadoDoPonto], removidos: Sequence[tuple[Ponto, str]]
) -> int:
    """Escreve `descartes.csv` — a prova documental do `context/06` §4.

    Args:
        destino: Diretório de saída.
        resultados: Todos os resultados do lote; só os inválidos são escritos.
        removidos: Pontos apagados do banco por `--repetir`, com o motivo.

    Returns:
        Quantas linhas foram escritas.
    """
    agora = datetime.now(UTC).isoformat(timespec="seconds")
    linhas: list[tuple[str, str, str, str, int, str, str]] = []

    for ponto, motivo in removidos:
        linhas.append((agora, "REEXECUCAO", ponto.cenario, ponto.modo, ponto.seed, motivo, ""))

    for resultado in resultados:
        ponto = resultado.ponto
        if resultado.erro is not None:
            # Com ajustes, a pasta é o único lugar que diz qual combinação falhou.
            evidencia = str(ponto.pasta.relative_to(RAIZ)) if ponto.ajustes else ""
            linhas.append(
                (agora, "FALHA", ponto.cenario, ponto.modo, ponto.seed, resultado.erro, evidencia)
            )
        for problema in resultado.problemas:
            linhas.append(
                (
                    agora,
                    "DESCARTE",
                    ponto.cenario,
                    ponto.modo,
                    ponto.seed,
                    problema,
                    str(ponto.pasta.relative_to(RAIZ)),
                )
            )

    if not linhas:
        return 0

    destino.mkdir(parents=True, exist_ok=True)
    alvo = destino / ARQUIVO_DESCARTES
    novo = not alvo.is_file()
    with alvo.open("a", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo)
        if novo:
            escritor.writerow(
                ("registrado_em", "tipo", "cenario", "modo", "seed", "detalhe", "evidencia")
            )
        escritor.writerows(linhas)
    return len(linhas)


# ---------------------------------------------------------------------------
# Banco — a restrição única de (cenário, modo, seed)
# ---------------------------------------------------------------------------


def remover_do_banco(pontos: Sequence[Ponto]) -> tuple[list[Ponto], str | None]:
    """Apaga as linhas de `execucao_simulacao` dos pontos dados.

    Existe porque a restrição única em (cenário, modo, seed) **recusa** gravar o
    mesmo ponto duas vezes. Reexecutar depende de apagar a linha anterior — e é
    essa fricção que torna o descarte visível em vez de silencioso.

    Returns:
        Os pontos efetivamente removidos e, se houver, o erro que impediu a
        operação (banco fora do ar não derruba o lote).
    """
    try:
        from app.models import ExecucaoSimulacao, ModoControle  # import local: I/O fora de core/
        from app.repositories.sessao import (  # import local
            criar_engine,
            criar_fabrica_sessao,
            sessao_de,
        )

        removidos: list[Ponto] = []
        fabrica = criar_fabrica_sessao(criar_engine())
        with sessao_de(fabrica) as sessao:
            for ponto in pontos:
                achados = (
                    sessao.query(ExecucaoSimulacao)
                    .filter_by(
                        nome_cenario=ponto.cenario,
                        modo=ModoControle(ponto.modo),
                        seed=ponto.seed,
                    )
                    .all()
                )
                for execucao in achados:
                    sessao.delete(execucao)
                    removidos.append(ponto)
        return removidos, None
    except Exception as erro:
        return [], f"{erro.__class__.__name__}: {erro}"


# ---------------------------------------------------------------------------
# O lote
# ---------------------------------------------------------------------------


def _por_destino(pontos: Sequence[Ponto], saida: Path) -> dict[Path, list[Ponto]]:
    """Agrupa os pontos pelo diretório em que serão consolidados, na ordem da matriz."""
    grupos: dict[Path, list[Ponto]] = {}
    for ponto in pontos:
        grupos.setdefault(ponto.destino(saida), []).append(ponto)
    return grupos


@dataclass(frozen=True)
class ResumoDoLote:
    """O que o lote produziu.

    Attributes:
        resultados: Um por ponto, na ordem da matriz.
        segundos: Tempo de parede do lote inteiro.
        linhas_csv: Linhas consolidadas por arquivo.
        removidos: Pontos cuja evidência anterior foi apagada — do CSV, do banco
            ou dos dois — para permitir a reexecução.
    """

    resultados: tuple[ResultadoDoPonto, ...]
    segundos: float
    linhas_csv: dict[str, int]
    removidos: tuple[Ponto, ...] = ()

    @property
    def validas(self) -> tuple[ResultadoDoPonto, ...]:
        """Execuções que podem entrar na análise."""
        return tuple(resultado for resultado in self.resultados if resultado.valida)

    @property
    def descartadas(self) -> tuple[ResultadoDoPonto, ...]:
        """Execuções reprovadas por `validar_execucao()` ou que falharam."""
        return tuple(resultado for resultado in self.resultados if not resultado.valida)


def rodar(
    pontos: Sequence[Ponto],
    *,
    paralelo: int = 4,
    duracao_s: float | None = None,
    persistir: bool = True,
    marcar_exemplares: bool = True,
    saida: Path = DADOS,
    repetir_motivo: str | None = None,
    ao_terminar: Callable[[ResultadoDoPonto], None] | None = None,
) -> ResumoDoLote:
    """Roda a matriz e consolida os resultados.

    Args:
        pontos: Os pontos experimentais, na ordem em que devem aparecer nos CSV.
        paralelo: Quantos processos simultâneos. Cada um sobe o seu SUMO.
        duracao_s: Duração simulada. `None` usa a de `cenarios.yaml`.
        persistir: Se grava em `execucao_simulacao`.
        marcar_exemplares: Se marca uma execução por par cenário x modo (P5).
        saida: Diretório dos CSV consolidados.
        repetir_motivo: Se dado, apaga a evidência anterior dos pontos que já
            existirem — nos CSV e no banco —, registrando este motivo em
            `descartes.csv`.
        ao_terminar: Chamado com cada `ResultadoDoPonto` assim que ele fica
            pronto — serve para o progresso na linha de comando.

    Returns:
        O resumo do lote.

    Raises:
        PontoJaConsolidadoError: se algum ponto da matriz já tem linhas nos CSV
            de destino e `repetir_motivo` não foi dado.
    """
    inicio = time.perf_counter()

    if persistir and any(ponto.ajustes for ponto in pontos):
        raise ValueError(
            "pontos com ajustes de parâmetro não podem gravar em execucao_simulacao: "
            "o snapshot do banco é o de parametros.yaml (use persistir=False / --sem-banco)"
        )
    grupos = _por_destino(pontos, saida)

    # A checagem vem ANTES de qualquer execução, de propósito: descobrir a
    # duplicata só na hora de consolidar significaria descobri-la depois de horas
    # de máquina, com os processos já gastos.
    repetidos = tuple(
        ponto for destino, membros in grupos.items() for ponto in pontos_ja_no_csv(destino, membros)
    )
    if repetidos:
        if repetir_motivo is None:
            raise PontoJaConsolidadoError(
                f"{len(repetidos)} ponto(s) da matriz já têm linhas em "
                f"{saida / ARQUIVO_EXECUCOES}: "
                + ", ".join(str(ponto) for ponto in repetidos[:5])
                + ("..." if len(repetidos) > 5 else "")
                + ".\nConsolidar de novo duplicaria a evidência — e uma linha duplicada "
                "num CSV de 600 aparece como uma seed com peso dobrado na média, não como "
                "erro.\nPara reexecutar de propósito, passe --repetir MOTIVO: a evidência "
                "anterior é apagada dos CSV e do banco, e a remoção fica registrada em "
                f"{ARQUIVO_DESCARTES} (context/06 §4)."
            )
        for destino, membros in grupos.items():
            apagadas = remover_dos_csv(destino, [p for p in repetidos if p in membros])
            for nome, quantas in apagadas.items():
                print(f"  --repetir: {quantas} linha(s) removida(s) de {destino / nome}")

    # Pareamento por seed: os arquivos de rota nascem aqui, em série, antes de
    # qualquer processo subir (context/04 §7).
    for cenario, seed in sorted({(ponto.cenario, ponto.seed) for ponto in pontos}):
        gerar_rotas.garantir(cenario, seed)

    removidos: list[Ponto] = []
    if repetir_motivo is not None and persistir:
        removidos, erro = remover_do_banco(pontos)
        if erro is not None:
            print(f"  aviso: não consegui limpar o banco ({erro})")

    marcados = exemplares(pontos) if marcar_exemplares else frozenset()
    tarefas = [
        Tarefa(
            ponto=ponto,
            duracao_s=duracao_s,
            exemplar=ponto in marcados,
            persistir=persistir,
        )
        for ponto in pontos
    ]

    por_ponto: dict[Ponto, ResultadoDoPonto] = {}
    with ProcessPoolExecutor(max_workers=max(1, paralelo)) as piscina:
        futuros = {piscina.submit(executar_ponto, tarefa): tarefa.ponto for tarefa in tarefas}
        for futuro in as_completed(futuros):
            resultado = futuro.result()
            por_ponto[resultado.ponto] = resultado
            if ao_terminar is not None:
                ao_terminar(resultado)

    resultados = tuple(por_ponto[ponto] for ponto in pontos)

    # Só execução válida entra na análise (context/06 §4). A reprovada fica na
    # própria pasta, com a evidência bruta, e o motivo vai para descartes.csv.
    linhas: dict[str, int] = {}
    for destino, membros in grupos.items():
        validas = [r.ponto.pasta for r in resultados if r.valida and r.ponto in membros]
        for nome, quantas in consolidar(validas, destino).items():
            linhas[nome] = linhas.get(nome, 0) + quantas

    # A reexecução é registrada uma vez por ponto, tenha a evidência anterior
    # saído do CSV, do banco, ou dos dois.
    reexecutados = sorted(set(repetidos) | set(removidos))
    registrar_descartes(
        saida, resultados, [(ponto, repetir_motivo or "") for ponto in reexecutados]
    )

    return ResumoDoLote(
        resultados=resultados,
        segundos=time.perf_counter() - inicio,
        linhas_csv=linhas,
        removidos=tuple(reexecutados),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _duracao(segundos: float) -> str:
    horas, resto = divmod(int(segundos), 3600)
    minutos, restantes = divmod(resto, 60)
    if horas:
        return f"{horas}h{minutos:02d}m{restantes:02d}s"
    return f"{minutos}m{restantes:02d}s"


def _relatorio(resumo: ResumoDoLote) -> str:
    linhas = [
        "",
        f"=== lote: {len(resumo.resultados)} execuções em {_duracao(resumo.segundos)} ===",
        f"  válidas     {len(resumo.validas)}",
        f"  descartadas {len(resumo.descartadas)}",
    ]
    for resultado in resumo.descartadas:
        detalhe = resultado.erro or "; ".join(resultado.problemas)
        linhas.append(f"  ! {resultado.ponto}: {detalhe}")

    linhas.append("")
    linhas.append(
        f"  {'cenário':<22} {'modo':<22} {'seed':>4} {'VEs':>4} "
        f"{'travessia':>10} {'paradas':>8} {'transv.':>8} {'p95 ms':>8}"
    )
    for resultado in resumo.validas:
        ponto = resultado.ponto
        linhas.append(
            f"  {ponto.cenario:<22} {ponto.modo:<22} {ponto.seed:>4} "
            f"{resultado.ves_completos:>4} "
            f"{resultado.tempo_medio_travessia_ve_s:>10.1f} "
            f"{resultado.paradas_medias_ve:>8.2f} "
            f"{resultado.tempo_espera_medio_transversal_s:>8.2f} "
            f"{resultado.latencia_p95_ms:>8.3f}"
        )

    linhas.append("")
    for nome, quantas in resumo.linhas_csv.items():
        linhas.append(f"  {nome:<32} +{quantas} linhas")
    return "\n".join(linhas)


def main(argumentos: Sequence[str] | None = None) -> int:
    saida_utf8()
    analisador = argparse.ArgumentParser(
        description="Roda a matriz experimental em lote (context/04 §7)."
    )
    analisador.add_argument(
        "--cenarios", default=",".join(CENARIOS_PADRAO), help="separados por vírgula"
    )
    analisador.add_argument("--modos", default=",".join(executor.MODOS))
    analisador.add_argument("--seeds", default="1..5", help='"1..5", "1,3,7" ou "1..3,10"')
    analisador.add_argument("--duracao", type=float, default=None, help="segundos simulados")
    analisador.add_argument("--paralelo", type=int, default=4, help="processos simultâneos")
    analisador.add_argument("--saida", type=Path, default=DADOS)
    analisador.add_argument(
        "--sem-banco", action="store_true", help="não grava em execucao_simulacao"
    )
    analisador.add_argument(
        "--repetir",
        metavar="MOTIVO",
        default=None,
        help="apaga do banco os pontos já gravados antes de rodar; o motivo vai "
        "para descartes.csv (context/06 §4)",
    )
    analisador.add_argument(
        "--ajuste",
        metavar="NOME=VALOR",
        action="append",
        default=[],
        help=f"substitui um parâmetro de E7 em todos os pontos ({', '.join(executor.AJUSTAVEIS)});"
        " exige --sem-banco e consolida numa subpasta de --saida com o rótulo do ajuste",
    )
    opcoes = analisador.parse_args(argumentos)

    try:
        ajustes = analisar_ajustes(opcoes.ajuste)
    except ValueError as erro:
        analisador.error(str(erro))
    if ajustes and not opcoes.sem_banco:
        analisador.error("--ajuste exige --sem-banco")

    cenarios = tuple(nome.strip() for nome in opcoes.cenarios.split(",") if nome.strip())
    modos = tuple(nome.strip() for nome in opcoes.modos.split(",") if nome.strip())
    if desconhecidos := [modo for modo in modos if modo not in executor.MODOS]:
        analisador.error(f"modo desconhecido: {', '.join(desconhecidos)}")

    seeds = analisar_seeds(opcoes.seeds)
    pontos = matriz(cenarios, modos, seeds, ajustes)
    marcados = exemplares(pontos)

    print(
        f"lote: {len(pontos)} execuções "
        f"({len(cenarios)} cenários x {len(modos)} modos x {len(seeds)} seeds)"
        f" · {opcoes.paralelo} processos · {len(marcados)} exemplares (P5)"
    )
    com_ml = {ponto.cenario for ponto in pontos if ponto.modo == executor.MODO_ML}
    if executor.MODO_ML in modos and (sem_ml := [c for c in cenarios if c not in com_ml]):
        print(
            f"  {executor.MODO_ML} fica de fora de {', '.join(sem_ml)}: um VE só, sem disputa"
            f" ({len(sem_ml) * len(seeds)} execuções a menos que o produto)"
        )

    concluidas = 0
    inicio = time.perf_counter()

    def progresso(resultado: ResultadoDoPonto) -> None:
        nonlocal concluidas
        concluidas += 1
        decorrido = time.perf_counter() - inicio
        restantes = (decorrido / concluidas) * (len(pontos) - concluidas)
        estado = "ok" if resultado.valida else "DESCARTE"
        print(
            f"  [{concluidas:>3}/{len(pontos)}] {resultado.ponto!s:<52} "
            f"{estado:<9} {_duracao(resultado.segundos)}"
            f" · restam ~{_duracao(restantes)}",
            flush=True,
        )

    resumo = rodar(
        pontos,
        paralelo=opcoes.paralelo,
        duracao_s=opcoes.duracao,
        persistir=not opcoes.sem_banco,
        saida=opcoes.saida,
        repetir_motivo=opcoes.repetir,
        ao_terminar=progresso,
    )
    print(_relatorio(resumo))
    return 1 if resumo.descartadas else 0


if __name__ == "__main__":
    raise SystemExit(main())
