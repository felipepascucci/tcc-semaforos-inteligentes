// O estado ao vivo do dashboard (RF04, RF06): o que cada mensagem do WebSocket
// faz com a tela. Mensagens no formato de backend/app/services (Bloco 6);
// valores obviamente artificiais.
import { describe, expect, it } from "vitest";

import {
  ESTADO_INICIAL,
  LIMITE_EVENTOS,
  reduzirStream,
  trafegoAtivo,
  VALIDADE_MS,
  vesAtivos,
} from "./estado";
import type { EstadoStream } from "./estado";

const T0 = 1_000_000;

function msg(tipo: string, dados: object): string {
  return JSON.stringify({ tipo, dados });
}

function aplicar(...mensagens: string[]): EstadoStream {
  return mensagens.reduce((estado, m, i) => reduzirStream(estado, m, T0 + i), ESTADO_INICIAL);
}

describe("estado_semaforo", () => {
  it("da bancada guarda as quatro aproximações, o regime, a rua ativa e a fila", () => {
    const estado = aplicar(
      msg("estado_semaforo", {
        id: "PROTO_CRUZ_01",
        fase: null,
        estado: "VERDE",
        em_preempcao: true,
        aproximacoes: "RRGR",
        regime: "E",
        rua_ativa: 3,
        rua_fila: 1,
        recebido_em: "2026-01-01T00:00:00+00:00",
      }),
    );

    const semaforo = estado.semaforos.PROTO_CRUZ_01;
    expect(semaforo).toMatchObject({
      fonte: "BANCADA",
      fase: null,
      estado: "VERDE",
      em_preempcao: true,
      aproximacoes: "RRGR",
      regime: "E",
      rua_ativa: 3,
      rua_fila: 1,
      chegou_em: T0,
    });
  });

  it("da simulação é reconhecida pela falta de aproximações e guarda o t simulado", () => {
    const estado = aplicar(
      msg("estado_semaforo", { id: "CRUZ_03", fase: 2, estado: "AMARELO", em_preempcao: false, t_simulacao: 12.5 }),
    );

    expect(estado.semaforos.CRUZ_03).toMatchObject({ fonte: "SIMULACAO", fase: 2, t_simulacao: 12.5 });
    expect(estado.semaforos.CRUZ_03?.aproximacoes).toBeUndefined();
  });

  it("a mensagem mais nova substitui a anterior do mesmo cruzamento", () => {
    const estado = aplicar(
      msg("estado_semaforo", { id: "CRUZ_01", fase: 1, estado: "VERDE", em_preempcao: false }),
      msg("estado_semaforo", { id: "CRUZ_01", fase: 1, estado: "AMARELO", em_preempcao: true }),
    );

    expect(Object.keys(estado.semaforos)).toEqual(["CRUZ_01"]);
    expect(estado.semaforos.CRUZ_01).toMatchObject({ estado: "AMARELO", em_preempcao: true, chegou_em: T0 + 1 });
  });

  it("sinal fora de VERDE, AMARELO e VERMELHO é recusado sem quebrar o estado", () => {
    const estado = aplicar(msg("estado_semaforo", { id: "CRUZ_01", estado: "AZUL" }));

    expect(estado.semaforos).toEqual({});
    expect(estado.invalidas).toBe(1);
  });
});

describe("posicao_ve", () => {
  it("guarda o id do SUMO, lat/lon e a velocidade em m/s", () => {
    const estado = aplicar(
      msg("posicao_ve", {
        id_veiculo: "ve_teste_0",
        tipo: "AMBULANCIA",
        criticidade: 1,
        lat: -23.5,
        lon: -46.6,
        velocidade: 10,
        t_simulacao: 3,
      }),
    );

    expect(estado.ves.ve_teste_0).toMatchObject({
      id: "ve_teste_0",
      tipo: "AMBULANCIA",
      criticidade: 1,
      lat: -23.5,
      lon: -46.6,
      velocidade_ms: 10,
    });
  });

  it("id numérico do cadastro também serve", () => {
    const estado = aplicar(msg("posicao_ve", { id_veiculo: 3, lat: -23.5, lon: -46.6, velocidade: 0 }));

    expect(estado.ves["3"]?.id).toBe("3");
  });

  it("sem coordenada a posição é recusada", () => {
    expect(aplicar(msg("posicao_ve", { id_veiculo: "ve", lat: -23.5 })).ves).toEqual({});
  });

  it("um VE sem posição nova há mais que a validade sai do mapa", () => {
    const estado = aplicar(msg("posicao_ve", { id_veiculo: "ve", lat: 1, lon: 2, velocidade: 0 }));

    expect(vesAtivos(estado, T0 + VALIDADE_MS - 1)).toHaveLength(1);
    expect(vesAtivos(estado, T0 + VALIDADE_MS)).toHaveLength(0);
  });
});

describe("evento", () => {
  it("entra no topo, com a origem", () => {
    const estado = aplicar(
      msg("evento", { nivel: "INFO", texto: "primeiro", origem: "BANCADA" }),
      msg("evento", { nivel: "WARNING", texto: "segundo", origem: "CENTRAL" }),
    );

    expect(estado.eventos.map((e) => e.texto)).toEqual(["segundo", "primeiro"]);
    expect(estado.eventos[0]).toMatchObject({ nivel: "WARNING", origem: "CENTRAL" });
  });

  it("a lista é limitada, e as chaves não se repetem", () => {
    const mensagens = Array.from({ length: LIMITE_EVENTOS + 10 }, (_, i) =>
      msg("evento", { texto: `evento ${i}` }),
    );
    const estado = aplicar(...mensagens);

    expect(estado.eventos).toHaveLength(LIMITE_EVENTOS);
    expect(estado.eventos[0]?.texto).toBe(`evento ${LIMITE_EVENTOS + 9}`);
    expect(new Set(estado.eventos.map((e) => e.chave)).size).toBe(LIMITE_EVENTOS);
  });
});

describe("metrica", () => {
  it("cada transmissão da simulação é uma amostra de latência", () => {
    const estado = aplicar(
      msg("metrica", { origem: "SIMULACAO", latencia_ms: 0.5, priorizacoes_ativas: 1, cenario: "moderado" }),
      msg("metrica", { origem: "SIMULACAO", latencia_ms: 0.5, priorizacoes_ativas: 1 }),
    );

    expect(estado.latencias).toHaveLength(2);
    expect(estado.metricas.SIMULACAO).toMatchObject({ latencia_ms: 0.5, priorizacoes_ativas: 1 });
  });

  it("a bancada repete a última amostra de H3 em toda telemetria: só a diferente conta", () => {
    const estado = aplicar(
      msg("metrica", { origem: "BANCADA", latencia_ms: 100, priorizacoes_ativas: 1 }),
      msg("metrica", { origem: "BANCADA", latencia_ms: 100, priorizacoes_ativas: 1 }),
      msg("metrica", { origem: "BANCADA", latencia_ms: 120, priorizacoes_ativas: 0 }),
    );

    expect(estado.latencias.map((a) => a.latencia_ms)).toEqual([100, 120]);
  });

  it("latência nula, como no modo FIXO, não vira amostra", () => {
    const estado = aplicar(msg("metrica", { origem: "SIMULACAO", latencia_ms: null, priorizacoes_ativas: 0 }));

    expect(estado.latencias).toEqual([]);
    expect(estado.metricas.SIMULACAO?.latencia_ms).toBeNull();
  });
});

describe("trafego (Bloco 7)", () => {
  it("guarda a fotografia inteira e a substitui na próxima", () => {
    const estado = aplicar(
      msg("trafego", { t_simulacao: 1, posicoes: [[-23.5, -46.6], [-23.6, -46.7]] }),
      msg("trafego", { t_simulacao: 2, posicoes: [[-23.4, -46.5]] }),
    );

    expect(estado.trafego).toEqual({ posicoes: [[-23.4, -46.5]], t_simulacao: 2, chegou_em: T0 + 1 });
  });

  it("descarta posição malformada sem perder as boas", () => {
    const estado = aplicar(msg("trafego", { posicoes: [[-23.5, -46.6], [1], "x", [null, 2]] }));

    expect(estado.trafego?.posicoes).toEqual([[-23.5, -46.6]]);
  });

  it("fotografia velha sai do mapa, como o VE", () => {
    const estado = aplicar(msg("trafego", { posicoes: [[-23.5, -46.6]] }));

    expect(trafegoAtivo(estado, T0 + VALIDADE_MS - 1)).toHaveLength(1);
    expect(trafegoAtivo(estado, T0 + VALIDADE_MS)).toEqual([]);
    expect(trafegoAtivo(ESTADO_INICIAL, T0)).toEqual([]);
  });

  it("a métrica da simulação traz o tempo simulado e a velocidade", () => {
    const estado = aplicar(
      msg("metrica", { origem: "SIMULACAO", latencia_ms: 0.1, priorizacoes_ativas: 0, t_simulacao: 42, velocidade: 5 }),
    );

    expect(estado.metricas.SIMULACAO).toMatchObject({ t_simulacao: 42, velocidade: 5 });
  });
});

describe("mensagens inválidas", () => {
  it.each(["não é json", JSON.stringify({ tipo: "estado_semaforo" }), msg("desconhecido", {})])(
    "%s só conta como inválida",
    (bruta) => {
      const estado = reduzirStream(ESTADO_INICIAL, bruta, T0);

      expect(estado.invalidas).toBe(1);
      expect(estado.mensagens).toBe(0);
    },
  );
});
