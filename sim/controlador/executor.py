"""Execução de um ponto experimental — entrega 3.7 (`context/04` §8).

    python -m sim.controlador.executor --cenario leve --modo FIXO --seed 1
    python -m sim.controlador.executor --cenario intenso --modo PREEMPCAO --seed 3 --gui

Uma execução = um (cenário, modo, seed). O lote das 600 (Bloco 8) chamará esta
mesma função em paralelo; nada aqui pressupõe execução única.

O QUE ESTA FUNÇÃO GARANTE, E POR QUÊ

* **Seed explícita, sempre.** É exigência do `CLAUDE.md`: rodar duas vezes com a
  mesma seed e a mesma configuração dá o mesmo resultado. A seed escolhe o
  arquivo de rotas (o mesmo nos três modos — pareamento de `context/04` §7) e vai
  também para o `--seed` do SUMO.
* **Registro em `execucao_simulacao`.** Com `versao_codigo` (`git rev-parse`) e o
  snapshot dos parâmetros. Sem os dois, a execução não é reproduzível e o número
  não é defensável na banca (`context/03` §4.3).
* **No modo `FIXO`, o motor não é chamado.** Não é economia: o baseline precisa
  ser genuinamente sem intervenção, senão a comparação não vale (`context/04`
  §8).
* **Os invariantes são verificados a cada passo, nos três modos.** Inclusive no
  baseline — é o que permite afirmar zero violações com evidência, e não por
  suposição.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from adapters.configuracao import carregar as carregar_parametros
from adapters.configuracao import snapshot as snapshot_parametros
from adapters.sumo import topologia as topologia_sumo
from adapters.sumo.adaptador import AdaptadorSumo
from adapters.sumo.cliente import abrir_cliente
from core.parametros import Parametros
from core.priorizacao.conflito import EventoConflito
from core.priorizacao.motor import MotorDecisao
from core.seguranca import VerificadorSeguranca
from sim.ambiente import executavel
from sim.controlador.coletor import DADOS, ColetorMetricas, ResultadoExecucao, gravar_csv
from sim.controlador.transmissor import Transmissor
from sim.demanda import gerar_rotas
from sim.rede import georreferencia

RAIZ = Path(__file__).resolve().parents[2]
CONFIGURACAO_SUMO = RAIZ / "sim" / "config" / "malha.sumocfg"
CENARIOS_YAML = RAIZ / "sim" / "config" / "cenarios.yaml"
TIPOS_VEICULO = RAIZ / "sim" / "demanda" / "veiculos.typ.xml"
DETECTORES = RAIZ / "sim" / "rede" / "malha.det.add.xml"
SAIDA = RAIZ / "sim" / "saida"

MODOS = ("FIXO", "PREEMPCAO", "PREEMPCAO_COMPENSADA")

#: Parâmetros que uma execução pode variar sem editar `parametros.yaml`. Só os de
#: E7, porque é o que a calibração de P17 precisa (`context/09` P17). Ampliar a
#: lista é decisão, não conveniência: todo parâmetro fora daqui só muda por
#: commit no YAML, que é o que o `versao_codigo` de cada execução registra.
AJUSTAVEIS = ("ganho_compensacao_k", "n_ciclos_compensacao")

#: Ajustes de parâmetro de uma execução, como pares (nome, valor) ordenados.
Ajustes = tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class Opcoes:
    """Parâmetros de uma execução.

    Attributes:
        cenario: Cenário de `cenarios.yaml`.
        modo: Braço de comparação.
        seed: Seed do ponto experimental.
        duracao_s: Duração simulada. `None` usa a de `cenarios.yaml`.
        gui: Se roda em `sumo-gui`.
        libsumo: Se usa `libsumo` (mais rápido, sem GUI).
        exemplar: Se as transições vão para o banco e as latências detalhadas
            para o CSV (decisão P5).
        persistir: Se grava em `execucao_simulacao`.
        saida_detalhada: Se grava também `queue.xml`, que é volumoso e redundante
            com os detectores E2. Útil para depurar uma execução específica.
        atraso_ms: Atraso por passo na GUI, em milissegundos. Só tem efeito com
            `gui=True`. Zero roda o mais rápido que a máquina permitir.
        diretorio_csv: Onde escrever os CSV de `context/04` §10. `None` usa
            `analysis/data/`. O lote (`sim/controlador/lote.py`) aponta cada
            execução para a **própria** pasta de saída e consolida depois: com
            vários processos escrevendo direto no arquivo compartilhado, as
            linhas se intercalariam e a ordem mudaria a cada corrida.
        ajustes: Valores que substituem os de `parametros.yaml` nesta execução,
            restritos a `AJUSTAVEIS`. Existe para a calibração de P17. Exige
            `persistir=False`: `execucao_simulacao` guarda o snapshot do YAML, e
            a linha mentiria sobre os parâmetros usados.
        transmitir: URL do backend para onde empurrar o estado a 5 Hz
            (`sim/controlador/transmissor.py`). `None`, o padrão, não transmite:
            é assim que o lote roda (decisão de 2026-10-05, Bloco 6).
        id_pedido: O pedido do atendente que originou esta execução, se houver.
    """

    cenario: str
    modo: str
    seed: int
    duracao_s: float | None = None
    gui: bool = False
    libsumo: bool = False
    exemplar: bool = False
    persistir: bool = True
    saida_detalhada: bool = False
    atraso_ms: int = 20
    diretorio_csv: Path | None = None
    ajustes: Ajustes = ()
    transmitir: str | None = None
    id_pedido: int | None = None


def versao_do_codigo() -> str:
    """`git rev-parse --short HEAD`, ou `"desconhecida"` fora de um repositório."""
    resultado = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        cwd=RAIZ,
        check=False,
    )
    return resultado.stdout.strip() or "desconhecida"


def _configuracao() -> dict[str, Any]:
    with CENARIOS_YAML.open(encoding="utf-8") as arquivo:
        dados: dict[str, Any] = yaml.safe_load(arquivo)
    return dados


def parametros_do_modo(modo: str, base: Parametros) -> Parametros:
    """Ajusta os parâmetros ao braço de comparação.

    A única diferença entre `PREEMPCAO` e `PREEMPCAO_COMPENSADA` é
    `n_ciclos_compensacao`: com zero, o motor emite `LIBERAR` em vez de
    `COMPENSAR` e E7 nunca roda. Os dois braços saem, portanto, do **mesmo
    código** — o que é o que permite atribuir a diferença medida a E7, e não a
    uma implementação separada.
    """
    from dataclasses import replace  # import local: uso local

    if modo == "PREEMPCAO":
        return replace(base, n_ciclos_compensacao=0)
    return base


def aplicar_ajustes(base: Parametros, ajustes: Ajustes) -> Parametros:
    """Substitui os parâmetros ajustáveis e revalida o conjunto.

    Args:
        base: Parâmetros lidos de `parametros.yaml`.
        ajustes: Pares (nome, valor), com nomes de `AJUSTAVEIS`.

    Returns:
        Os parâmetros com os ajustes aplicados, ou `base` se não houver ajuste.

    Raises:
        ValueError: se um nome não for ajustável, se aparecer duas vezes, ou se
            um valor inteiro vier com parte fracionária — truncar em silêncio
            mudaria o ponto da grade sem ninguém ver.
        ConfiguracaoInvalidaError: se o conjunto resultante for incoerente.
    """
    from dataclasses import replace  # import local: uso local

    if not ajustes:
        return base
    nomes = [nome for nome, _ in ajustes]
    if desconhecidos := [nome for nome in nomes if nome not in AJUSTAVEIS]:
        raise ValueError(
            f"parâmetro não ajustável: {', '.join(desconhecidos)} "
            f"(ajustáveis: {', '.join(AJUSTAVEIS)})"
        )
    if len(set(nomes)) != len(nomes):
        raise ValueError(f"parâmetro ajustado mais de uma vez: {nomes}")

    valores: dict[str, float | int] = {}
    for nome, valor in ajustes:
        if isinstance(getattr(base, nome), int):
            if valor != int(valor):
                raise ValueError(f"{nome} é inteiro e recebeu {valor}")
            valores[nome] = int(valor)
        else:
            valores[nome] = float(valor)
    ajustados = replace(base, **valores)  # type: ignore[arg-type]
    ajustados.validar()
    return ajustados


def rotulo_dos_ajustes(ajustes: Ajustes) -> str:
    """Nome curto e estável de um conjunto de ajustes, para pastas e relatórios.

    Vazio quando não há ajuste, para que as execuções normais continuem nas
    pastas de sempre.
    """
    return "__".join(f"{nome}-{valor:g}" for nome, valor in sorted(ajustes))


def pasta_de_saida(cenario: str, modo: str, seed: int, ajustes: Ajustes = ()) -> Path:
    """Pasta da saída bruta de uma execução.

    Com ajustes, o rótulo entra no nome. Sem isso, as 15 combinações da
    calibração de P17 escreveriam o `tripinfo.xml` do mesmo (cenário, modo,
    seed) na mesma pasta, em processos paralelos.
    """
    rotulo = rotulo_dos_ajustes(ajustes)
    return SAIDA / (f"{cenario}_{modo}_{seed}" + (f"__{rotulo}" if rotulo else ""))


def _detectores_da_execucao(saida: Path) -> Path:
    """Copia o arquivo de detectores para a pasta da execução.

    Parece um rodeio, e não é. O SUMO resolve o `file` de cada detector
    **relativo ao arquivo que o declara**, e a opção `output-prefix`, que
    existiria para redirecionar isso, é prefixada ao nome já resolvido — o que
    quebra com caminho absoluto. Com a cópia dentro da pasta da execução, os
    nomes relativos caem exatamente onde devem, e cada execução fica com sua
    própria saída de detectores sem nenhuma opção extra.
    """
    destino = saida / DETECTORES.name
    shutil.copy2(DETECTORES, destino)
    return destino


#: Período de agregação da saída `summary`, em segundos.
#:
#: O SUMO grava `summary` e `queue` a **cada passo** por padrão. Com passo de
#: 0,1 s isso dá 36.000 amostras por execução: uma execução de 3.600 s produziu
#: 77 MB de `queue.xml` e 10 MB de `summary.xml`. Nas 600 do Bloco 8 seriam ~46 GB
#: só de fila — num disco de estudante, e para um dado que os detectores E2 já
#: cobrem com agregação de 300 s.
#:
#: É a mesma aritmética das decisões P5 e da latência detalhada: o volume bruto
#: não é gratuito, e o que sustenta as hipóteses são os agregados.
PERIODO_SUMMARY_S = 60


def _comando_sumo(opcoes: Opcoes, rotas: Path, saida: Path, duracao_s: float) -> list[str]:
    binario = "sumo-gui" if opcoes.gui else "sumo"
    return [
        executavel(binario),
        "-c",
        str(CONFIGURACAO_SUMO),
        "--route-files",
        f"{TIPOS_VEICULO},{rotas}",
        "--additional-files",
        str(_detectores_da_execucao(saida)),
        "--seed",
        str(opcoes.seed),
        "--end",
        f"{duracao_s:.0f}",
        # `tripinfo` é a fonte das métricas do VE e das transversais
        # (context/04 §9.1 e §9.2) — uma linha por veículo, não por passo.
        "--tripinfo-output",
        str(saida / "tripinfo.xml"),
        "--summary-output",
        str(saida / "summary.xml"),
        "--summary-output.period",
        str(PERIODO_SUMMARY_S),
        # Colisão precisa ser contável para afirmar que é zero (context/04 §9.4).
        "--collision-output",
        str(saida / "colisoes.xml"),
        # `queue-output` só sob pedido: 77 MB por execução, redundante com os
        # detectores E2 e com a fila máxima que o coletor acumula em memória.
        *(
            ["--queue-output", str(saida / "queue.xml"), "--queue-output.period", "60"]
            if opcoes.saida_detalhada
            else []
        ),
        # Com GUI: começa a rodar sem esperar clique (a demonstração é gravada) e
        # com atraso por passo, senão a simulação passa rápido demais para
        # acompanhar a olho — que é justamente o que a demonstração precisa
        # mostrar. Com passo de 0,1 s, 20 ms de atraso dão ~5x o tempo real.
        *(
            [
                "--start",
                "true",
                "--quit-on-end",
                "false",
                "--delay",
                str(opcoes.atraso_ms),
            ]
            if opcoes.gui
            else []
        ),
    ]


def executar(opcoes: Opcoes) -> ResultadoExecucao:
    """Roda uma execução completa e devolve o resultado consolidado.

    Args:
        opcoes: O ponto experimental e como rodá-lo.

    Returns:
        As métricas da execução.

    Raises:
        ValueError: se o modo não for um dos três braços.
    """
    if opcoes.modo not in MODOS:
        raise ValueError(f"modo desconhecido: {opcoes.modo!r} (esperado um de {', '.join(MODOS)})")
    if opcoes.ajustes and opcoes.persistir:
        raise ValueError(
            "execução com ajustes de parâmetro não pode gravar em execucao_simulacao: "
            "o snapshot do banco é o de parametros.yaml e mentiria sobre o que rodou "
            "(use persistir=False / --sem-banco)"
        )

    configuracao = _configuracao()
    duracao_s = opcoes.duracao_s or float(configuracao["execucao"]["duracao_s"])

    malha = topologia_sumo.carregar()
    if problemas := topologia_sumo.validar(malha):
        raise ValueError("mapa de fases e rede não fecham:\n  " + "\n  ".join(problemas))

    parametros = parametros_do_modo(
        opcoes.modo, aplicar_ajustes(carregar_parametros("simulacao"), opcoes.ajustes)
    )
    rotas = gerar_rotas.garantir(opcoes.cenario, opcoes.seed)
    saida = pasta_de_saida(opcoes.cenario, opcoes.modo, opcoes.seed, opcoes.ajustes)
    saida.mkdir(parents=True, exist_ok=True)

    controlar = opcoes.modo != "FIXO"
    adaptador = AdaptadorSumo(
        cliente=abrir_cliente(gui=opcoes.gui, usar_libsumo=opcoes.libsumo),
        malha=malha,
        parametros=parametros,
        controlar=controlar,
    )
    # O motor publica os conflitos entre VEs num buffer, e não no coletor: a
    # publicação acontece dentro do trecho cronometrado do laço, e um `append`
    # não mexe na medição do RNF01 — agregar episódios mexeria (entrega 10.1).
    conflitos: list[EventoConflito] = []
    motor = MotorDecisao(
        parametros=parametros,
        topologia=malha.topologia,
        observador_conflito=conflitos.append,
    )
    verificador = VerificadorSeguranca(parametros=parametros)
    coletor = ColetorMetricas(
        cenario=opcoes.cenario,
        modo=opcoes.modo,
        seed=opcoes.seed,
        passo_s=float(configuracao["execucao"]["passo_s"]),
    )

    registro = _abrir_registro(opcoes, parametros, duracao_s) if opcoes.persistir else None

    transmissor = _transmissor(opcoes)
    adaptador.iniciar(_comando_sumo(opcoes, rotas, saida, duracao_s))
    try:
        _laco(adaptador, motor, verificador, coletor, duracao_s, controlar, conflitos, transmissor)
    finally:
        adaptador.fechar()
        if transmissor is not None:
            transmissor.encerrar()

    resultado = coletor.consolidar(
        tripinfo=saida / "tripinfo.xml",
        duracao_s=duracao_s,
        veiculos_planejados=_veiculos_planejados(rotas),
        aquecimento_s=float(configuracao["execucao"]["aquecimento_s"]),
        avisos=[
            *adaptador.avisos,
            *(
                f"{quantas}x comando {tipo} recusado ({motivo})"
                for (tipo, motivo), quantas in sorted(adaptador.recusas.items())
            ),
        ],
    )

    gravar_csv(
        resultado,
        id_execucao=registro,
        versao_codigo=versao_do_codigo(),
        detalhar_latencias=opcoes.exemplar,
        diretorio=opcoes.diretorio_csv or DADOS,
    )
    if registro is not None:
        _fechar_registro(registro, resultado, exemplar=opcoes.exemplar)

    return resultado


def _transmissor(opcoes: Opcoes) -> Transmissor | None:
    if opcoes.transmitir is None:
        return None
    transmissor = Transmissor(
        url_backend=opcoes.transmitir,
        cenario=opcoes.cenario,
        modo=opcoes.modo,
        seed=opcoes.seed,
        georreferencia=georreferencia.carregar(),
        id_pedido=opcoes.id_pedido,
    )
    transmissor.iniciar()
    return transmissor


def _laco(
    adaptador: AdaptadorSumo,
    motor: MotorDecisao,
    verificador: VerificadorSeguranca,
    coletor: ColetorMetricas,
    duracao_s: float,
    controlar: bool,
    conflitos: list[EventoConflito],
    transmissor: Transmissor | None = None,
) -> None:
    """O laço de `context/04` §8.

    A ordem importa: primeiro o passo do simulador, depois a leitura do estado,
    depois a decisão (cronometrada **sem** I/O), depois a atuação e, por último,
    a verificação dos invariantes sobre o estado resultante.

    O buffer `conflitos` é preenchido pelo motor durante a decisão e drenado
    depois que o cronômetro para. A transmissão ao vivo, quando ligada, também
    fica fora do trecho cronometrado, e só anexa o estado numa fila.
    """
    while adaptador.cliente.tempo() < duracao_s:
        t = adaptador.passo()
        estado = adaptador.ler_estado(t)

        latencia_ms: float | None = None
        if controlar:
            inicio = time.perf_counter()
            comandos = motor.avaliar(estado)
            latencia_ms = (time.perf_counter() - inicio) * 1000.0
            coletor.registrar_decisao(latencia_ms, len(comandos))
            coletor.registrar_conflitos(conflitos)
            conflitos.clear()
        else:
            comandos = []
        if transmissor is not None:
            transmissor.publicar(estado, latencia_ms)

        transicoes = adaptador.aplicar(comandos, t)

        coletor.registrar_estado(estado)
        coletor.registrar_transicoes(transicoes)
        coletor.registrar_incidentes(adaptador.colisoes(), adaptador.teleportes())

        for id_semaforo, controlador in adaptador.controladores().items():
            violacoes = verificador.verificar(
                controlador,
                adaptador.malha.topologia.cruzamento(id_semaforo),
                t,
                [tr for tr in transicoes if tr.id_semaforo == id_semaforo],
            )
            if violacoes:
                coletor.registrar_violacoes(violacoes)
                # Fail-safe de `context/01` §6: abandona a preempção e volta ao
                # ciclo fixo. A execução continua — o incidente fica registrado e
                # `validar_execucao()` a reprova depois (context/06 §4).
                adaptador.aplicar([motor.abortar(id_semaforo, str(violacoes[0]))], t)

        if adaptador.cliente.veiculos_restantes() == 0:
            break


def _veiculos_planejados(rotas: Path) -> int:
    """Quantos veículos o arquivo de rotas declara."""
    return rotas.read_text(encoding="utf-8").count("<vehicle ")


# ---------------------------------------------------------------------------
# Persistência — opcional, e sempre fora do laço
# ---------------------------------------------------------------------------


def _abrir_registro(opcoes: Opcoes, parametros: Parametros, duracao_s: float) -> int | None:
    """Cria a linha em `execucao_simulacao` e devolve o id.

    Devolve `None` (com aviso) se o banco não estiver acessível: uma execução de
    simulação não deve ser impedida por o Postgres estar fora do ar, e os CSV de
    `analysis/data/` seguem sendo escritos. O que **não** pode acontecer é a
    linha existir sem `versao_codigo` e sem o snapshot de parâmetros.
    """
    del parametros
    try:
        from app.models import ModoControle  # import local: I/O fora de core/
        from app.repositories.experimento import abrir_execucao  # import local
        from app.repositories.sessao import (  # import local
            criar_engine,
            criar_fabrica_sessao,
            sessao_de,
        )

        fabrica = criar_fabrica_sessao(criar_engine())
        with sessao_de(fabrica) as sessao:
            execucao = abrir_execucao(
                sessao,
                nome_cenario=opcoes.cenario,
                modo=ModoControle(opcoes.modo),
                seed=opcoes.seed,
                duracao_s=int(duracao_s),
                arquivo_rede="sim/rede/malha.net.xml",
                parametros=dict(snapshot_parametros("simulacao")),
                versao_codigo=versao_do_codigo(),
                exemplar=opcoes.exemplar,
            )
            return int(execucao.id_execucao)
    except Exception as erro:  # banco indisponível não derruba a simulação
        print(f"  aviso: não gravei em execucao_simulacao ({erro.__class__.__name__}: {erro})")
        return None


def _fechar_registro(id_execucao: int, resultado: ResultadoExecucao, *, exemplar: bool) -> None:
    """Marca a execução como finalizada e, se exemplar, grava as transições.

    A gravação das transições acontece **aqui**, depois do laço, em lote — nunca
    dentro do passo (`context/03` §4.1).
    """
    try:
        from app.models import EstadoSinal, ExecucaoSimulacao, Semaforo  # import local
        from app.repositories.experimento import (  # import local
            fechar_execucao,
            transicao_para_fila,
        )
        from app.repositories.fila_lote import fila_de_gravacao  # import local
        from app.repositories.sessao import (  # import local
            criar_engine,
            criar_fabrica_sessao,
            sessao_de,
        )

        fabrica = criar_fabrica_sessao(criar_engine())

        if exemplar and resultado.transicoes:
            with sessao_de(fabrica) as sessao:
                por_codigo = {
                    semaforo.codigo_externo: semaforo.id_semaforo
                    for semaforo in sessao.query(Semaforo).all()
                }
            with fila_de_gravacao(fabrica) as fila:
                for transicao in resultado.transicoes:
                    fk = por_codigo.get(transicao.id_semaforo)
                    if fk is None:
                        continue
                    transicao_para_fila(
                        fila,
                        fk_execucao=id_execucao,
                        fk_semaforo=fk,
                        t_simulacao=transicao.t,
                        fase=transicao.fase,
                        estado=EstadoSinal(transicao.sinal.value),
                        fase_anterior=transicao.fase_anterior,
                        duracao_fase_anterior_s=transicao.duracao_fase_anterior_s,
                        em_preempcao=transicao.em_preempcao,
                    )
                    fila.descarregar_se_necessario()

        with sessao_de(fabrica) as sessao:
            execucao = sessao.get(ExecucaoSimulacao, id_execucao)
            if execucao is not None:
                fechar_execucao(sessao, execucao)
    except Exception as erro:  # banco indisponível não derruba a simulação
        print(f"  aviso: não fechei execucao_simulacao ({erro.__class__.__name__}: {erro})")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _resumo(resultado: ResultadoExecucao) -> str:
    linhas = [
        f"cenário {resultado.cenario} · modo {resultado.modo} · seed {resultado.seed}",
        f"  veículos            {resultado.veiculos_completos}/{resultado.veiculos_planejados}"
        " completaram a rota",
        f"  VEs                 {len(resultado.viagens_ve)}"
        f" · travessia média {resultado.tempo_medio_travessia_ve_s:.1f}s"
        f" · paradas médias {resultado.paradas_medias_ve:.2f}",
        f"  transversal         espera média {resultado.tempo_espera_medio_transversal_s:.2f}s",
        f"  atraso total        {resultado.atraso_total_rede_s:.0f}s",
        f"  latência decisão    média {resultado.latencia_media_ms:.3f}ms"
        f" · p95 {resultado.latencia_p95_ms:.3f}ms"
        f" · p99 {resultado.latencia_p99_ms:.3f}ms"
        f" · máx {resultado.latencia_max_ms:.3f}ms",
        f"  transições          {len(resultado.transicoes)}",
        f"  colisões            {resultado.colisoes}",
        f"  teleportes          {resultado.teleportes}",
        f"  violações I1..I5    {len(resultado.violacoes)}",
    ]
    linhas += [f"  ! {violacao}" for violacao in resultado.violacoes[:5]]
    if resultado.avisos:
        linhas.append(f"  avisos              {len(resultado.avisos)}")
        linhas += [f"  ! {aviso}" for aviso in resultado.avisos[:5]]
    return "\n".join(linhas)


def main(argumentos: Sequence[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(description="Roda uma execução de simulação (3.7).")
    analisador.add_argument("--cenario", required=True)
    analisador.add_argument("--modo", required=True, choices=MODOS)
    analisador.add_argument("--seed", type=int, required=True)
    analisador.add_argument("--duracao", type=float, default=None, help="segundos simulados")
    analisador.add_argument("--gui", action="store_true", help="roda na sumo-gui")
    analisador.add_argument("--libsumo", action="store_true", help="mais rápido, sem GUI")
    analisador.add_argument(
        "--exemplar",
        action="store_true",
        help="persiste transições no banco e latências detalhadas (decisão P5)",
    )
    analisador.add_argument(
        "--sem-banco", action="store_true", help="não grava em execucao_simulacao"
    )
    analisador.add_argument(
        "--saida-detalhada",
        action="store_true",
        help="grava também queue.xml (~77 MB por execução; redundante com os detectores E2)",
    )
    analisador.add_argument(
        "--transmitir",
        nargs="?",
        const=os.getenv("BACKEND_URL", "http://localhost:8000"),
        default=None,
        metavar="URL",
        help="empurra o estado a 5 Hz ao backend, para o dashboard (padrão: $BACKEND_URL)",
    )
    analisador.add_argument(
        "--atraso-ms",
        type=int,
        default=20,
        help="atraso por passo na GUI, em ms (só com --gui; 0 roda o mais rápido possível)",
    )
    opcoes = analisador.parse_args(argumentos)

    resultado = executar(
        Opcoes(
            cenario=opcoes.cenario,
            modo=opcoes.modo,
            seed=opcoes.seed,
            duracao_s=opcoes.duracao,
            gui=opcoes.gui,
            libsumo=opcoes.libsumo,
            exemplar=opcoes.exemplar,
            persistir=not opcoes.sem_banco,
            saida_detalhada=opcoes.saida_detalhada,
            atraso_ms=opcoes.atraso_ms,
            transmitir=opcoes.transmitir,
        )
    )
    print(_resumo(resultado))
    return 1 if resultado.violacoes or resultado.colisoes or resultado.teleportes else 0


if __name__ == "__main__":
    raise SystemExit(main())
