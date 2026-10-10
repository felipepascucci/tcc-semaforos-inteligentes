// Painel "Central" (P20): a central de despacho simulada. Abrir uma ocorrência
// põe o VE em serviço com a criticidade dada; encerrar tira a prioridade.
// Vale no motor, na API, na simulação e, desde 2026-10-06, na bancada: o backend
// leva ao UNO, pela ponte, a criticidade de cada tipo com ocorrência ativa, e o
// UNO decide contra essa lista (context/05 §3.2.1 e §3.3).
import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";

import { mensagemDeErro } from "../api/cliente";
import { api } from "../api/rotas";
import { CRITICIDADES, rotuloCriticidade } from "../api/tipos";
import type { Ocorrencia, Veiculo } from "../api/tipos";
import { dataHora, NOME_TIPO } from "./formato";
import { Aviso, Botao, Campo, Cartao, ESTILO_ENTRADA } from "./ui";

export function PainelCentral() {
  const [veiculos, setVeiculos] = useState<Veiculo[]>([]);
  const [ocorrencias, setOcorrencias] = useState<Ocorrencia[]>([]);
  const [erroCarga, setErroCarga] = useState<string | null>(null);
  const [resultado, setResultado] = useState<{ tipo: "sucesso" | "erro"; texto: string } | null>(null);
  const [idVeiculo, setIdVeiculo] = useState("");
  const [criticidade, setCriticidade] = useState(1);
  const [descricao, setDescricao] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(async () => {
    try {
      const [v, o] = await Promise.all([api.veiculos(), api.ocorrenciasAtivas()]);
      setVeiculos(v);
      setOcorrencias(o);
      setErroCarga(null);
    } catch (erro) {
      setErroCarga(mensagemDeErro(erro));
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const despachaveis = veiculos.filter((v) => v.status_operacional === "ATIVO" && !v.em_servico);
  const porId = new Map(veiculos.map((v) => [v.id_veiculo, v]));

  async function executar(acao: () => Promise<string>) {
    setOcupado(true);
    setResultado(null);
    try {
      setResultado({ tipo: "sucesso", texto: await acao() });
      await carregar();
    } catch (erro) {
      setResultado({ tipo: "erro", texto: mensagemDeErro(erro) });
    } finally {
      setOcupado(false);
    }
  }

  function abrir(evento: FormEvent) {
    evento.preventDefault();
    const id = Number(idVeiculo);
    void executar(async () => {
      const ocorrencia = await api.abrirOcorrencia(id, criticidade, descricao.trim() || null);
      setIdVeiculo("");
      setDescricao("");
      return `Ocorrência ${ocorrencia.id_ocorrencia} aberta: ${porId.get(id)?.placa ?? id} em serviço.`;
    });
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Cartao titulo="Abrir ocorrência">
        <form onSubmit={abrir} className="flex flex-col gap-3">
          <Campo rotulo="Veículo">
            <select
              className={ESTILO_ENTRADA}
              value={idVeiculo}
              onChange={(e) => setIdVeiculo(e.target.value)}
              required
            >
              <option value="">Escolha um veículo livre…</option>
              {despachaveis.map((v) => (
                <option key={v.id_veiculo} value={v.id_veiculo}>
                  {v.placa} — {NOME_TIPO[v.tipo]}
                  {v.identificacao ? ` (${v.identificacao})` : ""}
                </option>
              ))}
            </select>
          </Campo>
          <Campo rotulo="Criticidade">
            <select
              className={ESTILO_ENTRADA}
              value={criticidade}
              onChange={(e) => setCriticidade(Number(e.target.value))}
            >
              {CRITICIDADES.map((c) => (
                <option key={c.nivel} value={c.nivel}>
                  {c.rotulo}
                </option>
              ))}
            </select>
          </Campo>
          <Campo rotulo="Descrição (opcional)">
            <input
              className={ESTILO_ENTRADA}
              value={descricao}
              maxLength={200}
              onChange={(e) => setDescricao(e.target.value)}
            />
          </Campo>
          <div>
            <Botao type="submit" disabled={ocupado || !idVeiculo}>
              Abrir ocorrência
            </Botao>
          </div>
          {resultado && <Aviso tipo={resultado.tipo}>{resultado.texto}</Aviso>}
        </form>
      </Cartao>

      <Cartao
        titulo="Em serviço"
        acao={
          <Botao variante="secundario" onClick={() => void carregar()}>
            Atualizar
          </Botao>
        }
      >
        {erroCarga && <Aviso tipo="erro">{erroCarga}</Aviso>}
        {ocorrencias.length === 0 ? (
          <p className="text-sm text-slate-500">Nenhuma ocorrência aberta: nenhum VE tem prioridade.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {ocorrencias.map((o) => {
              const veiculo = porId.get(o.id_veiculo);
              return (
                <li
                  key={o.id_ocorrencia}
                  className="flex items-center justify-between gap-3 rounded border border-slate-200 px-3 py-2 text-sm"
                >
                  <div>
                    <p className="font-medium">
                      #{o.id_ocorrencia} · {veiculo ? `${veiculo.placa} — ${NOME_TIPO[veiculo.tipo]}` : `veículo ${o.id_veiculo}`}
                    </p>
                    <p className="text-slate-500">
                      {rotuloCriticidade(o.criticidade)} · desde {dataHora(o.aberta_em)}
                      {o.descricao ? ` · ${o.descricao}` : ""}
                    </p>
                  </div>
                  <Botao
                    variante="perigo"
                    disabled={ocupado}
                    onClick={() =>
                      void executar(async () => {
                        await api.encerrarOcorrencia(o.id_ocorrencia);
                        return `Ocorrência ${o.id_ocorrencia} encerrada: o VE deixa de ter prioridade.`;
                      })
                    }
                  >
                    Encerrar
                  </Botao>
                </li>
              );
            })}
          </ul>
        )}
      </Cartao>

      <Cartao titulo="Frota" className="lg:col-span-2">
        <table className="w-full text-left text-sm">
          <thead className="text-slate-500">
            <tr>
              <th className="py-1">Placa</th>
              <th>Tipo</th>
              <th>Identificação</th>
              <th>Situação</th>
              <th>Em serviço</th>
            </tr>
          </thead>
          <tbody>
            {veiculos.map((v) => (
              <tr key={v.id_veiculo} className="border-t border-slate-100">
                <td className="py-1 font-medium">{v.placa}</td>
                <td>{NOME_TIPO[v.tipo]}</td>
                <td>{v.identificacao ?? "—"}</td>
                <td>{v.status_operacional}</td>
                <td>
                  {v.em_servico ? (
                    <span className="rounded bg-red-600 px-2 py-0.5 text-xs font-semibold text-white">SIM</span>
                  ) : (
                    "não"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Cartao>
    </div>
  );
}
