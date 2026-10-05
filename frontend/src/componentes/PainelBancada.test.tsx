import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VALIDADE_MS } from "../stream/estado";
import type { SemaforoAoVivo } from "../stream/estado";
import { PainelBancada } from "./PainelBancada";

const AGORA = 1_000_000;

function bancada(campos: Partial<SemaforoAoVivo> = {}): SemaforoAoVivo {
  return {
    id: "PROTO_CRUZ_01",
    fonte: "BANCADA",
    fase: null,
    estado: "VERDE",
    em_preempcao: true,
    aproximacoes: "RRGR",
    regime: "E",
    rua_ativa: 3,
    rua_fila: 1,
    chegou_em: AGORA,
    ...campos,
  };
}

describe("PainelBancada", () => {
  it("mostra cada aproximação com a cor da telemetria", () => {
    render(<PainelBancada estado={bancada({ aproximacoes: "RYGR" })} agora={AGORA} />);

    expect(screen.getByLabelText("S1 · Rua 1: vermelho")).toBeInTheDocument();
    expect(screen.getByLabelText("S2 · Rua 2: amarelo")).toBeInTheDocument();
    expect(screen.getByLabelText("S3 · Rua 3: verde")).toBeInTheDocument();
    expect(screen.getByLabelText("S4 · Rua 4: vermelho")).toBeInTheDocument();
  });

  it("em emergência mostra o regime, a rua atendida e a fila", () => {
    render(<PainelBancada estado={bancada()} agora={AGORA} />);

    expect(screen.getByText("Emergência")).toBeInTheDocument();
    expect(screen.getByText("— (verde exclusivo)")).toBeInTheDocument();
    expect(screen.getByText("Rua 3")).toBeInTheDocument();
    expect(screen.getByText("Rua 1")).toBeInTheDocument();
  });

  it("no ciclo mostra o eixo aberto e a fila vazia", () => {
    render(
      <PainelBancada
        estado={bancada({ regime: "C", fase: 2, aproximacoes: "RRGG", rua_ativa: 0, rua_fila: 0, em_preempcao: false })}
        agora={AGORA}
      />,
    );

    expect(screen.getByText("Ciclo normal")).toBeInTheDocument();
    expect(screen.getByText("Transversal (S3+S4)")).toBeInTheDocument();
    expect(screen.getByText("nenhuma")).toBeInTheDocument();
    expect(screen.getByText("vazia")).toBeInTheDocument();
  });

  it("telemetria velha é marcada como parada", () => {
    render(<PainelBancada estado={bancada()} agora={AGORA + VALIDADE_MS} />);

    expect(screen.getByText(/parada/)).toBeInTheDocument();
  });

  it("sem telemetria explica como subir a ponte", () => {
    render(<PainelBancada estado={undefined} agora={AGORA} />);

    expect(screen.getByText(/Sem telemetria da bancada/)).toBeInTheDocument();
    expect(screen.getByText("python -m bridge.main --simulado")).toBeInTheDocument();
  });
});
