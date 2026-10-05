/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend fora da mesma origem, sem proxy. Vazio: a mesma origem. */
  readonly VITE_API_URL?: string;
}
