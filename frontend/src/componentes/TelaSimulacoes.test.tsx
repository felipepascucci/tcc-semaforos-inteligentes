import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { FaixaSeedReservada, PedidoSimulacao } from "../api/tipos";
import { fetchFalso } from "../testes/http";
import { ESPERA_ATENDENTE_MS, faixaDaSeed, pedidoParado, TelaSimulacoes, textoDoResumo } from "./TelaSimulacoes";

const FAIXAS: FaixaSeedReservada[] = [
  { inicio: 1, fim: 50, uso: "Experimento de teste" },
  { inicio: 201, fim: 250, uso: "Treino de teste" },
];

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

describe("faixaDaSeed", () => {
  it("acha a faixa pelos dois extremos, e nada fora delas ou com o campo vazio", () => {
    expect(faixaDaSeed("1", FAIXAS)?.uso).toBe("Experimento de teste");
    expect(faixaDaSeed("250", FAIXAS)?.uso).toBe("Treino de teste");
    expect(faixaDaSeed("51", FAIXAS)).toBeNull();
    expect(faixaDaSeed("900", FAIXAS)).toBeNull();
    expect(faixaDaSeed("", FAIXAS)).toBeNull();
  });
});

describe("TelaSimulacoes", () => {
  it("lista as faixas reservadas e bloqueia o pedido com seed do experimento", async () => {
    const chamadas = fetchFalso({ corpo: FAIXAS }, { corpo: [] });
    const usuario = userEvent.setup();
    render(<TelaSimulacoes />);

    expect(await screen.findByText(/Treino de teste/)).toBeInTheDocument();
    expect(chamadas[0]?.url).toContain("/simulacoes/seeds-reservadas");

    const campo = screen.getByLabelText("Seed");
    await usuario.clear(campo);
    await usuario.type(campo, "210");
    expect(screen.getByRole("alert")).toHaveTextContent("A seed 210 é do experimento (201..250: Treino de teste)");
    expect(screen.getByRole("button", { name: "Pedir" })).toBeDisabled();

    await usuario.clear(campo);
    await usuario.type(campo, "900");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("button", { name: "Pedir" })).toBeEnabled();
  });

  it("manda a velocidade escolhida, e a máxima vai como nula", async () => {
    const chamadas = fetchFalso(
      { corpo: FAIXAS },
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
    expect(chamadas[2]?.corpo).toEqual({ cenario: "moderado", modo: "PREEMPCAO", seed: 900, duracao_s: null, velocidade: 5 });
    expect(await screen.findByText(/seed 900 · 5x/)).toBeInTheDocument();

    await usuario.selectOptions(screen.getByLabelText("Velocidade"), "");
    await usuario.click(screen.getByRole("button", { name: "Pedir" }));
    expect(await screen.findByText(/Pedido 6 na fila/)).toBeInTheDocument();
    expect(chamadas[4]?.corpo).toMatchObject({ velocidade: null });
  });

  it("pedido parado avisa que o atendente não está rodando", async () => {
    fetchFalso({ corpo: FAIXAS }, { corpo: [pedido({ criado_em: "2020-01-01T00:00:00Z" })] });
    render(<TelaSimulacoes />);

    expect(await screen.findByRole("alert")).toHaveTextContent("o atendente não está rodando");
  });

  it("pedido recém-criado não dispara o aviso", async () => {
    fetchFalso({ corpo: FAIXAS }, { corpo: [pedido({})] });
    render(<TelaSimulacoes />);

    expect(await screen.findByText(/seed 900 · 1x/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
