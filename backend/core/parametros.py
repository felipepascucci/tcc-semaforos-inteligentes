"""Parâmetros do algoritmo — espelho tipado de `backend/config/parametros.yaml`.

Este módulo **não lê arquivo**: `core/` é puro, sem I/O (`context/01` §1). A
leitura do YAML acontece em `adapters/configuracao.py`, que chama
`Parametros.de_dicionario()`.

A regra que este arquivo existe para sustentar é a de `context/08` §4.3: se você
digitou um número no meio de uma função de decisão, ele está no lugar errado.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.excecoes import ConfiguracaoInvalidaError
from core.modelos import TipoVeiculo


@dataclass(frozen=True)
class Parametros:
    """Todo número mágico do algoritmo, em um lugar só.

    Attributes:
        raio_deteccao_m: Alcance da detecção ao longo da rota (E1, RF01).
        tempo_antecipacao_margem_s: Margem somada ao tempo de transição segura
            para definir a janela de ativação (E3).
        velocidade_min_estimativa_ms: Piso de velocidade no cálculo de ETA (E2).
            Sem ele, um VE parado produziria ETA infinito.
        verde_min_s: Piso de I4 — nenhum verde é truncado antes disso.
        verde_max_s: Teto de verde, inclusive sob preempção.
        amarelo_s: Duração do amarelo (I2).
        all_red_s: Duração do all-red entre fases (I3).
        preempcao_timeout_s: Tempo máximo de preempção sem liberação (E6).
        n_ciclos_compensacao: Ciclos de compensação pós-evento (E7).
        ganho_compensacao_k: Ganho `K` da fórmula de compensação (E7).
        prioridade_tipo: Ordem de precedência por tipo de VE (E8).
        vermelho_max_s: Teto de vermelho por acesso (I5, starvation).
        watchdog_s: Silêncio máximo do atuador antes do fail-safe (I6).
        latencia_decisao_p95_max_ms: Orçamento do RNF01.
        latencia_fim_a_fim_p95_max_ms: Orçamento de H3.
    """

    raio_deteccao_m: float
    tempo_antecipacao_margem_s: float
    velocidade_min_estimativa_ms: float
    verde_min_s: float
    verde_max_s: float
    amarelo_s: float
    all_red_s: float
    preempcao_timeout_s: float
    n_ciclos_compensacao: int
    ganho_compensacao_k: float
    prioridade_tipo: tuple[TipoVeiculo, ...]
    vermelho_max_s: float
    watchdog_s: float
    latencia_decisao_p95_max_ms: int = 100
    latencia_fim_a_fim_p95_max_ms: int = 200

    def __post_init__(self) -> None:
        self.validar()

    # -- construção ----------------------------------------------------------

    @classmethod
    def de_dicionario(cls, dados: Mapping[str, Any]) -> Parametros:
        """Constrói a partir do dicionário lido do YAML.

        Args:
            dados: Conteúdo de `parametros.yaml`, já mesclado com o perfil de
                hardware quando for o caso.

        Returns:
            Os parâmetros validados.

        Raises:
            ConfiguracaoInvalidaError: se faltar chave ou um valor for incoerente.
        """
        try:
            prioridade = tuple(TipoVeiculo(t) for t in dados["prioridade_tipo"])
        except KeyError as erro:
            raise ConfiguracaoInvalidaError("prioridade_tipo ausente") from erro
        except ValueError as erro:
            raise ConfiguracaoInvalidaError(f"tipo de veículo desconhecido: {erro}") from erro

        obrigatorios = (
            "raio_deteccao_m",
            "tempo_antecipacao_margem_s",
            "velocidade_min_estimativa_ms",
            "verde_min_s",
            "verde_max_s",
            "amarelo_s",
            "all_red_s",
            "preempcao_timeout_s",
            "n_ciclos_compensacao",
            "ganho_compensacao_k",
            "vermelho_max_s",
            "watchdog_s",
        )
        faltando = [chave for chave in obrigatorios if chave not in dados]
        if faltando:
            raise ConfiguracaoInvalidaError(f"parâmetros ausentes: {', '.join(faltando)}")

        return cls(
            raio_deteccao_m=float(dados["raio_deteccao_m"]),
            tempo_antecipacao_margem_s=float(dados["tempo_antecipacao_margem_s"]),
            velocidade_min_estimativa_ms=float(dados["velocidade_min_estimativa_ms"]),
            verde_min_s=float(dados["verde_min_s"]),
            verde_max_s=float(dados["verde_max_s"]),
            amarelo_s=float(dados["amarelo_s"]),
            all_red_s=float(dados["all_red_s"]),
            preempcao_timeout_s=float(dados["preempcao_timeout_s"]),
            n_ciclos_compensacao=int(dados["n_ciclos_compensacao"]),
            ganho_compensacao_k=float(dados["ganho_compensacao_k"]),
            prioridade_tipo=prioridade,
            vermelho_max_s=float(dados["vermelho_max_s"]),
            watchdog_s=float(dados["watchdog_s"]),
            latencia_decisao_p95_max_ms=int(dados.get("latencia_decisao_p95_max_ms", 100)),
            latencia_fim_a_fim_p95_max_ms=int(dados.get("latencia_fim_a_fim_p95_max_ms", 200)),
        )

    # -- validação -----------------------------------------------------------

    def validar(self) -> None:
        """Recusa combinações incoerentes.

        Falhar aqui é barato; falhar no meio de 600 execuções não é.

        Raises:
            ConfiguracaoInvalidaError: se algum valor for incoerente.
        """
        problemas: list[str] = []
        if self.verde_min_s > self.verde_max_s:
            problemas.append(
                f"verde_min_s ({self.verde_min_s}) maior que verde_max_s ({self.verde_max_s})"
            )
        if self.amarelo_s <= 0:
            problemas.append(
                "amarelo_s precisa ser > 0 — I2 exige amarelo real entre verde e vermelho"
            )
        if self.all_red_s < 0:
            problemas.append("all_red_s não pode ser negativo")
        if self.velocidade_min_estimativa_ms <= 0:
            problemas.append("velocidade_min_estimativa_ms precisa ser > 0 (divisor do ETA)")
        if self.raio_deteccao_m <= 0:
            problemas.append("raio_deteccao_m precisa ser > 0")
        if not self.prioridade_tipo:
            problemas.append("prioridade_tipo não pode ser vazia")
        if len(set(self.prioridade_tipo)) != len(self.prioridade_tipo):
            problemas.append("prioridade_tipo tem tipo repetido")
        if self.n_ciclos_compensacao < 0:
            problemas.append("n_ciclos_compensacao não pode ser negativo")
        if self.vermelho_max_s <= self.verde_max_s:
            problemas.append(
                f"vermelho_max_s ({self.vermelho_max_s}) precisa ser maior que "
                f"verde_max_s ({self.verde_max_s}), senão I5 é violável por construção"
            )
        if problemas:
            raise ConfiguracaoInvalidaError("; ".join(problemas))

    # -- derivados -----------------------------------------------------------

    @property
    def tempo_transicao_segura_s(self) -> float:
        """Duração da transição obrigatória verde → amarelo → all-red → alvo.

        No pior caso a transição ainda precisa esperar o verde mínimo residual;
        este valor é a parcela fixa (E5).
        """
        return self.amarelo_s + self.all_red_s

    def tempo_antecipacao_s(self, verde_min_residual_s: float = 0.0) -> float:
        """Janela de ativação de E3.

        `TEMPO_ANTECIPACAO = tempo_transicao_segura(tls) + MARGEM`. Preemptar
        cedo demais trava a transversal sem necessidade — que é exatamente o
        custo que H2 quer minimizar.

        Args:
            verde_min_residual_s: Verde mínimo ainda a cumprir no cruzamento.

        Returns:
            Antecedência, em segundos, com que a preempção deve começar.
        """
        return (
            self.tempo_transicao_segura_s + verde_min_residual_s + self.tempo_antecipacao_margem_s
        )

    def indice_prioridade(self, tipo: TipoVeiculo) -> int:
        """Posição do tipo na ordem de precedência — menor vence (E8)."""
        try:
            return self.prioridade_tipo.index(tipo)
        except ValueError:
            return len(self.prioridade_tipo)
