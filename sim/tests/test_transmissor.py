"""Transmissão ao vivo da simulação (`--transmitir`, Bloco 6) e georreferência.

Sem SUMO: o transmissor recebe `EstadoMalha` montados à mão, e a georreferência
lê só o `.net.xml` e os seeds.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from core.modelos import (
    Criticidade,
    EstadoMalha,
    EstadoSemaforo,
    Sinal,
    TipoVeiculo,
    VeiculoEmergencia,
)
from db.seeds.carregar import carregar_dados, coordenadas_da_grade
from sim.controlador.transmissor import Transmissor
from sim.rede import georreferencia
from sim.rede.georreferencia import Georreferencia, posicao_da_juncao

GEO = Georreferencia(x0=500.0, y0=1000.0, lat0=-23.55, lon0=-46.63)


def _estado(t: float, em_preempcao: bool, x: float = 500.0) -> EstadoMalha:
    semaforos = {
        "CRUZ_01": EstadoSemaforo("CRUZ_01", 0, 1.0, em_preempcao=em_preempcao),
        "CRUZ_02": EstadoSemaforo("CRUZ_02", 2, 1.0, sinal=Sinal.AMARELO),
    }
    ve = VeiculoEmergencia(
        id="ve_amb_0",
        tipo=TipoVeiculo.AMBULANCIA,
        criticidade=Criticidade.RISCO_VIDA,
        posicao=(x, 1000.0),
        velocidade=12.5,
        rota=("A", "B"),
        indice_via_atual=0,
    )
    return EstadoMalha(t=t, semaforos=semaforos, veiculos_emergencia=(ve,), densidade_por_via={})


def _transmissor(enviados: list[dict[str, Any]]) -> Transmissor:
    return Transmissor(
        url_backend="http://backend",
        cenario="moderado",
        modo="PREEMPCAO",
        seed=1001,
        georreferencia=GEO,
        enviar=enviados.append,
    )


def test_envio_leva_o_estado_mais_recente_no_formato_da_api() -> None:
    enviados: list[dict[str, Any]] = []
    transmissor = _transmissor(enviados)
    transmissor.publicar(_estado(10.0, False, x=500.0), None)
    transmissor.publicar(_estado(10.1, False, x=600.0), 0.12)

    transmissor.enviar_pendentes()

    (corpo,) = enviados
    assert (corpo["t"], corpo["latencia_ms"], corpo["seed"]) == (10.1, 0.12, 1001)
    assert corpo["semaforos"] == [
        {"id": "CRUZ_01", "fase": 0, "sinal": "VERDE", "em_preempcao": False},
        {"id": "CRUZ_02", "fase": 2, "sinal": "AMARELO", "em_preempcao": False},
    ]
    (ve,) = corpo["veiculos"]
    assert (ve["id"], ve["tipo"], ve["criticidade"], ve["velocidade"]) == (
        "ve_amb_0",
        "AMBULANCIA",
        1,
        12.5,
    )
    assert (ve["lat"], ve["lon"]) == pytest.approx(GEO.para_lat_lon(600.0, 1000.0))


def test_sem_trafego_lido_o_envio_leva_lista_vazia_e_a_velocidade() -> None:
    enviados: list[dict[str, Any]] = []
    transmissor = _transmissor(enviados)
    transmissor.velocidade = 5
    transmissor.publicar(_estado(1.0, False), None)

    transmissor.enviar_pendentes()

    assert enviados[0]["trafego"] == []
    assert enviados[0]["velocidade"] == 5


def test_trafego_vai_em_lat_lon_arredondado() -> None:
    enviados: list[dict[str, Any]] = []
    transmissor = _transmissor(enviados)
    transmissor.publicar(_estado(1.0, False), None)
    transmissor.publicar_trafego([(500.0, 1000.0), (750.25, 990.5)])

    transmissor.enviar_pendentes()

    trafego = enviados[0]["trafego"]
    assert trafego[0] == (-23.55, -46.63)
    lat, lon = GEO.para_lat_lon(750.25, 990.5)
    assert trafego[1] == (round(lat, 6), round(lon, 6))


def test_trafego_e_lido_no_maximo_uma_vez_por_intervalo() -> None:
    """A leitura custa uma chamada ao SUMO por veículo: só a 5 Hz de relógio."""
    agora = [100.0]
    transmissor = _transmissor([])
    transmissor.relogio = lambda: agora[0]

    assert transmissor.quer_trafego()
    transmissor.publicar_trafego([(1.0, 2.0)])
    agora[0] = 100.0 + transmissor.intervalo_s * 0.9
    assert not transmissor.quer_trafego()
    agora[0] = 100.0 + transmissor.intervalo_s * 1.1
    assert transmissor.quer_trafego()


def test_preempcao_curta_entre_dois_envios_nao_some() -> None:
    """Os eventos saem de todas as fotos acumuladas, não só da última."""
    enviados: list[dict[str, Any]] = []
    transmissor = _transmissor(enviados)
    transmissor.publicar(_estado(10.0, False), None)
    transmissor.publicar(_estado(10.1, True), 0.1)
    transmissor.publicar(_estado(10.2, False), 0.1)

    transmissor.enviar_pendentes()

    textos = [evento["texto"] for evento in enviados[0]["eventos"]]
    assert textos == [
        "Preempção iniciada em CRUZ_01 (t=10.1 s)",
        "Preempção encerrada em CRUZ_01 (t=10.2 s)",
    ]
    assert enviados[0]["semaforos"][0]["em_preempcao"] is False


def test_sem_fotos_nada_e_enviado() -> None:
    enviados: list[dict[str, Any]] = []
    _transmissor(enviados).enviar_pendentes()
    assert enviados == []


def test_backend_fora_do_ar_nao_derruba_a_simulacao() -> None:
    def recusar(_: dict[str, Any]) -> None:
        raise httpx.ConnectError("backend fora do ar")

    transmissor = Transmissor("http://backend", "leve", "FIXO", 1001, GEO, enviar=recusar)
    transmissor.publicar(_estado(1.0, False), None)
    transmissor.enviar_pendentes()

    assert (transmissor.enviados, transmissor.falhas) == (0, 1)


def test_fila_limitada_descarta_as_fotos_mais_antigas() -> None:
    transmissor = _transmissor([])
    for passo in range(1000):
        transmissor.publicar(_estado(passo * 0.1, False), None)
    assert len(transmissor._fotos) == 600


def test_thread_envia_sozinha_e_encerrar_manda_o_resto() -> None:
    enviados: list[dict[str, Any]] = []
    transmissor = _transmissor(enviados)
    transmissor.intervalo_s = 0.01
    transmissor.iniciar()
    transmissor.publicar(_estado(1.0, False), None)
    transmissor.encerrar()
    assert enviados and enviados[-1]["t"] == 1.0


# ---------------------------------------------------------------------------
# Georreferência: a rede e os seeds põem os cruzamentos no mesmo lugar
# ---------------------------------------------------------------------------


def test_os_oito_cruzamentos_da_rede_caem_onde_os_seeds_os_poem() -> None:
    """Senão o marcador do VE andaria fora das ruas do mapa (RF06)."""
    geo = georreferencia.carregar()
    for codigo, _, latitude, longitude in coordenadas_da_grade(carregar_dados()["malha_sumo"]):
        lat, lon = geo.para_lat_lon(*posicao_da_juncao(georreferencia.REDE, codigo))
        assert lat == pytest.approx(float(latitude), abs=1e-8), codigo
        assert lon == pytest.approx(float(longitude), abs=1e-8), codigo


def test_juncao_que_nao_existe_e_erro() -> None:
    with pytest.raises(LookupError):
        posicao_da_juncao(georreferencia.REDE, "CRUZ_99")
