// Sessão do operador (context/02 §6: JWT simples, um perfil). O token fica no
// localStorage do navegador para sobreviver a um F5; é conveniência, não estado
// que precise ser confiável, então qualquer falha de leitura vira "sem sessão".
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { definirToken, quandoTokenRecusado } from "../api/cliente";
import { api } from "../api/rotas";

const CHAVE = "tcc.sessao.operador";

export interface SessaoOperador {
  token: string;
  usuario: string;
  expira_em: string;
}

function valida(sessao: SessaoOperador | null, agora = Date.now()): SessaoOperador | null {
  if (!sessao?.token || !sessao.expira_em) return null;
  return Date.parse(sessao.expira_em) > agora ? sessao : null;
}

export function lerSessaoSalva(): SessaoOperador | null {
  try {
    const bruta = localStorage.getItem(CHAVE);
    return valida(bruta ? (JSON.parse(bruta) as SessaoOperador) : null);
  } catch {
    return null;
  }
}

function salvar(sessao: SessaoOperador | null): void {
  try {
    if (sessao) localStorage.setItem(CHAVE, JSON.stringify(sessao));
    else localStorage.removeItem(CHAVE);
  } catch {
    // Sem armazenamento (janela privada, bloqueio): a sessão vale até o F5.
  }
}

interface ContextoSessao {
  sessao: SessaoOperador | null;
  aviso: string | null;
  entrar: (usuario: string, senha: string) => Promise<void>;
  sair: (aviso?: string) => void;
}

const Contexto = createContext<ContextoSessao | null>(null);

export function ProvedorSessao({ children }: { children: ReactNode }) {
  const [sessao, setSessao] = useState<SessaoOperador | null>(() => {
    const salva = lerSessaoSalva();
    definirToken(salva?.token ?? null); // antes do primeiro render dos filhos
    return salva;
  });
  const [aviso, setAviso] = useState<string | null>(null);

  const sair = useCallback((motivo?: string) => {
    definirToken(null);
    salvar(null);
    setSessao(null);
    setAviso(motivo ?? null);
  }, []);

  const entrar = useCallback(async (usuario: string, senha: string) => {
    const resposta = await api.entrar(usuario, senha);
    const nova = {
      token: resposta.access_token,
      usuario: resposta.usuario,
      expira_em: resposta.expira_em,
    };
    definirToken(nova.token);
    salvar(nova);
    setAviso(null);
    setSessao(nova);
  }, []);

  useEffect(() => {
    quandoTokenRecusado(() => sair("Sessão expirada ou inválida: entre de novo."));
    return () => quandoTokenRecusado(null);
  }, [sair]);

  // Um token guardado pode ter sido invalidado no backend (segredo trocado).
  // Só ao abrir: depois, quem descobre o token recusado é a própria escrita, e
  // o 401 dela chama `quandoTokenRecusado`.
  const [tokenDaAbertura] = useState(sessao?.token);
  useEffect(() => {
    if (tokenDaAbertura) api.sessao().catch(() => undefined);
  }, [tokenDaAbertura]);

  // O token expira sozinho depois de 8 h; a tela volta ao login na hora certa.
  useEffect(() => {
    if (!sessao) return;
    const restante = Date.parse(sessao.expira_em) - Date.now();
    const temporizador = setTimeout(
      () => sair("Sessão expirada: entre de novo."),
      Math.max(restante, 0),
    );
    return () => clearTimeout(temporizador);
  }, [sessao, sair]);

  const valor = useMemo(() => ({ sessao, aviso, entrar, sair }), [sessao, aviso, entrar, sair]);
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useSessao(): ContextoSessao {
  const contexto = useContext(Contexto);
  if (!contexto) throw new Error("useSessao fora do ProvedorSessao");
  return contexto;
}
