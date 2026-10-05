// Pedidos de simulação (POST /simulacoes, Bloco 6). O backend não roda o SUMO:
// grava o pedido, e o atendente no host o executa com transmissão ao vivo. As
// seeds 1..50 e 101..105 são do experimento e a API as recusa com 422; a tela
// mostra o motivo que veio do backend.
import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";

import { mensagemDeErro } from "../api/cliente";
import { api } from "../api/rotas";
import { MODOS_CONTROLE } from "../api/tipos";
import type { ModoControle, PedidoSimulacao } from "../api/tipos";
import { dataHora } from "./formato";
import { Aviso, Botao, Campo, Cartao, ESTILO_ENTRADA } from "./ui";

/** Os cenários de sim/config/cenarios.yaml; a API valida o nome de qualquer forma. */
const CENARIOS = ["leve", "moderado", "intenso", "multiplas_emergencias"];
const INTERVALO_MS = 3000;

/** Múltiplos do tempo real aceitos pela API; "" é a velocidade máxima (nula). */
const VELOCIDADES = [
  { valor: "1", rotulo: "1x (tempo real)" },
  { valor: "2", rotulo: "2x" },
  { valor: "5", rotulo: "5x" },
  { valor: "10", rotulo: "10x" },
  { valor: "", rotulo: "Máxima (~50x, para não assistir)" },
];

/** Pendente há mais que isto: o atendente, que pega em até 2 s, não está rodando. */
export const ESPERA_ATENDENTE_MS = 10_000;

export function pedidoParado(pedido: PedidoSimulacao, agora: number): boolean {
  return pedido.status === "PENDENTE" && agora - Date.parse(pedido.criado_em) > ESPERA_ATENDENTE_MS;
}

export function rotuloVelocidade(velocidade: number | null): string {
  return velocidade ? `${velocidade}x` : "máxima";
}

/** O que o executor mediu nessa execução: demonstração, não capítulo 5. */
export function textoDoResumo(resumo: Record<string, unknown> | null): string | null {
  if (!resumo) return null;
  const n = (chave: string) => (typeof resumo[chave] === "number" ? (resumo[chave] as number) : null);
  const contagem = (valor: number | null, um: string, varios: string) =>
    `${valor ?? "?"} ${valor === 1 ? um : varios}`;
  const viagens = n("viagens_ve");
  const partes = [
    viagens !== null && contagem(viagens, "viagem de VE concluída", "viagens de VE concluídas"),
    // Sem viagem concluída a média é zero por convenção, não uma travessia.
    viagens ? `travessia média ${n("tempo_medio_travessia_ve_s")} s` : null,
    viagens ? contagem(n("paradas_ve"), "parada", "paradas") : null,
    n("latencia_p95_ms") !== null && `p95 da decisão ${n("latencia_p95_ms")} ms`,
    contagem(n("colisoes"), "colisão", "colisões"),
    contagem(n("violacoes"), "violação", "violações"),
  ];
  return partes.filter(Boolean).join(" · ");
}

const COR_STATUS: Record<string, string> = {
  PENDENTE: "bg-slate-200 text-slate-800",
  RODANDO: "bg-sky-200 text-sky-900",
  CONCLUIDA: "bg-green-200 text-green-900",
  FALHA: "bg-red-200 text-red-900",
};

export function TelaSimulacoes() {
  const [pedidos, setPedidos] = useState<PedidoSimulacao[]>([]);
  const [cenario, setCenario] = useState("moderado");
  const [modo, setModo] = useState<ModoControle>("PREEMPCAO");
  const [seed, setSeed] = useState("900");
  const [duracao, setDuracao] = useState("");
  const [velocidade, setVelocidade] = useState("1");
  const [agora, setAgora] = useState(() => Date.now());
  const [resultado, setResultado] = useState<{ tipo: "sucesso" | "erro"; texto: string } | null>(null);
  const [erroCarga, setErroCarga] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(async () => {
    try {
      setPedidos(await api.simulacoes());
      setAgora(Date.now());
      setErroCarga(null);
    } catch (falha) {
      setErroCarga(mensagemDeErro(falha));
    }
  }, []);

  useEffect(() => {
    void carregar();
    const temporizador = setInterval(() => void carregar(), INTERVALO_MS);
    return () => clearInterval(temporizador);
  }, [carregar]);

  async function pedir(evento: FormEvent) {
    evento.preventDefault();
    setOcupado(true);
    setResultado(null);
    try {
      const pedido = await api.pedirSimulacao({
        cenario,
        modo,
        seed: Number(seed),
        duracao_s: duracao ? Number(duracao) : null,
        velocidade: velocidade ? Number(velocidade) : null,
      });
      setResultado({
        tipo: "sucesso",
        texto: `Pedido ${pedido.id_pedido} na fila. O atendente no host o executa e transmite ao vivo; acompanhe na aba Ao vivo.`,
      });
      await carregar();
    } catch (falha) {
      setResultado({ tipo: "erro", texto: mensagemDeErro(falha) });
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <Cartao titulo="Pedir simulação">
        <form onSubmit={pedir} className="flex flex-col gap-3">
          <Campo rotulo="Cenário">
            <select className={ESTILO_ENTRADA} value={cenario} onChange={(e) => setCenario(e.target.value)}>
              {CENARIOS.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </Campo>
          <Campo rotulo="Modo">
            <select
              className={ESTILO_ENTRADA}
              value={modo}
              onChange={(e) => setModo(e.target.value as ModoControle)}
            >
              {MODOS_CONTROLE.map((m) => (
                <option key={m}>{m}</option>
              ))}
            </select>
          </Campo>
          <Campo rotulo="Seed (fora de 1..50 e 101..105)">
            <input
              className={ESTILO_ENTRADA}
              type="number"
              min={0}
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              required
            />
          </Campo>
          <Campo rotulo="Velocidade">
            <select className={ESTILO_ENTRADA} value={velocidade} onChange={(e) => setVelocidade(e.target.value)}>
              {VELOCIDADES.map((v) => (
                <option key={v.valor} value={v.valor}>
                  {v.rotulo}
                </option>
              ))}
            </select>
          </Campo>
          <Campo rotulo="Duração em s (vazio usa a do cenário, 3600 s)">
            <input
              className={ESTILO_ENTRADA}
              type="number"
              min={1}
              max={3600}
              value={duracao}
              onChange={(e) => setDuracao(e.target.value)}
            />
          </Campo>
          <div>
            <Botao type="submit" disabled={ocupado}>
              Pedir
            </Botao>
          </div>
          {resultado && <Aviso tipo={resultado.tipo}>{resultado.texto}</Aviso>}
          <p className="text-xs text-slate-500">
            Quem executa é o atendente, no host: <code>python -m sim.controlador.atendente</code>.
            Sem ele, o pedido fica pendente. A velocidade não muda o resultado: a mesma seed dá a
            mesma execução.
          </p>
        </form>
      </Cartao>

      <Cartao
        titulo="Pedidos recentes"
        className="lg:col-span-2"
        acao={
          <Botao variante="secundario" onClick={() => void carregar()}>
            Atualizar
          </Botao>
        }
      >
        {erroCarga && <Aviso tipo="erro">{erroCarga}</Aviso>}
        {pedidos.some((p) => pedidoParado(p, agora)) && (
          <div className="mb-3">
            <Aviso tipo="erro">
              Há pedido pendente há mais de 10 s: o atendente não está rodando. No host, na raiz do
              projeto: <code>.\.venv\Scripts\python.exe -m sim.controlador.atendente</code>
            </Aviso>
          </div>
        )}
        {pedidos.length === 0 ? (
          <p className="text-sm text-slate-500">Nenhum pedido ainda.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-slate-500">
                <tr>
                  <th className="py-1 pr-3">#</th>
                  <th className="pr-3">Ponto</th>
                  <th className="pr-3">Status</th>
                  <th className="pr-3">Pedido em</th>
                  <th className="pr-3">Fim</th>
                  <th>Resultado</th>
                </tr>
              </thead>
              <tbody>
                {pedidos.map((p) => (
                  <tr key={p.id_pedido} className="border-t border-slate-100 align-top">
                    <td className="py-1 pr-3">{p.id_pedido}</td>
                    <td className="pr-3">
                      {p.nome_cenario} · {p.modo} · seed {p.seed}
                      {p.duracao_s ? ` · ${p.duracao_s} s` : ""} · {rotuloVelocidade(p.velocidade)}
                    </td>
                    <td className="pr-3">
                      <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${COR_STATUS[p.status] ?? ""}`}>
                        {p.status}
                      </span>
                    </td>
                    <td className="whitespace-nowrap pr-3">{dataHora(p.criado_em)}</td>
                    <td className="whitespace-nowrap pr-3">{dataHora(p.finalizado_em)}</td>
                    <td className="text-xs">{p.mensagem ?? textoDoResumo(p.resumo) ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Cartao>
    </div>
  );
}
