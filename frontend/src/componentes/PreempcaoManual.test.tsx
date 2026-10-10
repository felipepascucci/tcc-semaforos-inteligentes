// A tela da preempção manual mostra o motivo que o backend deu, nunca um erro
// genérico (context/01 §7, Bloco 6).
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Semaforo } from "../api/tipos";
import { fetchFalso } from "../testes/http";
import { PreempcaoManual } from "./PreempcaoManual";

function semaforo(id: number, codigo: string): Semaforo {
  return {
    id_semaforo: id,
    codigo_externo: codigo,
    descricao: null,
    latitude: "0",
    longitude: "0",
    tempo_ciclo: 12,
    status_operacao: "ATIVO",
    estado_atual: "VERMELHO",
    ao_vivo: null,
  };
}

const SEMAFOROS = [semaforo(1, "CRUZ_01"), semaforo(9, "PROTO_CRUZ_01")];

describe("PreempcaoManual", () => {
  it("na bancada mostra a decisão do UNO e manda rua e veículo", async () => {
    const chamadas = fetchFalso({
      corpo: { linha: "RUA3,BOMBEIRO", decisao: "PREEMP_INI", t_decisao: null },
    });
    const usuario = userEvent.setup();
    render(<PreempcaoManual semaforos={SEMAFOROS} />);

    await usuario.selectOptions(screen.getByLabelText("Rua (S1..S4)"), "3");
    await usuario.selectOptions(screen.getByLabelText("Veículo"), "BOMBEIRO");
    await usuario.click(screen.getByRole("button", { name: "Solicitar preempção" }));

    expect(await screen.findByText(/UNO decidiu PREEMP_INI/)).toBeInTheDocument();
    expect(chamadas[0]).toMatchObject({
      url: "/api/v1/semaforos/PROTO_CRUZ_01/preempcao",
      metodo: "POST",
      corpo: { rua: 3, veiculo: "BOMBEIRO" },
    });
  });

  it("num CRUZ_xx mostra o 409 com o motivo do backend", async () => {
    fetchFalso({
      status: 409,
      corpo: { detail: "a API não comanda os cruzamentos da simulação: o motor roda no processo do executor" },
    });
    const usuario = userEvent.setup();
    render(<PreempcaoManual semaforos={SEMAFOROS} />);

    await usuario.selectOptions(screen.getByLabelText("Cruzamento"), "CRUZ_01");
    await usuario.click(screen.getByRole("button", { name: "Solicitar preempção" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "409 — a API não comanda os cruzamentos da simulação: o motor roda no processo do executor",
    );
  });

  it("o cancelamento recusado mostra o motivo de I6", async () => {
    const chamadas = fetchFalso({
      status: 409,
      corpo: { detail: "o UNO não aceita cancelamento: a emergência termina sozinha" },
    });
    const usuario = userEvent.setup();
    render(<PreempcaoManual semaforos={SEMAFOROS} />);

    await usuario.click(screen.getByRole("button", { name: "Cancelar preempção" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("a emergência termina sozinha");
    expect(chamadas[0]?.metodo).toBe("DELETE");
  });

  it("504 da ponte vira a explicação do UNO sem decisão", async () => {
    fetchFalso({ status: 504, corpo: { linha: "RUA1,AMBULANCIA", decisao: null, t_decisao: null } });
    const usuario = userEvent.setup();
    render(<PreempcaoManual semaforos={SEMAFOROS} />);

    await usuario.click(screen.getByRole("button", { name: "Solicitar preempção" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("O UNO não decidiu em 1 s");
  });
});
