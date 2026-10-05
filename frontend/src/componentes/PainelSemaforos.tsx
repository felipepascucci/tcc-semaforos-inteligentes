// Estado de todos os cruzamentos em tempo real (RF04). O cadastro vem de
// GET /semaforos; o estado, do WebSocket.
import type { Semaforo } from "../api/tipos";
import type { SemaforoAoVivo } from "../stream/estado";
import { aoVivo } from "../stream/estado";
import { COR_SINAL, NOME_SINAL } from "./formato";
import { Cartao } from "./ui";

export function PainelSemaforos({
  semaforos,
  aoVivoPorId,
  agora,
}: {
  semaforos: Semaforo[];
  aoVivoPorId: Record<string, SemaforoAoVivo>;
  agora: number;
}) {
  return (
    <Cartao titulo="Semáforos">
      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {semaforos.map((semaforo) => {
          const estado = aoVivoPorId[semaforo.codigo_externo];
          const vivo = estado !== undefined && aoVivo(estado.chegou_em, agora);
          const sinal = vivo ? estado.estado : "SEM_DADO";
          return (
            <li
              key={semaforo.id_semaforo}
              data-testid={`semaforo-${semaforo.codigo_externo}`}
              className={`flex items-center gap-3 rounded border px-3 py-2 ${
                vivo && estado.em_preempcao ? "border-blue-400 bg-blue-50" : "border-slate-200"
              }`}
            >
              <span
                className="h-4 w-4 shrink-0 rounded-full"
                style={{ backgroundColor: COR_SINAL[sinal] }}
                aria-hidden
              />
              <div className="min-w-0 text-sm">
                <p className="font-medium">{semaforo.codigo_externo}</p>
                <p className="text-slate-500">
                  {vivo
                    ? `${NOME_SINAL[sinal]}${estado.fase ? ` · fase ${estado.fase}` : ""}${
                        estado.fonte === "SIMULACAO" && estado.t_simulacao !== undefined
                          ? ` · t = ${estado.t_simulacao.toFixed(1)} s`
                          : ""
                      }`
                    : "sem dado ao vivo"}
                </p>
              </div>
              {vivo && estado.em_preempcao && (
                <span className="ml-auto rounded bg-blue-600 px-2 py-0.5 text-xs font-semibold text-white">
                  PREEMPÇÃO
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </Cartao>
  );
}
