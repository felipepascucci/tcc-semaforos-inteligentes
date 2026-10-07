"""Roteiro de aceitação da bancada, pelo HTTP da ponte — com o dublê ou com a placa.

Injeta VEs pela ponte (`POST /injecao`), acompanha o UNO por `GET /estado` e
confere o comportamento de `context/05` §3 e §4. O mesmo roteiro serve aos dois
lados do cabo::

    python -m bridge.main --simulado        # ou --porta COM3, com a placa
    python -m bridge.verificar              # noutro terminal, logo em seguida

**Com o backend parado.** Desde 2026-10-06 o roteiro manda ao UNO a lista da
Central ele mesmo (`PUT /autorizacoes`), e o backend, se estiver no ar, a
trocaria pela das ocorrências abertas no banco. O roteiro percebe e para.

O receptor está no A0, e o RX do UNO é só do USB: a injeção chega com a bancada
montada, sem soltar fio.

Leva cerca de quatro minutos, quase todos esperando o relógio do semáforo: o
ciclo é de 12 s, o verde de um VE dura até 9 s e o teto da emergência é de 30 s.

As durações são conferidas no `millis()` do UNO, que vem em cada linha: é exato
dentro da placa, e não depende de quando a ponte foi consultada.

**Isto não mede H3.** A latência que aparece aqui vai do envio pela ponte à
decisão do UNO, e com o dublê é uma constante digitada. H3 vai da leitura da tag
no veículo à decisão, e segue o procedimento de `context/05` §4.3.
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
from typing import Any

# Perfil da bancada (parametros.hardware.yaml) — o que o roteiro espera ver.
VERDE_MS, VERDE_MIN_MS, AMARELO_MS, ALL_RED_MS = 3000, 3000, 2000, 1000
CICLO_MS = 2 * (VERDE_MS + AMARELO_MS + ALL_RED_MS)
PIOR_CASO_MS = VERDE_MIN_MS + AMARELO_MS + ALL_RED_MS
TETO_MS = 30_000
VERDE_DO_TIPO_MS = {"AMBULANCIA": 9000, "BOMBEIRO": 8000, "POLICIA": 7000}

#: Folga nas durações medidas no `millis()` do UNO: uma volta do `loop()`.
FOLGA_MS = 60

PRINCIPAL, TRANSVERSAL = "GGRR", "RRGG"
_EIXO = (0, 0, 1, 1)

#: A lista da Central com que o roteiro roda: uma ocorrência de cada tipo, na
#: ordem antiga dos tipos, para que prioridade e fila tenham o mesmo roteiro de
#: antes de 2026-10-06. Os passos da Central a trocam e a devolvem.
CENTRAL_DO_ROTEIRO = {"AMBULANCIA": 1, "BOMBEIRO": 2, "POLICIA": 3}


# ---------------------------------------------------------------------------
# Invariantes sobre a sequência de telemetrias — puro, testado à parte
# ---------------------------------------------------------------------------


def transicoes(sequencia: Sequence[tuple[int, str]]) -> list[tuple[int, str]]:
    """Só as mudanças de luz, cada uma com o `millis()` em que aconteceu."""
    saida: list[tuple[int, str]] = []
    for ms, estado in sequencia:
        if not saida or saida[-1][1] != estado:
            saida.append((ms, estado))
    return saida


def violacoes(
    sequencia: Sequence[tuple[int, str]],
    *,
    verde_min_ms: int = VERDE_MIN_MS,
    amarelo_ms: int = AMARELO_MS,
    all_red_ms: int = ALL_RED_MS,
    folga_ms: int = 0,
) -> list[str]:
    """I1 a I4 sobre uma sequência de `(ms, S1S2S3S4)`, como nas linhas `ST`.

    Pressupõe que a sequência traz toda mudança de luz, que é o que a `ST` a
    cada mudança de estado garante (`context/05` §4.2).

    Returns:
        Uma descrição por violação; vazia quando nada foi violado.
    """
    achados: list[str] = []
    passos = transicoes(sequencia)
    desde: dict[int, int] = {}  # aproximação -> ms em que a cor atual acendeu
    vermelho_geral_desde: int | None = None
    for indice, (ms, estado) in enumerate(passos):
        eixos = {_EIXO[i] for i, cor in enumerate(estado) if cor == "G"}
        if len(eixos) > 1:
            achados.append(f"I1: verde nos dois eixos em {ms} ms: {estado}")
        if indice == 0:
            if estado == "RRRR":
                vermelho_geral_desde = ms
            continue
        antes = passos[indice - 1][1]
        for i, (a, d) in enumerate(zip(antes, estado, strict=True)):
            if a == d:
                continue
            duracao = None if i not in desde else ms - desde[i]
            if a == "G" and d == "R":
                achados.append(f"I2: S{i + 1} verde -> vermelho em {ms} ms")
            if a == "Y" and d == "G":
                achados.append(f"amarelo -> verde: S{i + 1} em {ms} ms")
            if a == "G" and d == "Y" and duracao is not None and duracao < verde_min_ms - folga_ms:
                achados.append(f"I4: verde de S{i + 1} durou {duracao} ms")
            if a == "Y" and d == "R" and duracao is not None and duracao < amarelo_ms - folga_ms:
                achados.append(f"I2: amarelo de S{i + 1} durou {duracao} ms")
            if d == "G":
                limpo = (
                    antes == "RRRR"
                    and vermelho_geral_desde is not None
                    and ms - vermelho_geral_desde >= all_red_ms - folga_ms
                )
                if not limpo:
                    achados.append(f"I3: S{i + 1} abriu sem all-red em {ms} ms (antes {antes})")
            desde[i] = ms
        if estado == "RRRR" and antes != "RRRR":
            vermelho_geral_desde = ms
    return achados


# ---------------------------------------------------------------------------
# Acesso à ponte
# ---------------------------------------------------------------------------


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

    def injetar(self, rua: int, veiculo: str) -> tuple[int, Any]:
        return self._pedir("POST", "/injecao", {"rua": rua, "veiculo": veiculo})

    def injetar_bruta(self, linha: str) -> tuple[int, Any]:
        return self._pedir("POST", "/injecao/bruta", {"linha": linha})

    def autorizar(self, autorizacoes: dict[str, int]) -> tuple[int, Any]:
        return self._pedir("PUT", "/autorizacoes", {"autorizacoes": autorizacoes})


@dataclass(frozen=True)
class Amostra:
    ms: int
    cores: str
    regime: str
    rua_ativa: int | None
    rua_fila: int | None
    autorizacoes: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class Ev:
    ms: int
    tipo: str
    rua: int | None
    veiculo: str | None


@dataclass
class Observador:
    """Lê `/estado` a 5 Hz numa thread e guarda cada telemetria e evento novo.

    A ponte guarda as últimas telemetrias, e a `ST` sai a cada mudança de estado;
    lendo o histórico, nenhuma transição se perde entre duas consultas.
    """

    ponte: Ponte
    amostras: list[Amostra] = field(default_factory=list)
    eventos: list[Ev] = field(default_factory=list)
    _vistos: set[tuple[Any, ...]] = field(default_factory=set)
    _trava: threading.Lock = field(default_factory=threading.Lock)
    _parar: threading.Event = field(default_factory=threading.Event)

    def iniciar(self) -> None:
        threading.Thread(target=self._laco, daemon=True).start()

    def parar(self) -> None:
        self._parar.set()

    def _laco(self) -> None:
        while not self._parar.is_set():
            try:
                estado = self.ponte.estado()
            except OSError:
                time.sleep(0.2)
                continue
            with self._trava:
                for st in estado["telemetrias"]:
                    chave = ("ST", st["recebida_em"], st["t_dispositivo_ms"])
                    if chave not in self._vistos:
                        self._vistos.add(chave)
                        self.amostras.append(
                            Amostra(
                                st["t_dispositivo_ms"],
                                st["cores"],
                                st["regime"],
                                st["rua_ativa"],
                                st["rua_fila"],
                                tuple(sorted(st["autorizacoes"].items())),
                            )
                        )
                for ev in estado["eventos"]:
                    chave = ("EV", ev["recebido_em"], ev["t_dispositivo_ms"], ev["tipo"], ev["rua"])
                    if chave not in self._vistos:
                        self._vistos.add(chave)
                        self.eventos.append(
                            Ev(ev["t_dispositivo_ms"], ev["tipo"], ev["rua"], ev["veiculo"])
                        )
            time.sleep(0.2)

    def copia(self) -> tuple[list[Amostra], list[Ev]]:
        with self._trava:
            return list(self.amostras), list(self.eventos)

    def agora_ms(self) -> int:
        amostras, _ = self.copia()
        return amostras[-1].ms if amostras else 0

    def esperar(self, condicao: Callable[[], Any], limite_s: float) -> Any:
        fim = time.monotonic() + limite_s
        while time.monotonic() < fim:
            resultado = condicao()
            if resultado:
                return resultado
            time.sleep(0.05)
        return None

    def evento(self, tipo: str, desde_ms: int, rua: int | None = None) -> Ev | None:
        _, eventos = self.copia()
        for ev in eventos:
            if ev.tipo == tipo and ev.ms >= desde_ms and (rua is None or ev.rua == rua):
                return ev
        return None

    def esperar_evento(
        self, tipo: str, desde_ms: int, limite_s: float, rua: int | None = None
    ) -> Ev | None:
        resultado: Ev | None = self.esperar(lambda: self.evento(tipo, desde_ms, rua), limite_s)
        return resultado

    def primeira(self, condicao: Callable[[Amostra], bool], desde_ms: int) -> Amostra | None:
        amostras, _ = self.copia()
        return next((a for a in amostras if a.ms >= desde_ms and condicao(a)), None)

    def esperar_amostra(
        self, condicao: Callable[[Amostra], bool], desde_ms: int, limite_s: float
    ) -> Amostra | None:
        resultado: Amostra | None = self.esperar(
            lambda: self.primeira(condicao, desde_ms), limite_s
        )
        return resultado

    def entre(self, inicio_ms: int, fim_ms: int) -> list[Amostra]:
        amostras, _ = self.copia()
        return [a for a in amostras if inicio_ms <= a.ms <= fim_ms]


def _exclusivo(rua: int) -> Callable[[Amostra], bool]:
    alvo = "".join("G" if i == rua - 1 else "R" for i in range(4))
    return lambda a: a.cores == alvo


def _proximo(duracao: int | None, esperado: int) -> bool:
    return duracao is not None and abs(duracao - esperado) <= FOLGA_MS


def _ms(valor: int | None) -> str:
    return "nunca" if valor is None else f"{valor} ms"


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

    def _injetar(self, rua: int, veiculo: str) -> Ev:
        """Injeta e devolve o evento de decisão do UNO, com o `millis()` dele."""
        status, corpo = self.ponte.injetar(rua, veiculo)
        if status != 200:
            raise RuntimeError(
                f"injeção RUA{rua},{veiculo} sem decisão (HTTP {status}). "
                "A placa está com o firmware de 2026-10-06 (receptor no A0)?"
            )
        return Ev(corpo["decisao_t_dispositivo_ms"], corpo["decisao"], rua, veiculo)

    def _central(self, autorizacoes: dict[str, int], limite_s: float = 3.0) -> None:
        """Manda a lista ao UNO e espera a `ST` confirmá-la."""
        status, corpo = self.ponte.autorizar(autorizacoes)
        if status != 202:
            raise RuntimeError(f"PUT /autorizacoes falhou (HTTP {status}): {corpo}")

        def confirmada() -> bool:
            amostras, _ = self.obs.copia()
            return bool(amostras) and dict(amostras[-1].autorizacoes) == {
                **dict(amostras[-1].autorizacoes),
                **autorizacoes,
            }

        if not self.obs.esperar(confirmada, limite_s):
            raise RuntimeError(f"a ST não confirmou a lista {autorizacoes} em {limite_s:.0f} s")

    def _abertura(self, estado: str, limite_s: float = CICLO_MS / 1000 + 3) -> Amostra:
        """Espera o eixo `estado` abrir no ciclo e devolve a amostra da abertura."""
        inicio = self.obs.agora_ms()
        amostra = self.obs.esperar_amostra(
            lambda a: a.cores == estado and a.regime == "C", inicio + 1, limite_s
        )
        if amostra is None:
            raise RuntimeError(f"{estado} não abriu em {limite_s:.0f} s")
        # Só vale a abertura propriamente dita: a amostra anterior era all-red.
        anteriores = self.obs.entre(inicio, amostra.ms - 1)
        if anteriores and anteriores[-1].cores != "RRRR":
            return self._abertura(estado, limite_s)
        return amostra

    def _ciclo_ocioso(self) -> None:
        def em_ciclo() -> bool:
            amostras, _ = self.obs.copia()
            return bool(amostras) and amostras[-1].regime == "C"

        if not self.obs.esperar(em_ciclo, limite_s=TETO_MS / 1000 + 10):
            raise RuntimeError("a emergência anterior não terminou")

    # -- passos ----------------------------------------------------------------

    def health(self) -> None:
        status, corpo = self.ponte.health()
        self.registrar(
            "health",
            status == 200 and corpo["estado"] == "ok",
            f"HTTP {status}, porta {corpo['porta']}, UNO respondendo: {corpo['uno_respondendo']}",
        )

    def boot_em_all_red(self) -> None:
        # A ST do all-red sai já no boot; o primeiro verde vem ~1 s depois (na
        # placa, ~1,1 s, por causa do lcd.init()). Espera ele chegar.
        self.obs.esperar(
            lambda: any("G" in a.cores for a in self.obs.copia()[0]), limite_s=ALL_RED_MS / 1000 + 3
        )
        amostras, eventos = self.obs.copia()
        primeiras = [a for a in amostras if a.ms < ALL_RED_MS]
        if not primeiras or not any(ev.tipo == "BOOT" for ev in eventos):
            self.registrar(
                "liga em all-red",
                None,
                "a ponte já estava no ar; rode o verificador logo depois de subir a ponte",
            )
            return
        abertura = next((a for a in amostras if "G" in a.cores), None)
        # All-red de PELO MENOS 1 s: na placa o lcd.init() bloqueia ~1,1 s no
        # setup(), e o primeiro verde sai depois disso. Mais all-red é seguro.
        self.registrar(
            "liga em all-red e só então abre o eixo principal",
            all(a.cores == "RRRR" for a in primeiras)
            and abertura is not None
            and abertura.cores == PRINCIPAL
            and abertura.ms >= ALL_RED_MS - FOLGA_MS
            and all(a.cores == "RRRR" for a in amostras if a.ms < abertura.ms),
            "primeiro verde: "
            + ("-" if abertura is None else f"{abertura.cores} em {abertura.ms} ms"),
        )

    def central(self) -> None:
        """O UNO liga negando todos; o roteiro manda a lista e confere que ela fica."""
        amostras, eventos = self.obs.copia()
        if amostras and any(ev.tipo == "BOOT" for ev in eventos) and amostras[0].ms < ALL_RED_MS:
            self.registrar(
                "liga negando todos (nenhum tipo com ocorrência)",
                all(c == 0 for _, c in amostras[0].autorizacoes),
                f"lista no boot: {dict(amostras[0].autorizacoes)}",
            )
        self._central(CENTRAL_DO_ROTEIRO)
        # Se o backend estiver no ar, ele troca a lista pela do banco em ~1 s.
        time.sleep(2.0)
        amostras, _ = self.obs.copia()
        if dict(amostras[-1].autorizacoes) != CENTRAL_DO_ROTEIRO:
            raise RuntimeError(
                "a lista da Central mudou sozinha: o backend está no ar? "
                "Pare-o e suba a ponte de novo antes do roteiro."
            )
        self.registrar(
            "a lista da Central chega ao UNO e aparece na ST",
            True,
            f"{CENTRAL_DO_ROTEIRO}",
        )

    def sem_ocorrencia(self) -> None:
        self._ciclo_ocioso()
        self._central({"AMBULANCIA": 0})
        antes = self.obs.agora_ms()
        try:
            decisao = self._injetar(3, "AMBULANCIA")
            time.sleep(0.5)
            preemptou = self.obs.evento("PREEMP_INI", antes)
        finally:
            self._central(CENTRAL_DO_ROTEIRO)
        self.registrar(
            "VE de tipo sem ocorrência na Central não preempta (SEM_OCORRENCIA)",
            decisao.tipo == "SEM_OCORRENCIA" and preemptou is None,
            f"decisão: {decisao.tipo}; preemptou: {preemptou is not None}",
        )

    def criticidade_decide(self) -> None:
        """Polícia com risco à vida interrompe ambulância com urgência."""
        self._ciclo_ocioso()
        self._central({"AMBULANCIA": 3, "POLICIA": 1})
        try:
            ambulancia = self._injetar(3, "AMBULANCIA")
            policia = self._injetar(1, "POLICIA")
            fila = self.obs.esperar_evento("FILA", policia.ms, 2, rua=3)
        finally:
            self._central(CENTRAL_DO_ROTEIRO)
        self.registrar(
            "a criticidade, e não o tipo, decide quem interrompe",
            ambulancia.tipo == "PREEMP_INI"
            and policia.tipo == "PREEMP_INI"
            and fila is not None
            and fila.veiculo == "AMBULANCIA",
            f"ambulância (3): {ambulancia.tipo}; polícia (1): {policia.tipo}; "
            f"ambulância na fila: {fila is not None}",
        )

    def ciclo(self) -> None:
        primeira = self._abertura(PRINCIPAL)
        transversal = self._abertura(TRANSVERSAL)
        segunda = self._abertura(PRINCIPAL)
        meio = transversal.ms - primeira.ms
        volta = segunda.ms - primeira.ms
        self.registrar(
            "ciclo de 2 fases, eixos alternando",
            _proximo(meio, CICLO_MS // 2) and _proximo(volta, CICLO_MS),
            f"principal -> transversal {meio} ms, ciclo {volta} ms (esperado {CICLO_MS} ms)",
        )

    def ve_em_outro_eixo(self) -> None:
        """Contexto/05 §4.2, o exemplo: VE na Rua 3 com o eixo principal verde."""
        self._ciclo_ocioso()
        abertura = self._abertura(PRINCIPAL)
        decisao = self._injetar(3, "AMBULANCIA")
        if decisao is None or decisao.tipo != "PREEMP_INI":
            self.registrar("VE em outro eixo é atendido", False, f"decisão: {decisao}")
            return
        verde = self.obs.esperar_amostra(_exclusivo(3), decisao.ms, PIOR_CASO_MS / 1000 + 2)
        espera = None if verde is None else verde.ms - decisao.ms
        pelo_meio = [a.cores for a in self.obs.entre(decisao.ms, verde.ms if verde else decisao.ms)]
        self.registrar(
            "VE em outro eixo: verde exclusivo em até 6 s, sem abrir o eixo transversal",
            espera is not None
            and espera <= PIOR_CASO_MS + FOLGA_MS
            and not any(c[3] == "G" for c in pelo_meio),
            f"eixo principal verde desde {abertura.ms} ms; Rua 3 exclusiva {_ms(espera)} "
            "depois da decisão",
        )
        if verde is None:
            return
        fim = self.obs.esperar_evento("PREEMP_FIM", verde.ms, 12, rua=3)
        duracao = None if fim is None else fim.ms - verde.ms
        self.registrar(
            "verde da ambulância dura 9 s, contados do verde exclusivo",
            _proximo(duracao, VERDE_DO_TIPO_MS["AMBULANCIA"]),
            f"PREEMP_FIM {_ms(duracao)} depois do verde exclusivo",
        )
        if fim is None:
            return
        depois = self.obs.esperar_amostra(lambda a: "G" in a.cores, fim.ms + 1, 6)
        self.registrar(
            "fim da emergência volta pelo eixo oposto",
            depois is not None and depois.cores == PRINCIPAL and depois.regime == "C",
            f"primeiro verde depois: {depois.cores if depois else '-'}",
        )

    def ve_no_eixo_verde(self) -> None:
        self._ciclo_ocioso()
        self._abertura(PRINCIPAL)
        decisao = self._injetar(1, "POLICIA")
        if decisao is None or decisao.tipo != "PREEMP_INI":
            self.registrar("VE no eixo verde é atendido", False, f"decisão: {decisao}")
            return
        exclusivo = self.obs.esperar_amostra(_exclusivo(1), decisao.ms, PIOR_CASO_MS / 1000 + 2)
        fim = self.obs.esperar_evento("PREEMP_FIM", decisao.ms, 15, rua=1)
        apagou = [
            a.cores
            for a in self.obs.entre(decisao.ms, fim.ms - 1 if fim else decisao.ms)
            if a.cores[0] != "G"
        ]
        duracao = None if fim is None or exclusivo is None else fim.ms - exclusivo.ms
        self.registrar(
            "VE no eixo verde: o verde dele não apaga, só o S2 sai pelo amarelo",
            exclusivo is not None and not apagou,
            f"S1 exclusivo {_ms(None if exclusivo is None else exclusivo.ms - decisao.ms)} "
            f"depois da decisão; S1 apagou no meio: {bool(apagou)}",
        )
        self.registrar(
            "verde da polícia dura 7 s",
            _proximo(duracao, VERDE_DO_TIPO_MS["POLICIA"]),
            f"PREEMP_FIM {_ms(duracao)} depois do verde exclusivo",
        )

    def prioridade_e_fila(self) -> None:
        self._ciclo_ocioso()
        bombeiro = self._injetar(1, "BOMBEIRO")
        if bombeiro is None:
            self.registrar("prioridade e fila", False, "bombeiro sem decisão")
            return
        self.obs.esperar_amostra(_exclusivo(1), bombeiro.ms, PIOR_CASO_MS / 1000 + 2)
        ambulancia = self._injetar(3, "AMBULANCIA")
        fila = self.obs.esperar_evento("FILA", bombeiro.ms + 1, 2, rua=1)
        policia = self._injetar(2, "POLICIA")
        self.registrar(
            "ambulância interrompe o bombeiro, que vai para a fila",
            ambulancia is not None
            and ambulancia.tipo == "PREEMP_INI"
            and fila is not None
            and fila.veiculo == "BOMBEIRO",
            f"ambulância: {ambulancia.tipo if ambulancia else '-'}; "
            f"bombeiro: {fila.tipo if fila else 'sem FILA'}",
        )
        self.registrar(
            "polícia com a fila ocupada por bombeiro é descartada",
            policia is not None and policia.tipo == "DESCARTADO",
            f"polícia: {policia.tipo if policia else '-'}",
        )
        if ambulancia is None:
            return
        fim = self.obs.esperar_evento("PREEMP_FIM", ambulancia.ms, 20, rua=3)
        retomada = None if fim is None else self.obs.esperar_evento("PREEMP_INI", fim.ms, 2, rua=1)
        verde = (
            None
            if retomada is None
            else self.obs.esperar_amostra(_exclusivo(1), retomada.ms, PIOR_CASO_MS / 1000 + 2)
        )
        fim_bombeiro = (
            None if verde is None else self.obs.esperar_evento("PREEMP_FIM", verde.ms, 12, rua=1)
        )
        duracao = None if fim_bombeiro is None or verde is None else fim_bombeiro.ms - verde.ms
        self.registrar(
            "o bombeiro da fila é atendido depois, com o verde inteiro",
            retomada is not None and _proximo(duracao, VERDE_DO_TIPO_MS["BOMBEIRO"]),
            f"retomado: {retomada is not None}; verde do bombeiro {_ms(duracao)}",
        )

    def renovacao_e_teto(self) -> None:
        self._ciclo_ocioso()
        inicio = self._injetar(4, "AMBULANCIA")
        if inicio is None or inicio.tipo != "PREEMP_INI":
            self.registrar("renovação e teto", False, f"decisão: {inicio}")
            return
        print("      (renovando a cada 4 s até o teto de 30 s...)", flush=True)
        renovacoes = []
        while True:
            time.sleep(4.0)
            # Para antes do teto: uma releitura depois do TIMEOUT abriria uma
            # emergência nova, e o roteiro confundiria as duas.
            if self.obs.agora_ms() - inicio.ms > TETO_MS - 3000:
                break
            renovacoes.append(self._injetar(4, "AMBULANCIA"))
        timeout = self.obs.esperar_evento("TIMEOUT", inicio.ms, 8)
        duracao = None if timeout is None else timeout.ms - inicio.ms
        renovados = [r for r in renovacoes if r.tipo == "RENOVADO"]
        self.registrar(
            "o mesmo VE relendo a mesma rua renova o verde",
            bool(renovacoes) and len(renovados) == len(renovacoes),
            f"{len(renovados)} de {len(renovacoes)} releituras renovaram",
        )
        fim = None if timeout is None else self.obs.esperar_evento("PREEMP_FIM", timeout.ms, 2)
        depois = (
            None
            if fim is None
            else self.obs.esperar_amostra(lambda a: "G" in a.cores, fim.ms + 1, 6)
        )
        self.registrar(
            "emergência contínua para no teto de 30 s e volta pelo eixo oposto",
            _proximo(duracao, TETO_MS)
            and fim is not None
            and depois is not None
            and depois.cores == PRINCIPAL,
            f"TIMEOUT {_ms(duracao)} depois do PREEMP_INI; depois abriu "
            f"{depois.cores if depois else '-'}",
        )

    def recusa(self) -> None:
        self._ciclo_ocioso()
        antes = self.obs.agora_ms()
        status, _ = self.ponte.injetar_bruta("RUA3,HELICOPTERO")
        recusado = self.obs.esperar_evento("RECUSADO", antes, 2)
        atendido = self.obs.evento("PREEMP_INI", antes)
        self.registrar(
            "tipo desconhecido é recusado e não mexe no semáforo",
            status == 202 and recusado is not None and atendido is None,
            f"RECUSADO: {recusado is not None}; preemptou: {atendido is not None}",
        )

    def invariantes(self) -> None:
        amostras, _ = self.obs.copia()
        sequencia = [(a.ms, a.cores) for a in amostras]
        achados = violacoes(sequencia, folga_ms=FOLGA_MS)
        self.registrar(
            "I1 a I4 em toda a telemetria observada",
            not achados,
            f"{len(transicoes(sequencia))} transições; "
            + ("; ".join(achados[:3]) or "nenhuma violação"),
        )
        _, corpo = self.ponte.health()
        self.registrar(
            "contadores da ponte",
            corpo["telemetrias_violando_i1"] == 0 and corpo["reconexoes"] == 0,
            f"violando I1 {corpo['telemetrias_violando_i1']}, reconexões {corpo['reconexoes']}, "
            f"linhas inválidas {corpo['linhas_invalidas']}",
        )


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
        if not observador.esperar(lambda: observador.amostras, limite_s=10):
            print("A ponte não entregou telemetria em 10 s. Ela está no ar?", file=sys.stderr)
            return 2
        roteiro.health()
        roteiro.boot_em_all_red()
        roteiro.central()
        roteiro.ciclo()
        roteiro.ve_em_outro_eixo()
        roteiro.ve_no_eixo_verde()
        roteiro.prioridade_e_fila()
        roteiro.renovacao_e_teto()
        roteiro.sem_ocorrencia()
        roteiro.criticidade_decide()
        roteiro.recusa()
        roteiro.invariantes()
    except RuntimeError as erro:
        roteiro.registrar("roteiro interrompido", False, str(erro))
    finally:
        observador.parar()

    falhas = [r for r in roteiro.resultados if r.ok is False]
    print(
        f"\n{len(roteiro.resultados) - len(falhas)} de {len(roteiro.resultados)} conferências ok."
        " Fora do alcance da ponte: LCD, leitura da tag, ESP-NOW e o receptor no A0"
        " (checklist de bancada)."
    )
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
