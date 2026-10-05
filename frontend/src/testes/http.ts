// Um `fetch` falso para os testes: cada chamada consome a próxima resposta
// da lista e fica registrada para conferência.
import { vi } from "vitest";

export interface RespostaFalsa {
  status?: number;
  corpo?: unknown;
}

export interface ChamadaRegistrada {
  url: string;
  metodo: string;
  cabecalhos: Record<string, string>;
  corpo: unknown;
}

export function fetchFalso(...respostas: RespostaFalsa[]) {
  const chamadas: ChamadaRegistrada[] = [];
  const fila = [...respostas];
  const fn = vi.fn(async (url: string, init: RequestInit = {}) => {
    chamadas.push({
      url,
      metodo: init.method ?? "GET",
      cabecalhos: (init.headers ?? {}) as Record<string, string>,
      corpo: typeof init.body === "string" ? JSON.parse(init.body) : undefined,
    });
    const proxima = fila.shift() ?? { status: 200, corpo: [] };
    const status = proxima.status ?? 200;
    return new Response(status === 204 ? null : JSON.stringify(proxima.corpo ?? null), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fn);
  return chamadas;
}
