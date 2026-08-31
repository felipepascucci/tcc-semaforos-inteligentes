"""Contabilidade do relatório do piloto — `analysis/relatorio_piloto.py`.

O relatório é o que vai responder se H1 se sustenta, e o número que ele imprime
vira decisão de projeto. Então a conta precisa estar testada — sobretudo o
pareamento por VE, que é onde um viés entraria sem fazer barulho: se o baseline
perder o VE mais difícil por não ter chegado dentro do horizonte, a média dele
melhora sozinha e a redução medida **encolhe**. O erro seria conservador, e por
isso mesmo passaria despercebido.

Puro: lê listas em memória, não toca disco nem SUMO.
"""

from __future__ import annotations

from analysis import relatorio_piloto as relatorio


def _viagem(
    modo: str,
    identificador: str,
    tempo: float,
    *,
    cenario: str = "moderado",
    seed: int = 1,
    paradas: int = 0,
) -> relatorio.ViagemVE:
    return relatorio.ViagemVE(
        cenario=cenario,
        modo=modo,
        seed=seed,
        id_veiculo=identificador,
        tipo="ambulancia",
        tempo_viagem_s=tempo,
        paradas=paradas,
    )


def _execucao(
    modo: str, *, cenario: str = "moderado", seed: int = 1, **campos: object
) -> relatorio.Execucao:
    base: dict[str, object] = {
        "cenario": cenario,
        "modo": modo,
        "seed": seed,
        "versao_codigo": "abc1234",
        "duracao_s": 3600.0,
        "veiculos_planejados": 1000,
        "veiculos_completos": 980,
        "ves_completos": 5,
        "tempo_espera_medio_transversal_s": 10.0,
        "atraso_total_rede_s": 1000.0,
        "latencia_p95_ms": 0.05,
        "latencia_p99_ms": 0.08,
        "latencia_max_ms": 0.5,
        "colisoes": 0,
        "teleportes": 0,
        "violacoes": 0,
    }
    base.update(campos)
    return relatorio.Execucao(**base)  # type: ignore[arg-type]


# --- pareamento por VE ------------------------------------------------------


def test_pareamento_usa_so_os_ves_presentes_nos_tres_bracos() -> None:
    """O VE que não chegou no baseline sai dos **três** braços.

    Se ele ficasse só na preempção, a média do baseline melhoraria por exclusão
    do caso difícil, e a redução medida encolheria — um viés silencioso a favor
    do controle.
    """
    viagens = [
        _viagem("FIXO", "VE_0", 400.0),
        _viagem("FIXO", "VE_1", 500.0),
        _viagem("PREEMPCAO", "VE_0", 300.0),
        _viagem("PREEMPCAO", "VE_1", 320.0),
        _viagem("PREEMPCAO", "VE_2", 250.0),  # não chegou no FIXO
        _viagem("PREEMPCAO_COMPENSADA", "VE_0", 305.0),
        _viagem("PREEMPCAO_COMPENSADA", "VE_1", 325.0),
    ]
    (par,) = relatorio.parear(viagens)

    assert par.ves_comuns == 2
    assert par.ves_descartados == 1
    assert par.travessia_por_modo["FIXO"] == 450.0
    assert par.travessia_por_modo["PREEMPCAO"] == 310.0


def test_reducao_e_relativa_ao_baseline() -> None:
    viagens = [
        _viagem("FIXO", "VE_0", 400.0),
        _viagem("PREEMPCAO", "VE_0", 300.0),
        _viagem("PREEMPCAO_COMPENSADA", "VE_0", 320.0),
    ]
    (par,) = relatorio.parear(viagens)
    assert par.reducao("PREEMPCAO") == 0.25
    assert par.reducao("PREEMPCAO_COMPENSADA") == 0.2


def test_ponto_sem_ve_em_comum_nao_entra() -> None:
    viagens = [_viagem("FIXO", "VE_0", 400.0), _viagem("PREEMPCAO", "VE_9", 300.0)]
    assert relatorio.parear(viagens) == ()


def test_pontos_saem_ordenados_por_cenario_e_seed() -> None:
    viagens = [
        _viagem(modo, "VE_0", 100.0, cenario=cenario, seed=seed)
        for cenario, seed in (("moderado", 2), ("intenso", 1), ("moderado", 1))
        for modo in relatorio.MODOS
    ]
    pares = relatorio.parear(viagens)
    assert [(par.cenario, par.seed) for par in pares] == [
        ("intenso", 1),
        ("moderado", 1),
        ("moderado", 2),
    ]


# --- H1 ---------------------------------------------------------------------


def test_resumo_h1_media_as_reducoes_das_seeds() -> None:
    viagens = [
        _viagem("FIXO", "VE_0", 400.0, seed=1),
        _viagem("PREEMPCAO", "VE_0", 300.0, seed=1),  # -25%
        _viagem("PREEMPCAO_COMPENSADA", "VE_0", 300.0, seed=1),
        _viagem("FIXO", "VE_0", 400.0, seed=2),
        _viagem("PREEMPCAO", "VE_0", 340.0, seed=2),  # -15%
        _viagem("PREEMPCAO_COMPENSADA", "VE_0", 340.0, seed=2),
    ]
    (resumo,) = relatorio.resumir_h1(relatorio.parear(viagens))

    assert resumo.seeds == 2
    assert resumo.reducoes["PREEMPCAO"] == 0.20
    assert resumo.piores["PREEMPCAO"] == 0.15
    assert resumo.melhores["PREEMPCAO"] == 0.25


def test_meta_de_h1_so_vale_para_moderado_e_intenso() -> None:
    """Decisão P1: a meta é condicionada à saturação.

    O `leve` mede v/c 0,18 e é discutido sem meta numérica — a Tabela 1 do
    pré-projeto já mostrava 8,3% nesse regime. O piloto tem de responder pelos
    cenários certos, não pelo mais fácil.
    """
    viagens = [
        _viagem(modo, "VE_0", 400.0 if modo == "FIXO" else 300.0, cenario=cenario)
        for cenario in ("leve", "moderado", "intenso", "multiplas_emergencias")
        for modo in relatorio.MODOS
    ]
    com_meta = {
        resumo.cenario
        for resumo in relatorio.resumir_h1(relatorio.parear(viagens))
        if resumo.tem_meta
    }
    assert com_meta == {"moderado", "intenso"}


def test_atinge_meta_no_limiar_dos_25_por_cento() -> None:
    viagens = [
        _viagem("FIXO", "VE_0", 400.0),
        _viagem("PREEMPCAO", "VE_0", 300.0),
        _viagem("PREEMPCAO_COMPENSADA", "VE_0", 301.0),
    ]
    (resumo,) = relatorio.resumir_h1(relatorio.parear(viagens))
    assert resumo.atinge_meta("PREEMPCAO")
    assert not resumo.atinge_meta("PREEMPCAO_COMPENSADA")


# --- H2 ---------------------------------------------------------------------


def test_h2_separa_custo_de_mitigacao() -> None:
    """As duas leituras de "mitigar em até 15%" dão números diferentes.

    Sobre a espera transversal: (20 - 17) / 20 = 15%. Sobre o **acréscimo** que a
    preempção causou: (20 - 17) / (20 - 10) = 30%. Qual vale é ação de redação, e
    o relatório imprime as duas justamente para que a escolha seja consciente.
    """
    execucoes = [
        _execucao("FIXO", tempo_espera_medio_transversal_s=10.0),
        _execucao("PREEMPCAO", tempo_espera_medio_transversal_s=20.0),
        _execucao("PREEMPCAO_COMPENSADA", tempo_espera_medio_transversal_s=17.0),
    ]
    (resumo,) = relatorio.resumir_h2(execucoes)

    assert resumo.custo == 1.0
    assert resumo.mitigacao == 0.15
    assert resumo.mitigacao_do_acrescimo == 0.30


def test_h2_sem_braco_compensado_devolve_none() -> None:
    execucoes = [
        _execucao("FIXO", tempo_espera_medio_transversal_s=10.0),
        _execucao("PREEMPCAO", tempo_espera_medio_transversal_s=20.0),
    ]
    (resumo,) = relatorio.resumir_h2(execucoes)
    assert resumo.custo == 1.0
    assert resumo.mitigacao is None


# --- saúde da execução ------------------------------------------------------


def test_saude_soma_incidentes_e_reprova() -> None:
    execucoes = [_execucao("FIXO"), _execucao("PREEMPCAO", teleportes=2)]
    saude = relatorio.resumir_saude(execucoes)
    assert saude.teleportes == 2
    assert not saude.segura


def test_saude_reporta_o_pior_p95_e_nao_a_media() -> None:
    """Sistema crítico se avalia pela cauda (`context/04` §9.3)."""
    execucoes = [
        _execucao("PREEMPCAO", latencia_p95_ms=0.05),
        _execucao("PREEMPCAO", seed=2, latencia_p95_ms=120.0),
    ]
    saude = relatorio.resumir_saude(execucoes)
    assert saude.p95_maximo_ms == 120.0
    assert not saude.dentro_do_rnf01


def test_latencia_zero_do_baseline_nao_conta() -> None:
    """No modo `FIXO` o motor não é chamado, então não há latência a reportar."""
    execucoes = [
        _execucao("FIXO", latencia_p95_ms=0.0, latencia_p99_ms=0.0, latencia_max_ms=0.0),
        _execucao("PREEMPCAO", latencia_p95_ms=0.07),
    ]
    assert relatorio.resumir_saude(execucoes).p95_maximo_ms == 0.07


def test_escoamento_aponta_o_pior_ponto() -> None:
    execucoes = [
        _execucao("FIXO", veiculos_completos=980),
        _execucao("PREEMPCAO", cenario="intenso", seed=3, veiculos_completos=700),
    ]
    saude = relatorio.resumir_saude(execucoes)
    assert saude.escoamento_minimo == 0.7
    assert saude.escoamento_pior_ponto == "intenso/PREEMPCAO/seed=3"


# --- markdown ---------------------------------------------------------------


def test_markdown_responde_as_tres_perguntas_do_bloco_4() -> None:
    viagens = [
        _viagem(modo, "VE_0", 400.0 if modo == "FIXO" else 280.0, cenario=cenario)
        for cenario in ("moderado", "intenso")
        for modo in relatorio.MODOS
    ]
    execucoes = [
        _execucao(modo, cenario=cenario)
        for cenario in ("moderado", "intenso")
        for modo in relatorio.MODOS
    ]
    texto = relatorio.gerar_markdown(execucoes, relatorio.parear(viagens), [], planejadas=6)

    assert "Veredito do piloto" in texto
    assert "Há gridlock?" in texto
    assert "100 ms" in texto
    # 30% de redução com meta de 25%: o veredito precisa sair positivo.
    assert "chega aos 25% de H1?** **sim**" in texto


def test_pendencias_aparecem_quando_h1_fica_abaixo_da_meta() -> None:
    """A seção que diz o que decidir é calculada, não escrita.

    Uma seção que só existisse quando alguém se lembrasse de escrevê-la não
    cumpriria o papel do Bloco 4, que é forçar a correção agora e não na última
    semana.
    """
    viagens = [
        _viagem(modo, "VE_0", 400.0 if modo == "FIXO" else 360.0, cenario="intenso")
        for modo in relatorio.MODOS
    ]
    execucoes = [_execucao(modo, cenario="intenso") for modo in relatorio.MODOS]
    texto = relatorio.gerar_markdown(execucoes, relatorio.parear(viagens), [], planejadas=3)

    assert "O que este piloto obriga a decidir" in texto
    assert "H1 não se sustenta em `intenso`" in texto


def test_pendencias_somem_quando_tudo_passa() -> None:
    viagens = [
        _viagem(modo, "VE_0", 400.0 if modo == "FIXO" else 280.0, cenario=cenario)
        for cenario in ("moderado", "intenso")
        for modo in relatorio.MODOS
    ]
    espera = {"FIXO": 10.0, "PREEMPCAO": 20.0, "PREEMPCAO_COMPENSADA": 15.0}
    execucoes = [
        _execucao(modo, cenario=cenario, tempo_espera_medio_transversal_s=espera[modo])
        for cenario in ("moderado", "intenso")
        for modo in relatorio.MODOS
    ]
    texto = relatorio.gerar_markdown(execucoes, relatorio.parear(viagens), [], planejadas=6)

    assert "O que este piloto obriga a decidir" not in texto


def test_pendencia_de_e7_aparece_quando_a_mitigacao_fica_abaixo_de_15() -> None:
    viagens = [
        _viagem(modo, "VE_0", 400.0 if modo == "FIXO" else 280.0, cenario="moderado")
        for modo in relatorio.MODOS
    ]
    espera = {"FIXO": 10.0, "PREEMPCAO": 20.0, "PREEMPCAO_COMPENSADA": 19.9}
    execucoes = [
        _execucao(modo, tempo_espera_medio_transversal_s=espera[modo]) for modo in relatorio.MODOS
    ]
    texto = relatorio.gerar_markdown(execucoes, relatorio.parear(viagens), [], planejadas=3)

    assert "E7 não entrega a mitigação de H2" in texto
