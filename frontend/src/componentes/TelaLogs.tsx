// Logs de priorização com filtros e paginação (GET /logs/prioridade, RF05). O
// `id_correlacao` reconstrói uma priorização inteira: clicar nele filtra por ele.
import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";

import { mensagemDeErro } from "../api/cliente";
import { api } from "../api/rotas";
import type { FiltrosLogs } from "../api/rotas";
import { STATUS_EXECUCAO } from "../api/tipos";
import type { PaginaLogs, Semaforo, StatusExecucao } from "../api/tipos";
import { dataHora } from "./formato";
import { Aviso, Botao, Campo, Cartao, ESTILO_ENTRADA } from "./ui";

export const POR_PAGINA = 50;

/** `datetime-local` é hora local sem fuso; a API recebe o instante em UTC. */
export function instanteUtc(valorLocal: string): string | undefined {
  if (!valorLocal) return undefined;
  const data = new Date(valorLocal);
  return Number.isNaN(data.getTime()) ? undefined : data.toISOString();
}

interface Formulario {
  semaforo: string;
  status_execucao: StatusExecucao | "";
  veiculo: string;
  id_correlacao: string;
  desde: string;
  ate: string;
}

const VAZIO: Formulario = {
  semaforo: "",
  status_execucao: "",
  veiculo: "",
  id_correlacao: "",
  desde: "",
  ate: "",
};

export function paraFiltros(formulario: Formulario): FiltrosLogs {
  return {
    semaforo: formulario.semaforo || undefined,
    status_execucao: formulario.status_execucao || undefined,
    veiculo: formulario.veiculo.trim() || undefined,
    id_correlacao: formulario.id_correlacao.trim() || undefined,
    desde: instanteUtc(formulario.desde),
    ate: instanteUtc(formulario.ate),
  };
}

const COR_STATUS: Record<StatusExecucao, string> = {
  SUCESSO: "bg-green-100 text-green-800",
  FALHA: "bg-red-100 text-red-800",
  TIMEOUT: "bg-amber-100 text-amber-800",
  CONFLITO_ADIADO: "bg-sky-100 text-sky-800",
  ABORTADO_SEGURANCA: "bg-red-200 text-red-900",
};

export function TelaLogs({ semaforos }: { semaforos: Semaforo[] }) {
  const [formulario, setFormulario] = useState<Formulario>(VAZIO);
  const [filtros, setFiltros] = useState<FiltrosLogs>({});
  const [pagina, setPagina] = useState(0);
  const [dados, setDados] = useState<PaginaLogs | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      setDados(await api.logs(filtros, POR_PAGINA, pagina * POR_PAGINA));
      setErro(null);
    } catch (falha) {
      setErro(mensagemDeErro(falha));
    } finally {
      setCarregando(false);
    }
  }, [filtros, pagina]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  function aplicar(evento: FormEvent) {
    evento.preventDefault();
    setPagina(0);
    setFiltros(paraFiltros(formulario));
  }

  function filtrarCorrelacao(id: string) {
    const novo = { ...VAZIO, id_correlacao: id };
    setFormulario(novo);
    setPagina(0);
    setFiltros(paraFiltros(novo));
  }

  const campo = (nome: keyof Formulario) => ({
    value: formulario[nome],
    onChange: (e: { target: { value: string } }) =>
      setFormulario((atual) => ({ ...atual, [nome]: e.target.value })),
  });

  const total = dados?.total ?? 0;
  const paginas = Math.max(1, Math.ceil(total / POR_PAGINA));

  return (
    <div className="flex flex-col gap-4">
      <Cartao titulo="Filtros">
        <form onSubmit={aplicar} className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <Campo rotulo="Semáforo">
            <select className={ESTILO_ENTRADA} {...campo("semaforo")}>
              <option value="">Todos</option>
              {semaforos.map((s) => (
                <option key={s.id_semaforo} value={s.codigo_externo}>
                  {s.codigo_externo}
                </option>
              ))}
            </select>
          </Campo>
          <Campo rotulo="Status">
            <select className={ESTILO_ENTRADA} {...campo("status_execucao")}>
              <option value="">Todos</option>
              {STATUS_EXECUCAO.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </Campo>
          <Campo rotulo="Veículo (id)">
            <input className={ESTILO_ENTRADA} inputMode="numeric" {...campo("veiculo")} />
          </Campo>
          <Campo rotulo="Correlação">
            <input className={ESTILO_ENTRADA} placeholder="uuid" {...campo("id_correlacao")} />
          </Campo>
          <Campo rotulo="Desde">
            <input className={ESTILO_ENTRADA} type="datetime-local" {...campo("desde")} />
          </Campo>
          <Campo rotulo="Até">
            <input className={ESTILO_ENTRADA} type="datetime-local" {...campo("ate")} />
          </Campo>
          <div className="col-span-full flex gap-2">
            <Botao type="submit">Filtrar</Botao>
            <Botao
              variante="secundario"
              onClick={() => {
                setFormulario(VAZIO);
                setPagina(0);
                setFiltros({});
              }}
            >
              Limpar
            </Botao>
          </div>
        </form>
      </Cartao>

      <Cartao
        titulo={`Priorizações — ${total} registro${total === 1 ? "" : "s"}`}
        acao={
          <Botao variante="secundario" onClick={() => void carregar()} disabled={carregando}>
            Atualizar
          </Botao>
        }
      >
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-slate-500">
              <tr>
                <th className="py-1 pr-3">Início</th>
                <th className="pr-3">Fim</th>
                <th className="pr-3">Semáforo</th>
                <th className="pr-3">Status</th>
                <th className="pr-3">Veículo</th>
                <th className="pr-3">Fase</th>
                <th className="pr-3">Motivo</th>
                <th>Correlação</th>
              </tr>
            </thead>
            <tbody>
              {dados?.itens.map((log) => (
                <tr key={log.id_log} className="border-t border-slate-100 align-top">
                  <td className="whitespace-nowrap py-1 pr-3">{dataHora(log.timestamp_inicio)}</td>
                  <td className="whitespace-nowrap pr-3">{dataHora(log.timestamp_fim)}</td>
                  <td className="pr-3">{log.codigo_semaforo}</td>
                  <td className="pr-3">
                    <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${COR_STATUS[log.status_execucao]}`}>
                      {log.status_execucao}
                    </span>
                  </td>
                  <td className="pr-3">{log.fk_veiculo ?? "—"}</td>
                  <td className="whitespace-nowrap pr-3">
                    {log.fase_anterior ?? "—"} → {log.fase_aplicada ?? "—"}
                  </td>
                  <td className="pr-3">{log.motivo ?? "—"}</td>
                  <td>
                    <button
                      type="button"
                      className="font-mono text-xs text-sky-700 hover:underline"
                      title="Filtrar por esta priorização"
                      onClick={() => filtrarCorrelacao(log.id_correlacao)}
                    >
                      {log.id_correlacao.slice(0, 8)}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {dados && dados.itens.length === 0 && (
            <p className="py-3 text-sm text-slate-500">Nenhum registro com esses filtros.</p>
          )}
        </div>
        <div className="mt-3 flex items-center gap-2 text-sm">
          <Botao variante="secundario" disabled={pagina === 0} onClick={() => setPagina((p) => p - 1)}>
            Anterior
          </Botao>
          <span>
            Página {pagina + 1} de {paginas}
          </span>
          <Botao
            variante="secundario"
            disabled={pagina + 1 >= paginas}
            onClick={() => setPagina((p) => p + 1)}
          >
            Próxima
          </Botao>
        </div>
      </Cartao>
    </div>
  );
}
