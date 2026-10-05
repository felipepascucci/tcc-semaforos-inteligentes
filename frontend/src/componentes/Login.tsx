// Login do operador (context/02 §6). Uma credencial, a do .env do backend.
import { useState } from "react";
import type { FormEvent } from "react";

import { mensagemDeErro } from "../api/cliente";
import { useSessao } from "../auth/sessao";
import { Aviso, Campo, ESTILO_ENTRADA } from "./ui";

export function Login() {
  const { entrar, aviso } = useSessao();
  const [usuario, setUsuario] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setEnviando(true);
    setErro(null);
    try {
      await entrar(usuario, senha);
    } catch (falha) {
      setErro(mensagemDeErro(falha));
      setEnviando(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <form
        onSubmit={enviar}
        className="flex w-full max-w-sm flex-col gap-4 rounded-lg border border-slate-200 bg-white p-6 shadow"
      >
        <div>
          <h1 className="text-lg font-semibold">Painel do operador</h1>
          <p className="text-sm text-slate-500">
            Controle dinâmico de semáforos com prioridade para veículos de emergência
          </p>
        </div>
        {aviso && <Aviso tipo="info">{aviso}</Aviso>}
        <Campo rotulo="Usuário">
          <input
            className={ESTILO_ENTRADA}
            value={usuario}
            onChange={(e) => setUsuario(e.target.value)}
            autoComplete="username"
            required
          />
        </Campo>
        <Campo rotulo="Senha">
          <input
            className={ESTILO_ENTRADA}
            type="password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            autoComplete="current-password"
            required
          />
        </Campo>
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        <button
          type="submit"
          disabled={enviando}
          className="rounded bg-slate-800 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {enviando ? "Entrando…" : "Entrar"}
        </button>
      </form>
    </main>
  );
}
