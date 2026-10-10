"""Invariantes de segurança I1 a I5 — `context/01` §6.

**Segurança viária é invariante, não requisito negociável.** Nenhuma otimização
pode violar estas cinco regras, e a ação diante de uma violação é sempre a mesma:
abortar a preempção, voltar ao ciclo fixo e registrar o incidente.

| ID | Regra | Verificado sobre |
| -- | ----- | ---------------- |
| I1 | Nunca dois verdes conflitantes | o estado, a cada passo |
| I2 | Nunca verde → vermelho sem amarelo | a sequência de transições |
| I3 | All-red entre fases | a sequência de transições |
| I4 | Verde nunca truncado antes de `verde_min` | a sequência de transições |
| I5 | Nenhum acesso em vermelho além de `vermelho_max_s` | o estado, a cada passo |

I6 é responsabilidade exclusiva do firmware e não aparece aqui: se o backend
travar ou o cabo cair, ele não está lá para garantir nada. Desde 2026-10-05 I6
não é mais um watchdog: nenhum verde de emergência depende de comunicação para
terminar, e o teto é de 30 s (`context/01` §6).

As verificações de I2, I3 e I4 operam exatamente sobre os campos que
`estado_semaforo_amostra` persiste (decisão P5). Isso é deliberado: o mesmo
código que valida em memória durante a execução também valida os dados gravados,
no relatório de validação — sem uma segunda implementação para divergir.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from itertools import pairwise

from core.comandos import Comando, TipoComando
from core.malha import Cruzamento
from core.modelos import Sinal, Transicao
from core.parametros import Parametros
from core.priorizacao.fases import EstadoControlador


@dataclass(frozen=True)
class Violacao:
    """Um invariante quebrado.

    Attributes:
        invariante: Identificador — `"I1"` a `"I5"`.
        id_semaforo: Cruzamento onde ocorreu.
        t: Instante, em segundos.
        detalhe: Descrição legível, para o log de incidente e o relatório.
    """

    invariante: str
    id_semaforo: str
    t: float
    detalhe: str

    def __str__(self) -> str:
        return f"[{self.invariante}] {self.id_semaforo} t={self.t:.2f}s: {self.detalhe}"


# ---------------------------------------------------------------------------
# I1 — dois verdes conflitantes
# ---------------------------------------------------------------------------


def verificar_i1(
    estado: EstadoControlador, cruzamento: Cruzamento, t: float
) -> tuple[Violacao, ...]:
    """I1 — dois grupos de movimentos conflitantes nunca recebem verde junto.

    Sob *split phasing* (protótipo, decisão P13) a matriz de conflito é total e
    isto se reduz a `contar_verdes() <= 1`. A verificação geral abaixo cobre os
    dois casos.
    """
    verdes = sorted(estado.fases_verdes(cruzamento))
    violacoes: list[Violacao] = []

    for posicao, fase_a in enumerate(verdes):
        for fase_b in verdes[posicao + 1 :]:
            if cruzamento.conflitam(fase_a, fase_b):
                violacoes.append(
                    Violacao(
                        "I1",
                        cruzamento.id,
                        t,
                        f"fases conflitantes {fase_a} e {fase_b} com verde simultâneo",
                    )
                )
    return tuple(violacoes)


def comandos_criam_conflito(
    comandos: Iterable[Comando], estado: EstadoControlador, cruzamento: Cruzamento
) -> tuple[Comando, ...]:
    """Comandos que levariam a um verde conflitante — a metade do motor em P13.

    A matriz de conflito é aplicada aqui para que o motor nunca emita o comando.
    *(Até 2026-10-05 ela era aplicada uma segunda vez, de forma independente, no
    firmware do UNO, que recusava com `NAK,<cmd>,CONFLITO`: defesa em
    profundidade, para a segurança não depender de a serial estar íntegra nem
    de o backend estar correto. Desde então o UNO não recebe comandos do motor,
    e garante I1 na bancada com uma guarda própria, que lê os pinos antes de
    acender qualquer verde, `context/05` §3.5.)*

    Returns:
        Os comandos perigosos. Vazio significa que o conjunto é seguro.
    """
    verdes_atuais = estado.fases_verdes(cruzamento)
    perigosos: list[Comando] = []
    for comando in comandos:
        if comando.tipo is not TipoComando.IR_PARA_FASE or comando.fase_alvo is None:
            continue
        # `IR_PARA_FASE` só é perigoso se pudesse acender o verde alvo sem passar
        # pela transição — a máquina de estados impede, mas a checagem existe
        # para que a garantia não dependa de a máquina estar correta.
        for verde in verdes_atuais:
            if cruzamento.conflitam(verde, comando.fase_alvo) and comando.duracao_s == 0:
                perigosos.append(comando)
                break
    return tuple(perigosos)


# ---------------------------------------------------------------------------
# I2, I3, I4 — sobre a sequência de transições
# ---------------------------------------------------------------------------


def verificar_transicao(atual: Transicao, cruzamento: Cruzamento) -> tuple[Violacao, ...]:
    """I4 sobre uma transição isolada.

    I4 não precisa da transição anterior: um amarelo **só** pode suceder um
    verde, então `duracao_fase_anterior_s` de uma transição para `AMARELO` é,
    por construção, a duração daquele verde.

    Isso não é detalhe de implementação. Verificar I4 em pares deixaria a
    **primeira** transição de cada execução sem checagem — e a primeira é
    justamente a que ocorre logo após a partida do controlador, quando um
    comando prematuro é mais provável. O furo foi encontrado por um teste de
    mutação (verde mínimo sabotado, violação não acusada).
    """
    if atual.sinal is not Sinal.AMARELO:
        return ()

    duracao = atual.duracao_fase_anterior_s
    if duracao is None:
        return ()

    fase = atual.fase_anterior if atual.fase_anterior is not None else atual.fase
    verde_min = cruzamento.fase(fase).verde_min_s
    if duracao + 1e-9 >= verde_min:
        return ()

    return (
        Violacao(
            "I4",
            cruzamento.id,
            atual.t,
            f"verde da fase {fase} durou {duracao:.2f}s, abaixo do mínimo de {verde_min:.2f}s",
        ),
    )


def verificar_par_de_transicoes(
    anterior: Transicao, atual: Transicao, cruzamento: Cruzamento
) -> tuple[Violacao, ...]:
    """I2 e I3 sobre duas transições consecutivas do mesmo cruzamento.

    I4 sai daqui de propósito — ver `verificar_transicao`.
    """
    violacoes: list[Violacao] = []

    # I2 — verde nunca vai direto a vermelho.
    if anterior.sinal is Sinal.VERDE and atual.sinal is Sinal.VERMELHO:
        violacoes.append(
            Violacao(
                "I2",
                cruzamento.id,
                atual.t,
                f"fase {anterior.fase} foi de VERDE a VERMELHO sem amarelo",
            )
        )

    # I3 — toda troca de fase passa por all-red.
    if (
        atual.sinal is Sinal.VERDE
        and atual.fase != anterior.fase
        and anterior.sinal is not Sinal.VERMELHO
    ):
        violacoes.append(
            Violacao(
                "I3",
                cruzamento.id,
                atual.t,
                f"fase {anterior.fase} -> {atual.fase} sem all-red "
                f"(sinal anterior: {anterior.sinal})",
            )
        )

    return tuple(violacoes)


def verificar_sequencia(
    transicoes: Sequence[Transicao], cruzamento: Cruzamento
) -> tuple[Violacao, ...]:
    """I2, I3 e I4 sobre uma sequência completa de transições de um cruzamento.

    É a mesma verificação que o relatório de validação faz sobre as linhas de
    `estado_semaforo_amostra` (`context/06` §3).
    """
    violacoes: list[Violacao] = []
    for transicao in transicoes:
        violacoes.extend(verificar_transicao(transicao, cruzamento))
    for anterior, atual in pairwise(transicoes):
        violacoes.extend(verificar_par_de_transicoes(anterior, atual, cruzamento))
    return tuple(violacoes)


# ---------------------------------------------------------------------------
# I5 — starvation
# ---------------------------------------------------------------------------


def verificar_i5(
    estado: EstadoControlador, cruzamento: Cruzamento, parametros: Parametros, t: float
) -> tuple[Violacao, ...]:
    """I5 — nenhuma fase fica sem verde por mais de `vermelho_max_s`.

    É o invariante que a preempção mais ameaça: manter o corredor verde por tempo
    demais é, do ponto de vista da transversal, exatamente starvation. Também é o
    que dá sentido ao teto `verde_max_s` e ao `preempcao_timeout_s`.
    """
    violacoes: list[Violacao] = []
    verdes = estado.fases_verdes(cruzamento)
    for indice in cruzamento.indices_de_fase:
        if indice in verdes:
            continue
        desde = estado.t_ultimo_verde.get(indice)
        espera = t - desde if desde is not None else t
        if espera > parametros.vermelho_max_s:
            violacoes.append(
                Violacao(
                    "I5",
                    cruzamento.id,
                    t,
                    f"fase {indice} sem verde há {espera:.1f}s "
                    f"(máximo {parametros.vermelho_max_s:.0f}s)",
                )
            )
    return tuple(violacoes)


# ---------------------------------------------------------------------------
# Verificador acumulativo
# ---------------------------------------------------------------------------


@dataclass
class VerificadorSeguranca:
    """Aplica I1 a I5 a cada passo, guardando o histórico mínimo necessário.

    Guarda apenas a **última** transição de cada cruzamento: I2, I3 e I4 são
    propriedades de pares consecutivos, então não é preciso reter a série
    inteira. Num lote de 600 execuções isso é a diferença entre alguns bytes por
    cruzamento e centenas de megabytes.
    """

    parametros: Parametros
    _ultima_transicao: dict[str, Transicao] = field(default_factory=dict, repr=False)
    violacoes: list[Violacao] = field(default_factory=list)

    def verificar(
        self,
        estado: EstadoControlador,
        cruzamento: Cruzamento,
        t: float,
        transicoes: Sequence[Transicao] = (),
    ) -> tuple[Violacao, ...]:
        """Verifica todos os invariantes para um cruzamento neste passo.

        Args:
            estado: Estado do controlador após o passo.
            cruzamento: Cruzamento verificado.
            t: Instante, em segundos.
            transicoes: Transições emitidas neste passo.

        Returns:
            As violações encontradas agora. Vazio é o resultado esperado.
        """
        encontradas: list[Violacao] = []
        encontradas.extend(verificar_i1(estado, cruzamento, t))
        encontradas.extend(verificar_i5(estado, cruzamento, self.parametros, t))

        for transicao in transicoes:
            # I4 é verificado sempre, inclusive na primeira transição da execução.
            encontradas.extend(verificar_transicao(transicao, cruzamento))
            anterior = self._ultima_transicao.get(cruzamento.id)
            if anterior is not None:
                encontradas.extend(verificar_par_de_transicoes(anterior, transicao, cruzamento))
            self._ultima_transicao[cruzamento.id] = transicao

        self.violacoes.extend(encontradas)
        return tuple(encontradas)

    @property
    def seguro(self) -> bool:
        """Se nenhuma violação foi registrada até agora."""
        return not self.violacoes

    def resumo(self) -> dict[str, int]:
        """Contagem por invariante — a tabela do relatório de validação §5."""
        contagem = {f"I{n}": 0 for n in range(1, 6)}
        for violacao in self.violacoes:
            contagem[violacao.invariante] = contagem.get(violacao.invariante, 0) + 1
        return contagem
