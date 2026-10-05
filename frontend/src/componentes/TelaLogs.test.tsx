import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { LogPrioridade } from "../api/tipos";
import { fetchFalso } from "../testes/http";
import { instanteUtc, paraFiltros, TelaLogs } from "./TelaLogs";

const LOG: LogPrioridade = {
  id_log: 1,
  id_correlacao: "00000000-0000-4000-8000-000000000001",
  codigo_semaforo: "PROTO_CRUZ_01",
  fk_veiculo: null,
  fk_execucao: null,
  timestamp_inicio: "2026-01-01T12:00:00+00:00",
  timestamp_fim: null,
  status_execucao: "SUCESSO",
  motivo: "verde exclusivo S3 (RUA3) para AMBULANCIA",
  fase_anterior: null,
  fase_aplicada: null,
};

describe("filtros dos logs", () => {
  it("datetime-local, que é hora local, vai à API como instante UTC", () => {
    const valor = "2026-01-01T09:00";
    expect(instanteUtc(valor)).toBe(new Date(valor).toISOString());
    expect(instanteUtc("")).toBeUndefined();
  });

  it("campo vazio não vira filtro", () => {
    expect(
      paraFiltros({ semaforo: "", status_execucao: "", veiculo: " ", id_correlacao: "", desde: "", ate: "" }),
    ).toEqual({
      semaforo: undefined,
      status_execucao: undefined,
      veiculo: undefined,
      id_correlacao: undefined,
      desde: undefined,
      ate: undefined,
    });
  });
});

describe("TelaLogs", () => {
  it("lista, filtra pela correlação clicada e pagina", async () => {
    const chamadas = fetchFalso(
      { corpo: { total: 120, limite: 50, deslocamento: 0, itens: [LOG] } },
      { corpo: { total: 1, limite: 50, deslocamento: 0, itens: [LOG] } },
    );
    const usuario = userEvent.setup();
    render(<TelaLogs semaforos={[]} />);

    expect(await screen.findByText("verde exclusivo S3 (RUA3) para AMBULANCIA")).toBeInTheDocument();
    expect(screen.getByText("Página 1 de 3")).toBeInTheDocument();
    expect(chamadas[0]?.url).toBe("/api/v1/logs/prioridade?limite=50&deslocamento=0");

    await usuario.click(screen.getByRole("button", { name: "00000000" }));

    expect(await screen.findByText("Página 1 de 1")).toBeInTheDocument();
    expect(chamadas[1]?.url).toBe(
      `/api/v1/logs/prioridade?id_correlacao=${LOG.id_correlacao}&limite=50&deslocamento=0`,
    );
  });
});
