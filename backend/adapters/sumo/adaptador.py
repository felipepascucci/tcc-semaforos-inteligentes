"""Adaptador SUMO — entrega 3.6 (`context/01` §1, C3).

O motor devolve **intenções** (`IR_PARA_FASE`, `ESTENDER_VERDE`...). Este módulo é
quem as traduz em ação concreta no simulador, e quem faz o caminho de volta:
transforma o que o SUMO tem em `EstadoMalha`, a única entrada que o motor aceita.

DUAS DECISÕES DE DESENHO QUE MERECEM EXPLICAÇÃO

**1. A sinalização é conduzida pela máquina de estados de `core`, não por
`setPhase`.** O TraCI oferece `trafficlight.setPhase()`, que salta direto para a
fase pedida. Usá-lo violaria I2 e I3 na primeira preempção: o verde da
transversal viraria verde da arterial sem amarelo e sem all-red. Em vez disso, o
adaptador roda `core.priorizacao.fases.avancar()` — a mesma máquina que o
property-based testing exercita e que o firmware do UNO reimplementa em C++ — e
empurra para o SUMO a *state string* correspondente ao estado resultante. Os
invariantes de segurança passam a valer na simulação pela mesma construção que os
faz valer na bancada.

**2. O adaptador mantém o estado do controlador também no modo `FIXO`.** Ali ele
não comanda nada — o baseline precisa ser genuinamente sem intervenção
(`context/04` §8) —, mas observa a fase do SUMO e reconstrói o mesmo
`EstadoControlador`. Com isso o verificador de invariantes e o coletor de
transições rodam **idênticos nos três braços**, e o relatório de validação pode
afirmar "zero violações" sobre o baseline com a mesma evidência que sobre o
proposto. Sem isso, o braço de controle seria o único não auditado.

Sobre desempenho: o estado é lido por **assinaturas** (`subscribe`), não por
chamada por objeto a cada passo. Com 48 detectores e 36.000 passos, a diferença
entre uma chamada por passo e 48 é a diferença entre minutos e horas nas 600
execuções do Bloco 8.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from adapters.sumo.cliente import ClienteSumo, constantes
from adapters.sumo.topologia import MalhaSumo
from core.comandos import Comando
from core.modelos import (
    Criticidade,
    EstadoMalha,
    EstadoSemaforo,
    Sinal,
    TipoVeiculo,
    Transicao,
    VeiculoEmergencia,
)
from core.parametros import Parametros
from core.priorizacao.fases import Avanco, EstadoControlador, avancar, estado_inicial

#: `vType` do SUMO -> tipo de VE do domínio. A detecção em si é por `vClass`
#: (`emergency`); este mapa só resolve a prioridade de E8.
TIPO_POR_VTYPE = {
    "ambulancia": TipoVeiculo.AMBULANCIA,
    "bombeiro": TipoVeiculo.BOMBEIRO,
    "policia": TipoVeiculo.POLICIA,
}

VCLASS_EMERGENCIA = "emergency"

#: Parâmetro SUMO (`<param key=... value=.../>` do `<vehicle>`) que diz que o VE
#: **está em serviço** e com qual criticidade (P20). O `vClass` diz que o veículo
#: é de emergência; este parâmetro, que ele atende uma ocorrência. Sem ele, o
#: veículo não chega ao motor — é o equivalente simulado da tag reconhecida sem
#: ocorrência aberta. Quem o escreve é `sim/demanda/gerar_rotas.py`.
PARAMETRO_CRITICIDADE = "criticidade"

#: Prefixo que o SUMO dá às vias internas de um cruzamento (`:cruzamento_0`).
#: Um VE nelas está **dentro** do cruzamento — ver `_posicao_na_via`.
PREFIXO_VIA_INTERNA = ":"


@dataclass
class AdaptadorSumo:
    """Ponte entre o simulador e o motor de decisão.

    Attributes:
        cliente: Conexão com o SUMO (`traci` ou `libsumo`).
        malha: Topologia e programas semafóricos já traduzidos.
        parametros: Parâmetros do algoritmo.
        controlar: Se o adaptador conduz a sinalização. `False` no modo `FIXO`.
        avisos: Problemas não fatais encontrados durante a execução.
        recusas: Contagem de comandos recusados pela máquina de estados, por
            (tipo, motivo). **Recusa não é erro**: o motor reafirma a intenção a
            cada passo e a máquina recusa enquanto a transição anterior não
            termina, como o firmware respondia `NAK,<cmd>,MODO` até 2026-10-05,
            quando ainda recebia comandos (decisão P13, defesa em
            profundidade). Contar em vez de alertar é o
            que separa o ruído esperado do sinal: um `FASE_INVALIDA` aqui, sim,
            indicaria mapa de fases errado.
    """

    cliente: ClienteSumo
    malha: MalhaSumo
    parametros: Parametros
    controlar: bool = True
    avisos: list[str] = field(default_factory=list)
    recusas: Counter[tuple[str, str]] = field(default_factory=Counter)

    _controladores: dict[str, EstadoControlador] = field(default_factory=dict, repr=False)
    _estado_aplicado: dict[str, str] = field(default_factory=dict, repr=False)
    _tipos_ve: dict[str, TipoVeiculo] = field(default_factory=dict, repr=False)
    _criticidades_ve: dict[str, Criticidade] = field(default_factory=dict, repr=False)
    _rotas_ve: dict[str, tuple[str, ...]] = field(default_factory=dict, repr=False)
    _fase_observada: dict[str, int] = field(default_factory=dict, repr=False)

    # -- ciclo de vida -------------------------------------------------------

    def iniciar(self, comando: Sequence[str]) -> None:
        """Sobe o SUMO, assina o que será lido a cada passo e alinha os semáforos."""
        self.cliente.iniciar(comando)
        self._assinar()
        self._preparar_semaforos()

    def fechar(self) -> None:
        """Encerra a conexão."""
        self.cliente.fechar()

    def _assinar(self) -> None:
        """Assina detectores e semáforos, tolerando detector ausente.

        Uma execução pode não carregar o `.add.xml` — é o caso do cenário curto
        de teste. Faltar detector não é motivo para derrubar a simulação, mas
        também não pode passar em silêncio: sem os E2 as filas chegam ao motor
        como zero, e E7 compensaria um cruzamento que ele acredita estar vazio.
        Daí o aviso.
        """
        tc = constantes()
        existentes = set(self.cliente.detector_fila.getIDList())
        esperados = {
            f"E2_{faixa}" for faixas in self.malha.faixas_do_acesso.values() for faixa in faixas
        }

        for detector in sorted(esperados & existentes):
            self.cliente.detector_fila.subscribe(detector, [tc.LAST_STEP_VEHICLE_HALTING_NUMBER])

        if faltando := esperados - existentes:
            self.avisos.append(
                f"{len(faltando)} de {len(esperados)} detectores E2 ausentes na execução — "
                "as filas chegarão ao motor como zero e E7 não terá o que compensar"
            )

        if not self.controlar:
            for id_semaforo in self.malha.semaforos:
                self.cliente.semaforo.subscribe(id_semaforo, [tc.TL_CURRENT_PHASE])

    def _preparar_semaforos(self) -> None:
        """Alinha a máquina de estados com o que o SUMO está exibindo em t=0.

        Nos modos com preempção o adaptador impõe o estado inicial ao SUMO; no
        modo `FIXO` ele apenas registra o que encontrou. Nos dois casos os oito
        cruzamentos partem da fase 1 em verde, com offset zero — é o mesmo ponto
        de partida do `.tll.xml`, e é o que faz os braços serem comparáveis desde
        o primeiro segundo.
        """
        for id_semaforo in self.malha.semaforos:
            cruzamento = self.malha.topologia.cruzamento(id_semaforo)
            estado = estado_inicial(id_semaforo, cruzamento, t=0.0)
            self._controladores[id_semaforo] = estado
            if self.controlar:
                self._empurrar(id_semaforo, estado)
            else:
                self._fase_observada[id_semaforo] = self.malha.programas[id_semaforo].indices[
                    (estado.fase_corrente, Sinal.VERDE)
                ]

    # -- leitura do mundo ----------------------------------------------------

    def passo(self) -> float:
        """Avança um passo e devolve o instante da simulação, em segundos."""
        self.cliente.passo()
        return self.cliente.tempo()

    def ler_estado(self, t: float) -> EstadoMalha:
        """Monta o `EstadoMalha` deste instante.

        `densidade_por_via` fica vazia de propósito: nenhuma etapa de E1 a E8 a
        consulta, e preenchê-la custaria 44 chamadas por passo para alimentar um
        campo que ninguém lê. Quando o dashboard precisar (Bloco 6), ela vem dos
        detectores E1, que já estão na rede.
        """
        filas = self._filas_por_acesso()
        semaforos = {
            id_semaforo: self._estado_semaforo(id_semaforo, t, filas)
            for id_semaforo in self.malha.semaforos
        }
        return EstadoMalha(
            t=t,
            semaforos=semaforos,
            veiculos_emergencia=self._veiculos_de_emergencia(),
        )

    def _filas_por_acesso(self) -> dict[str, int]:
        """Fila parada em cada via de aproximação, somando as faixas."""
        tc = constantes()
        resultados = self.cliente.detector_fila.getAllSubscriptionResults()
        filas: dict[str, int] = {}
        for acesso, faixas in self.malha.faixas_do_acesso.items():
            filas[acesso] = sum(
                int(resultados.get(f"E2_{faixa}", {}).get(tc.LAST_STEP_VEHICLE_HALTING_NUMBER, 0))
                for faixa in faixas
            )
        return filas

    def _estado_semaforo(
        self, id_semaforo: str, t: float, filas: Mapping[str, int]
    ) -> EstadoSemaforo:
        controlador = self._controladores[id_semaforo]
        acessos = [via for vias in self.malha.acessos[id_semaforo].values() for via in vias]
        return EstadoSemaforo(
            id=id_semaforo,
            fase_atual=controlador.fase_corrente,
            tempo_na_fase=max(t - controlador.t_mudanca, 0.0),
            fila_por_acesso={via: filas.get(via, 0) for via in acessos},
            em_preempcao=controlador.em_preempcao,
            sinal=controlador.sinal,
        )

    def _veiculos_de_emergencia(self) -> tuple[VeiculoEmergencia, ...]:
        """VEs ativos, a partir das assinaturas."""
        tc = constantes()
        self._acompanhar_entradas_e_saidas()
        resultados = self.cliente.veiculo.getAllSubscriptionResults()

        veiculos: list[VeiculoEmergencia] = []
        for identificador, dados in resultados.items():
            rota = self._rotas_ve.get(identificador)
            if rota is None:
                continue
            indice = int(dados[tc.VAR_ROUTE_INDEX])
            veiculos.append(
                VeiculoEmergencia(
                    id=identificador,
                    tipo=self._tipos_ve[identificador],
                    criticidade=self._criticidades_ve[identificador],
                    posicao=tuple(dados[tc.VAR_POSITION]),  # type: ignore[arg-type]
                    velocidade=float(dados[tc.VAR_SPEED]),
                    rota=rota,
                    indice_via_atual=indice,
                    posicao_na_via_m=self._posicao_na_via(
                        rota, indice, str(dados[tc.VAR_ROAD_ID]), float(dados[tc.VAR_LANEPOSITION])
                    ),
                )
            )
        return tuple(veiculos)

    def _posicao_na_via(
        self, rota: tuple[str, ...], indice: int, via_do_sumo: str, posicao_na_faixa_m: float
    ) -> float:
        """Posição ao longo da via da rota, corrigida dentro do cruzamento.

        **Por que não basta ler `VAR_LANEPOSITION`.** Enquanto o veículo
        atravessa a área interna de um cruzamento, o SUMO o coloca numa faixa
        interna, cujo identificador começa por `:`. Nesse trecho `VAR_ROUTE_INDEX`
        ainda aponta para a via que ele **acabou de deixar**, e
        `VAR_LANEPOSITION` já é medida na faixa interna, recomeçando do zero.
        Combinar os dois campos crus posiciona o VE no **começo da via anterior**
        — quase um quarteirão atrás de onde ele está.

        O efeito foi medido na entrega 10.1: a distância do VE ao cruzamento
        seguinte saltava de 486 m para 492 m e o ETA de 32 s para 63 s, por cerca
        de um segundo a cada travessia, e a disputa com o outro VE **sumia** da
        visão do motor nesse intervalo. As 60 disputas do cenário
        `multiplas_emergencias` apareciam como 120 episódios, uma quebra por
        disputa, sem exceção.

        A correção trata o veículo como estando **no fim da via atual**, que é a
        linha de retenção do cruzamento que ele está atravessando. O erro
        residual é, no máximo, o comprimento da faixa interna (~13 m na malha), e
        é conservador na direção certa: o VE continua demandando o cruzamento até
        limpá-lo, que é o que E5 precisa para não soltar a preempção cedo demais.

        Args:
            rota: Vias da rota do VE.
            indice: Índice da via atual, como o SUMO o reporta.
            via_do_sumo: Identificador da via onde o SUMO diz que o VE está.
            posicao_na_faixa_m: Posição medida na faixa, em metros.

        Returns:
            A posição ao longo da via `rota[indice]`, em metros.
        """
        if not via_do_sumo.startswith(PREFIXO_VIA_INTERNA) or not 0 <= indice < len(rota):
            return posicao_na_faixa_m
        return self.malha.topologia.comprimento(rota[indice])

    def _acompanhar_entradas_e_saidas(self) -> None:
        """Assina os VEs que entraram e esquece os que saíram.

        Perguntar a classe de **todo** veículo a cada passo custaria milhares de
        chamadas por passo no cenário intenso. Perguntar só de quem acabou de
        entrar custa algumas por passo, e a resposta não muda depois.

        **Só o VE em serviço é acompanhado (P20).** Um veículo de `vClass`
        emergência sem o parâmetro `criticidade` é tratado como tráfego comum:
        não é assinado e nunca chega ao motor — a mesma regra da bancada, onde a
        tag reconhecida sem ocorrência aberta não preempta. Fica um aviso, para
        que um arquivo de rotas escrito à mão sem o parâmetro não passe em
        silêncio.
        """
        tc = constantes()
        for identificador in self.cliente.simulacao.getDepartedIDList():
            if self.cliente.veiculo.getVehicleClass(identificador) != VCLASS_EMERGENCIA:
                continue
            criticidade = self._criticidade_declarada(identificador)
            if criticidade is None:
                self.avisos.append(
                    f"VE {identificador!r} sem o parâmetro {PARAMETRO_CRITICIDADE!r}: "
                    "fora de serviço, tratado como tráfego comum (P20)"
                )
                continue
            self._criticidades_ve[identificador] = criticidade
            vtype = self.cliente.veiculo.getTypeID(identificador)
            tipo = TIPO_POR_VTYPE.get(vtype)
            if tipo is None:
                tipo = TipoVeiculo.AMBULANCIA
                self.avisos.append(
                    f"vType {vtype!r} tem vClass de emergência mas não está em "
                    f"TIPO_POR_VTYPE; tratado como AMBULANCIA (prioridade máxima)"
                )
            self._tipos_ve[identificador] = tipo
            self._rotas_ve[identificador] = tuple(self.cliente.veiculo.getRoute(identificador))
            self.cliente.veiculo.subscribe(
                identificador,
                [
                    tc.VAR_POSITION,
                    tc.VAR_SPEED,
                    tc.VAR_LANEPOSITION,
                    tc.VAR_ROUTE_INDEX,
                    tc.VAR_ROAD_ID,
                ],
            )

        for identificador in self.cliente.simulacao.getArrivedIDList():
            self._tipos_ve.pop(identificador, None)
            self._criticidades_ve.pop(identificador, None)
            self._rotas_ve.pop(identificador, None)

    def _criticidade_declarada(self, identificador: str) -> Criticidade | None:
        """Criticidade da ocorrência do VE, lida do parâmetro da rota (P20).

        Returns:
            A criticidade, ou `None` se o VE não declara ocorrência.

        Raises:
            ValueError: se o parâmetro existir com valor fora da escala. Valor
                inválido é erro de configuração, e não pode virar "fora de
                serviço" em silêncio.
        """
        valor = str(self.cliente.veiculo.getParameter(identificador, PARAMETRO_CRITICIDADE))
        if not valor:
            return None
        try:
            return Criticidade(int(valor))
        except ValueError as erro:
            raise ValueError(
                f"VE {identificador!r}: {PARAMETRO_CRITICIDADE}={valor!r} fora da escala "
                f"{[int(nivel) for nivel in Criticidade]}"
            ) from erro

    # -- escrita no mundo ----------------------------------------------------

    def aplicar(self, comandos: Iterable[Comando], t: float) -> tuple[Transicao, ...]:
        """Aplica os comandos do motor e devolve as transições ocorridas.

        Args:
            comandos: O que o motor decidiu neste passo.
            t: Instante da simulação, em segundos.

        Returns:
            As transições de sinalização deste passo — a matéria-prima de
            `estado_semaforo_amostra` (decisão P5) e da verificação de I2/I3/I4.
        """
        if not self.controlar:
            return self.observar(t)

        por_semaforo: dict[str, list[Comando]] = {}
        for comando in comandos:
            por_semaforo.setdefault(comando.id_semaforo, []).append(comando)

        transicoes: list[Transicao] = []
        for id_semaforo, controlador in list(self._controladores.items()):
            avanco: Avanco = avancar(
                controlador,
                t,
                self.malha.topologia.cruzamento(id_semaforo),
                self.parametros,
                tuple(por_semaforo.get(id_semaforo, ())),
            )
            self._controladores[id_semaforo] = avanco.estado
            transicoes.extend(avanco.transicoes)
            for recusa in avanco.recusas:
                self.recusas[(str(recusa.comando.tipo), recusa.motivo)] += 1
            if avanco.transicoes:
                self._empurrar(id_semaforo, avanco.estado)

        return tuple(transicoes)

    def observar(self, t: float) -> tuple[Transicao, ...]:
        """Modo `FIXO`: lê a fase que o SUMO está exibindo e registra a mudança.

        Nada é escrito no simulador aqui — o baseline roda o programa estático do
        `.tll.xml` sem intervenção nenhuma, que é o que torna a comparação
        legítima.
        """
        tc = constantes()
        resultados = self.cliente.semaforo.getAllSubscriptionResults()
        transicoes: list[Transicao] = []

        for id_semaforo in self.malha.semaforos:
            atual = resultados.get(id_semaforo, {}).get(tc.TL_CURRENT_PHASE)
            if atual is None or atual == self._fase_observada.get(id_semaforo):
                continue

            programa = self.malha.programas[id_semaforo]
            fase, sinal = programa.fase_e_sinal(int(atual))
            anterior = self._controladores[id_semaforo]
            transicoes.append(
                Transicao(
                    id_semaforo=id_semaforo,
                    t=t,
                    fase=fase,
                    sinal=sinal,
                    fase_anterior=anterior.fase_corrente,
                    duracao_fase_anterior_s=max(t - anterior.t_mudanca, 0.0),
                    em_preempcao=False,
                )
            )
            ultimo_verde = dict(anterior.t_ultimo_verde)
            if sinal is Sinal.VERDE:
                ultimo_verde[fase] = t
            self._controladores[id_semaforo] = EstadoControlador(
                id_semaforo=id_semaforo,
                fase_corrente=fase,
                sinal=sinal,
                t_mudanca=t,
                t_ultimo_verde=ultimo_verde,
            )
            self._fase_observada[id_semaforo] = int(atual)

        return tuple(transicoes)

    def _empurrar(self, id_semaforo: str, estado: EstadoControlador) -> None:
        """Escreve no SUMO a *state string* do estado atual, se ela mudou."""
        alvo = self.malha.programas[id_semaforo].estado(estado.fase_corrente, estado.sinal)
        if self._estado_aplicado.get(id_semaforo) == alvo:
            return
        self.cliente.semaforo.setRedYellowGreenState(id_semaforo, alvo)
        self._estado_aplicado[id_semaforo] = alvo

    # -- consulta ------------------------------------------------------------

    def controlador(self, id_semaforo: str) -> EstadoControlador:
        """Estado interno do controlador de um cruzamento.

        É o que o verificador de invariantes recebe — e existe nos dois modos,
        para que o baseline seja auditado com o mesmo código.
        """
        return self._controladores[id_semaforo]

    def controladores(self) -> Mapping[str, EstadoControlador]:
        """Estado de todos os cruzamentos."""
        return dict(self._controladores)

    def colisoes(self) -> int:
        """Colisões ocorridas neste passo (`context/04` §9.4)."""
        return int(self.cliente.simulacao.getCollidingVehiclesNumber())

    def teleportes(self) -> int:
        """Veículos teleportados neste passo — deve ser sempre zero."""
        return int(self.cliente.simulacao.getStartingTeleportNumber())

    def estatisticas_do_passo(self) -> dict[str, Any]:
        """Números do passo que interessam à validação da execução."""
        return {
            "colisoes": self.colisoes(),
            "teleportes": self.teleportes(),
            "veiculos": int(self.cliente.veiculo.getIDCount()),
        }
