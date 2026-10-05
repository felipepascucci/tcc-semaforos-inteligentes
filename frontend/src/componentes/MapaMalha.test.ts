// A cor de cada linha de retenção, pela regra de core/priorizacao/fases.py: a
// fase corrente mostra o sinal transmitido; as outras, vermelho.
import { describe, expect, it } from "vitest";

import malha from "../malha/malha.json";
import type { SemaforoAoVivo } from "../stream/estado";
import { VALIDADE_MS } from "../stream/estado";
import { sinalDaAproximacao } from "./MapaMalha";

const AGORA = 1_000_000;

function cruz(campos: Partial<SemaforoAoVivo>): SemaforoAoVivo {
  return { id: "CRUZ_01", fonte: "SIMULACAO", fase: 1, estado: "VERDE", em_preempcao: false, chegou_em: AGORA, ...campos };
}

describe("sinalDaAproximacao", () => {
  it("a fase corrente em verde: arterial verde, transversal vermelha", () => {
    expect(sinalDaAproximacao(cruz({ fase: 1, estado: "VERDE" }), 1, AGORA)).toBe("VERDE");
    expect(sinalDaAproximacao(cruz({ fase: 1, estado: "VERDE" }), 2, AGORA)).toBe("VERMELHO");
  });

  it("o amarelo é só da fase que está saindo", () => {
    expect(sinalDaAproximacao(cruz({ fase: 2, estado: "AMARELO" }), 2, AGORA)).toBe("AMARELO");
    expect(sinalDaAproximacao(cruz({ fase: 2, estado: "AMARELO" }), 1, AGORA)).toBe("VERMELHO");
  });

  it("no all-red, todas vermelhas", () => {
    expect(sinalDaAproximacao(cruz({ fase: 1, estado: "VERMELHO" }), 1, AGORA)).toBe("VERMELHO");
    expect(sinalDaAproximacao(cruz({ fase: 1, estado: "VERMELHO" }), 2, AGORA)).toBe("VERMELHO");
  });

  it("sem estado, ou estado velho, fica sem dado em vez de inventar uma cor", () => {
    expect(sinalDaAproximacao(undefined, 1, AGORA)).toBe("SEM_DADO");
    expect(sinalDaAproximacao(cruz({}), 1, AGORA + VALIDADE_MS)).toBe("SEM_DADO");
  });
});

describe("malha.json", () => {
  it("traz os oito cruzamentos da simulação, cada um com as duas fases", () => {
    expect(malha.cruzamentos.map((c) => c.id)).toEqual([
      "CRUZ_01",
      "CRUZ_02",
      "CRUZ_03",
      "CRUZ_04",
      "CRUZ_05",
      "CRUZ_06",
      "CRUZ_07",
      "CRUZ_08",
    ]);
    for (const cruzamento of malha.cruzamentos) {
      expect(new Set(cruzamento.aproximacoes.map((a) => a.fase))).toEqual(new Set([1, 2]));
    }
  });
});
