// A bancada (PROTO_CRUZ_01) ao vivo: as quatro aproximações S1..S4, o regime do
// UNO, a rua atendida e a fila de um lugar (context/05 §3 e §4.2). Quem decide
// é o UNO; o dashboard só mostra o que a ponte ouviu (context/01 §4).
import type { Sinal } from "../api/tipos";
import type { SemaforoAoVivo } from "../stream/estado";
import { aoVivo } from "../stream/estado";
import { COR_SINAL, hora, NOME_SINAL, sinalDaLetra } from "./formato";
import { Aviso, Cartao } from "./ui";

export const CODIGO_BANCADA = "PROTO_CRUZ_01";

const ORDEM: Sinal[] = ["VERMELHO", "AMARELO", "VERDE"];

export function Luzes({ sinal, rotulo }: { sinal: Sinal | "SEM_DADO"; rotulo: string }) {
  return (
    <div className="flex flex-col items-center gap-1" aria-label={`${rotulo}: ${NOME_SINAL[sinal]}`}>
      <div className="flex flex-col gap-1 rounded-md bg-slate-800 p-1.5">
        {ORDEM.map((cor) => (
          <span
            key={cor}
            className="block h-4 w-4 rounded-full"
            style={{ backgroundColor: sinal === cor ? COR_SINAL[cor] : "#1e293b" }}
          />
        ))}
      </div>
      <span className="text-xs font-medium text-slate-600">{rotulo}</span>
    </div>
  );
}

export function PainelBancada({
  estado,
  agora,
}: {
  estado: SemaforoAoVivo | undefined;
  agora: number;
}) {
  const vivo = estado?.fonte === "BANCADA" && aoVivo(estado.chegou_em, agora);
  return (
    <Cartao titulo="Bancada — PROTO_CRUZ_01">
      {!estado || estado.fonte !== "BANCADA" ? (
        <Aviso tipo="info">
          Sem telemetria da bancada. A ponte está rodando? Na bancada,{" "}
          <code>python -m bridge.main --porta COM3</code>; sem a placa,{" "}
          <code>python -m bridge.main --simulado</code>.
        </Aviso>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex justify-around">
            {[0, 1, 2, 3].map((i) => (
              <Luzes
                key={i}
                sinal={sinalDaLetra(estado.aproximacoes?.[i])}
                rotulo={`S${i + 1} · Rua ${i + 1}`}
              />
            ))}
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            <dt className="text-slate-500">Regime</dt>
            <dd className={estado.regime === "E" ? "font-semibold text-red-700" : ""}>
              {estado.regime === "E" ? "Emergência" : "Ciclo normal"}
            </dd>
            <dt className="text-slate-500">Eixo aberto</dt>
            <dd>
              {estado.fase === 1
                ? "Principal (S1+S2)"
                : estado.fase === 2
                  ? "Transversal (S3+S4)"
                  : estado.regime === "E"
                    ? "— (verde exclusivo)"
                    : "— (all-red)"}
            </dd>
            <dt className="text-slate-500">Rua atendida</dt>
            <dd>{estado.rua_ativa ? `Rua ${estado.rua_ativa}` : "nenhuma"}</dd>
            <dt className="text-slate-500">Fila</dt>
            <dd>{estado.rua_fila ? `Rua ${estado.rua_fila}` : "vazia"}</dd>
            <dt className="text-slate-500">Última telemetria</dt>
            <dd className={vivo ? "" : "font-semibold text-amber-700"}>
              {hora(estado.chegou_em)}
              {!vivo && " — parada"}
            </dd>
          </dl>
        </div>
      )}
    </Cartao>
  );
}
