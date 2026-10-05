// Mapa da malha (RF04 e RF06), desenhado a partir da rede SUMO, sem mapa de rua:
// as coordenadas dos cruzamentos são fictícias (db/seeds/dados.yaml). O desenho
// vem de src/malha/malha.json, gerado por `python -m sim.rede.exportar_mapa`.
//
// Cada linha de retenção tem a cor do sinal da sua aproximação. A regra é a de
// core/priorizacao/fases.py: a fase corrente mostra o sinal transmitido, e as
// demais ficam vermelhas. Por cima, o tráfego de fundo (cinza) e os VEs.
import { CircleMarker, MapContainer, Polygon, Polyline, Tooltip } from "react-leaflet";

import type { Sinal } from "../api/tipos";
import malha from "../malha/malha.json";
import type { PosicaoVe, SemaforoAoVivo } from "../stream/estado";
import { aoVivo } from "../stream/estado";
import { COR_PREEMPCAO, COR_SINAL, kmh, NOME_TIPO } from "./formato";

type LatLon = [number, number];

interface Aproximacao {
  via: string;
  fase: number;
  linhas: LatLon[][];
  /** 30 m antes da linha de retenção: a cor legível com a malha inteira na tela. */
  sinal: LatLon;
}

interface Cruzamento {
  id: string;
  centro: LatLon;
  contorno: LatLon[];
  aproximacoes: Aproximacao[];
}

interface Desenho {
  limites: [LatLon, LatLon];
  vias: { id: string; faixas: LatLon[][] }[];
  cruzamentos: Cruzamento[];
}

const DESENHO = malha as unknown as Desenho;

const COR_VIA = "#475569";
const COR_CRUZAMENTO = "#334155";
const COR_TRAFEGO = "#cbd5e1";

export const COR_VE: Record<string, string> = {
  AMBULANCIA: "#ffffff",
  BOMBEIRO: "#f97316",
  POLICIA: "#38bdf8",
};

/** Cor da linha de retenção de uma aproximação servida por `fase`. */
export function sinalDaAproximacao(
  estado: SemaforoAoVivo | undefined,
  fase: number,
  agora: number,
): Sinal | "SEM_DADO" {
  if (!estado || !aoVivo(estado.chegou_em, agora)) return "SEM_DADO";
  return estado.fase === fase ? estado.estado : "VERMELHO";
}

export function MapaMalha({
  aoVivoPorId,
  ves,
  trafego,
  agora,
}: {
  aoVivoPorId: Record<string, SemaforoAoVivo>;
  ves: PosicaoVe[];
  trafego: LatLon[];
  agora: number;
}) {
  return (
    <div className="relative h-full w-full">
      <MapContainer
        bounds={DESENHO.limites}
        boundsOptions={{ padding: [24, 24] }}
        preferCanvas
        attributionControl={false}
        zoomSnap={0.25}
        className="h-full w-full rounded-lg"
        style={{ background: "#0f172a" }}
      >
        {DESENHO.vias.map((via) =>
          via.faixas.map((faixa, i) => (
            <Polyline
              key={`${via.id}-${i}`}
              positions={faixa}
              pathOptions={{ color: COR_VIA, weight: 3, interactive: false }}
            />
          )),
        )}

        {DESENHO.cruzamentos.map((cruzamento) => {
          const estado = aoVivoPorId[cruzamento.id];
          const preempcao = estado !== undefined && aoVivo(estado.chegou_em, agora) && estado.em_preempcao;
          return (
            <Polygon
              key={cruzamento.id}
              positions={cruzamento.contorno}
              pathOptions={{
                color: preempcao ? COR_PREEMPCAO : COR_CRUZAMENTO,
                weight: preempcao ? 4 : 1,
                fillColor: COR_CRUZAMENTO,
                fillOpacity: 1,
              }}
            >
              <Tooltip
                permanent
                direction="top"
                offset={[0, -14]}
                className={preempcao ? "rotulo-cruzamento rotulo-preempcao" : "rotulo-cruzamento"}
              >
                {cruzamento.id}
                {preempcao ? " · preempção" : ""}
              </Tooltip>
            </Polygon>
          );
        })}

        {DESENHO.cruzamentos.flatMap((cruzamento) =>
          cruzamento.aproximacoes.flatMap((aproximacao) => {
            const sinal = sinalDaAproximacao(aoVivoPorId[cruzamento.id], aproximacao.fase, agora);
            return [
              ...aproximacao.linhas.map((linha, i) => (
                <Polyline
                  key={`${aproximacao.via}-${i}`}
                  positions={linha}
                  pathOptions={{ color: COR_SINAL[sinal], weight: 5, lineCap: "butt", interactive: false }}
                />
              )),
              <CircleMarker
                key={`${aproximacao.via}-sinal`}
                center={aproximacao.sinal}
                radius={5}
                pathOptions={{ color: "#0f172a", weight: 1.5, fillColor: COR_SINAL[sinal], fillOpacity: 1 }}
              >
                <Tooltip>
                  {cruzamento.id} · {aproximacao.via} · fase {aproximacao.fase}
                </Tooltip>
              </CircleMarker>,
            ];
          }),
        )}

        {trafego.map((posicao, i) => (
          <CircleMarker
            key={`t${i}`}
            center={posicao}
            radius={2.5}
            pathOptions={{ stroke: false, fillColor: COR_TRAFEGO, fillOpacity: 0.9, interactive: false }}
          />
        ))}

        {ves.map((ve) => (
          <CircleMarker
            key={ve.id}
            center={[ve.lat, ve.lon]}
            radius={7}
            pathOptions={{
              color: "#dc2626",
              weight: 3,
              fillColor: COR_VE[ve.tipo ?? ""] ?? "#a855f7",
              fillOpacity: 1,
            }}
          >
            <Tooltip permanent direction="right" offset={[10, 0]}>
              {NOME_TIPO[ve.tipo ?? ""] ?? ve.tipo ?? "VE"}
              {ve.criticidade ? ` · crit. ${ve.criticidade}` : ""} · {kmh(ve.velocidade_ms)}
            </Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>

      <ul className="pointer-events-none absolute bottom-2 left-2 z-[400] flex flex-wrap gap-x-3 gap-y-1 rounded bg-slate-900/85 px-3 py-1.5 text-xs text-slate-200">
        <li className="flex items-center gap-1">
          {(["VERDE", "AMARELO", "VERMELHO"] as const).map((cor) => (
            <span key={cor} className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: COR_SINAL[cor] }} />
          ))}
          sinal de cada aproximação
        </li>
        <li className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: COR_TRAFEGO }} />
          tráfego ({trafego.length})
        </li>
        <li className="flex items-center gap-1">
          <span className="inline-block h-3 w-3 rounded-full border-2 border-red-600 bg-white" />
          VE em serviço ({ves.length})
        </li>
        <li className="flex items-center gap-1">
          <span
            className="inline-block h-3 w-3 border-2"
            style={{ background: COR_CRUZAMENTO, borderColor: COR_PREEMPCAO }}
          />
          cruzamento em preempção
        </li>
      </ul>
    </div>
  );
}
