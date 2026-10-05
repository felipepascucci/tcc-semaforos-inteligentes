// Peças visuais repetidas pelas telas.
import type { ButtonHTMLAttributes, ReactNode } from "react";

export function Cartao({
  titulo,
  acao,
  children,
  className = "",
}: {
  titulo: string;
  acao?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-lg border border-slate-200 bg-white shadow-sm ${className}`}>
      <header className="flex items-center justify-between border-b border-slate-100 px-4 py-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-600">{titulo}</h2>
        {acao}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Aviso({
  tipo,
  children,
}: {
  tipo: "erro" | "sucesso" | "info";
  children: ReactNode;
}) {
  const cores = {
    erro: "border-red-300 bg-red-50 text-red-800",
    sucesso: "border-green-300 bg-green-50 text-green-800",
    info: "border-slate-300 bg-slate-50 text-slate-700",
  }[tipo];
  return (
    <p role={tipo === "erro" ? "alert" : "status"} className={`rounded border px-3 py-2 text-sm ${cores}`}>
      {children}
    </p>
  );
}

export function Botao({
  children,
  variante = "primario",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variante?: "primario" | "secundario" | "perigo" }) {
  const cores = {
    primario: "bg-slate-800 text-white hover:bg-slate-700",
    secundario: "border border-slate-300 bg-white text-slate-800 hover:bg-slate-50",
    perigo: "bg-red-700 text-white hover:bg-red-600",
  }[variante];
  return (
    <button
      type="button"
      {...props}
      className={`rounded px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50 ${cores} ${props.className ?? ""}`}
    >
      {children}
    </button>
  );
}

export function Campo({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium text-slate-700">{rotulo}</span>
      {children}
    </label>
  );
}

export const ESTILO_ENTRADA =
  "rounded border border-slate-300 bg-white px-2 py-1.5 text-sm focus:border-slate-500 focus:outline-none";
