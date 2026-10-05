// O dashboard (Bloco 7): login, e depois as abas. A aba fica no `#` da URL,
// sem biblioteca de rotas, para um F5 voltar à mesma tela.
import { useEffect, useState } from "react";

import { mensagemDeErro } from "./api/cliente";
import { api } from "./api/rotas";
import type { Semaforo } from "./api/tipos";
import { useSessao } from "./auth/sessao";
import { FeedEventos } from "./componentes/FeedEventos";
import { Login } from "./componentes/Login";
import { MapaMalha } from "./componentes/MapaMalha";
import { CODIGO_BANCADA, PainelBancada } from "./componentes/PainelBancada";
import { PainelCentral } from "./componentes/PainelCentral";
import { PainelMetricas } from "./componentes/PainelMetricas";
import { PainelSemaforos } from "./componentes/PainelSemaforos";
import { PreempcaoManual } from "./componentes/PreempcaoManual";
import { TelaLogs } from "./componentes/TelaLogs";
import { TelaSimulacoes } from "./componentes/TelaSimulacoes";
import { Aviso, Botao } from "./componentes/ui";
import { aoVivo, trafegoAtivo, vesAtivos } from "./stream/estado";
import type { MetricaAoVivo } from "./stream/estado";
import type { Conexao } from "./stream/useStream";
import { useStream } from "./stream/useStream";

export const ABAS = [
  { id: "ao-vivo", nome: "Ao vivo" },
  { id: "central", nome: "Central" },
  { id: "logs", nome: "Logs" },
  { id: "metricas", nome: "Métricas" },
  { id: "simulacoes", nome: "Simulações" },
] as const;
type Aba = (typeof ABAS)[number]["id"];

function abaDoEndereco(): Aba {
  const id = window.location.hash.replace("#", "");
  return ABAS.some((a) => a.id === id) ? (id as Aba) : "ao-vivo";
}

/** Relógio da tela, para o "ao vivo" vencer sem precisar de mensagem nova. */
function useAgora(intervaloMs = 1000): number {
  const [agora, setAgora] = useState(() => Date.now());
  useEffect(() => {
    const temporizador = setInterval(() => setAgora(Date.now()), intervaloMs);
    return () => clearInterval(temporizador);
  }, [intervaloMs]);
  return agora;
}

const ROTULO_CONEXAO: Record<Conexao, { texto: string; cor: string }> = {
  aberta: { texto: "ao vivo", cor: "bg-green-500" },
  conectando: { texto: "conectando…", cor: "bg-amber-400" },
  fechada: { texto: "sem conexão", cor: "bg-red-500" },
};

/** O que está rodando na malha agora, ou como pôr algo para rodar. */
export function FaixaSimulacao({ metrica, agora }: { metrica: MetricaAoVivo | undefined; agora: number }) {
  if (!metrica || !aoVivo(metrica.chegou_em, agora)) {
    return (
      <p className="rounded bg-slate-200 px-3 py-1.5 text-sm text-slate-700">
        Nenhuma simulação transmitindo. Peça uma na aba <a href="#simulacoes" className="underline">Simulações</a>{" "}
        com o atendente rodando no host: <code>python -m sim.controlador.atendente</code>.
      </p>
    );
  }
  return (
    <p className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white">
      Simulação ao vivo: <strong>{metrica.cenario}</strong> · {metrica.modo} · seed {metrica.seed}
      {metrica.t_simulacao !== undefined && ` · t = ${metrica.t_simulacao.toFixed(0)} s`}
      {` · ${metrica.velocidade ? `${metrica.velocidade}x o tempo real` : "velocidade máxima"}`}
    </p>
  );
}

export function App() {
  const { sessao } = useSessao();
  return sessao ? <Painel usuario={sessao.usuario} /> : <Login />;
}

function Painel({ usuario }: { usuario: string }) {
  const { sair } = useSessao();
  const { estado, conexao } = useStream();
  const agora = useAgora();
  const [aba, setAba] = useState<Aba>(abaDoEndereco);
  const [semaforos, setSemaforos] = useState<Semaforo[]>([]);
  const [erroCadastro, setErroCadastro] = useState<string | null>(null);

  useEffect(() => {
    const aoMudar = () => setAba(abaDoEndereco());
    window.addEventListener("hashchange", aoMudar);
    return () => window.removeEventListener("hashchange", aoMudar);
  }, []);

  useEffect(() => {
    api
      .semaforos()
      .then(setSemaforos)
      .catch((erro) => setErroCadastro(mensagemDeErro(erro)));
  }, []);

  const conexaoAtual = ROTULO_CONEXAO[conexao];

  return (
    <div className="min-h-screen">
      <header className="flex flex-wrap items-center gap-4 bg-slate-900 px-6 py-3 text-white">
        <h1 className="font-semibold">Semáforos · Painel do operador</h1>
        <nav className="flex gap-1">
          {ABAS.map((a) => (
            <a
              key={a.id}
              href={`#${a.id}`}
              className={`rounded px-3 py-1 text-sm ${
                aba === a.id ? "bg-white text-slate-900" : "text-slate-200 hover:bg-slate-700"
              }`}
              aria-current={aba === a.id ? "page" : undefined}
            >
              {a.nome}
            </a>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-4 text-sm">
          <span className="flex items-center gap-2" title="WebSocket /api/v1/stream">
            <span className={`h-2.5 w-2.5 rounded-full ${conexaoAtual.cor}`} />
            {conexaoAtual.texto}
          </span>
          <span className="text-slate-300">{usuario}</span>
          <Botao variante="secundario" onClick={() => sair()}>
            Sair
          </Botao>
        </div>
      </header>

      <main className="mx-auto flex max-w-screen-2xl flex-col gap-4 p-4">
        {erroCadastro && <Aviso tipo="erro">Cadastro de semáforos: {erroCadastro}</Aviso>}

        {aba === "ao-vivo" && (
          <>
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
              <div className="flex flex-col gap-2 xl:col-span-2">
                <FaixaSimulacao metrica={estado.metricas.SIMULACAO} agora={agora} />
                <div className="h-[520px]">
                  <MapaMalha
                    aoVivoPorId={estado.semaforos}
                    ves={vesAtivos(estado, agora)}
                    trafego={trafegoAtivo(estado, agora)}
                    agora={agora}
                  />
                </div>
              </div>
              <div className="flex flex-col gap-4">
                <PainelBancada estado={estado.semaforos[CODIGO_BANCADA]} agora={agora} />
                <PreempcaoManual semaforos={semaforos} />
              </div>
            </div>
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
              <div className="xl:col-span-2">
                <PainelSemaforos semaforos={semaforos} aoVivoPorId={estado.semaforos} agora={agora} />
              </div>
              <FeedEventos eventos={estado.eventos} />
            </div>
          </>
        )}
        {aba === "central" && <PainelCentral />}
        {aba === "logs" && <TelaLogs semaforos={semaforos} />}
        {aba === "metricas" && (
          <PainelMetricas latencias={estado.latencias} metricas={estado.metricas} />
        )}
        {aba === "simulacoes" && <TelaSimulacoes />}
      </main>
    </div>
  );
}
