"""Cliente do simulador: `traci` no desenvolvimento, `libsumo` no lote.

O `context/02` §2 define a estratégia: `traci` com `sumo-gui` para desenvolver e
gravar a demonstração; `libsumo` nas execuções em lote, por ser ~10x mais rápido
(roda no mesmo processo, sem socket) ao custo de não ter GUI nem múltiplos
clientes. Esta camada existe para que a escolha seja uma flag na linha de comando
e não uma segunda implementação do controlador.

As duas bibliotecas expõem a **mesma** API de módulo (`simulationStep`,
`trafficlight.setRedYellowGreenState`, ...), então o embrulho é fino de
propósito: ele cuida do ciclo de vida e das poucas diferenças reais, e deixa o
adaptador falar diretamente com os subdomínios.

Nenhuma das duas vem do pip: ambas são importadas de `%SUMO_HOME%/tools`, para
que o cliente Python seja exatamente o da versão do binário instalado (decisão
registrada em `context/09`).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


class ClienteIndisponivelError(RuntimeError):
    """O cliente pedido não pôde ser carregado."""


@dataclass
class ClienteSumo:
    """Conexão com uma instância do SUMO.

    Attributes:
        modulo: O módulo `traci` ou `libsumo` já importado.
        usa_libsumo: Se está rodando em processo, sem socket.
        gui: Se a instância é `sumo-gui`.
    """

    modulo: Any
    usa_libsumo: bool
    gui: bool = False
    _aberto: bool = field(default=False, init=False, repr=False)

    # -- ciclo de vida -------------------------------------------------------

    def iniciar(self, comando: Sequence[str]) -> None:
        """Sobe o SUMO com o comando dado e conecta.

        Raises:
            ClienteIndisponivelError: se já houver conexão aberta neste cliente.
        """
        if self._aberto:
            raise ClienteIndisponivelError("cliente já está conectado")
        self.modulo.start(list(comando))
        self._aberto = True

    def passo(self) -> None:
        """Avança um passo de simulação."""
        self.modulo.simulationStep()

    def tempo(self) -> float:
        """Instante atual da simulação, em segundos."""
        return float(self.modulo.simulation.getTime())

    def veiculos_restantes(self) -> int:
        """Veículos ainda na malha ou por inserir."""
        return int(self.modulo.simulation.getMinExpectedNumber())

    def fechar(self) -> None:
        """Encerra a simulação, se estiver aberta."""
        if not self._aberto:
            return
        try:
            self.modulo.close()
        finally:
            self._aberto = False

    def __enter__(self) -> ClienteSumo:
        return self

    def __exit__(self, *_: object) -> None:
        self.fechar()

    # -- atalhos usados pelo adaptador ---------------------------------------

    @property
    def semaforo(self) -> Any:
        """Subdomínio `trafficlight`."""
        return self.modulo.trafficlight

    @property
    def veiculo(self) -> Any:
        """Subdomínio `vehicle`."""
        return self.modulo.vehicle

    @property
    def detector_fila(self) -> Any:
        """Subdomínio `lanearea` — os detectores E2."""
        return self.modulo.lanearea

    @property
    def simulacao(self) -> Any:
        """Subdomínio `simulation`."""
        return self.modulo.simulation


def abrir_cliente(*, gui: bool = False, usar_libsumo: bool = False) -> ClienteSumo:
    """Carrega `traci` ou `libsumo` e devolve o cliente correspondente.

    Args:
        gui: Se a execução usará `sumo-gui`.
        usar_libsumo: Se deve usar `libsumo` (lote headless).

    Returns:
        O cliente, ainda sem conexão aberta.

    Raises:
        ClienteIndisponivelError: se pedir GUI com `libsumo`, que não a suporta,
            ou se a biblioteca não puder ser importada.
    """
    if gui and usar_libsumo:
        raise ClienteIndisponivelError(
            "libsumo não suporta GUI — use traci (sem --libsumo) para gravar a demonstração"
        )

    from sim.ambiente import registrar_ferramentas  # import local: evita ciclo de import

    registrar_ferramentas()

    if usar_libsumo:
        try:
            import libsumo  # import local: não vem do instalador Windows
        except ImportError as erro:  # pragma: no cover — depende da instalação
            raise ClienteIndisponivelError(
                "libsumo não está disponível para Python nesta instalação. O instalador "
                "Windows do SUMO traz os bindings Java/C#/C++ (libsumo-*.jar, "
                "libsumocpp.dll), mas NÃO o módulo Python — ele vem do pip, e a versão "
                "precisa ser a mesma do binário instalado "
                "(`pip install libsumo==<versão do sumo --version>`).\n"
                "Instalar é decisão de dependência e está registrada como pendência do "
                "Bloco 8 em context/09. Enquanto isso, rode sem --libsumo: o lote "
                "paraleliza com traci, cada processo com seu próprio SUMO."
            ) from erro
        return ClienteSumo(modulo=libsumo, usa_libsumo=True)

    try:
        import traci  # import local: depende de SUMO_HOME no sys.path
    except ImportError as erro:  # pragma: no cover — depende da instalação
        raise ClienteIndisponivelError(
            f"não consegui importar o cliente do SUMO: {erro}. "
            "Confira SUMO_HOME (README, seção SUMO)."
        ) from erro
    return ClienteSumo(modulo=traci, usa_libsumo=False, gui=gui)


def constantes() -> Any:
    """Módulo `traci.constants`, com os códigos de variável das assinaturas."""
    from sim.ambiente import registrar_ferramentas  # import local: evita ciclo de import

    registrar_ferramentas()
    import traci.constants as tc  # import local: depende de SUMO_HOME no sys.path

    return tc
