import { describe, expect, it } from "vitest";

import { ms } from "./PainelMetricas";

describe("ms", () => {
  it("abaixo de 1 ms mostra três casas: a decisão do motor fica no centésimo", () => {
    expect(ms(0.021)).toBe("0.021 ms");
    expect(ms(0)).toBe("0.000 ms");
  });

  it("de 1 ms para cima, uma casa", () => {
    expect(ms(45)).toBe("45.0 ms");
    expect(ms("52.25")).toBe("52.3 ms");
  });

  it("sem valor, travessão", () => {
    expect(ms(null)).toBe("—");
    expect(ms(undefined)).toBe("—");
    expect(ms("abc")).toBe("—");
  });
});
