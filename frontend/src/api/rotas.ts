// Uma função por rota de context/01 §7 que o dashboard usa.
import { requisitar } from "./cliente";
import type {
  FaixaSeedReservada,
  ModoControle,
  Ocorrencia,
  PaginaLogs,
  PedidoSimulacao,
  RespostaLogin,
  RespostaPreempcao,
  ResumoMetricas,
  Semaforo,
  Sessao,
  StatusExecucao,
  TipoVeiculo,
  Veiculo,
} from "./tipos";

export const api = {
  entrar: (usuario: string, senha: string) =>
    requisitar<RespostaLogin>("/auth/login", { metodo: "POST", corpo: { usuario, senha } }),
  sessao: () => requisitar<Sessao>("/auth/sessao"),

  semaforos: () => requisitar<Semaforo[]>("/semaforos"),
  preemptar: (codigo: string, rua: number, veiculo: TipoVeiculo) =>
    requisitar<RespostaPreempcao>(`/semaforos/${encodeURIComponent(codigo)}/preempcao`, {
      metodo: "POST",
      corpo: { rua, veiculo },
    }),
  cancelarPreempcao: (codigo: string) =>
    requisitar<void>(`/semaforos/${encodeURIComponent(codigo)}/preempcao`, { metodo: "DELETE" }),

  veiculos: () => requisitar<Veiculo[]>("/veiculos"),
  ocorrenciasAtivas: () =>
    requisitar<Ocorrencia[]>("/ocorrencias", { consulta: { ativas: true } }),
  abrirOcorrencia: (id_veiculo: number, criticidade: number, descricao: string | null) =>
    requisitar<Ocorrencia>("/ocorrencias", {
      metodo: "POST",
      corpo: { id_veiculo, criticidade, descricao, origem: "OPERADOR" },
    }),
  encerrarOcorrencia: (id: number) =>
    requisitar<Ocorrencia>(`/ocorrencias/${id}/encerramento`, { metodo: "POST" }),

  logs: (filtros: FiltrosLogs, limite: number, deslocamento: number) =>
    requisitar<PaginaLogs>("/logs/prioridade", {
      consulta: { ...filtros, limite, deslocamento },
    }),

  metricas: () => requisitar<ResumoMetricas>("/metricas/resumo"),

  simulacoes: () => requisitar<PedidoSimulacao[]>("/simulacoes"),
  seedsReservadas: () => requisitar<FaixaSeedReservada[]>("/simulacoes/seeds-reservadas"),
  pedirSimulacao: (pedido: {
    cenario: string;
    modo: ModoControle;
    seed: number;
    duracao_s: number | null;
    velocidade: number | null;
  }) => requisitar<PedidoSimulacao>("/simulacoes", { metodo: "POST", corpo: pedido }),
};

export interface FiltrosLogs {
  semaforo?: string;
  status_execucao?: StatusExecucao | "";
  veiculo?: string;
  id_correlacao?: string;
  desde?: string;
  ate?: string;
}
