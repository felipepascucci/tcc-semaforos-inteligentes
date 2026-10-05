// O painel Central (P20): abrir ocorrência escolhendo veículo e criticidade,
// encerrar, e ver quem está em serviço.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Ocorrencia, Veiculo } from "../api/tipos";
import { fetchFalso } from "../testes/http";
import { PainelCentral } from "./PainelCentral";

function veiculo(id: number, placa: string, campos: Partial<Veiculo> = {}): Veiculo {
  return {
    id_veiculo: id,
    placa,
    tipo: "AMBULANCIA",
    identificacao: null,
    status_operacional: "ATIVO",
    tags: [],
    em_servico: false,
    ...campos,
  };
}

const LIVRE = veiculo(1, "TST1A01");
const EM_SERVICO = veiculo(2, "TST2B02", { tipo: "BOMBEIRO", em_servico: true });
const INATIVO = veiculo(3, "TST3C03", { tipo: "POLICIA", status_operacional: "INATIVO" });

const ABERTA: Ocorrencia = {
  id_ocorrencia: 7,
  id_veiculo: 2,
  criticidade: 2,
  descricao: "teste",
  origem: "OPERADOR",
  aberta_em: "2026-01-01T12:00:00+00:00",
  encerrada_em: null,
  aberta: true,
};

describe("PainelCentral", () => {
  it("só oferece para despacho o veículo ativo e livre, e mostra quem está em serviço", async () => {
    fetchFalso({ corpo: [LIVRE, EM_SERVICO, INATIVO] }, { corpo: [ABERTA] });
    render(<PainelCentral />);

    const select = await screen.findByLabelText("Veículo");
    await screen.findByText(/TST1A01 — Ambulância/);
    const opcoes = within(select).getAllByRole("option").map((o) => o.textContent);
    expect(opcoes).toEqual(["Escolha um veículo livre…", "TST1A01 — Ambulância"]);

    expect(screen.getByText("#7 · TST2B02 — Bombeiro")).toBeInTheDocument();
    expect(screen.getByText(/2 — Risco coletivo · desde/)).toBeInTheDocument();
  });

  it("abre a ocorrência com o veículo e a criticidade escolhidos", async () => {
    const chamadas = fetchFalso(
      { corpo: [LIVRE] },
      { corpo: [] },
      { status: 201, corpo: { ...ABERTA, id_ocorrencia: 8, id_veiculo: 1, criticidade: 1 } },
      { corpo: [{ ...LIVRE, em_servico: true }] },
      { corpo: [{ ...ABERTA, id_ocorrencia: 8, id_veiculo: 1, criticidade: 1 }] },
    );
    const usuario = userEvent.setup();
    render(<PainelCentral />);

    await screen.findByText(/TST1A01 — Ambulância/);
    await usuario.selectOptions(screen.getByLabelText("Veículo"), "1");
    await usuario.selectOptions(screen.getByLabelText("Criticidade"), "1");
    await usuario.type(screen.getByLabelText("Descrição (opcional)"), "parada cardíaca");
    await usuario.click(screen.getByRole("button", { name: "Abrir ocorrência" }));

    expect(await screen.findByText(/Ocorrência 8 aberta: TST1A01 em serviço/)).toBeInTheDocument();
    expect(chamadas[2]).toMatchObject({
      url: "/api/v1/ocorrencias",
      metodo: "POST",
      corpo: { id_veiculo: 1, criticidade: 1, descricao: "parada cardíaca", origem: "OPERADOR" },
    });
    expect(await screen.findByText("SIM")).toBeInTheDocument();
  });

  it("recusa do backend aparece com o motivo", async () => {
    fetchFalso(
      { corpo: [LIVRE] },
      { corpo: [] },
      { status: 409, corpo: { detail: "veículo 1 já tem ocorrência aberta" } },
    );
    const usuario = userEvent.setup();
    render(<PainelCentral />);

    await screen.findByText(/TST1A01 — Ambulância/);
    await usuario.selectOptions(screen.getByLabelText("Veículo"), "1");
    await usuario.click(screen.getByRole("button", { name: "Abrir ocorrência" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("409 — veículo 1 já tem ocorrência aberta");
  });

  it("encerra a ocorrência", async () => {
    const chamadas = fetchFalso(
      { corpo: [EM_SERVICO] },
      { corpo: [ABERTA] },
      { corpo: { ...ABERTA, aberta: false } },
      { corpo: [{ ...EM_SERVICO, em_servico: false }] },
      { corpo: [] },
    );
    const usuario = userEvent.setup();
    render(<PainelCentral />);

    await usuario.click(await screen.findByRole("button", { name: "Encerrar" }));

    expect(await screen.findByText(/Ocorrência 7 encerrada/)).toBeInTheDocument();
    expect(chamadas[2]).toMatchObject({ url: "/api/v1/ocorrencias/7/encerramento", metodo: "POST" });
    expect(await screen.findByText(/Nenhuma ocorrência aberta/)).toBeInTheDocument();
  });
});
