// RF04 e RF06 no cliente: a mensagem do WebSocket chega à tela, e a conexão
// perdida é refeita sozinha. Socket falso, sem rede.
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { urlDoStream, useStream } from "./useStream";

class SocketFalso {
  static criados: SocketFalso[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((evento: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  fechado = false;

  constructor(readonly url: string) {
    SocketFalso.criados.push(this);
  }

  abrir() {
    this.onopen?.();
  }

  receber(tipo: string, dados: object) {
    this.onmessage?.({ data: JSON.stringify({ tipo, dados }) });
  }

  cair() {
    this.onclose?.();
  }

  close() {
    this.fechado = true;
  }
}

const fabrica = (url: string) => new SocketFalso(url) as unknown as WebSocket;

function Sonda() {
  const { estado, conexao } = useStream("ws://teste/api/v1/stream", fabrica);
  const semaforo = estado.semaforos.CRUZ_01;
  const ve = estado.ves.ve_teste_0;
  return (
    <div>
      <p>conexão: {conexao}</p>
      <p>CRUZ_01: {semaforo?.estado ?? "nada"}</p>
      <p>VE: {ve ? `${ve.lat},${ve.lon}` : "nada"}</p>
    </div>
  );
}

describe("useStream", () => {
  beforeEach(() => {
    SocketFalso.criados = [];
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("estado do semáforo e posição do VE chegam à tela a cada mensagem", () => {
    render(<Sonda />);
    const socket = SocketFalso.criados[0]!;
    expect(socket.url).toBe("ws://teste/api/v1/stream");
    expect(screen.getByText("conexão: conectando")).toBeInTheDocument();

    act(() => socket.abrir());
    expect(screen.getByText("conexão: aberta")).toBeInTheDocument();

    act(() => socket.receber("estado_semaforo", { id: "CRUZ_01", fase: 1, estado: "VERDE", em_preempcao: true }));
    expect(screen.getByText("CRUZ_01: VERDE")).toBeInTheDocument();

    act(() => socket.receber("estado_semaforo", { id: "CRUZ_01", fase: 1, estado: "AMARELO", em_preempcao: true }));
    expect(screen.getByText("CRUZ_01: AMARELO")).toBeInTheDocument();

    act(() => socket.receber("posicao_ve", { id_veiculo: "ve_teste_0", lat: -23.5, lon: -46.6, velocidade: 10 }));
    expect(screen.getByText("VE: -23.5,-46.6")).toBeInTheDocument();
  });

  it("conexão que cai é refeita, com espera crescente", () => {
    render(<Sonda />);
    act(() => SocketFalso.criados[0]!.cair());
    expect(screen.getByText("conexão: fechada")).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(999));
    expect(SocketFalso.criados).toHaveLength(1);
    act(() => vi.advanceTimersByTime(1));
    expect(SocketFalso.criados).toHaveLength(2);

    act(() => SocketFalso.criados[1]!.cair());
    act(() => vi.advanceTimersByTime(1999));
    expect(SocketFalso.criados).toHaveLength(2);
    act(() => vi.advanceTimersByTime(1));
    expect(SocketFalso.criados).toHaveLength(3);
  });

  it("ao desmontar fecha o socket e não reconecta", () => {
    const { unmount } = render(<Sonda />);
    const socket = SocketFalso.criados[0]!;

    unmount();
    socket.cair();
    act(() => vi.advanceTimersByTime(60_000));

    expect(socket.fechado).toBe(true);
    expect(SocketFalso.criados).toHaveLength(1);
  });
});

describe("urlDoStream", () => {
  it("segue o protocolo da página: wss atrás do nginx com HTTPS", () => {
    expect(urlDoStream({ protocol: "https:", host: "localhost:8443" } as Location)).toBe(
      "wss://localhost:8443/api/v1/stream",
    );
    expect(urlDoStream({ protocol: "http:", host: "localhost:5173" } as Location)).toBe(
      "ws://localhost:5173/api/v1/stream",
    );
  });
});
