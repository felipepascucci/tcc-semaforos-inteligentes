"""O adaptador TraCI num cenário curto — `context/06` §1 (integração `sim/`).

Marcado `sumo`. Usa `sim/config/teste_60s.sumocfg`: 60 s, 1 VE, 2 cruzamentos.
Roda em segundos, que é o requisito para estar numa suíte de testes — a execução
de 3.600 s fica para o experimento.

O que se prova aqui é o contrato do adaptador, e não o desempenho do algoritmo:
que o estado lido do SUMO é um `EstadoMalha` válido, que os comandos do motor
viram sinalização de verdade, que as transições emitidas respeitam I2/I3/I4 e
que o modo `FIXO` não escreve nada no simulador.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.sumo

RAIZ = Path(__file__).resolve().parents[2]
CONFIGURACAO = RAIZ / "sim" / "config" / "teste_60s.sumocfg"
DURACAO_S = 60.0


@pytest.fixture(scope="module", autouse=True)
def rede_construida() -> None:
    from sim.rede import construir

    if not (RAIZ / "sim" / "rede" / "malha.net.xml").is_file():
        construir.construir()


def _comando(area: Path) -> list[str]:
    """Comando do SUMO com os detectores copiados para `area`.

    A cópia é o mesmo rodeio que o executor faz, e pela mesma razão: o SUMO
    resolve o `file` de cada detector relativo a quem o declara, então a saída
    cai em `area` e não suja o repositório. Sem detectores, as filas chegariam
    ao motor como zero e o teste passaria por um caminho degenerado.
    """
    from sim.ambiente import executavel
    from sim.controlador.executor import _detectores_da_execucao

    return [
        executavel("sumo"),
        "-c",
        str(CONFIGURACAO),
        "--additional-files",
        str(_detectores_da_execucao(area)),
        "--seed",
        "1",
    ]


def _rodar(controlar: bool, area: Path):  # tipos vêm de módulos sob demanda
    """Roda os 60 s e devolve (adaptador, transições, comandos, estados, verificador)."""
    from adapters.configuracao import carregar
    from adapters.sumo import topologia as topologia_sumo
    from adapters.sumo.adaptador import AdaptadorSumo
    from adapters.sumo.cliente import abrir_cliente
    from core.priorizacao.motor import MotorDecisao
    from core.seguranca import VerificadorSeguranca

    parametros = carregar("simulacao")
    malha = topologia_sumo.carregar()
    adaptador = AdaptadorSumo(
        cliente=abrir_cliente(), malha=malha, parametros=parametros, controlar=controlar
    )
    motor = MotorDecisao(parametros=parametros, topologia=malha.topologia)
    verificador = VerificadorSeguranca(parametros=parametros)

    transicoes: list = []
    comandos: list = []
    estados: list = []

    adaptador.iniciar(_comando(area))
    try:
        while adaptador.cliente.tempo() < DURACAO_S:
            t = adaptador.passo()
            estado = adaptador.ler_estado(t)
            estados.append(estado)
            do_passo = motor.avaliar(estado) if controlar else []
            comandos += do_passo
            novas = adaptador.aplicar(do_passo, t)
            transicoes += novas
            for id_semaforo, controlador in adaptador.controladores().items():
                verificador.verificar(
                    controlador,
                    malha.topologia.cruzamento(id_semaforo),
                    t,
                    [tr for tr in novas if tr.id_semaforo == id_semaforo],
                )
    finally:
        adaptador.fechar()

    return adaptador, transicoes, comandos, estados, verificador


# ---------------------------------------------------------------------------
# Leitura do mundo
# ---------------------------------------------------------------------------


def test_estado_lido_descreve_a_malha_inteira(tmp_path: Path) -> None:
    """`EstadoMalha` é a única entrada do motor: precisa vir completo."""
    _, _, _, estados, _ = _rodar(controlar=True, area=tmp_path)
    ultimo = estados[-1]

    assert len(ultimo.semaforos) == 8
    assert all(semaforo.fila_por_acesso for semaforo in ultimo.semaforos.values())
    assert all(
        set(semaforo.fila_por_acesso) == {via for via in semaforo.fila_por_acesso}
        for semaforo in ultimo.semaforos.values()
    )


def test_ve_e_detectado_pela_classe_e_nao_pelo_nome(tmp_path: Path) -> None:
    """`vClass="emergency"` é o que identifica o VE — não uma convenção de id."""
    _, _, _, estados, _ = _rodar(controlar=True, area=tmp_path)

    com_ve = [estado for estado in estados if estado.veiculos_emergencia]
    assert com_ve, "a ambulância do cenário de teste não foi detectada"

    veiculo = com_ve[0].veiculos_emergencia[0]
    assert veiculo.tipo.value == "AMBULANCIA"
    assert veiculo.rota[0] == "A1_L0"
    assert veiculo.posicao_na_via_m >= 0.0


# ---------------------------------------------------------------------------
# Escrita no mundo
# ---------------------------------------------------------------------------


def test_preempcao_emite_comandos_e_gera_transicoes(tmp_path: Path) -> None:
    """O caminho completo: estado -> motor -> comando -> sinalização."""
    _, transicoes, comandos, _, _ = _rodar(controlar=True, area=tmp_path)

    assert comandos, "o motor não decidiu nada em 60 s com um VE na malha"
    assert transicoes
    assert any(transicao.em_preempcao for transicao in transicoes)


def test_invariantes_valem_no_modo_com_preempcao(tmp_path: Path) -> None:
    """I1 a I5 verificados a cada passo, contra o SUMO de verdade."""
    _, _, _, _, verificador = _rodar(controlar=True, area=tmp_path)

    assert verificador.seguro, [str(violacao) for violacao in verificador.violacoes]


def test_modo_fixo_nao_preempta_nada(tmp_path: Path) -> None:
    """O baseline precisa ser genuinamente sem intervenção (context/04 §8)."""
    _, transicoes, comandos, _, verificador = _rodar(controlar=False, area=tmp_path)

    assert comandos == []
    assert transicoes, "sem transições não haveria como verificar I2/I3 no baseline"
    assert not any(transicao.em_preempcao for transicao in transicoes)
    assert verificador.seguro


def test_baseline_cumpre_o_ciclo_de_setenta_segundos(tmp_path: Path) -> None:
    """A sequência do `.tll.xml`: verde -> amarelo -> all-red -> próxima fase."""
    _, transicoes, _, _, _ = _rodar(controlar=False, area=tmp_path)

    de_um = [t for t in transicoes if t.id_semaforo == "CRUZ_01"]
    sinais = [t.sinal.value for t in de_um]

    assert sinais[:3] == ["AMARELO", "VERMELHO", "VERDE"]
    # O verde base dura 30 s — a primeira transição sai por volta disso.
    assert de_um[0].duracao_fase_anterior_s == pytest.approx(30.0, abs=0.2)
