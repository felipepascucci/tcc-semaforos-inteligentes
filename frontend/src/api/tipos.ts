// Os contratos da API — espelho dos schemas Pydantic de backend/app/schemas/
// (context/01 §7). Mudou lá, muda aqui.

export type TipoVeiculo = "AMBULANCIA" | "BOMBEIRO" | "POLICIA";
export type StatusOperacao = "ATIVO" | "INATIVO" | "MANUTENCAO" | "FALHA";
export type StatusExecucao =
  | "SUCESSO"
  | "FALHA"
  | "TIMEOUT"
  | "CONFLITO_ADIADO"
  | "ABORTADO_SEGURANCA";
export type ModoControle = "FIXO" | "PREEMPCAO" | "PREEMPCAO_COMPENSADA";
export type Sinal = "VERDE" | "AMARELO" | "VERMELHO";

export const TIPOS_VEICULO: TipoVeiculo[] = ["AMBULANCIA", "BOMBEIRO", "POLICIA"];
export const STATUS_EXECUCAO: StatusExecucao[] = [
  "SUCESSO",
  "FALHA",
  "TIMEOUT",
  "CONFLITO_ADIADO",
  "ABORTADO_SEGURANCA",
];
export const MODOS_CONTROLE: ModoControle[] = ["FIXO", "PREEMPCAO", "PREEMPCAO_COMPENSADA"];

/** Criticidade da ocorrência (P20): menor é mais crítico. */
export const CRITICIDADES = [
  { nivel: 1, nome: "RISCO_VIDA", rotulo: "1 — Risco à vida" },
  { nivel: 2, nome: "RISCO_COLETIVO", rotulo: "2 — Risco coletivo" },
  { nivel: 3, nome: "URGENCIA", rotulo: "3 — Urgência" },
] as const;

export function rotuloCriticidade(nivel: number): string {
  return CRITICIDADES.find((c) => c.nivel === nivel)?.rotulo ?? `nível ${nivel}`;
}

// --- /auth ---------------------------------------------------------------

export interface Sessao {
  usuario: string;
  perfil: string;
  expira_em: string;
}

export interface RespostaLogin extends Sessao {
  access_token: string;
  token_type: "bearer";
}

// --- /semaforos ------------------------------------------------------------

/** `ao_vivo` da simulação: o que o executor transmitiu por último. */
export interface AoVivoSimulacao {
  fonte: "SIMULACAO";
  id: string;
  fase: number;
  sinal: Sinal;
  em_preempcao: boolean;
  t_simulacao: number;
  recebido_em: string | null;
}

/** `ao_vivo` da bancada: a última `ST` do UNO, traduzida (context/01 §7). */
export interface AoVivoBancada {
  fonte: "BANCADA";
  id: string;
  fase: number | null;
  estado: Sinal;
  em_preempcao: boolean;
  aproximacoes: string;
  regime: string;
  /** 1..4; nula quando nenhuma. */
  rua_ativa: number | null;
  rua_fila: number | null;
  /** A criticidade que o UNO tem para cada tipo; 0 é sem ocorrência (2026-10-06). */
  autorizacoes: Record<string, number> | null;
  recebido_em: string;
}

export interface Semaforo {
  id_semaforo: number;
  codigo_externo: string;
  descricao: string | null;
  latitude: string;
  longitude: string;
  tempo_ciclo: number;
  status_operacao: StatusOperacao;
  estado_atual: string;
  ao_vivo: AoVivoSimulacao | AoVivoBancada | null;
}

export interface RespostaPreempcao {
  linha: string;
  decisao: string | null;
  t_decisao: string | null;
}

// --- /veiculos e /ocorrencias -------------------------------------------------

export interface Veiculo {
  id_veiculo: number;
  placa: string;
  tipo: TipoVeiculo;
  identificacao: string | null;
  status_operacional: StatusOperacao;
  tags: { uid: string; ativo: boolean }[];
  em_servico: boolean;
}

export interface Ocorrencia {
  id_ocorrencia: number;
  id_veiculo: number;
  criticidade: number;
  descricao: string | null;
  origem: string;
  aberta_em: string;
  encerrada_em: string | null;
  aberta: boolean;
}

// --- /logs/prioridade --------------------------------------------------------

export interface LogPrioridade {
  id_log: number;
  id_correlacao: string;
  codigo_semaforo: string;
  fk_veiculo: number | null;
  fk_execucao: number | null;
  timestamp_inicio: string;
  timestamp_fim: string | null;
  status_execucao: StatusExecucao;
  motivo: string | null;
  fase_anterior: number | null;
  fase_aplicada: number | null;
}

export interface PaginaLogs {
  total: number;
  limite: number;
  deslocamento: number;
  itens: LogPrioridade[];
}

// --- /metricas/resumo ---------------------------------------------------------

export interface ResumoMetricas {
  priorizacoes: { total: number; por_status: Record<string, number> };
  deteccoes: { total: number; reconhecidas: number; autorizadas: number };
  ocorrencias_ativas: number;
  latencia: {
    simulacao: { n: number; p95_decisao_ms: number | null; p99_decisao_ms: number | null };
    hardware: {
      n: number;
      min_total_ms: number | null;
      mediana_total_ms: number | null;
      max_total_ms: number | null;
    };
  };
  simulacoes: { execucoes: number; pedidos_por_status: Record<string, number> };
  ao_vivo: { bancada: boolean; simulacao: boolean };
}

// --- /simulacoes --------------------------------------------------------------

export type StatusPedido = "PENDENTE" | "RODANDO" | "CONCLUIDA" | "FALHA";

export interface PedidoSimulacao {
  id_pedido: number;
  nome_cenario: string;
  modo: ModoControle;
  seed: number;
  duracao_s: number | null;
  /** Múltiplo do tempo real; nula é a velocidade máxima (Bloco 7). */
  velocidade: number | null;
  status: StatusPedido;
  mensagem: string | null;
  resumo: Record<string, unknown> | null;
  criado_em: string;
  iniciado_em: string | null;
  finalizado_em: string | null;
  execucao: { id_execucao: number } | null;
}
