"""Medição do fluxo de saturação da malha — entrega 3.0 (P11).

**O fluxo de saturação é medido, não adotado da literatura** (decisão de
2026-08-25, `context/09`). A malha simulada tem um fluxo de saturação próprio,
que emerge dos parâmetros de car-following de `sim/demanda/veiculos.typ.xml`
(`accel`, `decel`, `tau`, `minGap`, `length`). Adotar um valor de manual e
aplicá-lo a uma malha que na verdade escoa outro produziria um v/c errado com
aparência de rigor.

O MÉTODO é o de campo, aplicado à simulação:

1. Mantém a aproximação no vermelho enquanto uma fila se forma.
2. Abre o verde e o mantém aberto.
3. Cronometra o instante em que cada veículo cruza a linha de retenção, por faixa.
4. **Descarta os primeiros veículos** — o *start-up lost time*, em que a fila
   ainda está acelerando e o headway ainda não estabilizou.
5. Calcula `3600 / headway médio` do trecho saturado.

O tempo perdido na partida sai da mesma medição, como o excesso de headway dos
veículos descartados em relação ao headway de saturação. Ele entra na conta de
capacidade em `cenarios.py` — sem ele, o verde efetivo seria superestimado e
todos os v/c sairiam otimistas.

Uso::

    python -m sim.calibracao.fluxo_saturacao            # mede e grava o CSV
    python -m sim.calibracao.fluxo_saturacao --seed 7   # outra seed

Marcado indiretamente como teste `sumo`: exige o binário instalado.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

import yaml

from adapters.terminal import saida_utf8
from sim.ambiente import executavel, registrar_ferramentas
from sim.controlador.executor import versao_do_codigo

RAIZ = Path(__file__).resolve().parents[2]
REDE = RAIZ / "sim" / "rede" / "malha.net.xml"
TIPOS = RAIZ / "sim" / "demanda" / "veiculos.typ.xml"
CENARIOS = RAIZ / "sim" / "config" / "cenarios.yaml"
SAIDA_CSV = RAIZ / "analysis" / "data" / "fluxo_saturacao.csv"

#: Veículos descartados no início do verde (start-up lost time). Quatro é a
#: prática consolidada em estudo de campo: a partir do quinto veículo o headway
#: já estabilizou. O valor é parâmetro do método e vai declarado no CSV.
VEICULOS_DESCARTADOS = 4

#: Veículos enfileirados por faixa antes de abrir o verde. Precisa ser bem maior
#: que `VEICULOS_DESCARTADOS` para que o trecho saturado tenha amostra.
FILA_POR_FAIXA = 30

#: Duração do vermelho de acumulação, em segundos.
ACUMULACAO_S = 120.0

#: Teto de tempo simulado da medição, em segundos. Só para não travar caso algo
#: dê errado — a medição termina sozinha quando a fila escoa.
LIMITE_S = 900.0

PASSO_S = 0.1

#: Aproximações medidas: (nome, via de entrada, cruzamento, via de saída).
#: Uma por tipo de via — arterial e transversal têm velocidade e número de
#: faixas diferentes, e nada garante a priori que descarreguem no mesmo ritmo.
APROXIMACOES = {
    "arterial": ("A1_L0", "CRUZ_01", "A1_L1"),
    "transversal": ("T1_S0", "CRUZ_01", "T1_S1"),
}


@dataclass(frozen=True)
class MedicaoDeFaixa:
    """Resultado da medição em uma faixa.

    Attributes:
        aproximacao: `"arterial"` ou `"transversal"`.
        faixa: Id da faixa no SUMO.
        n_veiculos_uteis: Veículos usados no cálculo, já descontados os descartados.
        headway_saturacao_s: Headway médio do trecho saturado, em segundos.
        fluxo_saturacao_veic_h_faixa: `3600 / headway`, em veíc./h por faixa.
        tempo_perdido_partida_s: Excesso de headway dos primeiros veículos, em segundos.
    """

    aproximacao: str
    faixa: str
    n_veiculos_uteis: int
    headway_saturacao_s: float
    fluxo_saturacao_veic_h_faixa: float
    tempo_perdido_partida_s: float


# ---------------------------------------------------------------------------
# Aritmética da medição — pura, testável sem SUMO
# ---------------------------------------------------------------------------


def headway_de_saturacao(
    travessias_s: Sequence[float],
    inicio_do_verde_s: float,
    descartados: int = VEICULOS_DESCARTADOS,
    janela_s: float | None = None,
) -> tuple[float, float]:
    """Headway de saturação e tempo perdido na partida, a partir das travessias.

    A `janela_s` é o que impede um erro sutil e caro. Fluxo de saturação é a taxa
    com que a fila escoa **durante um verde**, e o verde real dura 30 s. Se a
    medição continuar contando depois disso, os veículos do fim da fila já
    cruzam a linha em velocidade de fluxo livre, com headway bem menor que o de
    descarga — e o número sai inflado, descrevendo um regime que o cruzamento
    nunca vive. Limitar a janela à duração do verde é o mesmo recorte do estudo
    de campo, que mede a descarga da fila inicial.

    Args:
        travessias_s: Instantes em que cada veículo cruzou a linha de retenção,
            em ordem crescente, em segundos.
        inicio_do_verde_s: Instante em que o verde abriu, em segundos. É a
            referência do headway do primeiro veículo.
        descartados: Quantos veículos do início da fila ignorar (*start-up lost
            time*, em que a fila ainda acelera).
        janela_s: Duração do verde considerada, em segundos. `None` conta todas
            as travessias.

    Returns:
        `(headway_saturacao_s, tempo_perdido_partida_s)`.

    Raises:
        ValueError: se não sobrarem veículos suficientes depois do descarte —
            medir saturação com dois carros não mede nada.
    """
    if janela_s is not None:
        limite = inicio_do_verde_s + janela_s
        travessias_s = [t for t in travessias_s if t <= limite]

    if len(travessias_s) <= descartados + 1:
        raise ValueError(
            f"amostra insuficiente: {len(travessias_s)} travessias para "
            f"{descartados} descartes; aumente FILA_POR_FAIXA ou a janela"
        )

    marcos = [inicio_do_verde_s, *travessias_s]
    headways = [depois - antes for antes, depois in pairwise(marcos)]

    uteis = headways[descartados:]
    headway_saturacao = sum(uteis) / len(uteis)

    # O tempo perdido na partida é o quanto os primeiros veículos gastaram ALÉM
    # do headway já saturado — é o custo de a fila ter de acelerar do zero.
    perda = sum(h - headway_saturacao for h in headways[:descartados])
    return headway_saturacao, max(perda, 0.0)


def fluxo_veic_h(headway_s: float) -> float:
    """Converte headway de saturação em fluxo, em veículos por hora e por faixa."""
    if headway_s <= 0:
        raise ValueError("headway precisa ser > 0")
    return 3600.0 / headway_s


# ---------------------------------------------------------------------------
# Montagem do cenário de saturação
# ---------------------------------------------------------------------------


def _configuracao() -> dict[str, Any]:
    with CENARIOS.open(encoding="utf-8") as arquivo:
        dados: dict[str, Any] = yaml.safe_load(arquivo)
    return dados


def _proporcao_onibus() -> float:
    return float(_configuracao()["composicao"]["proporcao_onibus"])


def verde_do_programa_s() -> float:
    """Duração do verde do baseline, em segundos — a janela de medição.

    Vem de `sim/config/cenarios.yaml`, o mesmo lugar de onde a conta de
    capacidade a lê. Se o programa semafórico mudar, a medição acompanha sem que
    ninguém precise lembrar de mexer em dois arquivos.
    """
    return float(_configuracao()["programa"]["verde_s"])


def _escrever_rotas(destino: Path, entrada: str, saida: str, n_veiculos: int) -> None:
    """Fila de veículos parados na aproximação, com a composição dos cenários.

    A alternância carro/ônibus é determinística (a cada `1/proporção` veículos),
    não sorteada: a medição precisa dar o mesmo resultado a cada execução, e um
    ônibus a mais ou a menos no trecho saturado mexe no headway médio.
    """
    proporcao = _proporcao_onibus()
    passo_onibus = round(1 / proporcao) if proporcao > 0 else 0

    linhas = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<!-- GERADO por sim/calibracao/fluxo_saturacao.py. Arquivo temporário. -->",
        "<routes>",
        f'    <route id="SAT" edges="{entrada} {saida}"/>',
    ]
    for indice in range(n_veiculos):
        tipo = "onibus" if passo_onibus and indice % passo_onibus == passo_onibus - 1 else "carro"
        linhas.append(
            f'    <vehicle id="sat_{indice:03d}" type="{tipo}" route="SAT" '
            f'depart="0.00" departLane="free" departSpeed="0"/>'
        )
    linhas.append("</routes>")
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def _escrever_detectores(destino: Path, faixas: Sequence[str]) -> None:
    """Laços de indução na linha de retenção, um por faixa.

    `pos="-0.10"` põe o laço rente ao fim da faixa, que é onde fica a linha de
    retenção. O instante de passagem vem de `getVehicleData`, que interpola
    dentro do passo — sem isso a resolução seria o passo de 0,1 s, uns 5% de erro
    sobre um headway de 2 s.
    """
    linhas = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<!-- GERADO por sim/calibracao/fluxo_saturacao.py. Arquivo temporário. -->",
        "<additional>",
    ]
    linhas += [
        f'    <inductionLoop id="SAT_{faixa}" lane="{faixa}" pos="-0.10" '
        f'period="100000" file="saturacao_detectores.xml"/>'
        for faixa in faixas
    ]
    linhas.append("</additional>")
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def _faixas_de(entrada: str) -> list[str]:
    registrar_ferramentas()
    import sumolib  # import local: depende de SUMO_HOME no sys.path

    rede = sumolib.net.readNet(str(REDE))
    return [faixa.getID() for faixa in rede.getEdge(entrada).getLanes()]


def _estados_do_semaforo(traci_: Any, id_semaforo: str, entrada: str) -> tuple[str, str]:
    """Devolve `(estado_all_red, estado_verde_da_aproximação)` do programa vigente.

    A fase de verde é **procurada**, não assumida: qual índice serve a arterial e
    qual serve a transversal é detalhe do programa, e fixar `phases[0]` faria a
    medição da transversal rodar com ela no vermelho — a fila nunca escoaria e o
    erro apareceria como "amostra insuficiente", longe da causa.

    Args:
        traci_: Módulo TraCI conectado.
        id_semaforo: Cruzamento medido.
        entrada: Via de aproximação cujos links precisam estar verdes.

    Returns:
        `(todo_vermelho, verde)` como state strings.

    Raises:
        ValueError: se nenhuma fase do programa der verde à aproximação.
    """
    links = traci_.trafficlight.getControlledLinks(id_semaforo)
    indices = [
        posicao
        for posicao, conexoes in enumerate(links)
        if conexoes and str(conexoes[0][0]).rsplit("_", 1)[0] == entrada
    ]
    if not indices:
        raise ValueError(f"{entrada} não é aproximação de {id_semaforo}")

    logica = traci_.trafficlight.getAllProgramLogics(id_semaforo)[0]
    for fase in logica.phases:
        if all(fase.state[i] in "Gg" for i in indices):
            return "r" * len(fase.state), fase.state
    raise ValueError(f"nenhuma fase de {id_semaforo} dá verde a {entrada}")


def medir_aproximacao(
    nome: str,
    *,
    seed: int = 1,
    fila_por_faixa: int = FILA_POR_FAIXA,
    janela_s: float | None = None,
) -> list[MedicaoDeFaixa]:
    """Mede o fluxo de saturação de uma aproximação da malha.

    Args:
        nome: Chave de `APROXIMACOES` — `"arterial"` ou `"transversal"`.
        seed: Seed do SUMO. Registrada no CSV; a medição é pouco sensível a ela,
            já que a fila é determinística.
        fila_por_faixa: Veículos enfileirados por faixa antes de abrir o verde.
        janela_s: Duração do verde considerada. Padrão: o verde do baseline.

    Returns:
        Uma medição por faixa da aproximação.
    """
    registrar_ferramentas()
    import traci  # import local: depende de SUMO_HOME no sys.path

    entrada, id_semaforo, saida = APROXIMACOES[nome]
    faixas = _faixas_de(entrada)

    with tempfile.TemporaryDirectory() as temporario:
        area = Path(temporario)
        rotas, detectores = area / "saturacao.rou.xml", area / "saturacao.add.xml"
        _escrever_rotas(rotas, entrada, saida, fila_por_faixa * len(faixas))
        _escrever_detectores(detectores, faixas)

        comando = [
            executavel("sumo"),
            "--net-file",
            str(REDE),
            "--route-files",
            f"{TIPOS},{rotas}",
            "--additional-files",
            str(detectores),
            "--step-length",
            str(PASSO_S),
            "--seed",
            str(seed),
            "--no-step-log",
            "true",
            "--no-warnings",
            "true",
            "--time-to-teleport",
            "-1",
        ]
        traci.start(comando)
        try:
            travessias = _coletar_travessias(traci, id_semaforo, entrada, faixas)
        finally:
            traci.close()

    inicio_verde = ACUMULACAO_S
    janela = janela_s if janela_s is not None else verde_do_programa_s()
    medicoes: list[MedicaoDeFaixa] = []
    for faixa in faixas:
        na_janela = [t for t in sorted(travessias[faixa]) if t <= inicio_verde + janela]
        headway, perda = headway_de_saturacao(na_janela, inicio_verde, janela_s=janela)
        medicoes.append(
            MedicaoDeFaixa(
                aproximacao=nome,
                faixa=faixa,
                n_veiculos_uteis=len(na_janela) - VEICULOS_DESCARTADOS,
                headway_saturacao_s=headway,
                fluxo_saturacao_veic_h_faixa=fluxo_veic_h(headway),
                tempo_perdido_partida_s=perda,
            )
        )
    return medicoes


def _coletar_travessias(
    traci_: Any, id_semaforo: str, entrada: str, faixas: Sequence[str]
) -> dict[str, list[float]]:
    """Roda a simulação e devolve os instantes de travessia por faixa.

    O vermelho de acumulação é imposto por `setRedYellowGreenState`, não pelo
    programa: durante a medição o cruzamento não cicla, e é isso que garante que
    todo o escoamento observado pertence a um único verde.

    Travessias anteriores à abertura do verde são ignoradas. Elas só ocorrem se o
    veículo da cabeça da fila parar em cima do laço — situação que o SUMO não
    produz na prática (ele para uns centímetros antes da linha), mas que, se
    ocorresse, contaminaria o headway do primeiro veículo com tempo de vermelho.
    """
    todo_vermelho, verde = _estados_do_semaforo(traci_, id_semaforo, entrada)
    travessias: dict[str, list[float]] = {faixa: [] for faixa in faixas}
    vistos: set[str] = set()

    traci_.trafficlight.setRedYellowGreenState(id_semaforo, todo_vermelho)
    verde_aberto = False

    while traci_.simulation.getTime() < LIMITE_S:
        traci_.simulationStep()
        agora = traci_.simulation.getTime()

        if not verde_aberto and agora >= ACUMULACAO_S:
            traci_.trafficlight.setRedYellowGreenState(id_semaforo, verde)
            verde_aberto = True

        if not verde_aberto:
            continue

        for faixa in faixas:
            for dados in traci_.inductionloop.getVehicleData(f"SAT_{faixa}"):
                identificador, _, entrada_s = dados[0], dados[1], dados[2]
                if identificador not in vistos and entrada_s >= ACUMULACAO_S:
                    vistos.add(identificador)
                    travessias[faixa].append(entrada_s)

        # A fila escoou: não há mais veículo esperando nem rodando.
        if traci_.simulation.getMinExpectedNumber() == 0:
            break

    return travessias


# ---------------------------------------------------------------------------
# CSV e CLI
# ---------------------------------------------------------------------------


def _versao_do_sumo() -> str:
    saida = subprocess.run(
        [executavel("sumo"), "--version"], capture_output=True, text=True, timeout=30, check=True
    )
    return saida.stdout.splitlines()[0].strip()


def gravar_csv(medicoes: Sequence[MedicaoDeFaixa], seed: int, destino: Path = SAIDA_CSV) -> Path:
    """Grava a medição em `analysis/data/fluxo_saturacao.csv`.

    O CSV carrega a versão do SUMO, a versão do código e a data: uma medição sem
    a procedência não é reprodutível, e é ela que sustenta o número no texto.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(
            [
                "medido_em",
                "versao_sumo",
                "versao_codigo",
                "seed",
                "veiculos_descartados",
                "janela_verde_s",
                "aproximacao",
                "faixa",
                "n_veiculos_uteis",
                "headway_saturacao_s",
                "fluxo_saturacao_veic_h_faixa",
                "tempo_perdido_partida_s",
            ]
        )
        agora = datetime.now(UTC).isoformat(timespec="seconds")
        sumo, codigo = _versao_do_sumo(), versao_do_codigo()
        for medicao in medicoes:
            escritor.writerow(
                [
                    agora,
                    sumo,
                    codigo,
                    seed,
                    VEICULOS_DESCARTADOS,
                    f"{verde_do_programa_s():.1f}",
                    medicao.aproximacao,
                    medicao.faixa,
                    medicao.n_veiculos_uteis,
                    f"{medicao.headway_saturacao_s:.4f}",
                    f"{medicao.fluxo_saturacao_veic_h_faixa:.1f}",
                    f"{medicao.tempo_perdido_partida_s:.3f}",
                ]
            )
    return destino


def main(argumentos: list[str] | None = None) -> int:
    saida_utf8()
    analisador = argparse.ArgumentParser(
        description="Mede o fluxo de saturação da malha (entrega 3.0, P11)."
    )
    analisador.add_argument("--seed", type=int, default=1)
    analisador.add_argument("--fila-por-faixa", type=int, default=FILA_POR_FAIXA)
    opcoes = analisador.parse_args(argumentos)

    if not REDE.is_file():
        print(f"{REDE} não existe — rode `python -m sim.rede.construir` antes.")
        return 1

    medicoes: list[MedicaoDeFaixa] = []
    for nome in APROXIMACOES:
        print(f"medindo aproximação {nome}...")
        medicoes += medir_aproximacao(nome, seed=opcoes.seed, fila_por_faixa=opcoes.fila_por_faixa)

    destino = gravar_csv(medicoes, opcoes.seed)

    print(f"\n{'aproximação':<14}{'faixa':<12}{'headway':>9}{'veíc/h/faixa':>14}{'perda':>9}")
    for medicao in medicoes:
        print(
            f"{medicao.aproximacao:<14}{medicao.faixa:<12}"
            f"{medicao.headway_saturacao_s:>8.3f}s"
            f"{medicao.fluxo_saturacao_veic_h_faixa:>14.0f}"
            f"{medicao.tempo_perdido_partida_s:>8.2f}s"
        )
    print(f"\ngravado em {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
