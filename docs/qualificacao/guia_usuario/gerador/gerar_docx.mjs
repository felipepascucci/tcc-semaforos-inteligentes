// Gera o .docx do Guia do Usuário v2.0 a partir de ../guia_usuario.md.
//
//   cd docs/qualificacao/guia_usuario/gerador
//   npm ci
//   node gerar_docx.mjs
//   powershell -File converter_pdf.ps1      (Word: atualiza o sumário e salva o PDF)
//
// Formatação no padrão do TCC final (Arial 12, legendas e tabelas em 10) e ABNT:
// A4, margens 3 cm (superior e esquerda) e 2 cm (inferior e direita), espaçamento
// 1,5, recuo de 1,25 cm, numeração de página no canto superior direito a partir
// do texto, legenda acima e "Fonte:" abaixo de figuras e tabelas. Figuras largas
// (arquitetura e esquemas complementares) vão em página paisagem.
//
// O conversor entende só o Markdown que o guia usa: front matter simples,
// títulos de 1 a 3 níveis, parágrafos, listas (com blocos aninhados), blocos de
// código, tabelas, imagens e os realces **negrito**, *itálico*, `código` e <sub>.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  AlignmentType,
  BorderStyle,
  Document,
  Header,
  HeadingLevel,
  ImageRun,
  LevelFormat,
  Packer,
  PageNumber,
  PageOrientation,
  Paragraph,
  ShadingType,
  Table,
  TableCell,
  TableOfContents,
  TableRow,
  TextRun,
  WidthType,
} from "docx";

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const PASTA_GUIA = path.resolve(AQUI, "..");
const FONTE_MD = path.join(PASTA_GUIA, "guia_usuario.md");
const SAIDA = path.join(PASTA_GUIA, "Guia_Usuario_Semaforos_Inteligentes_v2.0.docx");

// Integrantes com RA, como na capa do TCC final.
const RA = {
  "Felipe Rafael Tancredi Pascucci": "T895HG3",
  "Giovanna Santos da Silva": "G828HA5",
  "Isabelle Rosa Moura Ferreira": "N075465",
};

const FONTE = "Arial";
const CM = 567; // twips por centímetro
const A4 = { w: 11906, h: 16838 };
const MARGEM = { top: 3 * CM, left: 3 * CM, bottom: 2 * CM, right: 2 * CM };
const LARGURA_RETRATO_CM = 16;
const LARGURA_PAISAGEM_CM = 24.7;
const ALTURA_PAISAGEM_CM = 13.2;

// Figuras: largura máxima e altura máxima (cm); `paisagem` manda para página deitada.
const FIGURAS = {
  "arquitetura_camadas.png": { largura: 24.7, paisagem: true },
  "esquema_componentes_internos.png": { largura: 24.7, paisagem: true },
  "esquema_alimentacao.png": { largura: 24.7, paisagem: true },
  "foto_maquete.jpg": { largura: 15 },
  "foto_tags.jpg": { largura: 8, altura: 10 },
  "esquema_cruzamento.png": { largura: 16, altura: 12 },
  "foto_circuito_cruzamento.jpg": { largura: 15 },
  "esquema_veiculo.png": { largura: 16 },
  "foto_circuito_carrinho.jpg": { largura: 8, altura: 11 },
  "foto_lcd.jpg": { largura: 14 },
};

// --- Leitura do Markdown -----------------------------------------------------

function lerFrontMatter(texto) {
  const m = texto.match(/^---\n([\s\S]*?)\n---\n/);
  const dados = {};
  let chaveLista = null;
  for (const linha of m[1].split("\n")) {
    const item = linha.match(/^\s+-\s+"?(.*?)"?$/);
    if (item && chaveLista) {
      dados[chaveLista].push(item[1]);
      continue;
    }
    const kv = linha.match(/^(\w+):\s*(.*)$/);
    if (!kv) continue;
    if (kv[2] === "") {
      chaveLista = kv[1];
      dados[chaveLista] = [];
    } else {
      chaveLista = null;
      dados[kv[1]] = kv[2].replace(/^"|"$/g, "");
    }
  }
  return { dados, corpo: texto.slice(m[0].length) };
}

const INICIO_BLOCO = /^(#{1,3} |```|\||!\[|- |\d+\. )/;

function analisar(linhas) {
  const blocos = [];
  let i = 0;
  while (i < linhas.length) {
    const l = linhas[i];
    if (l.trim() === "") {
      i++;
      continue;
    }
    let m;
    if ((m = l.match(/^(#{1,3}) (.*)$/))) {
      blocos.push({ tipo: "titulo", nivel: m[1].length, texto: m[2] });
      i++;
    } else if (l.startsWith("```")) {
      const codigo = [];
      i++;
      while (i < linhas.length && !linhas[i].startsWith("```")) codigo.push(linhas[i++]);
      i++;
      blocos.push({ tipo: "codigo", linhas: codigo });
    } else if (l.startsWith("|")) {
      const linhasTabela = [];
      while (i < linhas.length && linhas[i].startsWith("|")) linhasTabela.push(linhas[i++]);
      const celulas = linhasTabela
        .filter((t) => !/^\|\s*:?-{3}/.test(t))
        .map((t) =>
          t
            .replace(/^\|/, "")
            .replace(/\|\s*$/, "")
            .split("|")
            .map((c) => c.trim()),
        );
      blocos.push({ tipo: "tabela", linhas: celulas });
    } else if ((m = l.match(/^!\[[^\]]*\]\(([^)]+)\)/))) {
      blocos.push({ tipo: "imagem", src: m[1] });
      i++;
    } else if (/^- /.test(l) || /^\d+\. /.test(l)) {
      const ordenada = /^\d+\. /.test(l);
      const recuo = ordenada ? 3 : 2;
      const itens = [];
      while (i < linhas.length) {
        const atual = linhas[i];
        const inicio = ordenada ? atual.match(/^(\d+)\. (.*)$/) : atual.match(/^- (.*)$/);
        if (!inicio) break;
        const conteudo = [ordenada ? inicio[2] : inicio[1]];
        i++;
        while (i < linhas.length) {
          const prox = linhas[i];
          if (prox.trim() === "") {
            // Linha em branco continua o item se a próxima não vazia for recuada.
            let j = i + 1;
            while (j < linhas.length && linhas[j].trim() === "") j++;
            if (j < linhas.length && linhas[j].startsWith(" ".repeat(recuo))) {
              conteudo.push("");
              i++;
              continue;
            }
            break;
          }
          if (prox.startsWith(" ".repeat(recuo))) {
            conteudo.push(prox.slice(recuo));
            i++;
          } else if (!INICIO_BLOCO.test(prox) && !prox.startsWith(" ")) {
            conteudo.push(prox); // continuação preguiçosa do parágrafo
            i++;
          } else break;
        }
        itens.push(analisar(conteudo));
        // Itens separados por linha em branco continuam na mesma lista.
        let j = i;
        while (j < linhas.length && linhas[j].trim() === "") j++;
        const segue = ordenada ? /^\d+\. /.test(linhas[j] ?? "") : /^- /.test(linhas[j] ?? "");
        if (segue) i = j;
        else break;
      }
      blocos.push({ tipo: ordenada ? "numerada" : "marcadores", itens });
    } else {
      const texto = [];
      while (i < linhas.length && linhas[i].trim() !== "" && !INICIO_BLOCO.test(linhas[i])) {
        texto.push(linhas[i++].trim());
      }
      blocos.push({ tipo: "paragrafo", texto: texto.join(" ") });
    }
  }
  return blocos;
}

// --- Texto com realces -------------------------------------------------------

function realces(texto, base = {}) {
  const runs = [];
  const re = /(\*\*[\s\S]+?\*\*|`[^`]+`|<sub>[^<]+<\/sub>|\*[^*\s][^*]*?\*)/g;
  let fim = 0;
  let m;
  while ((m = re.exec(texto))) {
    if (m.index > fim) runs.push(run(texto.slice(fim, m.index), base));
    const t = m[0];
    if (t.startsWith("**")) runs.push(...realces(t.slice(2, -2), { ...base, bold: true }));
    else if (t.startsWith("`")) runs.push(run(t.slice(1, -1), { ...base, codigo: true }));
    else if (t.startsWith("<sub>")) runs.push(run(t.slice(5, -6), { ...base, subScript: true }));
    else runs.push(...realces(t.slice(1, -1), { ...base, italics: true }));
    fim = m.index + t.length;
  }
  if (fim < texto.length) runs.push(run(texto.slice(fim), base));
  return runs;
}

function run(texto, { codigo, tamanho, ...resto }) {
  return new TextRun({
    text: texto,
    font: codigo ? "Consolas" : FONTE,
    size: codigo ? Math.round((tamanho ?? 24) * 0.9) : (tamanho ?? 24),
    ...resto,
  });
}

// --- Parágrafos --------------------------------------------------------------

const ESPACO_15 = { line: 360, before: 0, after: 120 };
const ESPACO_1 = { line: 240, before: 0, after: 0 };

function paragrafoCorpo(texto, opcoes = {}) {
  if (texto.startsWith("[COLOCAR AQUI")) {
    return new Paragraph({
      children: [run(texto, { bold: true, highlight: "yellow" })],
      spacing: ESPACO_15,
      alignment: AlignmentType.LEFT,
    });
  }
  return new Paragraph({
    children: realces(texto),
    alignment: AlignmentType.JUSTIFIED,
    spacing: ESPACO_15,
    indent: { firstLine: Math.round(1.25 * CM) },
    ...opcoes,
  });
}

function legenda(texto) {
  // "**Figura N – Título**" ou "**Tabela N – Título**": rótulo em negrito.
  const m = texto.match(/^\*\*((?:Figura|Tabela) \d+) – (.*)\*\*$/);
  return new Paragraph({
    children: [run(`${m[1]} – `, { bold: true, tamanho: 20 }), ...realces(m[2], { tamanho: 20 })],
    alignment: AlignmentType.CENTER,
    spacing: { line: 240, before: 240, after: 80 },
    keepNext: true,
    keepLines: true,
  });
}

function fonteLegenda(texto) {
  return new Paragraph({
    children: realces(texto, { tamanho: 20 }),
    alignment: AlignmentType.LEFT,
    spacing: { line: 240, before: 60, after: 240 },
  });
}

function codigo(linhas, recuoCm = 0) {
  return linhas.map(
    (l, k) =>
      new Paragraph({
        children: [new TextRun({ text: l === "" ? " " : l, font: "Consolas", size: 17 })],
        shading: { type: ShadingType.CLEAR, color: "auto", fill: "F2F2F2" },
        spacing: { line: 240, before: k === 0 ? 60 : 0, after: k === linhas.length - 1 ? 160 : 0 },
        indent: { left: Math.round((recuoCm + 0.25) * CM), right: Math.round(0.25 * CM) },
        keepNext: k < linhas.length - 1,
        keepLines: true,
      }),
  );
}

// --- Tabelas -----------------------------------------------------------------

function larguras(linhas, totalCm) {
  const n = linhas[0].length;
  const peso = Array.from({ length: n }, (_, c) => {
    const tamanhos = linhas.map((l) => (l[c] ?? "").replace(/[*`]/g, "").length);
    const maior = Math.max(...tamanhos);
    const medio = tamanhos.reduce((a, b) => a + b, 0) / tamanhos.length;
    return Math.max(4, Math.min(60, 0.5 * maior + 0.5 * medio));
  });
  const soma = peso.reduce((a, b) => a + b, 0);
  return peso.map((p) => Math.round(((p / soma) * totalCm) * CM));
}

function tabela(linhas, totalCm = LARGURA_RETRATO_CM) {
  const cols = larguras(linhas, totalCm);
  const borda = { style: BorderStyle.SINGLE, size: 4, color: "808080" };
  const bordas = { top: borda, bottom: borda, left: borda, right: borda };
  // Estimativa grosseira de "maior que uma página": a maior tabela que cabe numa
  // página do guia tem cerca de 1.850 caracteres; a de troubleshooting da
  // bancada, com 4.000, ocupa duas.
  const longa = linhas.flat().join("").length > 3000;
  return new Table({
    width: { size: cols.reduce((a, b) => a + b, 0), type: WidthType.DXA },
    columnWidths: cols,
    rows: linhas.map(
      (l, r) =>
        new TableRow({
          tableHeader: r === 0,
          cantSplit: true,
          children: cols.map(
            (w, c) =>
              new TableCell({
                width: { size: w, type: WidthType.DXA },
                borders: bordas,
                shading: r === 0 ? { type: ShadingType.CLEAR, color: "auto", fill: "D9E2EC" } : undefined,
                margins: { top: 40, bottom: 40, left: 80, right: 80 },
                children: [
                  new Paragraph({
                    children: realces(l[c] ?? "", { tamanho: 18, bold: r === 0 }),
                    spacing: { line: 240, before: 0, after: 0 },
                    // Tabela que cabe numa página: todas as linhas presas à seguinte,
                    // para não se dividir e a última linha ficar junto da "Fonte:".
                    // Tabela maior que uma página: só as duas primeiras e as duas
                    // últimas, para não deixar linha órfã nem a "Fonte:" sozinha.
                    keepNext: !longa || r < 2 || r >= linhas.length - 2,
                  }),
                ],
              }),
          ),
        }),
    ),
  });
}

// --- Imagens -----------------------------------------------------------------

function dimensoes(arquivo) {
  const b = fs.readFileSync(arquivo);
  if (b[0] === 0x89) return { w: b.readUInt32BE(16), h: b.readUInt32BE(20), tipo: "png" };
  let i = 2;
  while (i < b.length) {
    const marcador = b[i + 1];
    const tam = b.readUInt16BE(i + 2);
    if (marcador >= 0xc0 && marcador <= 0xc3) {
      return { h: b.readUInt16BE(i + 5), w: b.readUInt16BE(i + 7), tipo: "jpg" };
    }
    i += 2 + tam;
  }
  throw new Error(`dimensões não encontradas: ${arquivo}`);
}

function imagem(src) {
  const arquivo = path.resolve(PASTA_GUIA, src);
  const nome = path.basename(arquivo);
  const conf = FIGURAS[nome];
  if (!conf) throw new Error(`figura sem tamanho definido: ${nome}`);
  const { w, h, tipo } = dimensoes(arquivo);
  let largura = conf.largura;
  let altura = (largura * h) / w;
  const alturaMax = conf.altura ?? (conf.paisagem ? ALTURA_PAISAGEM_CM : 20);
  if (altura > alturaMax) {
    altura = alturaMax;
    largura = (altura * w) / h;
  }
  const px = (cm) => Math.round((cm / 2.54) * 96);
  return {
    paisagem: !!conf.paisagem,
    paragrafo: new Paragraph({
      children: [
        new ImageRun({
          type: tipo,
          data: fs.readFileSync(arquivo),
          transformation: { width: px(largura), height: px(altura) },
        }),
      ],
      alignment: AlignmentType.CENTER,
      spacing: { line: 240, before: 0, after: 0 },
      keepNext: true,
    }),
  };
}

// --- Montagem ----------------------------------------------------------------

const NUMERACAO = {
  config: [
    {
      reference: "marcadores",
      levels: [
        {
          level: 0,
          format: LevelFormat.BULLET,
          text: "•",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: Math.round(0.95 * CM), hanging: Math.round(0.45 * CM) } } },
        },
      ],
    },
    {
      reference: "numerada",
      levels: [
        {
          level: 0,
          format: LevelFormat.DECIMAL,
          text: "%1.",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: Math.round(0.95 * CM), hanging: Math.round(0.6 * CM) } } },
        },
      ],
    },
  ],
};

let instanciaNumerada = 0;

function renderizarLista(bloco) {
  const saida = [];
  const instancia = ++instanciaNumerada;
  for (const item of bloco.itens) {
    item.forEach((b, k) => {
      if (k === 0 && b.tipo === "paragrafo") {
        saida.push(
          new Paragraph({
            children: realces(b.texto),
            numbering:
              bloco.tipo === "numerada"
                ? { reference: "numerada", level: 0, instance: instancia }
                : { reference: "marcadores", level: 0 },
            alignment: AlignmentType.JUSTIFIED,
            spacing: { line: 360, before: 0, after: 80 },
          }),
        );
      } else if (b.tipo === "codigo") {
        saida.push(...codigo(b.linhas, 0.95));
      } else if (b.tipo === "paragrafo") {
        saida.push(
          new Paragraph({
            children: realces(b.texto),
            alignment: AlignmentType.JUSTIFIED,
            spacing: { line: 360, before: 0, after: 80 },
            indent: { left: Math.round(0.95 * CM) },
          }),
        );
      } else {
        saida.push(...renderizar([b]));
      }
    });
  }
  return saida;
}

function titulo(nivel, texto) {
  const numerado = /^\d/.test(texto);
  if (nivel === 1) {
    return new Paragraph({
      heading: HeadingLevel.HEADING_1,
      children: [new TextRun({ text: texto.toUpperCase(), bold: true, font: FONTE, size: 24 })],
      alignment: numerado ? AlignmentType.LEFT : AlignmentType.CENTER,
      pageBreakBefore: true,
      spacing: { line: 360, before: 0, after: 360 },
      keepNext: true,
    });
  }
  return new Paragraph({
    heading: nivel === 2 ? HeadingLevel.HEADING_2 : HeadingLevel.HEADING_3,
    children: [new TextRun({ text: texto, bold: true, italics: nivel === 3, font: FONTE, size: 24 })],
    spacing: { line: 360, before: 360, after: 120 },
    keepNext: true,
  });
}

/** Converte blocos em elementos; as figuras em paisagem saem como marcadores de seção. */
function renderizar(blocos) {
  const saida = [];
  for (let k = 0; k < blocos.length; k++) {
    const b = blocos[k];
    if (b.tipo === "titulo") saida.push(titulo(b.nivel, b.texto));
    else if (b.tipo === "codigo") saida.push(...codigo(b.linhas));
    else if (b.tipo === "tabela") saida.push(tabela(b.linhas));
    else if (b.tipo === "marcadores" || b.tipo === "numerada") saida.push(...renderizarLista(b));
    else if (b.tipo === "imagem") {
      const img = imagem(b.src);
      saida.push(img.paisagem ? { paisagem: img.paragrafo } : img.paragrafo);
    } else if (b.tipo === "paragrafo") {
      if (/^\*\*(Figura|Tabela) \d+ – /.test(b.texto)) {
        const proxima = blocos[k + 1];
        const leg = legenda(b.texto);
        if (proxima?.tipo === "imagem" && imagem(proxima.src).paisagem) {
          // Legenda, imagem e fonte vão juntas para a página em paisagem.
          const fonte = blocos[k + 2]?.tipo === "paragrafo" && blocos[k + 2].texto.startsWith("Fonte:")
            ? fonteLegenda(blocos[k + 2].texto)
            : null;
          saida.push({ paisagem: [leg, imagem(proxima.src).paragrafo, ...(fonte ? [fonte] : [])] });
          k += fonte ? 2 : 1;
        } else saida.push(leg);
      } else if (b.texto.startsWith("Fonte:")) saida.push(fonteLegenda(b.texto));
      else saida.push(paragrafoCorpo(b.texto));
    }
  }
  return saida;
}

function cabecalho() {
  return {
    default: new Header({
      children: [
        new Paragraph({
          alignment: AlignmentType.RIGHT,
          children: [new TextRun({ children: [PageNumber.CURRENT], font: FONTE, size: 20 })],
        }),
      ],
    }),
  };
}

function paginaRetrato() {
  return { page: { size: { width: A4.w, height: A4.h }, margin: MARGEM } };
}

function paginaPaisagem() {
  return {
    page: {
      size: { width: A4.w, height: A4.h, orientation: PageOrientation.LANDSCAPE },
      margin: { top: 3 * CM, left: 3 * CM, bottom: 2 * CM, right: 2 * CM },
    },
  };
}

function capa(d) {
  const centro = (texto, opcoes = {}) =>
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { line: 360, before: 0, after: 0 },
      children: [new TextRun({ text: texto, font: FONTE, size: 24, ...opcoes })],
      ...(opcoes.antes ? { spacing: { line: 360, before: opcoes.antes, after: 0 } } : {}),
    });
  const vazio = (n) => Array.from({ length: n }, () => centro(""));
  return [
    centro("UNIVERSIDADE PAULISTA", { bold: true }),
    centro("INSTITUTO DE CIÊNCIAS EXATAS E TECNOLOGIA", { bold: true }),
    centro(d.curso.toUpperCase(), { bold: true }),
    ...vazio(3),
    ...d.equipe.map((nome) => centro(`${nome} - RA: ${RA[nome]}`)),
    ...vazio(4),
    centro(d.title.toUpperCase(), { bold: true, size: 28 }),
    ...vazio(1),
    centro(d.subtitle),
    ...vazio(2),
    centro(`Vertente: ${d.vertente}`),
    centro(`Orientador: ${d.orientador}`),
    centro(`Versão ${d.versao}`),
    ...vazio(5),
    centro("SÃO PAULO, SP", { bold: true }),
    centro("2026", { bold: true }),
  ];
}

function sumario() {
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { line: 360, after: 360 },
      children: [new TextRun({ text: "SUMÁRIO", bold: true, font: FONTE, size: 24 })],
    }),
    new TableOfContents("Sumário", { hyperlink: true, headingStyleRange: "1-3" }),
  ];
}

function main() {
  const { dados, corpo } = lerFrontMatter(fs.readFileSync(FONTE_MD, "utf8").replace(/\r\n/g, "\n"));
  const semComentarios = corpo.replace(/<!--[\s\S]*?-->/g, "");
  const elementos = renderizar(analisar(semComentarios.split("\n")));

  // Quebra em seções: retrato, e uma seção em paisagem por figura larga.
  const secoes = [
    { properties: { ...paginaRetrato(), titlePage: false }, children: capa(dados) },
    { properties: paginaRetrato(), children: sumario() },
  ];
  let atual = [];
  const fecharRetrato = () => {
    if (atual.length) secoes.push({ properties: paginaRetrato(), headers: cabecalho(), children: atual });
    atual = [];
  };
  for (const e of elementos) {
    if (e && e.paisagem) {
      fecharRetrato();
      const filhos = Array.isArray(e.paisagem) ? e.paisagem : [e.paisagem];
      secoes.push({ properties: paginaPaisagem(), headers: cabecalho(), children: filhos });
    } else atual.push(e);
  }
  fecharRetrato();

  // O primeiro título de cada seção retrato que vem depois de uma paisagem não
  // precisa de quebra de página antes (a seção nova já começa numa página).
  const doc = new Document({
    creator: "Equipe do TCC",
    title: dados.title,
    numbering: NUMERACAO,
    styles: {
      default: { document: { run: { font: FONTE, size: 24 } } },
      paragraphStyles: [
        { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { font: FONTE, size: 24, bold: true, color: "000000" } },
        { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { font: FONTE, size: 24, bold: true, color: "000000" } },
        { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { font: FONTE, size: 24, bold: true, italics: true, color: "000000" } },
      ],
    },
    sections: secoes,
  });
  return Packer.toBuffer(doc).then((buf) => {
    fs.writeFileSync(SAIDA, buf);
    console.log(`gerado: ${path.relative(process.cwd(), SAIDA)} (${secoes.length} seções)`);
  });
}

main();
