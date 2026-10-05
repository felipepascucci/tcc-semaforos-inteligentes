// Login do operador (context/02 §6): sem sessão, a tela é o login; com ela, o
// token vai nas escritas e sobrevive ao F5; token recusado volta ao login.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { requisitar } from "../api/cliente";
import { Login } from "../componentes/Login";
import { fetchFalso } from "../testes/http";
import { lerSessaoSalva, ProvedorSessao, useSessao } from "./sessao";

function Portao() {
  const { sessao } = useSessao();
  return sessao ? <p>logado como {sessao.usuario}</p> : <Login />;
}

function montar() {
  return render(
    <ProvedorSessao>
      <Portao />
    </ProvedorSessao>,
  );
}

const DAQUI_A_UMA_HORA = new Date(Date.now() + 3_600_000).toISOString();

describe("sessão do operador", () => {
  it("credencial errada mostra o motivo e continua no login", async () => {
    fetchFalso({ status: 401, corpo: { detail: "usuário ou senha incorretos" } });
    const usuario = userEvent.setup();
    montar();

    await usuario.type(screen.getByLabelText("Usuário"), "operador");
    await usuario.type(screen.getByLabelText("Senha"), "errada");
    await usuario.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("401 — usuário ou senha incorretos");
    expect(lerSessaoSalva()).toBeNull();
  });

  it("login certo guarda a sessão, e as requisições seguintes levam o token", async () => {
    const chamadas = fetchFalso(
      {
        corpo: {
          access_token: "token-de-teste",
          token_type: "bearer",
          usuario: "operador",
          perfil: "operador",
          expira_em: DAQUI_A_UMA_HORA,
        },
      },
      { corpo: [] },
    );
    const usuario = userEvent.setup();
    montar();

    await usuario.type(screen.getByLabelText("Usuário"), "operador");
    await usuario.type(screen.getByLabelText("Senha"), "senha");
    await usuario.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByText("logado como operador")).toBeInTheDocument();
    expect(chamadas[0]?.corpo).toEqual({ usuario: "operador", senha: "senha" });
    expect(lerSessaoSalva()?.token).toBe("token-de-teste");

    await requisitar("/ocorrencias", { metodo: "POST", corpo: {} });
    expect(chamadas[1]?.cabecalhos.Authorization).toBe("Bearer token-de-teste");
  });

  it("sessão salva e válida abre direto, e o token recusado volta ao login com aviso", async () => {
    localStorage.setItem(
      "tcc.sessao.operador",
      JSON.stringify({ token: "token-salvo", usuario: "operador", expira_em: DAQUI_A_UMA_HORA }),
    );
    fetchFalso(
      { corpo: { usuario: "operador", perfil: "operador", expira_em: DAQUI_A_UMA_HORA } },
      { status: 401, corpo: { detail: "sessão expirada: entre de novo" } },
    );
    montar();

    expect(await screen.findByText("logado como operador")).toBeInTheDocument();

    await requisitar("/ocorrencias", { metodo: "POST", corpo: {} }).catch(() => undefined);

    expect(await screen.findByText(/Sessão expirada ou inválida/)).toBeInTheDocument();
    expect(lerSessaoSalva()).toBeNull();
  });

  it("sessão salva vencida é ignorada", () => {
    localStorage.setItem(
      "tcc.sessao.operador",
      JSON.stringify({ token: "velho", usuario: "operador", expira_em: "2020-01-01T00:00:00Z" }),
    );
    fetchFalso();
    montar();

    expect(screen.getByRole("button", { name: "Entrar" })).toBeInTheDocument();
  });
});
