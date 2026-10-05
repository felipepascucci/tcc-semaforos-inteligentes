import { describe, expect, it, vi } from "vitest";

import { fetchFalso } from "../testes/http";
import {
  definirToken,
  ErroApi,
  mensagemDeErro,
  montarConsulta,
  quandoTokenRecusado,
  requisitar,
  textoDoDetalhe,
} from "./cliente";

describe("textoDoDetalhe", () => {
  it("devolve o detail do FastAPI como veio", () => {
    expect(textoDoDetalhe({ detail: "o UNO não aceita cancelamento" }, 409)).toBe(
      "o UNO não aceita cancelamento",
    );
  });

  it("422 do Pydantic vira uma linha por campo, sem o 'body'", () => {
    const corpo = {
      detail: [
        { loc: ["body", "criticidade"], msg: "Input should be less than or equal to 3" },
        { loc: ["query", "limite"], msg: "inválido" },
      ],
    };
    expect(textoDoDetalhe(corpo, 422)).toBe(
      "criticidade: Input should be less than or equal to 3; query.limite: inválido",
    );
  });

  it("sem detail fica o código HTTP", () => {
    expect(textoDoDetalhe(null, 502)).toBe("HTTP 502");
    expect(textoDoDetalhe({ linha: "RUA3,AMBULANCIA" }, 504)).toBe("HTTP 504");
  });
});

describe("montarConsulta", () => {
  it("omite vazios e nulos", () => {
    expect(montarConsulta({ a: "x", b: "", c: undefined, d: null, e: 0, f: false })).toBe("?a=x&e=0&f=false");
    expect(montarConsulta({})).toBe("");
  });
});

describe("requisitar", () => {
  it("manda o token no Authorization quando há sessão", async () => {
    const chamadas = fetchFalso({ corpo: { ok: true } });
    definirToken("token-de-teste");

    await requisitar("/semaforos");

    expect(chamadas[0]?.cabecalhos.Authorization).toBe("Bearer token-de-teste");
    expect(chamadas[0]?.url).toBe("/api/v1/semaforos");
  });

  it("sem sessão não manda Authorization", async () => {
    const chamadas = fetchFalso({ corpo: [] });

    await requisitar("/semaforos");

    expect(chamadas[0]?.cabecalhos.Authorization).toBeUndefined();
  });

  it("erro do backend vira ErroApi com o status e o detail", async () => {
    fetchFalso({ status: 409, corpo: { detail: "a API não comanda os cruzamentos da simulação" } });

    const erro = await requisitar("/x", { metodo: "POST", corpo: {} }).catch((e: unknown) => e);

    expect(erro).toBeInstanceOf(ErroApi);
    expect(erro).toMatchObject({ status: 409, detalhe: "a API não comanda os cruzamentos da simulação" });
    expect(mensagemDeErro(erro)).toBe("409 — a API não comanda os cruzamentos da simulação");
  });

  it("401 com token avisa a sessão; 401 sem token (senha errada) não", async () => {
    const recusado = vi.fn();
    quandoTokenRecusado(recusado);

    fetchFalso({ status: 401, corpo: { detail: "usuário ou senha incorretos" } });
    await requisitar("/auth/login", { metodo: "POST", corpo: {} }).catch(() => undefined);
    expect(recusado).not.toHaveBeenCalled();

    definirToken("token-vencido");
    fetchFalso({ status: 401, corpo: { detail: "sessão expirada: entre de novo" } });
    await requisitar("/ocorrencias", { metodo: "POST", corpo: {} }).catch(() => undefined);
    expect(recusado).toHaveBeenCalledOnce();
  });

  it("204 devolve undefined", async () => {
    fetchFalso({ status: 204 });
    await expect(requisitar("/x", { metodo: "DELETE" })).resolves.toBeUndefined();
  });

  it("falha de rede vira status 0 com mensagem legível", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    const erro = await requisitar("/x").catch((e: unknown) => e);

    expect(erro).toMatchObject({ status: 0 });
    expect(mensagemDeErro(erro)).toBe("backend fora do ar ou inalcançável");
  });
});
