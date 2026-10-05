// Eventos do WebSocket: decisões do UNO, ocorrências da central e avisos da
// simulação. O backend nunca descarta evento no throttle (context/01 §7).
import type { EventoAoVivo } from "../stream/estado";
import { hora } from "./formato";
import { Cartao } from "./ui";

const COR_NIVEL: Record<string, string> = {
  INFO: "bg-slate-200 text-slate-700",
  WARNING: "bg-amber-200 text-amber-900",
  ERROR: "bg-red-200 text-red-900",
};

export function FeedEventos({ eventos }: { eventos: EventoAoVivo[] }) {
  return (
    <Cartao titulo="Eventos" className="flex flex-col">
      {eventos.length === 0 ? (
        <p className="text-sm text-slate-500">Nenhum evento desde que a tela abriu.</p>
      ) : (
        <ol className="flex max-h-80 flex-col gap-1 overflow-y-auto text-sm">
          {eventos.map((evento) => (
            <li key={evento.chave} className="flex items-start gap-2">
              <span className="w-16 shrink-0 tabular-nums text-slate-500">{hora(evento.chegou_em)}</span>
              <span
                className={`shrink-0 rounded px-1.5 text-xs font-semibold ${COR_NIVEL[evento.nivel] ?? COR_NIVEL.INFO}`}
              >
                {evento.origem ?? evento.nivel}
              </span>
              <span>{evento.texto}</span>
            </li>
          ))}
        </ol>
      )}
    </Cartao>
  );
}
