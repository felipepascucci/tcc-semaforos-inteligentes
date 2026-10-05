// Estado ao vivo do dashboard, montado a partir do WebSocket /api/v1/stream
// (context/01 §7). Função pura: recebe o estado e uma mensagem, devolve o
// estado novo. É o que os testes do Vitest exercitam sem rede.
//
// Mensagens: `estado_semaforo`, `posicao_ve`, `evento` e `metrica`, no
// envelope {"tipo", "dados"}. Duas extensões do Bloco 6:
//   * bancada (PROTO_CRUZ_01): `aproximacoes` ("RRGR", S1..S4), `regime`,
//     `rua_ativa`, `rua_fila`; `fase` nula em emergência e no all-red;
//   * simulação: `posicao_ve` com o id do SUMO e lat/lon.

import type { Sinal } from "../api/tipos";

export type Fonte = "BANCADA" | "SIMULACAO";

export interface SemaforoAoVivo {
  id: string;
  fonte: Fonte;
  fase: number | null;
  estado: Sinal;
  em_preempcao: boolean;
  /** Só na bancada: as cores de S1..S4, `R`, `Y` ou `G`. */
  aproximacoes?: string;
  /** Só na bancada: `C` ciclo, `E` emergência. */
  regime?: string;
  /** Só na bancada: 1..4, ou 0 se nenhuma (o backend manda nula). */
  rua_ativa?: number;
  rua_fila?: number;
  t_simulacao?: number;
  /** Relógio do navegador na chegada, em ms. */
  chegou_em: number;
}

export interface PosicaoVe {
  id: string;
  tipo?: string;
  criticidade?: number;
  lat: number;
  lon: number;
  /** m/s, como o backend manda; a conversão para km/h fica na tela. */
  velocidade_ms: number;
  t_simulacao?: number;
  chegou_em: number;
}

export interface EventoAoVivo {
  chave: number;
  nivel: string;
  texto: string;
  origem?: string;
  chegou_em: number;
}

export interface AmostraLatencia {
  origem: string;
  latencia_ms: number;
  chegou_em: number;
}

export interface MetricaAoVivo {
  origem: string;
  latencia_ms: number | null;
  priorizacoes_ativas: number;
  cenario?: string;
  modo?: string;
  seed?: number;
  /** Só na simulação: o tempo simulado e o múltiplo do tempo real (nulo é o máximo). */
  t_simulacao?: number;
  velocidade?: number | null;
  chegou_em: number;
}

/** Os demais veículos da simulação, numa fotografia só (Bloco 7). */
export interface TrafegoAoVivo {
  posicoes: [number, number][];
  t_simulacao?: number;
  chegou_em: number;
}

export interface EstadoStream {
  semaforos: Record<string, SemaforoAoVivo>;
  ves: Record<string, PosicaoVe>;
  trafego: TrafegoAoVivo | null;
  /** Do mais novo para o mais antigo. */
  eventos: EventoAoVivo[];
  metricas: Record<string, MetricaAoVivo>;
  /** Do mais antigo para o mais novo, para o gráfico. */
  latencias: AmostraLatencia[];
  mensagens: number;
  invalidas: number;
}

export const LIMITE_EVENTOS = 200;
export const LIMITE_LATENCIAS = 300;
/** Sem atualização há mais que isto, o dado deixa de ser "ao vivo". */
export const VALIDADE_MS = 5000;

export const ESTADO_INICIAL: EstadoStream = {
  semaforos: {},
  ves: {},
  trafego: null,
  eventos: [],
  metricas: {},
  latencias: [],
  mensagens: 0,
  invalidas: 0,
};

type Dados = Record<string, unknown>;

const SINAIS: readonly string[] = ["VERDE", "AMARELO", "VERMELHO"];

function numero(valor: unknown): number | undefined {
  return typeof valor === "number" && Number.isFinite(valor) ? valor : undefined;
}

function texto(valor: unknown): string | undefined {
  return typeof valor === "string" ? valor : undefined;
}

function semaforo(dados: Dados, agora: number): SemaforoAoVivo | null {
  const id = texto(dados.id);
  const estado = texto(dados.estado);
  if (!id || !estado || !SINAIS.includes(estado)) return null;
  const bancada = typeof dados.aproximacoes === "string";
  return {
    id,
    fonte: bancada ? "BANCADA" : "SIMULACAO",
    fase: numero(dados.fase) ?? null,
    estado: estado as Sinal,
    em_preempcao: dados.em_preempcao === true,
    ...(bancada && {
      aproximacoes: dados.aproximacoes as string,
      regime: texto(dados.regime),
      rua_ativa: numero(dados.rua_ativa) ?? 0,
      rua_fila: numero(dados.rua_fila) ?? 0,
    }),
    t_simulacao: numero(dados.t_simulacao),
    chegou_em: agora,
  };
}

function posicao(dados: Dados, agora: number): PosicaoVe | null {
  const id = dados.id_veiculo;
  const lat = numero(dados.lat);
  const lon = numero(dados.lon);
  if ((typeof id !== "string" && typeof id !== "number") || lat === undefined || lon === undefined)
    return null;
  return {
    id: String(id),
    tipo: texto(dados.tipo),
    criticidade: numero(dados.criticidade),
    lat,
    lon,
    velocidade_ms: numero(dados.velocidade) ?? 0,
    t_simulacao: numero(dados.t_simulacao),
    chegou_em: agora,
  };
}

/** Aplica uma mensagem do WebSocket. Mensagem inválida só conta, não quebra a tela. */
export function reduzirStream(estado: EstadoStream, bruta: string, agora: number): EstadoStream {
  let mensagem: { tipo?: unknown; dados?: unknown };
  try {
    mensagem = JSON.parse(bruta);
  } catch {
    return { ...estado, invalidas: estado.invalidas + 1 };
  }
  const dados = mensagem.dados as Dados | undefined;
  const invalida = { ...estado, invalidas: estado.invalidas + 1 };
  if (typeof dados !== "object" || dados === null) return invalida;
  const contado = { ...estado, mensagens: estado.mensagens + 1 };

  switch (mensagem.tipo) {
    case "estado_semaforo": {
      const novo = semaforo(dados, agora);
      if (!novo) return invalida;
      return { ...contado, semaforos: { ...estado.semaforos, [novo.id]: novo } };
    }
    case "posicao_ve": {
      const novo = posicao(dados, agora);
      if (!novo) return invalida;
      return { ...contado, ves: { ...estado.ves, [novo.id]: novo } };
    }
    case "evento": {
      const evento: EventoAoVivo = {
        chave: estado.mensagens,
        nivel: texto(dados.nivel) ?? "INFO",
        texto: texto(dados.texto) ?? "(evento sem texto)",
        origem: texto(dados.origem),
        chegou_em: agora,
      };
      return { ...contado, eventos: [evento, ...estado.eventos].slice(0, LIMITE_EVENTOS) };
    }
    case "metrica": {
      const origem = texto(dados.origem) ?? "DESCONHECIDA";
      const latencia = numero(dados.latencia_ms) ?? null;
      const metrica: MetricaAoVivo = {
        origem,
        latencia_ms: latencia,
        priorizacoes_ativas: numero(dados.priorizacoes_ativas) ?? 0,
        cenario: texto(dados.cenario),
        modo: texto(dados.modo),
        seed: numero(dados.seed),
        t_simulacao: numero(dados.t_simulacao),
        velocidade: numero(dados.velocidade) ?? null,
        chegou_em: agora,
      };
      // A bancada repete a última amostra de H3 em toda telemetria: só uma
      // latência diferente da anterior da mesma origem é amostra nova.
      const anterior = estado.metricas[origem]?.latencia_ms ?? null;
      const nova =
        latencia !== null && (origem !== "BANCADA" || latencia !== anterior)
          ? [...estado.latencias, { origem, latencia_ms: latencia, chegou_em: agora }]
          : estado.latencias;
      return {
        ...contado,
        metricas: { ...estado.metricas, [origem]: metrica },
        latencias: nova.slice(-LIMITE_LATENCIAS),
      };
    }
    case "trafego": {
      if (!Array.isArray(dados.posicoes)) return invalida;
      const posicoes = (dados.posicoes as unknown[]).filter(
        (p): p is [number, number] =>
          Array.isArray(p) && p.length === 2 && numero(p[0]) !== undefined && numero(p[1]) !== undefined,
      );
      return {
        ...contado,
        trafego: { posicoes, t_simulacao: numero(dados.t_simulacao), chegou_em: agora },
      };
    }
    default:
      return invalida;
  }
}

/** O tráfego de fundo, se ainda for fotografia recente. */
export function trafegoAtivo(estado: EstadoStream, agora: number): [number, number][] {
  const trafego = estado.trafego;
  return trafego && agora - trafego.chegou_em < VALIDADE_MS ? trafego.posicoes : [];
}

/** Os VEs com posição recebida há menos de `VALIDADE_MS`. */
export function vesAtivos(estado: EstadoStream, agora: number): PosicaoVe[] {
  return Object.values(estado.ves).filter((ve) => agora - ve.chegou_em < VALIDADE_MS);
}

export function aoVivo(chegouEm: number | undefined, agora: number): boolean {
  return chegouEm !== undefined && agora - chegouEm < VALIDADE_MS;
}
