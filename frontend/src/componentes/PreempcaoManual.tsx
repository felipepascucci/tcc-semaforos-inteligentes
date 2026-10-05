// Preempção manual (context/01 §7). Só a bancada tem atuador ligado ao backend,
// pela injeção da ponte, com o fio do NodeMCU solto do RX (context/05 §6). Nos
// CRUZ_xx e no cancelamento a resposta é 409, e a tela mostra o motivo que o
// backend deu, não um erro genérico.
import { useState } from "react";

import { ErroApi, mensagemDeErro } from "../api/cliente";
import { api } from "../api/rotas";
import { TIPOS_VEICULO } from "../api/tipos";
import type { RespostaPreempcao, Semaforo, TipoVeiculo } from "../api/tipos";
import { NOME_TIPO } from "./formato";
import { CODIGO_BANCADA } from "./PainelBancada";
import { Aviso, Botao, Campo, Cartao, ESTILO_ENTRADA } from "./ui";

type Resultado = { tipo: "sucesso" | "erro"; texto: string };

const SEM_DECISAO =
  "O UNO não decidiu no prazo. A injeção exige o fio do NodeMCU receptor solto do RX do UNO (context/05 §6).";

export function descreverDecisao(resposta: RespostaPreempcao): string {
  return `UNO decidiu ${resposta.decisao ?? "—"} para a linha "${resposta.linha}".`;
}

export function PreempcaoManual({ semaforos }: { semaforos: Semaforo[] }) {
  const [codigo, setCodigo] = useState(CODIGO_BANCADA);
  const [rua, setRua] = useState(1);
  const [veiculo, setVeiculo] = useState<TipoVeiculo>("AMBULANCIA");
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [ocupado, setOcupado] = useState(false);

  async function executar(acao: () => Promise<string>) {
    setOcupado(true);
    setResultado(null);
    try {
      setResultado({ tipo: "sucesso", texto: await acao() });
    } catch (erro) {
      const texto = erro instanceof ErroApi && erro.status === 504 ? SEM_DECISAO : mensagemDeErro(erro);
      setResultado({ tipo: "erro", texto });
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Cartao titulo="Preempção manual">
      <div className="flex flex-col gap-3">
        <p className="text-xs text-slate-500">
          Só o {CODIGO_BANCADA} aceita, pela injeção da ponte. A emergência termina sozinha (I6):
          o cancelamento é recusado pelo backend, com o motivo.
        </p>
        <div className="grid grid-cols-3 gap-2">
          <Campo rotulo="Cruzamento">
            <select className={ESTILO_ENTRADA} value={codigo} onChange={(e) => setCodigo(e.target.value)}>
              {semaforos.map((s) => (
                <option key={s.id_semaforo} value={s.codigo_externo}>
                  {s.codigo_externo}
                </option>
              ))}
            </select>
          </Campo>
          <Campo rotulo="Rua (S1..S4)">
            <select className={ESTILO_ENTRADA} value={rua} onChange={(e) => setRua(Number(e.target.value))}>
              {[1, 2, 3, 4].map((n) => (
                <option key={n} value={n}>
                  Rua {n}
                </option>
              ))}
            </select>
          </Campo>
          <Campo rotulo="Veículo">
            <select
              className={ESTILO_ENTRADA}
              value={veiculo}
              onChange={(e) => setVeiculo(e.target.value as TipoVeiculo)}
            >
              {TIPOS_VEICULO.map((t) => (
                <option key={t} value={t}>
                  {NOME_TIPO[t]}
                </option>
              ))}
            </select>
          </Campo>
        </div>
        <div className="flex gap-2">
          <Botao
            disabled={ocupado}
            onClick={() =>
              executar(async () => descreverDecisao(await api.preemptar(codigo, rua, veiculo)))
            }
          >
            Solicitar preempção
          </Botao>
          <Botao
            variante="secundario"
            disabled={ocupado}
            onClick={() =>
              executar(async () => {
                await api.cancelarPreempcao(codigo);
                return "Preempção cancelada.";
              })
            }
          >
            Cancelar preempção
          </Botao>
        </div>
        {resultado && <Aviso tipo={resultado.tipo}>{resultado.texto}</Aviso>}
      </div>
    </Cartao>
  );
}
