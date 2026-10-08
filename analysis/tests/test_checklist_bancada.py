"""Checklist da bancada pela telemetria gravada — `analysis/checklist_bancada.py`.

A telemetria daqui é a do dublê do UNO (`adapters/hardware/simulado.py`), o
modelo de referência do firmware, dirigido por tempo injetado e gravada pelo
gravador da própria ponte: testa a conta, não mede nada.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path

from adapters.hardware.simulado import Entrada, UnoSimulado, config_da_bancada
from analysis.checklist_bancada import (
    LISTA_VOLTA_MAX_S,
    LeituraEmissor,
    Resultado,
    _sem_nada_gravado,
    avaliar,
    item_15,
    ler_sessoes,
    main,
    trechos,
)
from bridge.latencia import COLUNAS_DESFECHOS
from bridge.protocolo import Autorizacao, Deteccao
from bridge.registro import Direcao, GravadorTelemetria
from core.modelos import TipoVeiculo

T0 = datetime(2026, 10, 7, 18, 0, tzinfo=UTC)
PASSO_S = 0.05
AMB, BOMB = TipoVeiculo.AMBULANCIA, TipoVeiculo.BOMBEIRO


class Ensaio:
    """Uma sessão da ponte contra o dublê: o que ele escreve e o que a ponte escreve nele."""

    def __init__(self, caminho: Path, sessao: datetime = T0) -> None:
        self.gravador = GravadorTelemetria(caminho, sessao=sessao, versao_codigo="teste")
        self.sessao = sessao
        self.t_s = 0.0
        self.uno = UnoSimulado(config_da_bancada(), 0.0)
        self._gravar(self.uno.avancar(0.0))

    def _gravar(self, linhas: list[bytes]) -> None:
        for linha in linhas:
            self.gravador.gravar(self._agora(), Direcao.UNO, linha)

    def _agora(self) -> datetime:
        return self.sessao + timedelta(seconds=self.t_s)

    def ate(self, t_s: float) -> None:
        """Deixa o tempo correr, em passos curtos: cada linha com o seu carimbo."""
        while self.t_s + PASSO_S <= t_s:
            self.t_s += PASSO_S
            self._gravar(self.uno.avancar(self.t_s))

    def esperar(self, duracao_s: float) -> None:
        self.ate(self.t_s + duracao_s)

    def escrever(self, linha: bytes) -> None:
        self.gravador.gravar(self._agora(), Direcao.PONTE, linha)
        self._gravar(self.uno.receber_bytes(linha, self.t_s, Entrada.USB))

    def central(self, **criticidades: int) -> None:
        for nome, criticidade in criticidades.items():
            self.escrever(Autorizacao(TipoVeiculo(nome), criticidade).codificar())

    def passagem(self, rua: int, veiculo: TipoVeiculo) -> None:
        """O receptor entregando a detecção pelo A0, como na bancada montada."""
        self._gravar(
            self.uno.receber_bytes(Deteccao(rua, veiculo).codificar(), self.t_s, Entrada.RECEPTOR)
        )


def _resultados(caminho: Path) -> dict[str, Resultado]:
    sessoes = ler_sessoes(caminho)
    assert len(sessoes) == 1
    return {r.item: r for r in avaliar(next(iter(sessoes.values())))}


def _roteiro_completo(caminho: Path) -> None:
    """Boot, 5 min de ciclo, 5b, prioridade pela criticidade e o teto."""
    ensaio = Ensaio(caminho)
    ensaio.ate(0.5)
    ensaio.central(AMBULANCIA=1, BOMBEIRO=0)
    ensaio.ate(310)
    # 5b: bombeiro sem ocorrência, e depois com ela.
    ensaio.passagem(1, BOMB)
    ensaio.esperar(5)
    ensaio.central(BOMBEIRO=2)
    ensaio.esperar(5)
    ensaio.passagem(1, BOMB)
    ensaio.esperar(25)
    # 10: o bombeiro (2) é interrompido pela ambulância (1).
    ensaio.passagem(1, BOMB)
    ensaio.esperar(7)
    ensaio.passagem(3, AMB)
    ensaio.esperar(40)
    # 11: a ambulância relendo a RUA4 a cada 4 s, até o teto.
    ensaio.passagem(4, AMB)
    for _ in range(7):
        ensaio.esperar(4)
        ensaio.passagem(4, AMB)
    ensaio.esperar(20)


def test_roteiro_completo_atende_o_que_o_dado_julga(tmp_path: Path) -> None:
    caminho = tmp_path / "telemetria.csv"
    _roteiro_completo(caminho)
    r = _resultados(caminho)

    for item in ("1", "2", "3", "5b", "10", "11", "15"):
        assert r[item].ok is True, (item, r[item].detalhes)
    # A sessão tem ~7 min, sem falha: não é o soak, e não há o que julgar.
    assert r["12"].ok is None
    assert "escreveu 100 0.50 s depois do BOOT, e a ST a trouxe inteira 0.50 s" in (
        " ".join(r["15"].detalhes)
    )
    assert any("BOMBEIRO (criticidade 2)" in d for d in r["10"].detalhes)


def test_relatorio_pela_linha_de_comando(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    caminho = tmp_path / "telemetria.csv"
    _roteiro_completo(caminho)
    saida = tmp_path / "checklist.md"

    assert main(["--telemetria", str(caminho), "--saida", str(saida)]) == 0

    texto = saida.read_text(encoding="utf-8")
    assert texto == capsys.readouterr().out
    assert f"## Sessão {T0.isoformat()}" in texto
    assert "| 11 | Teto de 30 s (EV,TIMEOUT) e volta pelo eixo oposto | **atende** |" in texto


def test_so_ciclo_nao_julga_a_emergencia(tmp_path: Path) -> None:
    caminho = tmp_path / "telemetria.csv"
    Ensaio(caminho).ate(6 * 60)
    r = _resultados(caminho)

    assert r["1"].ok is True
    assert r["3"].ok is None  # sem entrada e saída de emergência
    assert r["5b"].ok is None and r["10"].ok is None and r["11"].ok is None
    # Sem backend, a lista nunca chega: não há o que medir no 15.
    assert r["15"].ok is None


def test_sessao_curta_sem_falha_nao_julga_ciclo_nem_soak(tmp_path: Path) -> None:
    """A sessão de 20 s do item 15 não é evidência contra os itens 1 e 12."""
    caminho = tmp_path / "telemetria.csv"
    ensaio = Ensaio(caminho)
    ensaio.ate(0.2)
    ensaio.central(AMBULANCIA=2, BOMBEIRO=1, POLICIA=0)
    ensaio.ate(20)
    r = _resultados(caminho)

    assert r["1"].ok is None and r["12"].ok is None
    assert r["15"].ok is True
    assert "escreveu 210" in r["15"].detalhes[0]


def test_ciclo_fora_da_tolerancia_numa_sessao_curta_nao_atende(tmp_path: Path) -> None:
    caminho = tmp_path / "telemetria.csv"
    _gravar_a_mao(
        caminho,
        [
            (0.0, "EV,0,BOOT"),
            (0.0, "ST,0,RRRR,C,0,0,000"),
            (1.0, "ST,1000,GGRR,C,0,0,000"),
            (4.0, "ST,4000,YYRR,C,0,0,000"),
            (6.0, "ST,6000,RRRR,C,0,0,000"),
            (7.0, "ST,7000,RRGG,C,0,0,000"),
            (10.0, "ST,10000,RRYY,C,0,0,000"),
            (12.0, "ST,12000,RRRR,C,0,0,000"),
            (13.2, "ST,13200,GGRR,C,0,0,000"),  # ciclo de 12,2 s
        ],
    )
    assert _resultados(caminho)["1"].ok is False


def test_soak_de_30_min(tmp_path: Path) -> None:
    caminho = tmp_path / "telemetria.csv"
    Ensaio(caminho).ate(30 * 60 + 5)
    r = _resultados(caminho)

    assert r["12"].ok is True, r["12"].detalhes
    assert "Reinícios do UNO no meio da sessão: 0" in r["12"].detalhes


def test_reinicio_no_meio_derruba_o_soak(tmp_path: Path) -> None:
    caminho = tmp_path / "telemetria.csv"
    ensaio = Ensaio(caminho)
    ensaio.ate(16 * 60)
    # O UNO reinicia: o millis() volta a zero, com um BOOT novo.
    ensaio.uno = UnoSimulado(config_da_bancada(), ensaio.t_s)
    ensaio._gravar(ensaio.uno.avancar(ensaio.t_s))
    ensaio.esperar(15 * 60)
    r = _resultados(caminho)

    assert r["12"].ok is False
    assert "Reinícios do UNO no meio da sessão: 1" in r["12"].detalhes


def _gravar_a_mao(caminho: Path, linhas: list[tuple[float, str]]) -> None:
    gravador = GravadorTelemetria(caminho, sessao=T0, versao_codigo="teste")
    for t_s, linha in linhas:
        gravador.gravar(T0 + timedelta(seconds=t_s), Direcao.UNO, linha.encode("ascii"))


def test_verde_direto_para_vermelho_na_saida_da_emergencia_e_pego(tmp_path: Path) -> None:
    caminho = tmp_path / "telemetria.csv"
    _gravar_a_mao(
        caminho,
        [
            (0.0, "EV,0,BOOT"),
            (0.0, "ST,0,RRRR,C,0,0,000"),
            (1.0, "ST,1000,GGRR,C,0,0,100"),
            (2.0, "EV,2000,PREEMP_INI,3,AMBULANCIA"),
            (2.0, "ST,2000,GGRR,E,3,0,100"),
            (4.0, "ST,4000,YYRR,E,3,0,100"),
            (6.0, "ST,6000,RRRR,E,3,0,100"),
            (7.0, "ST,7000,RRGR,E,3,0,100"),
            (16.0, "EV,16000,PREEMP_FIM,3,AMBULANCIA"),
            (16.0, "ST,16000,RRRR,C,0,0,100"),  # sem amarelo
            (17.0, "ST,17000,GGRR,C,0,0,100"),
        ],
    )
    r = _resultados(caminho)

    assert r["3"].ok is False
    assert any("I2: S3 verde -> vermelho" in d for d in r["3"].detalhes)
    assert r["2"].ok is True


def test_verde_fora_da_aproximacao_do_ve_e_pego(tmp_path: Path) -> None:
    caminho = tmp_path / "telemetria.csv"
    _gravar_a_mao(
        caminho,
        [
            (0.0, "EV,0,BOOT"),
            (0.0, "ST,0,RRRR,C,0,0,000"),
            (1.0, "ST,1000,GGRR,C,0,0,100"),
            (4.0, "EV,4000,PREEMP_INI,3,AMBULANCIA"),
            (4.0, "ST,4000,YYRR,E,3,0,100"),
            (6.0, "ST,6000,RRRR,E,3,0,100"),
            (7.0, "ST,7000,RRRG,E,3,0,100"),  # a S4, não a S3
        ],
    )
    r = _resultados(caminho)

    assert r["2"].ok is False
    assert any("S4 abriu em 7000 ms com a rua ativa 3" in d for d in r["2"].detalhes)


def test_sessao_que_termina_em_emergencia(tmp_path: Path) -> None:
    caminho = tmp_path / "telemetria.csv"
    ensaio = Ensaio(caminho)
    ensaio.ate(0.5)
    ensaio.central(AMBULANCIA=1)
    ensaio.ate(20)
    ensaio.passagem(3, AMB)
    ensaio.esperar(8)
    r = _resultados(caminho)

    assert "encerrada no meio de uma emergência" in r["14"].detalhes[0]


def _item_15_com_a_central(caminho: Path, lista_no_boot: tuple[int, ...]) -> Resultado:
    linhas = next(iter(ler_sessoes(caminho).values()))
    consultas: list[datetime] = []

    def central(instante: datetime) -> tuple[int, ...]:
        consultas.append(instante)
        return lista_no_boot

    resultado = item_15(linhas, trechos(linhas), central)
    assert consultas == [T0]  # perguntou pela lista no instante do BOOT
    return resultado


def _lista_tardia(caminho: Path) -> None:
    ensaio = Ensaio(caminho)
    ensaio.ate(LISTA_VOLTA_MAX_S + 1)
    ensaio.central(AMBULANCIA=1)
    ensaio.esperar(2)


def test_lista_tardia_sem_o_banco_fica_sem_veredito_no_15(tmp_path: Path) -> None:
    """Sem o banco, "nada a reenviar" e "não voltou" são indistinguíveis (2026-10-08)."""
    caminho = tmp_path / "telemetria.csv"
    _lista_tardia(caminho)
    r = _resultados(caminho)

    assert r["15"].ok is None
    assert "--banco" in r["15"].detalhes[0]


def test_lista_da_central_que_nao_volta_em_2_s_nao_atende_o_15(tmp_path: Path) -> None:
    caminho = tmp_path / "telemetria.csv"
    _lista_tardia(caminho)
    r = _item_15_com_a_central(caminho, (1, 0, 0))

    assert r.ok is False
    assert "era 100" in r.detalhes[0]


def test_central_sem_ocorrencia_no_boot_nao_tem_o_que_reenviar(tmp_path: Path) -> None:
    """O caso das sessões do item 5 e dos três carrinhos: a ocorrência abre depois."""
    caminho = tmp_path / "telemetria.csv"
    _lista_tardia(caminho)
    r = _item_15_com_a_central(caminho, (0, 0, 0))

    assert r.ok is None
    assert "nada a reenviar" in r.detalhes[0]


def test_sem_nenhum_envio_e_central_com_lista_nao_atende_o_15(tmp_path: Path) -> None:
    caminho = tmp_path / "telemetria.csv"
    Ensaio(caminho).ate(30)
    r = _item_15_com_a_central(caminho, (0, 2, 0))

    assert r.ok is False
    assert "não escreveu" in r.detalhes[0]


def test_lista_que_volta_logo_nao_consulta_a_central(tmp_path: Path) -> None:
    caminho = tmp_path / "telemetria.csv"
    ensaio = Ensaio(caminho)
    ensaio.ate(0.5)
    ensaio.central(AMBULANCIA=1)
    ensaio.esperar(3)
    linhas = next(iter(ler_sessoes(caminho).values()))

    def central(instante: datetime) -> tuple[int, ...]:
        raise AssertionError("não devia consultar")

    assert item_15(linhas, trechos(linhas), central).ok is True


def test_lixo_de_boot_fica_de_fora_e_e_contado(tmp_path: Path) -> None:
    caminho = tmp_path / "telemetria.csv"
    gravador = GravadorTelemetria(caminho, sessao=T0, versao_codigo="teste")
    gravador.gravar(T0, Direcao.UNO, b"\xff\x00lixo\r\n")
    Ensaio(caminho).ate(30)
    linhas = ler_sessoes(caminho)[T0.isoformat()]

    assert linhas[0].texto == "\\xff\\x00lixo"
    assert linhas[0].resposta is None
    assert {r.item: r for r in avaliar(linhas)}["1"].detalhes[0].startswith("Arranque 1")


# ---------------------------------------------------------------------------
# Item 5: tag fora do mapa
# ---------------------------------------------------------------------------


def _leitura(t_s: float, rua: int = 1, uid: str = "F39BD606", desfecho: str = "PREEMP_INI"):  # type: ignore[no-untyped-def]
    return LeituraEmissor(T0 + timedelta(seconds=t_s), rua, uid, desfecho)


def _item_5(caminho: Path, leituras: list[LeituraEmissor]) -> Resultado:
    linhas = next(iter(ler_sessoes(caminho).values()))
    return {r.item: r for r in avaliar(linhas, leituras=leituras)}["5"]


def _sessao_do_item_5(caminho: Path, controle_s: float = 60.0) -> Ensaio:
    """Ambulância em ocorrência, a tag fora do mapa passando (sem rastro) e o controle."""
    ensaio = Ensaio(caminho)
    ensaio.ate(0.5)
    ensaio.central(AMBULANCIA=1)
    ensaio.ate(controle_s)
    # O controle na tag da RUA1: o emissor imprime e, seis passos depois, o UNO decide.
    ensaio.esperar(0.3)
    ensaio.passagem(1, AMB)
    ensaio.esperar(20)
    return ensaio


def test_item_5_janela_em_silencio_e_controle_que_preempta(tmp_path: Path) -> None:
    caminho = tmp_path / "telemetria.csv"
    _sessao_do_item_5(caminho)
    r = _item_5(caminho, [_leitura(60.0)])

    assert r.ok is True, r.detalhes
    assert "Eventos do UNO na janela: 0" in r.detalhes
    assert any(d.startswith("Ciclos puros inteiros na janela: 4") for d in r.detalhes)
    assert "Controle: F39BD606 (RUA1) → PREEMP_INI — ok" in r.detalhes


def test_item_5_uid_fora_do_mapa_no_emissor_nao_atende(tmp_path: Path) -> None:
    caminho = tmp_path / "telemetria.csv"
    _sessao_do_item_5(caminho)
    r = _item_5(caminho, [_leitura(30.0, uid="DEADBEEF"), _leitura(60.0)])

    assert r.ok is False
    assert "DEADBEEF" in r.detalhes[0]


def test_item_5_evento_na_janela_nao_atende(tmp_path: Path) -> None:
    """Uma detecção que chegou ao UNO sem o emissor imprimir é o envio que não podia haver."""
    caminho = tmp_path / "telemetria.csv"
    ensaio = Ensaio(caminho)
    ensaio.ate(0.5)
    ensaio.central(AMBULANCIA=1)
    ensaio.ate(30)
    ensaio.passagem(3, AMB)
    ensaio.ate(90)
    ensaio.passagem(1, AMB)
    ensaio.esperar(5)
    r = _item_5(caminho, [_leitura(89.9)])

    assert r.ok is False
    assert any(
        d.startswith("Eventos do UNO na janela: ") and "PREEMP_INI,3" in d for d in r.detalhes
    )


def test_item_5_controle_que_nao_chega_ao_uno_nao_atende(tmp_path: Path) -> None:
    caminho = tmp_path / "telemetria.csv"
    ensaio = Ensaio(caminho)
    ensaio.ate(0.5)
    ensaio.central(AMBULANCIA=1)
    ensaio.ate(60)
    r = _item_5(caminho, [_leitura(50.0, desfecho="SEM_DECISAO")])

    assert r.ok is False
    assert any(d.endswith("SEM_DECISAO — FALHA") for d in r.detalhes)


def test_item_5_sem_ocorrencia_sem_controle_ou_janela_curta_nao_julga(tmp_path: Path) -> None:
    sem_ocorrencia = tmp_path / "a.csv"
    Ensaio(sem_ocorrencia).ate(60)
    assert _item_5(sem_ocorrencia, [_leitura(50.0)]).ok is None

    sem_controle = tmp_path / "b.csv"
    _sessao_do_item_5(sem_controle)
    assert _item_5(sem_controle, []).ok is None

    curta = tmp_path / "c.csv"
    _sessao_do_item_5(curta, controle_s=8.0)
    r = _item_5(curta, [_leitura(8.0)])
    assert r.ok is None
    assert "Ciclos puros inteiros na janela: 0" in r.detalhes


def test_item_5_so_entra_com_a_opcao(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    caminho = tmp_path / "telemetria.csv"
    _sessao_do_item_5(caminho)
    deteccoes = tmp_path / "deteccoes.csv"
    with deteccoes.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(COLUNAS_DESFECHOS)
        t = (T0 + timedelta(seconds=60)).isoformat()
        escritor.writerow(
            [
                T0.isoformat(),
                t,
                1,
                "F39BD606",
                "PREEMP_INI",
                t,
                "25.0",
                "AMBULANCIA",
                60300,
                "teste",
            ]
        )
        # Outra sessão no mesmo arquivo não entra na conta.
        escritor.writerow(
            ["2026-10-07T16:18:08+00:00", t, 2, "DEADBEEF", "PREEMP_INI", t, "", "", "", "x"]
        )

    main(["--telemetria", str(caminho)])
    assert "| 5 |" not in capsys.readouterr().out

    main(["--telemetria", str(caminho), "--item5", "--deteccoes", str(deteccoes)])
    assert "| 5 | Tag fora das 4 ruas: sem envio e sem mexer no semáforo | **atende** |" in (
        capsys.readouterr().out
    )


# ---------------------------------------------------------------------------
# Item 9 sem nenhuma linha gravada (mesmo tratamento do 15, 2026-10-08)
# ---------------------------------------------------------------------------


def _item_9_sem_nada(caminho: Path, lista_no_banco: tuple[int, ...]) -> Resultado:
    linhas = next(iter(ler_sessoes(caminho).values()))
    resultado = Resultado("9", "Log", None)
    return _sem_nada_gravado(resultado, linhas, 1, lambda _instante: lista_no_banco)


def _com_lista(caminho: Path) -> None:
    ensaio = Ensaio(caminho)
    ensaio.ate(0.5)
    ensaio.central(AMBULANCIA=1)
    ensaio.esperar(3)


def test_item_9_lista_posta_a_mao_fica_sem_veredito(tmp_path: Path) -> None:
    """O caso das sessões do item 5: compose parado, lista por PUT /autorizacoes."""
    caminho = tmp_path / "telemetria.csv"
    _com_lista(caminho)
    r = _item_9_sem_nada(caminho, (0, 0, 0))

    assert r.ok is None
    assert "veio de fora do backend" in r.detalhes[-1]


def test_item_9_backend_no_caminho_sem_gravar_nao_atende(tmp_path: Path) -> None:
    caminho = tmp_path / "telemetria.csv"
    _com_lista(caminho)
    r = _item_9_sem_nada(caminho, (1, 0, 0))

    assert r.ok is False


def test_item_9_lista_sempre_nula_nao_separa(tmp_path: Path) -> None:
    caminho = tmp_path / "telemetria.csv"
    Ensaio(caminho).ate(5)
    r = _item_9_sem_nada(caminho, (0, 0, 0))

    assert r.ok is None
    assert "000 a sessão inteira" in r.detalhes[-1]
