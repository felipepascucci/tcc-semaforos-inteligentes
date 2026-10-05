import "leaflet/dist/leaflet.css";
import "./index.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { ProvedorSessao } from "./auth/sessao";

const raiz = document.getElementById("raiz");
if (!raiz) throw new Error("index.html sem #raiz");

createRoot(raiz).render(
  <StrictMode>
    <ProvedorSessao>
      <App />
    </ProvedorSessao>
  </StrictMode>,
);
