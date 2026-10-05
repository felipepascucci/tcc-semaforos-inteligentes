// Conexão com ws(s)://…/api/v1/stream, com reconexão. O backend já limita a
// 5 Hz (context/01 §7), então cada mensagem vira um render sem acúmulo.
import { useEffect, useReducer, useState } from "react";

import { ESTADO_INICIAL, reduzirStream } from "./estado";

export type Conexao = "conectando" | "aberta" | "fechada";

const ESPERA_INICIAL_MS = 1000;
const ESPERA_MAXIMA_MS = 10000;

/** A URL do stream na mesma origem do dashboard (nginx ou proxy do Vite). */
export function urlDoStream(local: Location = window.location): string {
  const base = import.meta.env.VITE_API_URL as string | undefined;
  if (base) return `${base.replace(/^http/, "ws")}/api/v1/stream`;
  const protocolo = local.protocol === "https:" ? "wss:" : "ws:";
  return `${protocolo}//${local.host}/api/v1/stream`;
}

export type FabricaSocket = (url: string) => WebSocket;

// Fora do componente: uma função nova a cada render reabriria o socket.
const SOCKET_DO_NAVEGADOR: FabricaSocket = (url) => new WebSocket(url);

export function useStream(
  url: string = urlDoStream(),
  criarSocket: FabricaSocket = SOCKET_DO_NAVEGADOR,
) {
  const [estado, despachar] = useReducer(
    (atual: typeof ESTADO_INICIAL, bruta: string) => reduzirStream(atual, bruta, Date.now()),
    ESTADO_INICIAL,
  );
  const [conexao, setConexao] = useState<Conexao>("conectando");

  useEffect(() => {
    let socket: WebSocket | null = null;
    let espera = ESPERA_INICIAL_MS;
    let temporizador: ReturnType<typeof setTimeout> | undefined;
    let encerrado = false;

    const conectar = () => {
      setConexao("conectando");
      socket = criarSocket(url);
      socket.onopen = () => {
        espera = ESPERA_INICIAL_MS;
        setConexao("aberta");
      };
      socket.onmessage = (evento: MessageEvent) => {
        if (typeof evento.data === "string") despachar(evento.data);
      };
      socket.onclose = () => {
        if (encerrado) return;
        setConexao("fechada");
        temporizador = setTimeout(conectar, espera);
        espera = Math.min(espera * 2, ESPERA_MAXIMA_MS);
      };
    };
    conectar();

    return () => {
      encerrado = true;
      clearTimeout(temporizador);
      socket?.close();
    };
  }, [url, criarSocket]);

  return { estado, conexao };
}
