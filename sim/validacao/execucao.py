"""Verificação estrutural de uma execução — `context/06` §4.

    def validar_execucao(execucao) -> list[str]:
        \"\"\"Retorna lista de problemas. Vazia = execução válida.\"\"\"

Execução que falhe qualquer item é **descartada e reexecutada com a mesma
seed**, e o descarte é registrado. A regra existe para separar duas coisas que
se parecem de fora: descartar dado ruim segundo critério fixado *antes* é
metodologia; descartar dado que não agradou é o contrário disso.

O critério mora aqui, em código versionado, e não no julgamento de quem olha o
resultado. É puro de propósito — recebe o `ResultadoExecucao` já consolidado e
não toca em SUMO, banco ou disco, o que o torna testável na suíte padrão.
"""

from __future__ import annotations

from core.parametros import Parametros
from sim.controlador.coletor import ResultadoExecucao


def validar_execucao(
    resultado: ResultadoExecucao,
    parametros: Parametros,
    *,
    ves_planejados: int | None = None,
    completa: bool = True,
) -> list[str]:
    """Confere se uma execução pode entrar na análise.

    Args:
        resultado: A execução consolidada.
        parametros: Parâmetros do algoritmo, de onde vêm os orçamentos de
            latência.
        ves_planejados: Quantos VEs a execução deveria ter completado. `None`
            desliga a verificação.
        completa: Se a execução rodou a duração planejada. Numa execução
            deliberadamente curta (teste, diagnóstico) as verificações que
            dependem de tudo ter terminado são puladas.

    Returns:
        Lista de problemas. Vazia significa execução válida.
    """
    problemas: list[str] = []

    if resultado.colisoes:
        problemas.append(
            f"{resultado.colisoes} colisão(ões) — o trabalho afirma zero, e isso se verifica"
        )

    if resultado.teleportes:
        problemas.append(
            f"{resultado.teleportes} teleporte(s) — com --time-to-teleport -1 isso não deveria "
            "acontecer; indica gridlock, e gridlock invalida a execução (context/04 §12)"
        )

    if resultado.violacoes:
        contagem: dict[str, int] = {}
        for violacao in resultado.violacoes:
            contagem[violacao.invariante] = contagem.get(violacao.invariante, 0) + 1
        detalhe = ", ".join(f"{chave}={valor}" for chave, valor in sorted(contagem.items()))
        problemas.append(f"{len(resultado.violacoes)} violação(ões) de invariante ({detalhe})")

    # Latência: o número que vale é o percentil, nunca a média (context/04 §9.3).
    if resultado.latencias_ms:
        orcamento = float(parametros.latencia_decisao_p95_max_ms)
        if resultado.latencia_p95_ms > orcamento:
            problemas.append(
                f"p95 da latência de decisão {resultado.latencia_p95_ms:.1f} ms acima do "
                f"orçamento do RNF01 ({orcamento:.0f} ms)"
            )
        if resultado.latencia_p99_ms > orcamento * 2:
            problemas.append(
                f"p99 da latência de decisão {resultado.latencia_p99_ms:.1f} ms — cauda longa "
                f"demais para um sistema com requisito de {orcamento:.0f} ms"
            )

    if not completa:
        return problemas

    if ves_planejados is not None and len(resultado.viagens_ve) < ves_planejados:
        problemas.append(
            f"apenas {len(resultado.viagens_ve)} de {ves_planejados} VEs completaram a rota — "
            "um VE que não chega não entra na comparação pareada e enviesaria a média"
        )

    if resultado.veiculos_planejados and not resultado.veiculos_completos:
        problemas.append("nenhum veículo completou a rota — execução vazia")

    return problemas
