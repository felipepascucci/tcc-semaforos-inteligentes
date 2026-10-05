import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { PedidoSimulacao } from "../api/tipos";
import { fetchFalso } from "../testes/http";
import { ESPERA_ATENDENTE_MS, pedidoParado, TelaSimulacoes, textoDoResumo } from "./TelaSimulacoes";

function pedido(campos: Partial<PedidoSimulacao>): PedidoSimulacao {
  return {
    id_pedido: 1,
    nome_cenario: "moderado",
    modo: "PREEMPCAO",
    seed: 900,
    duracao_s: null,
    velocidade: 1,
    status: "PENDENTE",
    mensagem: null,
    resumo: null,
    criado_em: new Date().toISOString(),
    iniciado_em: null,
    finalizado_em: null,
    execucao: null,
    ...campos,
  };
}

describe("pedidoParado", () => {
  it("só o pendente há mais que a espera do atendente", () => {
    const criado = Date.parse("2026-01-01T12:00:00Z");
    const p = pedido({ criado_em: "2026-01-01T12:00:00Z" });

    expect(pedidoParado(p, criado + ESPERA_ATENDENTE_MS - 1)).toBe(false);
    expect(pedidoParado(p, criado + ESPERA_ATENDENTE_MS + 1)).toBe(true);
    expect(pedidoParado({ ...p, status: "RODANDO" }, criado + 60_000)).toBe(false);
  });
});

describe("textoDoResumo", () => {
  it("resume o que o executor mediu", () => {
    expect(
      textoDoResumo({
        viagens_ve: 2,
        tempo_medio_travessia_ve_s: 310.5,
        paradas_ve: 0,
        latencia_p95_ms: 0.021,
        colisoes: 0,
        violacoes: 0,
      }),
    ).toBe(
      "2 viagens de VE concluídas · travessia média 310.5 s · 0 paradas · p95 da decisão 0.021 ms · 0 colisões · 0 violações",
    );
    expect(textoDoResumo(null)).toBeNull();
  });

  it("no singular, e sem travessia quando nenhuma viagem concluiu", () => {
    expect(textoDoResumo({ viagens_ve: 1, tempo_medio_travessia_ve_s: 327.3, paradas_ve: 1, colisoes: 1, violacoes: 1 })).toBe(
      "1 viagem de VE concluída · travessia média 327.3 s · 1 parada · 1 colisão · 1 violação",
    );
    expect(textoDoResumo({ viagens_ve: 0, tempo_medio_travessia_ve_s: 0, paradas_ve: 0, colisoes: 0, violacoes: 0 })).toBe(
      "0 viagens de VE concluídas · 0 colisões · 0 violações",
    );
  });
});

describe("TelaSimulacoes", () => {
  it("manda a velocidade escolhida, e a máxima vai como nula", async () => {
    const chamadas = fetchFalso(
      { corpo: [] },
      { status: 201, corpo: pedido({ id_pedido: 5, velocidade: 5 }) },
      { corpo: [pedido({ id_pedido: 5, velocidade: 5 })] },
      { status: 201, corpo: pedido({ id_pedido: 6, velocidade: null }) },
      { corpo: [] },
    );
    const usuario = userEvent.setup();
    render(<TelaSimulacoes />);

    await usuario.selectOptions(screen.getByLabelText("Velocidade"), "5");
    await usuario.click(screen.getByRole("button", { name: "Pedir" }));
    expect(await screen.findByText(/Pedido 5 na fila/)).toBeInTheDocument();
    expect(chamadas[1]?.corpo).toEqual({ cenario: "moderado", modo: "PREEMPCAO", seed: 900, duracao_s: null, velocidade: 5 });
    expect(await screen.findByText(/seed 900 · 5x/)).toBeInTheDocument();

    await usuario.selectOptions(screen.getByLabelText("Velocidade"), "");
    await usuario.click(screen.getByRole("button", { name: "Pedir" }));
    expect(await screen.findByText(/Pedido 6 na fila/)).toBeInTheDocument();
    expect(chamadas[3]?.corpo).toMatchObject({ velocidade: null });
  });

  it("pedido parado avisa que o atendente não está rodando", async () => {
    fetchFalso({ corpo: [pedido({ criado_em: "2020-01-01T00:00:00Z" })] });
    render(<TelaSimulacoes />);

    expect(await screen.findByRole("alert")).toHaveTextContent("o atendente não está rodando");
  });

  it("pedido recém-criado não dispara o aviso", async () => {
    fetchFalso({ corpo: [pedido({})] });
    render(<TelaSimulacoes />);

    expect(await screen.findByText(/seed 900 · 1x/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
