// Cliente HTTP da API (context/01 §7).
//
// O dashboard fala com a mesma origem que o serviu: atrás do nginx em produção,
// atrás do proxy do Vite em desenvolvimento. `VITE_API_URL` só existe para
// apontar para outro backend sem proxy.
//
// Erro do backend nunca vira "erro genérico": o `detail` vem para a tela. É ele
// que explica, por exemplo, por que a preempção manual num CRUZ_xx dá 409.

export const BASE_API = `${import.meta.env.VITE_API_URL ?? ""}/api/v1`;

export class ErroApi extends Error {
  constructor(
    readonly status: number,
    readonly detalhe: string,
  ) {
    super(detalhe);
    this.name = "ErroApi";
  }
}

interface ErroValidacao {
  loc?: (string | number)[];
  msg?: string;
}

/** O texto que a tela mostra para uma resposta de erro do FastAPI. */
export function textoDoDetalhe(corpo: unknown, status: number): string {
  const detalhe = (corpo as { detail?: unknown } | null)?.detail;
  if (typeof detalhe === "string" && detalhe) return detalhe;
  if (Array.isArray(detalhe) && detalhe.length > 0) {
    // 422 do Pydantic: uma linha por campo, sem o "body" do começo do caminho.
    return (detalhe as ErroValidacao[])
      .map((item) => {
        const campo = (item.loc ?? []).filter((parte) => parte !== "body").join(".");
        return campo ? `${campo}: ${item.msg ?? "inválido"}` : (item.msg ?? "inválido");
      })
      .join("; ");
  }
  return `HTTP ${status}`;
}

let tokenAtual: string | null = null;
let aoRecusarToken: (() => void) | null = null;

/** O token que vai no `Authorization` das requisições; `null` desliga. */
export function definirToken(token: string | null): void {
  tokenAtual = token;
}

/** Chamado quando o backend recusa o token (expirado, segredo trocado). */
export function quandoTokenRecusado(callback: (() => void) | null): void {
  aoRecusarToken = callback;
}

type Consulta = Record<string, string | number | boolean | null | undefined>;

export interface Opcoes {
  metodo?: "GET" | "POST" | "DELETE";
  corpo?: unknown;
  consulta?: Consulta;
}

export function montarConsulta(consulta: Consulta | undefined): string {
  if (!consulta) return "";
  const parametros = new URLSearchParams();
  for (const [chave, valor] of Object.entries(consulta)) {
    if (valor === null || valor === undefined || valor === "") continue;
    parametros.set(chave, String(valor));
  }
  const texto = parametros.toString();
  return texto ? `?${texto}` : "";
}

export async function requisitar<T>(caminho: string, opcoes: Opcoes = {}): Promise<T> {
  const cabecalhos: Record<string, string> = { Accept: "application/json" };
  if (opcoes.corpo !== undefined) cabecalhos["Content-Type"] = "application/json";
  const comToken = tokenAtual !== null;
  if (comToken) cabecalhos.Authorization = `Bearer ${tokenAtual}`;

  let resposta: Response;
  try {
    resposta = await fetch(`${BASE_API}${caminho}${montarConsulta(opcoes.consulta)}`, {
      method: opcoes.metodo ?? "GET",
      headers: cabecalhos,
      body: opcoes.corpo === undefined ? undefined : JSON.stringify(opcoes.corpo),
    });
  } catch {
    throw new ErroApi(0, "backend fora do ar ou inalcançável");
  }

  if (resposta.status === 204) return undefined as T;
  const corpo: unknown = await resposta.json().catch(() => null);
  if (!resposta.ok) {
    if (resposta.status === 401 && comToken) aoRecusarToken?.();
    throw new ErroApi(resposta.status, textoDoDetalhe(corpo, resposta.status));
  }
  return corpo as T;
}

/** A mensagem de qualquer erro, para a tela. */
export function mensagemDeErro(erro: unknown): string {
  if (erro instanceof ErroApi) {
    return erro.status ? `${erro.status} — ${erro.detalhe}` : erro.detalhe;
  }
  return erro instanceof Error ? erro.message : String(erro);
}
