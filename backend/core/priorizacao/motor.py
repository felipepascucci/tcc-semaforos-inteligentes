"""O motor de decisão — `avaliar(EstadoMalha) -> list[Comando]`.

Este é o núcleo do TCC. Recebe um estado normalizado e devolve comandos
abstratos: nada aqui sabe se do outro lado há um SUMO ou quatro LEDs numa
protoboard.

Sobre "puro": `avaliar()` não faz I/O — nem banco, nem rede, nem arquivo, nem
relógio. O motor **guarda** estado entre chamadas (de quem é cada preempção, há
quanto tempo, que compensação está em curso), porque preempção é um processo com
início e fim, não uma decisão instantânea. Esse estado é função determinística da
sequência de `EstadoMalha` recebida, o que preserva a reprodutibilidade exigida
pelo `CLAUDE.md`: mesma seed, mesma configuração, mesmo resultado.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from core.comandos import Comando, TipoComando, fallback_seguro
from core.excecoes import FaseInexistenteError
from core.malha import Cruzamento, TopologiaMalha
from core.modelos import EstadoMalha, EstadoSemaforo, Sinal
from core.parametros import Parametros
from core.priorizacao import compensacao as e7
from core.priorizacao.conflito import Disputa, EventoConflito, PoliticaDesempate, resolver
from core.priorizacao.deteccao import dentro_da_janela, detectar, fila_por_faixa
from core.priorizacao.fases import selecionar_fase


@dataclass
class PreempcaoAtiva:
    """Preempção em curso em um cruzamento.

    Attributes:
        id_veiculo: VE que a motivou.
        fase: Fase mantida em verde.
        t_inicio: Instante em que começou, em segundos.
    """

    id_veiculo: str
    fase: int
    t_inicio: float


@dataclass
class CompensacaoEmCurso:
    """Compensação pós-evento ainda vigente em um cruzamento.

    Attributes:
        plano: Durações de verde calculadas por E7.
        verdes_restantes: Quantas aberturas de verde o plano ainda rege. Conta-se
            em verdes, e não em ciclos, porque a compensação começa no meio de um
            ciclo — contar ciclos exigiria saber onde o ciclo "começa", que é uma
            convenção sem consequência física.
        ultima_fase: Última fase observada em verde, para detectar a virada.
    """

    plano: e7.PlanoCompensacao
    verdes_restantes: int
    ultima_fase: int | None = None


@dataclass
class MotorDecisao:
    """Agente reativo com otimização determinística baseada em conhecimento.

    A caracterização é a da decisão P3: técnica clássica de IA, coberta por
    Russell & Norvig. Não há modelo treinado — o comportamento vem inteiramente
    das regras E1 a E8 e dos parâmetros.

    Attributes:
        parametros: Parâmetros do algoritmo.
        topologia: Topologia da malha, com fases e geometria.
        observador_conflito: Chamado uma vez por passo e por cruzamento em que
            mais de um VE demanda fases distintas (entrega 10.1). É observação
            pura: não influencia decisão nenhuma, e o motor **não acumula** os
            eventos — quem quiser contá-los que os guarde. Manter o motor sem
            esse acúmulo é o que mantém o estado do motor nos três dicionários
            abaixo.
        politica: Quem propõe o vencedor de E8 no lugar da chave determinística
            (P19). `None`, o padrão, é o E8 de sempre. A criticidade continua
            acima da política, garantida por `resolver`.
    """

    parametros: Parametros
    topologia: TopologiaMalha
    observador_conflito: Callable[[EventoConflito], None] | None = None
    politica: PoliticaDesempate | None = None
    _preempcoes: dict[str, PreempcaoAtiva] = field(default_factory=dict, repr=False)
    _compensacoes: dict[str, CompensacaoEmCurso] = field(default_factory=dict, repr=False)
    _ultimo_verde: dict[str, dict[int, float]] = field(default_factory=dict, repr=False)

    # -- API principal -------------------------------------------------------

    def avaliar(self, estado: EstadoMalha) -> list[Comando]:
        """Decide o que fazer neste passo.

        Args:
            estado: Fotografia da malha no instante `estado.t`.

        Returns:
            Comandos a aplicar, um por cruzamento no máximo. Lista vazia
            significa "nada a fazer" — o caso mais comum, e o mais barato.
        """
        self._observar_verdes(estado)
        disputas = self._levantar_disputas(estado)
        self._publicar_conflitos(disputas, estado.t)
        comandos: list[Comando] = []

        for id_semaforo, estado_semaforo in estado.semaforos.items():
            comando = self._decidir_para(
                id_semaforo, estado_semaforo, disputas.get(id_semaforo, []), estado.t
            )
            if comando is not None:
                comandos.append(comando)

        return comandos

    # -- I5: starvation ------------------------------------------------------

    def _observar_verdes(self, estado: EstadoMalha) -> None:
        """Anota quando cada fase teve verde pela última vez.

        É a única memória que I5 exige, e ela vem do próprio `EstadoMalha`: o
        motor não precisa perguntar nada a ninguém para saber há quanto tempo
        uma aproximação está no vermelho.
        """
        for id_semaforo, semaforo in estado.semaforos.items():
            if semaforo.sinal is Sinal.VERDE:
                self._ultimo_verde.setdefault(id_semaforo, {})[semaforo.fase_atual] = estado.t

    def _fase_faminta(self, id_semaforo: str, cruzamento: Cruzamento, t: float) -> int | None:
        """Fase prestes a violar I5, se houver.

        A folga de uma transição segura existe porque a decisão precisa ser
        tomada **antes** do limite: descobrir a violação no instante em que ela
        acontece já é tarde — o vermelho excedente não se desfaz.
        """
        observados = self._ultimo_verde.get(id_semaforo, {})
        folga = self.parametros.tempo_transicao_segura_s
        for indice in cruzamento.indices_de_fase:
            desde = observados.get(indice)
            if desde is None:
                continue
            if t - desde >= self.parametros.vermelho_max_s - folga:
                return indice
        return None

    # -- E1, E2, E4: levantamento --------------------------------------------

    def _levantar_disputas(self, estado: EstadoMalha) -> dict[str, list[Disputa]]:
        """Detecta os VEs e traduz cada detecção na fase que ela demanda."""
        por_semaforo: dict[str, list[Disputa]] = {}

        for veiculo in estado.veiculos_emergencia:
            for deteccao in detectar(self.topologia, veiculo, self.parametros):
                cruzamento = self.topologia.cruzamentos.get(deteccao.id_semaforo)
                if cruzamento is None:
                    continue
                try:
                    fase = selecionar_fase(cruzamento, deteccao.movimento)
                except FaseInexistenteError:
                    # Mapa de fases incompleto para este movimento. Não é motivo
                    # para derrubar a execução, mas também não se inventa fase:
                    # o cruzamento simplesmente segue no ciclo fixo.
                    continue

                ativa = self._preempcoes.get(deteccao.id_semaforo)
                por_semaforo.setdefault(deteccao.id_semaforo, []).append(
                    Disputa(
                        deteccao=deteccao,
                        fase_desejada=fase,
                        ja_em_curso=ativa is not None and ativa.id_veiculo == deteccao.id_veiculo,
                    )
                )

        return por_semaforo

    def _publicar_conflitos(self, disputas: dict[str, list[Disputa]], t: float) -> None:
        """Publica os conflitos deste passo, se houver quem os observe (10.1).

        A publicação fica aqui, e não depois de `resolver`, porque
        `_decidir_para` pode retornar antes dele pelo timeout de E6 — e um
        conflito que existiu não pode deixar de ser contado por causa do
        caminho que a decisão tomou.

        Dois VEs no mesmo cruzamento só disputam se pedirem fases **distintas**:
        pedidos pela mesma fase são servidos pelo mesmo verde, e `resolver` os
        devolve em `atendidos_juntos`. Não há o que decidir, então não há evento.

        Args:
            disputas: Pedidos levantados neste passo, por cruzamento.
            t: Instante do passo, em segundos.
        """
        observador = self.observador_conflito
        if observador is None:
            return
        for evento in self._eventos_de_conflito(disputas, t):
            observador(evento)

    def _eventos_de_conflito(
        self, disputas: dict[str, list[Disputa]], t: float
    ) -> list[EventoConflito]:
        """Os conflitos contidos nos pedidos de um passo."""
        eventos: list[EventoConflito] = []
        for id_semaforo, pedidos in disputas.items():
            if len({pedido.fase_desejada for pedido in pedidos}) < 2:
                continue
            ativa = self._preempcoes.get(id_semaforo)
            eventos.append(
                EventoConflito(
                    t=t,
                    id_semaforo=id_semaforo,
                    disputas=tuple(pedidos),
                    preempcao_em_curso=ativa.id_veiculo if ativa is not None else None,
                )
            )
        return eventos

    def conflitos_em(self, estado: EstadoMalha) -> list[EventoConflito]:
        """Os conflitos que `avaliar(estado)` publicaria, **sem decidir nada**.

        Existe para a rotulagem por bifurcação (10.4), que precisa reconhecer a
        abertura da disputa **antes** de o motor escolher o vencedor, para ler os
        atributos e instalar a escolha forçada nesse instante. Não altera estado:
        só lê as preempções em curso.
        """
        return self._eventos_de_conflito(self._levantar_disputas(estado), estado.t)

    # -- E3, E5, E6, E7, E8: decisão -----------------------------------------

    def _decidir_para(
        self,
        id_semaforo: str,
        estado_semaforo: EstadoSemaforo,
        disputas: list[Disputa],
        t: float,
    ) -> Comando | None:
        """Decide o comando de um único cruzamento."""
        cruzamento = self.topologia.cruzamentos.get(id_semaforo)
        if cruzamento is None:
            return None

        ativa = self._preempcoes.get(id_semaforo)

        # E6 — timeout de segurança. Um VE que sumiu do estado (travou, mudou de
        # rota, saiu da malha) não pode manter a transversal parada para sempre.
        if ativa is not None and t - ativa.t_inicio >= self.parametros.preempcao_timeout_s:
            return self._liberar(
                id_semaforo,
                cruzamento,
                estado_semaforo,
                ativa,
                t,
                motivo=(
                    f"timeout de preempção: {t - ativa.t_inicio:.1f}s sem liberação "
                    f"(limite {self.parametros.preempcao_timeout_s:.0f}s)"
                ),
            )

        imposto = (
            self.politica.escolher(id_semaforo, disputas, t)
            if self.politica is not None and len(disputas) > 1
            else None
        )
        resolucao = resolver(id_semaforo, disputas, cruzamento, self.parametros, imposto)

        # Nenhum VE à vista: encerra a preempção que porventura esteja ativa e,
        # se houver plano de compensação vigente, é hora de executá-lo (E7).
        if resolucao is None:
            if ativa is not None:
                return self._liberar(
                    id_semaforo,
                    cruzamento,
                    estado_semaforo,
                    ativa,
                    t,
                    motivo=f"VE {ativa.id_veiculo} já atravessou; retomando ciclo",
                )
            return self._executar_compensacao(id_semaforo, estado_semaforo)

        vencedor = resolucao.vencedor
        fase_alvo = vencedor.fase_desejada

        # I5 — starvation. Se alguma aproximação está perto do teto de vermelho,
        # a preempção cede a vez. Segurança viária é invariante, não requisito
        # negociável: reter o corredor verde mais um pouco custaria menos tempo
        # ao VE do que custa deixar uma transversal parada por 2 minutos.
        faminta = self._fase_faminta(id_semaforo, cruzamento, t)
        if faminta is not None and faminta != fase_alvo:
            if ativa is not None:
                return self._liberar(
                    id_semaforo,
                    cruzamento,
                    estado_semaforo,
                    ativa,
                    t,
                    motivo=(
                        f"I5: fase {faminta} perto do limite de vermelho "
                        f"({self.parametros.vermelho_max_s:.0f}s); preempção cede a vez"
                    ),
                )
            return None

        # E3 — ainda é cedo? Preemptar antes da hora trava a transversal de graça,
        # e esse custo é justamente o que H2 quer minimizar. Tarde demais, porém,
        # abre o verde sem tempo de a fila escoar, e o VE para mesmo com verde
        # (P16) — por isso a janela consulta a fila do acesso de entrada.
        residual = self._verde_min_residual(estado_semaforo, cruzamento, fase_alvo)
        dissipacao = self.parametros.tempo_dissipacao_fila_s(
            fila_por_faixa(estado_semaforo, self.topologia, vencedor.deteccao.movimento[0])
        )
        if ativa is None and not dentro_da_janela(
            vencedor.deteccao, self.parametros, residual, dissipacao
        ):
            return None

        # Já estamos servindo a fase certa: estende, não recomeça a transição.
        if estado_semaforo.fase_atual == fase_alvo and estado_semaforo.sinal is Sinal.VERDE:
            self._preempcoes.setdefault(
                id_semaforo,
                PreempcaoAtiva(vencedor.deteccao.id_veiculo, fase_alvo, t),
            )
            duracao = min(
                vencedor.deteccao.eta_s + self.parametros.tempo_antecipacao_margem_s,
                cruzamento.fase(fase_alvo).verde_max_s,
                self.parametros.verde_max_s,
            )
            return Comando(
                tipo=TipoComando.ESTENDER_VERDE,
                id_semaforo=id_semaforo,
                fase_alvo=fase_alvo,
                duracao_s=duracao,
                id_veiculo=vencedor.deteccao.id_veiculo,
                motivo=resolucao.motivo,
            )

        # Transição segura para a fase alvo (E5). A sequência
        # verde -> amarelo -> all-red -> alvo é responsabilidade da máquina de
        # estados; aqui só se declara o destino.
        self._preempcoes[id_semaforo] = PreempcaoAtiva(
            vencedor.deteccao.id_veiculo, fase_alvo, ativa.t_inicio if ativa else t
        )
        return Comando(
            tipo=TipoComando.IR_PARA_FASE,
            id_semaforo=id_semaforo,
            fase_alvo=fase_alvo,
            duracao_s=vencedor.deteccao.eta_s + self.parametros.tempo_antecipacao_margem_s,
            id_veiculo=vencedor.deteccao.id_veiculo,
            motivo=resolucao.motivo,
        )

    # -- liberação e compensação --------------------------------------------

    def _liberar(
        self,
        id_semaforo: str,
        cruzamento: Cruzamento,
        estado_semaforo: EstadoSemaforo,
        ativa: PreempcaoAtiva,
        t: float,
        motivo: str,
    ) -> Comando:
        """Encerra a preempção e, se houver o que compensar, emite `COMPENSAR`.

        A escolha entre `LIBERAR` e `COMPENSAR` é o que separa os braços
        `PREEMPCAO` e `PREEMPCAO_COMPENSADA` do experimento: com
        `n_ciclos_compensacao = 0` o motor nunca compensa, e o braço sem
        compensação sai do mesmo código.
        """
        del self._preempcoes[id_semaforo]

        if self.parametros.n_ciclos_compensacao <= 0:
            return Comando(
                tipo=TipoComando.LIBERAR,
                id_semaforo=id_semaforo,
                id_veiculo=ativa.id_veiculo,
                motivo=motivo,
            )

        deficit = e7.calcular_deficit_s(t - ativa.t_inicio, ativa.fase, cruzamento, self.parametros)
        plano = e7.compensar(
            cruzamento, e7.filas_por_fase(estado_semaforo, cruzamento), deficit, self.parametros
        )
        self._compensacoes[id_semaforo] = CompensacaoEmCurso(
            plano, verdes_restantes=plano.n_ciclos * len(cruzamento.fases)
        )

        return Comando(
            tipo=TipoComando.COMPENSAR,
            id_semaforo=id_semaforo,
            id_veiculo=ativa.id_veiculo,
            duracao_s=plano.deficit_total_s,
            motivo=(
                f"{motivo}; compensando déficit de {deficit:.1f}s por {plano.n_ciclos} ciclo(s)"
            ),
        )

    def _executar_compensacao(
        self, id_semaforo: str, estado_semaforo: EstadoSemaforo
    ) -> Comando | None:
        """Etapa **E7**, parte de execução — aplica o plano ao verde corrente.

        Calcular o plano não muda semáforo nenhum. Quem o torna efetivo é este
        método: enquanto a compensação vigora, cada fase que abre recebe um
        `ESTENDER_VERDE` com o **restante** da duração planejada
        (`planejada - tempo_na_fase`). Repetir o comando a cada passo é
        idempotente — o alvo é sempre `t_mudanca + planejada` — e dispensa o
        motor guardar o instante em que cada verde começou.

        O comando sai **sem** `id_veiculo`, e isso é o que evita que a
        compensação seja confundida com preempção: a máquina de estados só marca
        `em_preempcao` quando a extensão é motivada por um VE. Sem essa
        distinção, os dois minutos de compensação apareceriam em
        `estado_semaforo_amostra` como preempção, e o custo transversal que H2
        mede ficaria atribuído ao evento errado.
        """
        em_curso = self._compensacoes.get(id_semaforo)
        if em_curso is None:
            return None
        if estado_semaforo.sinal is not Sinal.VERDE:
            return None

        if em_curso.ultima_fase != estado_semaforo.fase_atual:
            em_curso.ultima_fase = estado_semaforo.fase_atual
            em_curso.verdes_restantes -= 1
        if em_curso.verdes_restantes < 0:
            del self._compensacoes[id_semaforo]
            return None

        planejada = em_curso.plano.duracao_por_fase_s.get(estado_semaforo.fase_atual)
        if planejada is None:
            return None
        restante = planejada - estado_semaforo.tempo_na_fase
        if restante <= 0.0:
            return None

        return Comando(
            tipo=TipoComando.ESTENDER_VERDE,
            id_semaforo=id_semaforo,
            fase_alvo=estado_semaforo.fase_atual,
            duracao_s=restante,
            motivo=(
                f"compensação E7: fase {estado_semaforo.fase_atual} com "
                f"{planejada:.1f}s de verde (base + fila), "
                f"{em_curso.verdes_restantes} verde(s) restante(s)"
            ),
        )

    # -- apoio ---------------------------------------------------------------

    def _verde_min_residual(
        self,
        estado_semaforo: EstadoSemaforo,
        cruzamento: Cruzamento,
        fase_alvo: int,
    ) -> float:
        """Verde mínimo ainda a cumprir antes de poder iniciar a transição (I4)."""
        if estado_semaforo.sinal is not Sinal.VERDE:
            return 0.0
        if estado_semaforo.fase_atual == fase_alvo:
            return 0.0
        try:
            verde_min = cruzamento.fase(estado_semaforo.fase_atual).verde_min_s
        except FaseInexistenteError:
            verde_min = self.parametros.verde_min_s
        return max(verde_min - estado_semaforo.tempo_na_fase, 0.0)

    def plano_de_compensacao(self, id_semaforo: str) -> e7.PlanoCompensacao | None:
        """Plano de compensação vigente em um cruzamento, se houver."""
        em_curso = self._compensacoes.get(id_semaforo)
        return em_curso.plano if em_curso else None

    def preempcao_ativa(self, id_semaforo: str) -> PreempcaoAtiva | None:
        """Preempção em curso em um cruzamento, se houver."""
        return self._preempcoes.get(id_semaforo)

    def abortar(self, id_semaforo: str, motivo: str) -> Comando:
        """Fail-safe: abandona a preempção e volta ao ciclo fixo.

        Chamado quando `core.seguranca` acusa violação de invariante. Não é um
        caminho de erro excepcional — é o comportamento projetado diante de
        estado inseguro, e o incidente correspondente vira uma linha em
        `log_prioridade` com `status_execucao = 'ABORTADO_SEGURANCA'`.
        """
        self._preempcoes.pop(id_semaforo, None)
        self._compensacoes.pop(id_semaforo, None)
        return fallback_seguro(id_semaforo, motivo)
