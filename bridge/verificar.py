"""Verificação da ponte de ponta a ponta, pelo HTTP — com o dublê ou com a bancada.

Dirige a ponte como o backend vai dirigir (`POST /comandos`), acompanha o UNO
por `GET /estado` e confere o comportamento de referência de `context/05` §6 e
§8. O mesmo roteiro serve aos dois lados do cabo::

    python -m bridge.main --simulado        # ou --porta COM3, com a placa
    python -m bridge.verificar              # noutro terminal, logo em seguida

Leva cerca de dois minutos, quase todos esperando o relógio do semáforo: o ciclo
fixo é de 24 s e o timeout da preempção, de 30 s.

**Isto não mede H3.** As latências que aparecem aqui são uma conferência de que
o `t_atuacao` existe e vem depois do envio. Com o dublê, a latência é uma
constante digitada. Na bancada, a medição de H3 segue o checklist (`context/06`).

O que o HTTP não alcança fica de fora, e é dito no fim: watchdog, reconexão,
`SAFE` e modo de teste não têm `Comando` do motor que os acione. Eles são
cobertos por `backend/tests/adapters/test_hardware_simulado.py` e
`bridge/tests/test_ponte.py` e, na bancada, pelo checklist (puxar o cabo).
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

CRUZ = "PROTO_CRUZ_01"
N_FASES = 4

# Perfil de bancada (parametros.hardware.yaml) — o que o roteiro espera ver.
VERDE_S, AMARELO_S, ALL_RED_S = 3.0, 2.0, 1.0
CICLO_S = N_FASES * (VERDE_S + AMARELO_S + ALL_RED_S)
PIOR_CASO_S = VERDE_S + AMARELO_S + ALL_RED_S
TIMEOUT_PREEMPCAO_S = 30.0

#: A telemetria chega a 2 Hz: um instante observado pode estar até 0,5 s atrasado.
FOLGA_S = 0.6


# ---------------------------------------------------------------------------
# Invariantes sobre a sequência de telemetrias — puro, testado à parte
# ---------------------------------------------------------------------------


def violacoes(sequencia: Sequence[str]) -> list[str]:
    """I1, I2 e I3 sobre uma sequência de estados `S1S2S3S4`, como na linha `ST`.

    Pressupõe amostragem mais fina que o amarelo e o all-red — a 2 Hz, com 2 s e
    1 s, cada um aparece em pelo menos duas amostras. Estados de modo de teste
    não devem entrar: o teste garante I1, não I2 e I3.

    Returns:
        Uma descrição por violação; vazia quando nada foi violado.
    """
    achados: list[str] = []
    for i, estado in enumerate(sequencia):
        if estado.count("G") > 1:
            achados.append(f"I1: dois verdes na amostra {i}: {estado}")
        if i == 0:
            continue
        antes = sequencia[i - 1]
        for modulo, (a, d) in enumerate(zip(antes, estado, strict=True)):
            if a == "G" and d == "R":
                achados.append(f"I2: S{modulo + 1} verde -> vermelho na amostra {i}")
            if d == "G" and a != "G" and antes != "RRRR":
                achados.append(f"I3: S{modulo + 1} abriu sem all-red na amostra {i}: {antes}")
    return achados


# ---------------------------------------------------------------------------
# Acesso à ponte
# ---------------------------------------------------------------------------


def _instante(texto: str) -> float:
    return datetime.fromisoformat(texto).timestamp()


class Ponte:
    """Cliente HTTP mínimo — só biblioteca padrão, para rodar na bancada sem extras."""

    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/")

    def _pedir(self, metodo: str, caminho: str, corpo: Any = None) -> tuple[int, Any]:
        dados = None if corpo is None else json.dumps(corpo).encode()
        pedido = urllib.request.Request(
            self.url + caminho,
            data=dados,
            method=metodo,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(pedido, timeout=5) as resposta:
                return resposta.status, json.load(resposta)
        except urllib.error.HTTPError as erro:
            return erro.code, json.load(erro)

    def health(self) -> tuple[int, Any]:
        return self._pedir("GET", "/health")

    def estado(self) -> Any:
        return self._pedir("GET", "/estado")[1]

    def comando(self, tipo: str, **campos: Any) -> tuple[int, Any]:
        corpo = {"tipo": tipo, "id_semaforo": CRUZ, "motivo": "verificar.py", **campos}
        return self._pedir("POST", "/comandos", corpo)


@dataclass
class Amostra:
    recebida_em: float
    t_dispositivo_ms: int
    fase: int
    cores: str
    em_preempcao: bool
    em_teste: bool


@dataclass
class Observador:
    """Lê `/estado` a 10 Hz numa thread e guarda cada telemetria e evento novo."""

    ponte: Ponte
    amostras: list[Amostra] = field(default_factory=list)
    eventos: list[tuple[float, str]] = field(default_factory=list)
    _vistos: set[tuple[str, int, str]] = field(default_factory=set)
    _trava: threading.Lock = field(default_factory=threading.Lock)
    _parar: threading.Event = field(default_factory=threading.Event)

    def iniciar(self) -> None:
        threading.Thread(target=self._laco, daemon=True).start()

    def parar(self) -> None:
        self._parar.set()

    def _laco(self) -> None:
        ultima_ms: int | None = None
        while not self._parar.is_set():
            try:
                estado = self.ponte.estado()
            except OSError:
                time.sleep(0.1)
                continue
            telemetria = estado.get("telemetria")
            with self._trava:
                if telemetria and telemetria["t_dispositivo_ms"] != ultima_ms:
                    ultima_ms = telemetria["t_dispositivo_ms"]
                    self.amostras.append(Amostra(_instante(estado["recebida_em"]), **telemetria))
                for evento in estado["eventos"]:
                    chave = (evento["recebido_em"], evento["t_dispositivo_ms"], evento["tipo"])
                    if chave not in self._vistos:
                        self._vistos.add(chave)
                        self.eventos.append((_instante(evento["recebido_em"]), evento["tipo"]))
            time.sleep(0.1)

    def ultima(self) -> Amostra | None:
        with self._trava:
            return self.amostras[-1] if self.amostras else None

    def desde(self, t: float) -> list[Amostra]:
        with self._trava:
            return [a for a in self.amostras if a.recebida_em >= t]

    def eventos_desde(self, t: float, tipo: str) -> list[float]:
        with self._trava:
            return [quando for quando, nome in self.eventos if quando >= t and nome == tipo]

    def esperar(self, condicao: Callable[[Amostra], bool], limite_s: float) -> Amostra | None:
        fim = time.monotonic() + limite_s
        visto = len(self.amostras)
        while time.monotonic() < fim:
            with self._trava:
                novas = self.amostras[visto:]
                visto = len(self.amostras)
            for amostra in novas:
                if condicao(amostra):
                    return amostra
            time.sleep(0.05)
        return None

    def esperar_evento(self, desde: float, tipo: str, limite_s: float) -> float | None:
        fim = time.monotonic() + limite_s
        while time.monotonic() < fim:
            encontrados = self.eventos_desde(desde, tipo)
            if encontrados:
                return encontrados[0]
            time.sleep(0.05)
        return None


def _seg(valor: float | None) -> str:
    return "nunca" if valor is None else f"{valor:.1f} s"


def _verde(fase: int) -> Callable[[Amostra], bool]:
    return lambda a: a.cores[fase - 1] == "G"


def _duas_a_frente(fase: int) -> int:
    """Uma fase que **não** é a próxima do ciclo — senão o ciclo chegaria lá sozinho."""
    return (fase + 1) % N_FASES + 1


# ---------------------------------------------------------------------------
# Roteiro
# ---------------------------------------------------------------------------


@dataclass
class Resultado:
    nome: str
    ok: bool | None  # None: não observável nesta execução
    detalhe: str


class Roteiro:
    def __init__(self, ponte: Ponte, observador: Observador) -> None:
        self.ponte = ponte
        self.obs = observador
        self.resultados: list[Resultado] = []

    def registrar(self, nome: str, ok: bool | None, detalhe: str) -> None:
        self.resultados.append(Resultado(nome, ok, detalhe))
        marca = {True: "ok  ", False: "FALHA", None: "n/o "}[ok]
        print(f"[{marca}] {nome} — {detalhe}", flush=True)

    def _inicio_de_verde(self, limite_s: float = CICLO_S + 2) -> Amostra:
        """Espera um verde que acabou de abrir (a amostra anterior era all-red)."""
        anterior = self.obs.ultima()
        fim = time.monotonic() + limite_s
        while time.monotonic() < fim:
            atual = self.obs.ultima()
            if (
                atual is not None
                and anterior is not None
                and atual is not anterior
                and "G" in atual.cores
                and anterior.cores == "RRRR"
                and not atual.em_preempcao
            ):
                return atual
            anterior = atual
            time.sleep(0.05)
        raise RuntimeError("nenhum verde abriu no tempo de um ciclo")

    def _ciclo_ocioso(self) -> None:
        """Garante que nenhuma preempção ficou de um passo anterior."""
        if not self.obs.esperar(lambda a: not a.em_preempcao, limite_s=TIMEOUT_PREEMPCAO_S + 5):
            raise RuntimeError("a preempção anterior não terminou")

    # -- passos ----------------------------------------------------------------

    def health(self) -> None:
        status, corpo = self.ponte.health()
        self.registrar(
            "health",
            status == 200 and corpo["estado"] == "ok",
            f"HTTP {status}, porta {corpo['porta']}, UNO respondendo: {corpo['uno_respondendo']}",
        )

    def boot_em_all_red(self) -> None:
        primeiras = [a for a in self.obs.amostras if a.t_dispositivo_ms < 1000]
        if not primeiras:
            self.registrar(
                "liga em all-red",
                None,
                "a ponte já estava no ar; rode o verificador logo depois de subir a ponte",
            )
            return
        self.registrar(
            "liga em all-red",
            all(a.cores == "RRRR" for a in primeiras),
            "primeiros 1000 ms da placa: " + " ".join(a.cores for a in primeiras),
        )

    def ciclo_fixo(self) -> None:
        aberturas: list[tuple[int, float]] = []
        primeiro = self._inicio_de_verde()
        aberturas.append((primeiro.cores.index("G") + 1, primeiro.recebida_em))
        while len(aberturas) <= N_FASES:
            atual = self._inicio_de_verde(limite_s=PIOR_CASO_S + 2)
            aberturas.append((atual.cores.index("G") + 1, atual.recebida_em))
        ordem = [fase for fase, _ in aberturas]
        esperado = [(ordem[0] + i - 1) % N_FASES + 1 for i in range(N_FASES + 1)]
        duracao = aberturas[-1][1] - aberturas[0][1]
        self.registrar(
            "ciclo fixo, uma fase por vez",
            ordem == esperado and abs(duracao - CICLO_S) <= FOLGA_S * 2,
            f"ordem {ordem}, ciclo de {duracao:.1f} s (esperado {CICLO_S:.0f} s)",
        )

    def recusas(self) -> None:
        status, corpo = self.ponte.comando("LIBERAR")
        self.registrar(
            "CLR sem preempção é recusado",
            corpo.get("motivo_recusa") == "MODO" and corpo["t_atuacao"] is None,
            f"HTTP {status}, resposta {corpo.get('resposta')}",
        )
        status, corpo = self.ponte.comando(
            "IR_PARA_FASE", fase_alvo=5, duracao_s=20, id_veiculo="VE_VERIFICA"
        )
        self.registrar(
            "fase fora da bancada é recusada pelo UNO",
            corpo.get("motivo_recusa") == "FASE_INVALIDA",
            f"HTTP {status}, linha {corpo.get('linha')}, resposta {corpo.get('resposta')}",
        )
        status, corpo = self.ponte.comando("ESTENDER_VERDE", fase_alvo=2, duracao_s=2)
        self.registrar(
            "extensão de compensação não sai pela serial",
            status == 200 and corpo["linha"] is None,
            f"HTTP {status}, linha {corpo['linha']}",
        )

    def pre_em_verde_e_fim_por_dur_s(self) -> None:
        self._ciclo_ocioso()
        verde = self._inicio_de_verde()
        corrente = verde.cores.index("G") + 1
        alvo = _duas_a_frente(corrente)
        proxima = corrente % N_FASES + 1
        _, corpo = self.ponte.comando(
            "IR_PARA_FASE", fase_alvo=alvo, duracao_s=12, id_veiculo="VE_VERIFICA"
        )
        t_atuacao = _instante(corpo["t_atuacao"]) if corpo["t_atuacao"] else None
        self.registrar(
            "PRE aceito, com t_atuacao",
            corpo["aceito"] and t_atuacao is not None,
            f"{corpo['linha']} -> {corpo['resposta']}, "
            f"envio->ACK {corpo['latencia_serial_ms']:.1f} ms (conferência, não H3)",
        )
        if t_atuacao is None:
            return

        aberto = self.obs.esperar(_verde(alvo), limite_s=PIOR_CASO_S + 3)
        espera = None if aberto is None else aberto.recebida_em - t_atuacao
        no_meio = [a.cores for a in self.obs.desde(t_atuacao) if a.cores[proxima - 1] == "G"]
        self.registrar(
            "PRE em verde: alvo abre em até 6 s, sem passar pela fase seguinte",
            espera is not None and espera <= PIOR_CASO_S + FOLGA_S and not no_meio,
            f"fase {corrente} -> {alvo} em {_seg(espera)}"
            f"{', fase ' + str(proxima) + ' abriu no meio' if no_meio else ''}",
        )
        self.registrar(
            "telemetria marca preempção no verde alvo",
            aberto is not None and aberto.em_preempcao,
            f"ST: {aberto.cores if aberto else '-'}, "
            f"preemp={aberto.em_preempcao if aberto else '-'}",
        )

        fim = self.obs.esperar_evento(t_atuacao, "PREEMP_FIM", limite_s=20)
        duracao = None if fim is None else fim - t_atuacao
        depois = self.obs.esperar(_verde(alvo % N_FASES + 1), limite_s=PIOR_CASO_S + 3)
        self.registrar(
            "preempção termina sozinha quando dur_s esgota",
            duracao is not None and abs(duracao - 12) <= FOLGA_S and depois is not None,
            f"PREEMP_FIM {_seg(duracao)} após o ACK "
            f"(pedido: 12 s); depois abriu a fase {alvo % N_FASES + 1}",
        )

    def pre_em_amarelo_e_clr(self) -> None:
        self._ciclo_ocioso()
        amarela = self.obs.esperar(lambda a: "Y" in a.cores, limite_s=CICLO_S)
        if amarela is None:
            self.registrar("PRE em amarelo", False, "nenhum amarelo observado")
            return
        corrente = amarela.cores.index("Y") + 1
        alvo = _duas_a_frente(corrente)
        proxima = corrente % N_FASES + 1
        _, corpo = self.ponte.comando(
            "IR_PARA_FASE", fase_alvo=alvo, duracao_s=20, id_veiculo="VE_VERIFICA"
        )
        t_atuacao = _instante(corpo["t_atuacao"])
        aberto = self.obs.esperar(_verde(alvo), limite_s=AMARELO_S + ALL_RED_S + 3)
        espera = None if aberto is None else aberto.recebida_em - t_atuacao
        no_meio = [a.cores for a in self.obs.desde(t_atuacao) if a.cores[proxima - 1] == "G"]
        self.registrar(
            "PRE em amarelo é aceito e muda só o destino",
            corpo["aceito"]
            and espera is not None
            and espera <= AMARELO_S + ALL_RED_S + FOLGA_S
            and not no_meio,
            f"S{corrente} em amarelo -> fase {alvo} em "
            f"{_seg(espera)} (máx. {AMARELO_S + ALL_RED_S:.0f} s)",
        )

        _, liberacao = self.ponte.comando("LIBERAR")
        t_clr = _instante(liberacao["t_atuacao"]) if liberacao["t_atuacao"] else time.time()
        fim = self.obs.esperar_evento(t_clr - 0.01, "PREEMP_FIM", limite_s=2)
        saida = self.obs.esperar(lambda a: a.cores[alvo - 1] == "Y", limite_s=VERDE_S + 2)
        self.registrar(
            "CLR encerra a preempção pelo amarelo",
            liberacao["resposta"] == "ACK,CLR" and fim is not None and saida is not None,
            f"{liberacao['linha']} -> {liberacao['resposta']}; S{alvo} saiu pelo amarelo: "
            f"{saida is not None}",
        )

    def extensao_e_fail_safe(self) -> None:
        self._ciclo_ocioso()
        verde = self._inicio_de_verde()
        fase = verde.cores.index("G") + 1
        _, corpo = self.ponte.comando(
            "ESTENDER_VERDE", fase_alvo=fase, duracao_s=10, id_veiculo="VE_VERIFICA"
        )
        t_atuacao = _instante(corpo["t_atuacao"])
        time.sleep(6.0)  # o dobro do verde base: sem a extensão, a fase já teria fechado
        ainda = self.obs.ultima()
        abertas = [a for a in self.obs.desde(t_atuacao) if a.cores[fase - 1] != "G"]
        self.registrar(
            "PRE para a fase já verde estende, sem refazer a transição",
            corpo["linha"] == f"PRE,{fase},10"
            and ainda is not None
            and ainda.cores[fase - 1] == "G"
            and not abertas,
            f"{corpo['linha']}; 6 s depois: {ainda.cores if ainda else '-'}",
        )

        _, falha = self.ponte.comando("FALLBACK_SEGURO")
        t_falha = _instante(falha["t_atuacao"]) if falha["t_atuacao"] else time.time()
        fim = self.obs.esperar_evento(t_falha - 0.01, "PREEMP_FIM", limite_s=2)
        self.registrar(
            "fail-safe vira CLR e volta ao ciclo fixo",
            falha["linha"] == "CLR" and falha["resposta"] == "ACK,CLR" and fim is not None,
            f"{falha['linha']} -> {falha['resposta']}",
        )

    def timeout_de_30_s(self) -> None:
        self._ciclo_ocioso()
        corrente = (self.obs.ultima() or verde_padrao()).fase
        alvo = _duas_a_frente(corrente)
        _, corpo = self.ponte.comando(
            "IR_PARA_FASE", fase_alvo=alvo, duracao_s=60, id_veiculo="VE_VERIFICA"
        )
        t_atuacao = _instante(corpo["t_atuacao"])
        print("      (esperando o timeout de 30 s da preempção...)", flush=True)
        timeout = self.obs.esperar_evento(t_atuacao, "TIMEOUT", limite_s=TIMEOUT_PREEMPCAO_S + 5)
        duracao = None if timeout is None else timeout - t_atuacao
        self.registrar(
            "preempção nunca passa de 30 s, mesmo com dur_s maior",
            duracao is not None and abs(duracao - TIMEOUT_PREEMPCAO_S) <= FOLGA_S,
            f"PRE,{alvo},60 -> EV TIMEOUT {_seg(duracao)} depois",
        )

    def invariantes(self) -> None:
        sequencia = [a.cores for a in self.obs.amostras if not a.em_teste]
        achados = violacoes(sequencia)
        self.registrar(
            "I1, I2 e I3 em toda a telemetria observada",
            not achados,
            f"{len(sequencia)} telemetrias; " + ("; ".join(achados[:3]) or "nenhuma violação"),
        )
        _, corpo = self.ponte.health()
        self.registrar(
            "contadores da ponte",
            corpo["telemetrias_com_dois_verdes"] == 0
            and corpo["linhas_invalidas"] == 0
            and corpo["reconexoes"] == 0,
            f"dois verdes {corpo['telemetrias_com_dois_verdes']}, linhas inválidas "
            f"{corpo['linhas_invalidas']}, reconexões {corpo['reconexoes']}",
        )


def verde_padrao() -> Amostra:
    return Amostra(0.0, 0, 1, "GRRR", False, False)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m bridge.verificar", description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    args = parser.parse_args(argv)

    ponte = Ponte(args.url)
    observador = Observador(ponte)
    observador.iniciar()
    roteiro = Roteiro(ponte, observador)
    print(f"Verificando a ponte em {args.url}", flush=True)
    try:
        if not observador.esperar(lambda _: True, limite_s=10):
            print("A ponte não entregou telemetria em 10 s. Ela está no ar?", file=sys.stderr)
            return 2
        roteiro.health()
        roteiro.boot_em_all_red()
        roteiro.ciclo_fixo()
        roteiro.recusas()
        roteiro.pre_em_verde_e_fim_por_dur_s()
        roteiro.pre_em_amarelo_e_clr()
        roteiro.extensao_e_fail_safe()
        roteiro.timeout_de_30_s()
        roteiro.invariantes()
    finally:
        observador.parar()

    falhas = [r for r in roteiro.resultados if r.ok is False]
    print(
        f"\n{len(roteiro.resultados) - len(falhas)} de {len(roteiro.resultados)} conferências ok."
        " Fora do alcance do HTTP: watchdog, reconexão, SAFE e modo de teste"
        " (testes automatizados e checklist de bancada)."
    )
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
