// Métricas do dashboard: o resumo de GET /metricas/resumo e a latência ao vivo
// do WebSocket. É demonstração e auditoria; os números do capítulo 5 saem de
// analysis/, a partir dos CSV (context/07).
//
// As duas latências medem coisas diferentes (decisão P2): RNF01 é a decisão do
// motor, na simulação; H3 é a cadeia fim-a-fim da bancada. Por isso não dividem
// gráfico nem eixo. Desde 2026-10-06 H3 se mede em 100 passagens, com o
// critério no p95, que sai de analysis/ sobre o latencia_bancada.csv
// (context/05 §4.3). GET /metricas/resumo devolve da bancada só mín/mediana/máx
// e o n das amostras gravadas no banco, e é isso que esta tela mostra.
import { useCallback, useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { mensagemDeErro } from "../api/cliente";
import { api } from "../api/rotas";
import { STATUS_EXECUCAO } from "../api/tipos";
import type { ResumoMetricas } from "../api/tipos";
import type { AmostraLatencia, MetricaAoVivo } from "../stream/estado";
import { hora } from "./formato";
import { Aviso, Cartao } from "./ui";

const COR_SERIE = "#2a78d6";
const COR_GRADE = "#e2e8f0";
const COR_EIXO = "#64748b";
const INTERVALO_RESUMO_MS = 5000;

/** Milissegundos com precisão útil: a decisão do motor fica na casa do centésimo. */
export function ms(valor: number | string | null | undefined): string {
  const numero = valor === null || valor === undefined ? Number.NaN : Number(valor);
  if (!Number.isFinite(numero)) return "—";
  return `${numero.toFixed(Math.abs(numero) < 1 ? 3 : 1)} ms`;
}

function Numero({ rotulo, valor, detalhe }: { rotulo: string; valor: string; detalhe?: string }) {
  return (
    <div className="rounded border border-slate-200 px-3 py-2">
      <p className="text-xs uppercase tracking-wide text-slate-500">{rotulo}</p>
      <p className="text-2xl font-semibold tabular-nums">{valor}</p>
      {detalhe && <p className="text-xs text-slate-500">{detalhe}</p>}
    </div>
  );
}

export function PainelMetricas({
  latencias,
  metricas,
}: {
  latencias: AmostraLatencia[];
  metricas: Record<string, MetricaAoVivo>;
}) {
  const [resumo, setResumo] = useState<ResumoMetricas | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    try {
      setResumo(await api.metricas());
      setErro(null);
    } catch (falha) {
      setErro(mensagemDeErro(falha));
    }
  }, []);

  useEffect(() => {
    void carregar();
    const temporizador = setInterval(() => void carregar(), INTERVALO_RESUMO_MS);
    return () => clearInterval(temporizador);
  }, [carregar]);

  const porStatus = STATUS_EXECUCAO.map((status) => ({
    status,
    total: resumo?.priorizacoes.por_status[status] ?? 0,
  }));
  const decisao = latencias
    .filter((a) => a.origem === "SIMULACAO")
    .map((a) => ({ instante: hora(a.chegou_em), latencia_ms: a.latencia_ms }));
  const amostrasH3 = latencias.filter((a) => a.origem === "BANCADA").slice(-10).reverse();
  const simulacao = metricas.SIMULACAO;

  return (
    <div className="flex flex-col gap-4">
      <Aviso tipo="info">
        Painel de demonstração e auditoria. Os números do capítulo 5 saem de <code>analysis/</code>,
        a partir dos CSV das execuções, e não desta tela.
      </Aviso>
      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Numero rotulo="Priorizações registradas" valor={String(resumo?.priorizacoes.total ?? "—")} />
        <Numero rotulo="Ocorrências abertas" valor={String(resumo?.ocorrencias_ativas ?? "—")} />
        <Numero
          rotulo="Detecções V2I (API)"
          valor={String(resumo?.deteccoes.total ?? "—")}
          detalhe={
            resumo
              ? `${resumo.deteccoes.reconhecidas} reconhecidas · ${resumo.deteccoes.autorizadas} autorizadas`
              : undefined
          }
        />
        <Numero
          rotulo="Execuções de simulação"
          valor={String(resumo?.simulacoes.execucoes ?? "—")}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Cartao titulo="Priorizações por desfecho">
          <div className="h-64" aria-label="Gráfico de barras: priorizações por desfecho">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={porStatus} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
                <CartesianGrid vertical={false} stroke={COR_GRADE} />
                <XAxis dataKey="status" tick={{ fontSize: 11, fill: COR_EIXO }} interval={0} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: COR_EIXO }} width={40} />
                <Tooltip cursor={{ fill: "#f1f5f9" }} formatter={(v) => [v, "priorizações"]} />
                <Bar dataKey="total" fill={COR_SERIE} radius={[4, 4, 0, 0]} maxBarSize={48} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <table className="mt-2 w-full text-sm">
            <tbody>
              {porStatus.map((linha) => (
                <tr key={linha.status} className="border-t border-slate-100">
                  <td className="py-0.5 text-slate-600">{linha.status}</td>
                  <td className="text-right tabular-nums">{linha.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Cartao>

        <Cartao titulo="Latência — registrada no banco">
          <div className="flex flex-col gap-3">
            <div>
              <p className="mb-1 text-sm font-medium">Decisão do motor, simulação (RNF01 &lt; 100 ms)</p>
              {resumo && resumo.latencia.simulacao.n === 0 ? (
                <p className="text-sm text-slate-500">
                  Nenhuma amostra no banco: a simulação grava os percentis de cada execução nos CSV
                  de <code>analysis/</code>, e o p95 de cada pedido aparece na aba Simulações.
                </p>
              ) : (
                <div className="grid grid-cols-3 gap-2">
                  <Numero rotulo="p95" valor={ms(resumo?.latencia.simulacao.p95_decisao_ms)} />
                  <Numero rotulo="p99" valor={ms(resumo?.latencia.simulacao.p99_decisao_ms)} />
                  <Numero rotulo="n" valor={String(resumo?.latencia.simulacao.n ?? "—")} />
                </div>
              )}
            </div>
            <div>
              <p className="mb-1 text-sm font-medium">Fim-a-fim, bancada (H3 &lt; 200 ms)</p>
              <div className="grid grid-cols-4 gap-2">
                <Numero rotulo="mín" valor={ms(resumo?.latencia.hardware.min_total_ms)} />
                <Numero rotulo="mediana" valor={ms(resumo?.latencia.hardware.mediana_total_ms)} />
                <Numero rotulo="máx" valor={ms(resumo?.latencia.hardware.max_total_ms)} />
                <Numero rotulo="n" valor={String(resumo?.latencia.hardware.n ?? "—")} />
              </div>
              <p className="mt-1 text-xs text-slate-500">
                O limiar de H3 vale sobre o p95 das 100 passagens, calculado em{" "}
                <code>analysis/</code> a partir do <code>latencia_bancada.csv</code>.
              </p>
            </div>
          </div>
        </Cartao>

        <Cartao titulo="Decisão do motor ao vivo — simulação">
          {decisao.length === 0 ? (
            <p className="text-sm text-slate-500">
              Nenhuma simulação transmitindo. Peça uma na aba Simulações.
            </p>
          ) : (
            <>
              <p className="mb-2 text-xs text-slate-500">
                {simulacao?.cenario} · {simulacao?.modo} · seed {simulacao?.seed} — última
                latência {ms(simulacao?.latencia_ms)}
              </p>
              <div className="h-56" aria-label="Gráfico de linha: latência de decisão ao vivo">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={decisao} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
                    <CartesianGrid vertical={false} stroke={COR_GRADE} />
                    <XAxis dataKey="instante" tick={{ fontSize: 11, fill: COR_EIXO }} minTickGap={40} />
                    <YAxis
                      tick={{ fontSize: 11, fill: COR_EIXO }}
                      width={72}
                      tickFormatter={(v: number) => ms(v)}
                    />
                    <Tooltip formatter={(v) => [ms(Number(v)), "decisão"]} />
                    <Line
                      type="monotone"
                      dataKey="latencia_ms"
                      stroke={COR_SERIE}
                      strokeWidth={2}
                      dot={false}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </>
          )}
        </Cartao>

        <Cartao titulo="Amostras de H3 ao vivo — bancada">
          {amostrasH3.length === 0 ? (
            <p className="text-sm text-slate-500">
              Nenhuma amostra desde que a tela abriu. H3 só é medida com o NodeMCU emissor no USB
              do notebook (context/05 §4.3).
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-slate-500">
                <tr>
                  <th className="text-left">Chegada</th>
                  <th className="text-right">Leitura da tag → PREEMP_INI</th>
                </tr>
              </thead>
              <tbody>
                {amostrasH3.map((a) => (
                  <tr key={a.chegou_em} className="border-t border-slate-100">
                    <td>{hora(a.chegou_em)}</td>
                    <td className="text-right tabular-nums">{ms(a.latencia_ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Cartao>
      </div>
    </div>
  );
}
