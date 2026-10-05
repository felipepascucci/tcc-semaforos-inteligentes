// Preparação do Vitest: matchers do jest-dom e limpeza entre testes.
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { definirToken, quandoTokenRecusado } from "../api/cliente";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  definirToken(null);
  quandoTokenRecusado(null);
  localStorage.clear();
  window.location.hash = "";
});
