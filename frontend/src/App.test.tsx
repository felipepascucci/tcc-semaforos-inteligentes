// O dashboard inteiro monta e troca de aba sem erro de execução, com a API e o
// WebSocket falsos. Pega o que o `tsc` não pega (Leaflet e Recharts no DOM).
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { ProvedorSessao } from "./auth/sessao";

const DAQUI_A_UMA_HORA = new Date(Date.now() + 3_600_000).toISOString();

const SEMAFOROS = [
  {
    id_semaforo: 1,
    codigo_externo: "CRUZ_01",
    descricao: null,
    latitude: "-23.55000000",
    longitude: "-46.63000000",
    tempo_ciclo: 70,
    status_operacao: "ATIVO",
    estado_atual: "VERMELHO",
    ao_vivo: null,
  },
];

const RESUMO = {
  priorizacoes: { total: 0, por_status: {} },
  deteccoes: { total: 0, reconhecidas: 0, autorizadas: 0 },
  ocorrencias_ativas: 0,
  latencia: {
    simulacao: { n: 0, p95_decisao_ms: null, p99_decisao_ms: null },
    hardware: { n: 0, min_total_ms: null, mediana_total_ms: null, max_total_ms: null },
  },
  simulacoes: { execucoes: 0, pedidos_por_status: {} },
  ao_vivo: { bancada: false, simulacao: false },
};

/** Responde por rota, para a ordem das chamadas não importar. */
function apiFalsa(url: string): unknown {
  if (url.includes("/semaforos")) return SEMAFOROS;
  if (url.includes("/logs/prioridade")) return { total: 0, limite: 50, deslocamento: 0, itens: [] };
  if (url.includes("/metricas/resumo")) return RESUMO;
  if (url.includes("/auth/sessao")) return { usuario: "operador", perfil: "operador", expira_em: DAQUI_A_UMA_HORA };
  return [];
}

class SocketMudo {
  onopen: (() => void) | null = null;
  onmessage: (() => void) | null = null;
  onclose: (() => void) | null = null;
  close() {}
}

describe("App", () => {
  beforeEach(() => {
    localStorage.setItem(
      "tcc.sessao.operador",
      JSON.stringify({ token: "token-de-teste", usuario: "operador", expira_em: DAQUI_A_UMA_HORA }),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => new Response(JSON.stringify(apiFalsa(url)), { status: 200 })),
    );
    vi.stubGlobal("WebSocket", SocketMudo);
    // O mapa desenha em <canvas> (preferCanvas); o jsdom não tem contexto 2D.
    const contexto2d = new Proxy({}, { get: () => () => undefined });
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(contexto2d as never);
    // O ResponsiveContainer do Recharts mede o contêiner; o jsdom não tem.
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
  });

  it("monta logado e percorre todas as abas", async () => {
    const usuario = userEvent.setup();
    render(
      <ProvedorSessao>
        <App />
      </ProvedorSessao>,
    );

    expect(await screen.findByTestId("semaforo-CRUZ_01")).toHaveTextContent("sem dado ao vivo");
    expect(screen.getByText(/Sem telemetria da bancada/)).toBeInTheDocument();

    await usuario.click(screen.getByRole("link", { name: "Central" }));
    await act(async () => window.dispatchEvent(new HashChangeEvent("hashchange")));
    expect(await screen.findByText("Abrir ocorrência", { selector: "h2" })).toBeInTheDocument();

    await usuario.click(screen.getByRole("link", { name: "Logs" }));
    await act(async () => window.dispatchEvent(new HashChangeEvent("hashchange")));
    expect(await screen.findByText(/Priorizações — 0 registros/)).toBeInTheDocument();

    await usuario.click(screen.getByRole("link", { name: "Métricas" }));
    await act(async () => window.dispatchEvent(new HashChangeEvent("hashchange")));
    expect(await screen.findByText("Priorizações por desfecho")).toBeInTheDocument();

    await usuario.click(screen.getByRole("link", { name: "Simulações" }));
    await act(async () => window.dispatchEvent(new HashChangeEvent("hashchange")));
    expect(await screen.findByText("Pedir simulação")).toBeInTheDocument();
  });

  it("Sair volta ao login e apaga a sessão", async () => {
    const usuario = userEvent.setup();
    render(
      <ProvedorSessao>
        <App />
      </ProvedorSessao>,
    );

    await usuario.click(await screen.findByRole("button", { name: "Sair" }));

    expect(screen.getByRole("button", { name: "Entrar" })).toBeInTheDocument();
    expect(localStorage.getItem("tcc.sessao.operador")).toBeNull();
  });
});
