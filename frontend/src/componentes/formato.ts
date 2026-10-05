// Formatação para a tela. A conversão de m/s para km/h acontece aqui, e só
// aqui: o backend e o SUMO falam m/s (context/08 §3).
import type { Sinal } from "../api/tipos";

export const MS_PARA_KMH = 3.6;

export function kmh(velocidadeMs: number): string {
  return `${(velocidadeMs * MS_PARA_KMH).toFixed(0)} km/h`;
}

export function hora(instante: string | number | null | undefined): string {
  if (instante === null || instante === undefined) return "—";
  const data = new Date(instante);
  return Number.isNaN(data.getTime()) ? "—" : data.toLocaleTimeString("pt-BR");
}

export function dataHora(instante: string | null | undefined): string {
  if (!instante) return "—";
  const data = new Date(instante);
  return Number.isNaN(data.getTime()) ? "—" : data.toLocaleString("pt-BR");
}

/** Cor de preenchimento do sinal no mapa e nos painéis. */
export const COR_SINAL: Record<Sinal | "SEM_DADO", string> = {
  VERDE: "#16a34a",
  AMARELO: "#eab308",
  VERMELHO: "#dc2626",
  SEM_DADO: "#94a3b8",
};

/** Cruzamento em preempção. Azul, e não vermelho, para não se confundir com o sinal. */
export const COR_PREEMPCAO = "#2563eb";

/** Letra da telemetria do UNO (`R`, `Y`, `G`) para o sinal. */
export function sinalDaLetra(letra: string | undefined): Sinal | "SEM_DADO" {
  switch (letra) {
    case "G":
      return "VERDE";
    case "Y":
      return "AMARELO";
    case "R":
      return "VERMELHO";
    default:
      return "SEM_DADO";
  }
}

export const NOME_SINAL: Record<Sinal | "SEM_DADO", string> = {
  VERDE: "verde",
  AMARELO: "amarelo",
  VERMELHO: "vermelho",
  SEM_DADO: "sem dado",
};

export const NOME_TIPO: Record<string, string> = {
  AMBULANCIA: "Ambulância",
  BOMBEIRO: "Bombeiro",
  POLICIA: "Polícia",
};
