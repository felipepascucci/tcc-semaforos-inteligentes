"""Demonstração guiada da bancada — o roteiro de `context/05` §7.

Diz ao apresentador o que fazer, espera o evento chegar e narra o semáforo ao
vivo, passo a passo::

    python -m bridge.main --porta COM3      # terminal 1 (com --telemetria, se quiser o registro)
    python -m bridge.demo                   # terminal 2, com o compose no ar e o dashboard aberto

**Ao contrário do `bridge.verificar`, roda com o backend no ar.** A Central entra
pela API do backend (`POST /ocorrencias` e `/ocorrencias/{id}/encerramento`, com
o token do operador), e é o backend que leva a lista ao UNO, como na operação
normal (`context/05` §2). O roteiro nunca chama `PUT /autorizacoes` da ponte:
ele só confere, pela `ST`, que a lista chegou.

Os passos:

1. ciclo normal, ninguém em serviço — o roteiro encerra as ocorrências abertas;
2. o carrinho passa pela tag da Rua 3 sem ocorrência → `SEM_OCORRENCIA`;
3. a Central despacha a ambulância — pelo dashboard, ou pela API com
   `--central-pela-api`;
4. o carrinho passa de novo → preempção, e o ciclo volta pelo eixo oposto;
5. a criticidade decide: a ponte injeta a ambulância na Rua 3 e, 3 s depois, o
   bombeiro na Rua 1, uma vez com o bombeiro mais crítico e outra com a
   ambulância mais crítica (o emissor físico é sempre ambulância);
6. autonomia: o apresentador encerra a ponte, e o carrinho preempta assim mesmo.
   Sem a ponte ninguém no notebook vê o UNO, então este passo é conferido a olho.

Com `--sem-carrinho`, a ponte injeta a ambulância no lugar do carrinho (plano B
da apresentação, ou ensaio sem o veículo), e o passo 6 é pulado. As
ocorrências que o roteiro abriu são encerradas no fim.

**Isto não é medição.** O que o roteiro confere é o comportamento, para o
apresentador saber que cada passo saiu como devia. Nenhum número daqui vai
para o texto; H3 e o checklist têm os seus próprios procedimentos.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from adapters.terminal import saida_utf8
from bridge.verificar import (
    CICLO_MS,
    FOLGA_MS,
    PIOR_CASO_MS,
    PRINCIPAL,
    TETO_MS,
    TRANSVERSAL,
    Amostra,
    Ev,
    Observador,
    Ponte,
    violacoes,
)

#: `codigo_externo` do cruzamento da bancada (`app.configuracao.CODIGO_BANCADA`).
CODIGO_BANCADA = "PROTO_CRUZ_01"

TIPOS = ("AMBULANCIA", "BOMBEIRO", "POLICIA")

#: A rua da tag que o roteiro pede (`context/05` §7). O carrinho pode ler outra;
#: o roteiro segue com a que ele leu.
RUA_DO_CARRINHO = 3

#: No passo 5, o segundo VE entra 3 s depois do `PREEMP_INI` do primeiro: dá
#: tempo de a plateia ver a transição começar antes da interrupção.
INTERVALO_SEGUNDO_VE_S = 3.0

DECISOES = frozenset({"PREEMP_INI", "RENOVADO", "FILA", "DESCARTADO", "SEM_OCORRENCIA"})

_COR = {"G": "verde", "Y": "amarelo", "R": "vermelho"}
_EIXO = (0, 0, 1, 1)


# ---------------------------------------------------------------------------
# Puro — testado à parte
# ---------------------------------------------------------------------------


def descrever(cores: str, regime: str) -> str:
    """O estado das quatro luzes em português, para narrar ao vivo."""
    nomes = {
        "RRRR": "all-red: todos vermelhos",
        PRINCIPAL: "eixo principal verde (S1 e S2)",
        "YYRR": "eixo principal amarelo",
        TRANSVERSAL: "eixo transversal verde (S3 e S4)",
        "RRYY": "eixo transversal amarelo",
    }
    if cores in nomes:
        texto = nomes[cores]
    else:
        verdes = [i for i, cor in enumerate(cores) if cor == "G"]
        if regime == "E" and len(verdes) == 1 and cores.count("R") == 3:
            n = verdes[0] + 1
            texto = f"verde exclusivo no S{n} (Rua {n}), os outros três vermelhos"
        else:
            texto = ", ".join(f"S{i + 1} {_COR[cor]}" for i, cor in enumerate(cores))
    return f"[emergência] {texto}" if regime == "E" else texto


def eixo_oposto(rua: int) -> str:
    """O eixo pelo qual o ciclo recomeça depois do VE da `rua` (`context/05` §3.4, 6)."""
    return TRANSVERSAL if _EIXO[rua - 1] == 0 else PRINCIPAL


def exclusivo(rua: int) -> str:
    return "".join("G" if i == rua - 1 else "R" for i in range(4))


def central_esperada(
    ocorrencias: Iterable[dict[str, Any]], tipo_do_veiculo: dict[int, str]
) -> dict[str, int]:
    """A lista que o UNO deve ter: a criticidade mais alta aberta de cada tipo.

    É a regra de `app.repositories.ocorrencia.criticidade_por_tipo`, refeita
    sobre o que a API devolve. `tipo_do_veiculo` só traz veículos ativos:
    ocorrência de veículo inativo não conta, como lá.
    """
    lista = dict.fromkeys(TIPOS, 0)
    for ocorrencia in ocorrencias:
        tipo = tipo_do_veiculo.get(ocorrencia["id_veiculo"])
        if tipo is None or not ocorrencia.get("aberta", True):
            continue
        criticidade = ocorrencia["criticidade"]
        lista[tipo] = criticidade if lista[tipo] == 0 else min(lista[tipo], criticidade)
    return lista


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------


class FalhaDoBackendError(RuntimeError):
    pass


class Backend:
    """Cliente mínimo da API do backend — só biblioteca padrão, como o da ponte."""

    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/")
        self.token: str | None = None

    def _pedir(self, metodo: str, caminho: str, corpo: Any = None) -> Any:
        dados = None if corpo is None else json.dumps(corpo).encode()
        cabecalhos = {"Content-Type": "application/json"}
        if self.token is not None:
            cabecalhos["Authorization"] = f"Bearer {self.token}"
        pedido = urllib.request.Request(
            self.url + caminho, data=dados, method=metodo, headers=cabecalhos
        )
        try:
            with urllib.request.urlopen(pedido, timeout=5) as resposta:
                return json.load(resposta)
        except urllib.error.HTTPError as erro:
            detalhe = erro.read().decode(errors="replace")
            raise FalhaDoBackendError(f"{metodo} {caminho}: HTTP {erro.code} {detalhe}") from erro
        except OSError as erro:
            raise FalhaDoBackendError(f"{metodo} {caminho}: backend fora do ar? ({erro})") from erro

    def entrar(self, usuario: str, senha: str) -> None:
        self.token = self._pedir("POST", "/auth/login", {"usuario": usuario, "senha": senha})[
            "access_token"
        ]

    def veiculos(self) -> list[dict[str, Any]]:
        resultado: list[dict[str, Any]] = self._pedir("GET", "/veiculos")
        return resultado

    def ocorrencias_ativas(self) -> list[dict[str, Any]]:
        resultado: list[dict[str, Any]] = self._pedir("GET", "/ocorrencias?ativas=true")
        return resultado

    def abrir(self, id_veiculo: int, criticidade: int, descricao: str) -> dict[str, Any]:
        resultado: dict[str, Any] = self._pedir(
            "POST",
            "/ocorrencias",
            {"id_veiculo": id_veiculo, "criticidade": criticidade, "descricao": descricao},
        )
        return resultado

    def encerrar(self, id_ocorrencia: int) -> dict[str, Any]:
        resultado: dict[str, Any] = self._pedir(
            "POST", f"/ocorrencias/{id_ocorrencia}/encerramento"
        )
        return resultado

    def logs_da_bancada(self, desde: datetime) -> list[dict[str, Any]]:
        consulta = urlencode({"semaforo": CODIGO_BANCADA, "desde": desde.isoformat()})
        resultado: list[dict[str, Any]] = self._pedir("GET", f"/logs/prioridade?{consulta}")[
            "itens"
        ]
        return resultado


# ---------------------------------------------------------------------------
# Roteiro
# ---------------------------------------------------------------------------


class DemoInterrompidaError(RuntimeError):
    pass


@dataclass
class Resultado:
    nome: str
    ok: bool
    detalhe: str


@dataclass
class Opcoes:
    sem_carrinho: bool = False
    central_pela_api: bool = False
    pausa: bool = True
    espera_carrinho_s: float = 300.0


class Demo:
    def __init__(
        self,
        ponte: Ponte,
        observador: Observador,
        backend: Backend,
        opcoes: Opcoes,
        perguntar: Callable[[str], str] = input,
    ) -> None:
        self.ponte = ponte
        self.obs = observador
        self.backend = backend
        self.op = opcoes
        self.perguntar = perguntar
        self.resultados: list[Resultado] = []
        self.tipo_do_veiculo: dict[int, str] = {}
        self.veiculo_do_tipo: dict[str, dict[str, Any]] = {}
        self.abertas_pelo_roteiro: set[int] = set()
        self._narrado_ate = 0
        self._narrar = False
        self._referencia_ms = 0

    # -- saída -----------------------------------------------------------------

    def registrar(self, nome: str, ok: bool, detalhe: str) -> None:
        self.resultados.append(Resultado(nome, ok, detalhe))
        print(f"   [{'ok' if ok else 'FALHA'}] {nome} — {detalhe}", flush=True)

    @staticmethod
    def dizer(texto: str) -> None:
        print(f"   {texto}", flush=True)

    @staticmethod
    def pedir(texto: str) -> None:
        print(f"\n   >> FAÇA: {texto}", flush=True)

    def passo(self, numero: int, titulo: str) -> None:
        print(f"\n=== Passo {numero}: {titulo} ===", flush=True)
        if self.op.pausa:
            self.perguntar("   [Enter] para começar ")

    # -- observação --------------------------------------------------------------

    def narrar(self, ligado: bool, desde_ms: int | None = None) -> None:
        """Liga ou desliga a narração das luzes.

        Ao ligar, narra o que mudar depois de `desde_ms` (padrão: agora), com os
        segundos contados a partir dele.
        """
        self._narrar = ligado
        if ligado:
            inicio = self.obs.agora_ms() if desde_ms is None else desde_ms
            self._referencia_ms = inicio
            self._narrado_ate = inicio - 1

    def _narrar_novas(self) -> None:
        if not self._narrar:
            return
        amostras, _ = self.obs.copia()
        anterior = next((a for a in reversed(amostras) if a.ms <= self._narrado_ate), None)
        for amostra in amostras:
            if amostra.ms <= self._narrado_ate:
                continue
            if anterior is None or (amostra.cores, amostra.regime) != (
                anterior.cores,
                anterior.regime,
            ):
                segundos = (amostra.ms - self._referencia_ms) / 1000
                print(
                    f"      {segundos:5.1f} s  {descrever(amostra.cores, amostra.regime)}",
                    flush=True,
                )
            anterior = amostra
            self._narrado_ate = amostra.ms

    def esperar(self, condicao: Callable[[], Any], limite_s: float, lembrete_s: float = 0) -> Any:
        """Como `Observador.esperar`, narrando as luzes enquanto espera."""
        inicio = time.monotonic()
        proximo_lembrete = inicio + lembrete_s
        while time.monotonic() - inicio < limite_s:
            self._narrar_novas()
            resultado = condicao()
            if resultado:
                self._narrar_novas()
                return resultado
            if lembrete_s and time.monotonic() >= proximo_lembrete:
                self.dizer("(ainda esperando...)")
                proximo_lembrete += lembrete_s
            time.sleep(0.05)
        return None

    def esperar_evento(
        self,
        tipos: Iterable[str],
        desde_ms: int,
        limite_s: float,
        rua: int | None = None,
        veiculo: str | None = None,
        lembrete_s: float = 0,
    ) -> Ev | None:
        conjunto = frozenset(tipos)

        def achar() -> Ev | None:
            _, eventos = self.obs.copia()
            return next(
                (
                    ev
                    for ev in eventos
                    if ev.tipo in conjunto
                    and ev.ms >= desde_ms
                    and (rua is None or ev.rua == rua)
                    and (veiculo is None or ev.veiculo == veiculo)
                ),
                None,
            )

        resultado: Ev | None = self.esperar(achar, limite_s, lembrete_s)
        return resultado

    def esperar_amostra(
        self, condicao: Callable[[Amostra], bool], desde_ms: int, limite_s: float
    ) -> Amostra | None:
        resultado: Amostra | None = self.esperar(
            lambda: self.obs.primeira(condicao, desde_ms), limite_s
        )
        return resultado

    def lista_do_uno(self) -> dict[str, int]:
        amostras, _ = self.obs.copia()
        return dict(amostras[-1].autorizacoes) if amostras else {}

    def ciclo_ocioso(self) -> None:
        def em_ciclo() -> bool:
            amostras, _ = self.obs.copia()
            return bool(amostras) and amostras[-1].regime == "C"

        if not self.esperar(em_ciclo, TETO_MS / 1000 + 10):
            raise DemoInterrompidaError("a emergência anterior não terminou")

    def abertura(self, cores: str, limite_s: float = CICLO_MS / 1000 + 3) -> Amostra:
        """Espera o eixo `cores` abrir no ciclo, vindo do all-red."""
        inicio = self.obs.agora_ms()

        def aberto() -> Amostra | None:
            for amostra in self.obs.entre(inicio + 1, 10**12):
                if amostra.cores == cores and amostra.regime == "C":
                    anteriores = self.obs.entre(inicio, amostra.ms - 1)
                    if anteriores and anteriores[-1].cores == "RRRR":
                        return amostra
            return None

        resultado: Amostra | None = self.esperar(aberto, limite_s)
        if resultado is None:
            raise DemoInterrompidaError(f"{cores} não abriu em {limite_s:.0f} s")
        return resultado

    # -- Central -----------------------------------------------------------------

    def carregar_cadastro(self) -> None:
        for veiculo in self.backend.veiculos():
            if veiculo["status_operacional"] != "ATIVO":
                continue
            self.tipo_do_veiculo[veiculo["id_veiculo"]] = veiculo["tipo"]
            self.veiculo_do_tipo.setdefault(veiculo["tipo"], veiculo)
        faltam = [t for t in ("AMBULANCIA", "BOMBEIRO") if t not in self.veiculo_do_tipo]
        if faltam:
            raise DemoInterrompidaError(f"sem veículo ativo cadastrado do tipo {', '.join(faltam)}")

    def esperar_lista(self, limite_s: float = 5.0) -> dict[str, int]:
        """Espera a `ST` trazer a lista das ocorrências abertas, levada pelo backend."""
        esperada = central_esperada(self.backend.ocorrencias_ativas(), self.tipo_do_veiculo)
        if not self.esperar(lambda: self.lista_do_uno() == esperada, limite_s):
            raise DemoInterrompidaError(
                f"o UNO tem {self.lista_do_uno()}, e a Central diz {esperada}. "
                "O backend está lendo a ponte? (docker ps; o painel da bancada no dashboard)"
            )
        return esperada

    def definir_central(self, criticidades: dict[str, int]) -> None:
        """Deixa cada tipo dado com uma ocorrência dessa criticidade (0: nenhuma).

        Uma ocorrência aberta por VE (garantido pelo banco): para trocar a
        criticidade, encerra e abre outra. Confere na `ST` que o UNO recebeu.
        """
        abertas = self.backend.ocorrencias_ativas()
        for tipo, criticidade in criticidades.items():
            veiculo = self.veiculo_do_tipo[tipo]
            minhas = [o for o in abertas if o["id_veiculo"] == veiculo["id_veiculo"]]
            if criticidade and any(o["criticidade"] == criticidade for o in minhas):
                continue
            for ocorrencia in minhas:
                self.backend.encerrar(ocorrencia["id_ocorrencia"])
                self.abertas_pelo_roteiro.discard(ocorrencia["id_ocorrencia"])
            if criticidade:
                nova = self.backend.abrir(
                    veiculo["id_veiculo"], criticidade, "Demonstração da bancada (bridge.demo)"
                )
                self.abertas_pelo_roteiro.add(nova["id_ocorrencia"])
        lista = self.esperar_lista()
        self.dizer(f"Central no UNO: {_lista(lista)}")

    def garantir_ambulancia(self) -> None:
        """Para rodar um passo sozinho (`--passos`): sem ambulância em serviço, abre uma."""
        if self.lista_do_uno().get("AMBULANCIA", 0) == 0:
            self.dizer("A ambulância não está em serviço: abrindo uma ocorrência pela API.")
            self.definir_central({"AMBULANCIA": 1})

    def encerrar_todas(self) -> list[dict[str, Any]]:
        abertas = self.backend.ocorrencias_ativas()
        for ocorrencia in abertas:
            self.backend.encerrar(ocorrencia["id_ocorrencia"])
        return abertas

    # -- o carrinho ----------------------------------------------------------------

    def carrinho_passa(self, instrucao: str) -> Ev:
        """Pede a passagem do carrinho e devolve a decisão do UNO para ela."""
        desde = self.obs.agora_ms()
        if self.op.sem_carrinho:
            self.dizer(f"(sem carrinho: a ponte injeta AMBULANCIA na Rua {RUA_DO_CARRINHO})")
            status, corpo = self.ponte.injetar(RUA_DO_CARRINHO, "AMBULANCIA")
            if status != 200:
                raise DemoInterrompidaError(f"injeção sem decisão (HTTP {status}): {corpo}")
        else:
            self.pedir(instrucao)
        decisao = self.esperar_evento(DECISOES, desde, self.op.espera_carrinho_s, lembrete_s=30)
        if decisao is None:
            raise DemoInterrompidaError(
                f"nenhuma leitura chegou ao UNO em {self.op.espera_carrinho_s:.0f} s"
            )
        self.dizer(f"UNO decidiu: {decisao.tipo} — {decisao.veiculo} na Rua {decisao.rua}")
        return decisao

    def injetar(self, rua: int, veiculo: str) -> Ev:
        status, corpo = self.ponte.injetar(rua, veiculo)
        if status != 200:
            raise DemoInterrompidaError(f"injeção RUA{rua},{veiculo} sem decisão (HTTP {status})")
        ev = Ev(corpo["decisao_t_dispositivo_ms"], corpo["decisao"], rua, veiculo)
        self.dizer(f"ponte injetou {veiculo} na Rua {rua} → UNO decidiu {ev.tipo}")
        return ev

    # -- trechos comuns ------------------------------------------------------------

    def acompanhar_atendimento(self, inicio: Ev) -> Ev | None:
        """Do `PREEMP_INI` ao `PREEMP_FIM` do mesmo VE; devolve o fim.

        Confere o verde exclusivo em até 6 s. A releitura do carrinho no meio
        (`RENOVADO`) só estica o verde, e o roteiro segue até o fim.
        """
        assert inicio.rua is not None
        verde = self.esperar_amostra(
            lambda a: a.cores == exclusivo(inicio.rua or 0), inicio.ms, PIOR_CASO_MS / 1000 + 2
        )
        espera = None if verde is None else verde.ms - inicio.ms
        self.registrar(
            f"verde exclusivo da Rua {inicio.rua} em até 6 s",
            espera is not None and espera <= PIOR_CASO_MS + FOLGA_MS,
            "não abriu" if espera is None else f"{espera / 1000:.1f} s depois da decisão",
        )
        fim = self.esperar_evento(
            {"PREEMP_FIM"}, inicio.ms, TETO_MS / 1000 + 5, rua=inicio.rua, veiculo=inicio.veiculo
        )
        if fim is None:
            self.registrar(f"fim do verde da Rua {inicio.rua}", False, "PREEMP_FIM não chegou")
        return fim

    def conferir_volta(self, fim: Ev) -> None:
        assert fim.rua is not None
        depois = self.esperar_amostra(lambda a: "G" in a.cores, fim.ms + 1, PIOR_CASO_MS / 1000 + 2)
        esperado = eixo_oposto(fim.rua)
        self.registrar(
            "o ciclo volta pelo eixo que ficou esperando",
            depois is not None and depois.cores == esperado and depois.regime == "C",
            f"abriu {descrever(depois.cores, depois.regime) if depois else 'nada'}",
        )

    def conferir_invariantes(self) -> None:
        amostras, _ = self.obs.copia()
        achados = violacoes([(a.ms, a.cores) for a in amostras], folga_ms=FOLGA_MS)
        self.registrar(
            "I1 a I4 em toda a telemetria até aqui",
            not achados,
            "; ".join(achados[:3]) or f"{len(amostras)} telemetrias, nenhuma violação",
        )

    # -- passos --------------------------------------------------------------------

    def preparar(self) -> None:
        print("=== Preparação ===", flush=True)
        status, corpo = self.ponte.health()
        if status != 200:
            raise DemoInterrompidaError(f"a ponte não está pronta (HTTP {status}): {corpo}")
        self.dizer(f"ponte ok, UNO na {corpo['porta']}")
        self.carregar_cadastro()
        encerradas = self.encerrar_todas()
        for ocorrencia in encerradas:
            tipo = self.tipo_do_veiculo.get(ocorrencia["id_veiculo"], "veículo inativo")
            self.dizer(
                f"encerrada a ocorrência {ocorrencia['id_ocorrencia']} ({tipo}, "
                f"criticidade {ocorrencia['criticidade']}): o passo 1 começa sem ninguém em serviço"
            )
        lista = self.esperar_lista()
        self.dizer(f"Central no UNO: {_lista(lista)}")

    def passo1_ciclo(self) -> None:
        self.passo(1, "ciclo normal, ninguém em serviço")
        self.dizer("Mostre o dashboard: os dois eixos se alternam, 12 s por ciclo.")
        self.ciclo_ocioso()
        self.narrar(True)
        primeira = self.abertura(PRINCIPAL)
        self.abertura(TRANSVERSAL)
        segunda = self.abertura(PRINCIPAL)
        self.narrar(False)
        volta = segunda.ms - primeira.ms
        self.registrar(
            "ciclo de 12 s, eixos alternando",
            abs(volta - CICLO_MS) <= FOLGA_MS,
            f"ciclo de {volta / 1000:.1f} s",
        )
        lista = self.lista_do_uno()
        self.registrar(
            "ninguém em serviço na Central do UNO",
            all(c == 0 for c in lista.values()),
            _lista(lista),
        )

    def passo2_sem_ocorrencia(self) -> None:
        self.passo(2, "tag sem ocorrência")
        self.ciclo_ocioso()
        desde = datetime.now(UTC)
        decisao = self.carrinho_passa(
            f"passe o carrinho pela tag da Rua {RUA_DO_CARRINHO} e espere."
        )
        mexeu = self.esperar_evento({"PREEMP_INI"}, decisao.ms, 1.0)
        self.registrar(
            "a ambulância sem ocorrência não preempta",
            decisao.tipo == "SEM_OCORRENCIA" and mexeu is None,
            f"decisão {decisao.tipo}; semáforo {'mexeu' if mexeu else 'seguiu o ciclo'}",
        )
        self.dizer(f"Mostre o LCD: SEM OCORRENCIA / {decisao.veiculo} na R{decisao.rua} (por 3 s).")
        logado = self.esperar(
            lambda: any(
                "SEM_OCORRENCIA" in (log["motivo"] or "")
                for log in self.backend.logs_da_bancada(desde)
            ),
            3.0,
        )
        self.registrar(
            "o dashboard registra a negação (log_prioridade)",
            bool(logado),
            "linha SEM_OCORRENCIA gravada" if logado else "nenhuma linha em 3 s",
        )

    def passo3_despacho(self) -> None:
        self.passo(3, "a Central despacha a ambulância")
        ambulancia = self.veiculo_do_tipo["AMBULANCIA"]
        if self.op.central_pela_api:
            self.dizer("Abrindo pela API uma ocorrência de risco à vida para a ambulância.")
            self.definir_central({"AMBULANCIA": 1})
        else:
            self.pedir(
                f"na aba Central do dashboard, abra uma ocorrência para a ambulância "
                f"{ambulancia['placa']} (qualquer criticidade)."
            )
            if not self.esperar(
                lambda: self.lista_do_uno().get("AMBULANCIA", 0) != 0,
                self.op.espera_carrinho_s,
                lembrete_s=30,
            ):
                raise DemoInterrompidaError("a ambulância não entrou em serviço")
            for ocorrencia in self.backend.ocorrencias_ativas():
                if ocorrencia["id_veiculo"] == ambulancia["id_veiculo"]:
                    self.abertas_pelo_roteiro.add(ocorrencia["id_ocorrencia"])
        lista = self.lista_do_uno()
        self.registrar(
            "a ambulância está em serviço no UNO",
            lista.get("AMBULANCIA", 0) != 0,
            _lista(lista),
        )
        self.dizer('Mostre o painel da bancada: "Em serviço no UNO: Ambulância".')

    def passo4_preempcao(self) -> None:
        self.passo(4, "o carrinho passa de novo e preempta")
        self.garantir_ambulancia()
        self.ciclo_ocioso()
        decisao = self.carrinho_passa(
            f"passe o carrinho de novo pela tag da Rua {RUA_DO_CARRINHO}."
        )
        if decisao.tipo != "PREEMP_INI":
            self.registrar("a ambulância em serviço preempta", False, f"decisão {decisao.tipo}")
            return
        self.narrar(True, desde_ms=decisao.ms)
        self.dizer(
            f"Mostre: o eixo da Rua {decisao.rua} pelo amarelo e pelo all-red, e o LCD "
            f"{decisao.veiculo} na R{decisao.rua}."
        )
        fim = self.acompanhar_atendimento(decisao)
        if fim is not None:
            self.conferir_volta(fim)
        self.narrar(False)

    def _disputa(self, ambulancia: int, bombeiro: int) -> None:
        """Ambulância na Rua 3, bombeiro na Rua 1 3 s depois, com estas criticidades."""
        self.definir_central({"AMBULANCIA": ambulancia, "BOMBEIRO": bombeiro})
        self.ciclo_ocioso()
        self.narrar(True)
        primeiro = self.injetar(3, "AMBULANCIA")
        if primeiro.tipo != "PREEMP_INI":
            self.registrar("a ambulância é atendida", False, f"decisão {primeiro.tipo}")
            self.narrar(False)
            return
        self.esperar(lambda: False, INTERVALO_SEGUNDO_VE_S)
        segundo = self.injetar(1, "BOMBEIRO")
        atendido: Ev
        fila_rua, fila_veiculo = (3, "AMBULANCIA") if bombeiro < ambulancia else (1, "BOMBEIRO")
        if bombeiro < ambulancia:
            fila = self.esperar_evento({"FILA"}, segundo.ms, 2, rua=3, veiculo="AMBULANCIA")
            self.registrar(
                "o bombeiro, mais crítico, interrompe a ambulância, que vai para a fila",
                segundo.tipo == "PREEMP_INI" and fila is not None,
                f"bombeiro {segundo.tipo}; ambulância {'na fila' if fila else 'sem FILA'}",
            )
            atendido = segundo
        else:
            self.registrar(
                "o bombeiro, menos crítico, espera na fila",
                segundo.tipo == "FILA",
                f"bombeiro {segundo.tipo}",
            )
            atendido = primeiro
        # Quem está atendido vai até o fim; o da fila entra em seguida.
        fim = self.acompanhar_atendimento(atendido)
        if fim is None:
            self.narrar(False)
            return
        retomada = self.esperar_evento(
            {"PREEMP_INI"}, fim.ms, 2, rua=fila_rua, veiculo=fila_veiculo
        )
        self.registrar(
            f"{fila_veiculo} sai da fila e é atendido",
            retomada is not None,
            "PREEMP_INI logo depois do fim do primeiro" if retomada else "não saiu da fila",
        )
        if retomada is not None:
            fim = self.acompanhar_atendimento(retomada)
            if fim is not None:
                self.conferir_volta(fim)
        self.narrar(False)

    def passo5_criticidade(self) -> None:
        self.passo(5, "a criticidade decide quem interrompe")
        self.dizer(
            "O carrinho é sempre ambulância; o segundo VE vem pela ponte, como se o "
            "receptor o tivesse ouvido."
        )
        self.dizer("Primeiro: ambulância em RISCO_COLETIVO (2), bombeiro em RISCO_VIDA (1).")
        self._disputa(ambulancia=2, bombeiro=1)
        self.dizer("Agora trocadas: ambulância em RISCO_VIDA (1), bombeiro em RISCO_COLETIVO (2).")
        self._disputa(ambulancia=1, bombeiro=2)
        self.conferir_invariantes()

    def passo6_autonomia(self) -> None:
        self.passo(6, "autonomia do cruzamento")
        if self.op.sem_carrinho:
            self.dizer("Pulado: sem a ponte, só o carrinho chega ao UNO.")
            return
        self.garantir_ambulancia()
        self.ciclo_ocioso()
        self.dizer(
            "A ambulância está em serviço. A lista está na RAM do UNO, e é contra ela "
            "que ele decide."
        )
        self.pedir("encerre a ponte (Ctrl+C no terminal dela).")

        def ponte_fechada() -> bool:
            try:
                self.ponte.health()
            except OSError:
                return True
            return False

        if not self.esperar(ponte_fechada, self.op.espera_carrinho_s, lembrete_s=30):
            raise DemoInterrompidaError("a ponte continua no ar")
        self.obs.parar()
        self.dizer("Ponte fechada: o dashboard parou, e a Central não alcança mais o UNO.")
        self.pedir(
            f"passe o carrinho pela tag da Rua {RUA_DO_CARRINHO}. Mostre o amarelo, o all-red, "
            f"o verde só no S{RUA_DO_CARRINHO} e o LCD AMBULANCIA na R{RUA_DO_CARRINHO}."
        )
        # O BOM aparece quando a resposta vem por um pipe do PowerShell.
        resposta = self.perguntar("   O semáforo preemptou e voltou ao ciclo? [s/n] ")
        resposta = resposta.strip("﻿ \t\r\n").lower()
        self.registrar(
            "sem a ponte, o carrinho preempta assim mesmo",
            resposta.startswith("s"),
            f"conferido a olho (sem a ponte ninguém no notebook vê o UNO): {resposta}",
        )
        self.dizer(
            "Ao subir a ponte de novo, o UNO reinicia (DTR) e volta negando todos; o "
            "backend devolve a lista em ~1 s."
        )

    def encerrar_as_minhas(self) -> None:
        for id_ocorrencia in sorted(self.abertas_pelo_roteiro):
            try:
                self.backend.encerrar(id_ocorrencia)
            except FalhaDoBackendError as erro:
                self.dizer(f"não encerrei a ocorrência {id_ocorrencia}: {erro}")
            else:
                self.dizer(f"encerrada a ocorrência {id_ocorrencia}, aberta na demonstração")
        self.abertas_pelo_roteiro.clear()


def _lista(lista: dict[str, int]) -> str:
    em_servico = [f"{tipo} {c}" for tipo, c in lista.items() if c]
    return ", ".join(em_servico) if em_servico else "ninguém em serviço"


def _pedir_senha() -> str:
    """A senha pelo `getpass`, sem deixar tecla sobrando para a primeira pausa.

    No terminal do VS Code, o Enter da senha deixava um caractere no buffer do
    console, e a pausa do passo 1 o lia: o passo começava sozinho (ensaio de
    2026-10-07).
    """
    senha = getpass.getpass("Senha do operador: ")
    if sys.platform == "win32":
        import msvcrt

        while msvcrt.kbhit():
            msvcrt.getwch()
    return senha


def main(argv: Sequence[str] | None = None) -> int:
    saida_utf8()
    parser = argparse.ArgumentParser(
        prog="python -m bridge.demo",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--ponte", default="http://127.0.0.1:8001")
    parser.add_argument("--backend", default="http://localhost:8000/api/v1")
    parser.add_argument("--usuario", default=os.getenv("OPERADOR_USUARIO", "operador"))
    parser.add_argument(
        "--senha", default=None, help="senha do operador (padrão: OPERADOR_SENHA, ou pergunta)"
    )
    parser.add_argument(
        "--sem-carrinho",
        action="store_true",
        help="a ponte injeta a ambulância no lugar do carrinho; pula o passo 6",
    )
    parser.add_argument(
        "--central-pela-api",
        action="store_true",
        help="no passo 3, o roteiro abre a ocorrência em vez de pedir pelo dashboard",
    )
    parser.add_argument("--sem-pausa", action="store_true", help="não espera Enter entre os passos")
    parser.add_argument(
        "--passos", default="123456", help="quais passos rodar, por exemplo 45 (padrão: todos)"
    )
    parser.add_argument("--espera-carrinho", type=float, default=300.0, metavar="S")
    args = parser.parse_args(argv)

    senha = args.senha or os.getenv("OPERADOR_SENHA") or _pedir_senha()
    ponte = Ponte(args.ponte)
    observador = Observador(ponte)
    backend = Backend(args.backend)
    demo = Demo(
        ponte,
        observador,
        backend,
        Opcoes(
            sem_carrinho=args.sem_carrinho,
            central_pela_api=args.central_pela_api,
            pausa=not args.sem_pausa,
            espera_carrinho_s=args.espera_carrinho,
        ),
    )
    passos = {
        "1": demo.passo1_ciclo,
        "2": demo.passo2_sem_ocorrencia,
        "3": demo.passo3_despacho,
        "4": demo.passo4_preempcao,
        "5": demo.passo5_criticidade,
        "6": demo.passo6_autonomia,
    }
    try:
        backend.entrar(args.usuario, senha)
        observador.iniciar()
        if not observador.esperar(lambda: observador.amostras, limite_s=10):
            print("A ponte não entregou telemetria em 10 s. Ela está no ar?", file=sys.stderr)
            return 2
        demo.preparar()
        for numero in args.passos:
            passos[numero]()
    except (DemoInterrompidaError, FalhaDoBackendError) as erro:
        demo.registrar("demonstração interrompida", False, str(erro))
    except KeyboardInterrupt:
        demo.registrar("demonstração interrompida", False, "Ctrl+C")
    finally:
        observador.parar()
        if demo.abertas_pelo_roteiro:
            print("\n=== Fim: limpando a Central ===", flush=True)
            demo.encerrar_as_minhas()

    falhas = [r for r in demo.resultados if not r.ok]
    print(f"\n{len(demo.resultados) - len(falhas)} de {len(demo.resultados)} conferências ok.")
    for falha in falhas:
        print(f"  FALHA: {falha.nome} — {falha.detalhe}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
