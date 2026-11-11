# Guia do Usuário v2.0 — Pendências

Atualizado em 2026-11-05. Fonte do guia: `guia_usuario.md`.

## 1. Aguardando a equipe

| # | Onde no guia | O que falta |
| --- | --- | --- |
| 1 | 2.3 | [MEDIR] corrente da porta USB do cruzamento com um medidor USB, no ciclo e numa emergência (a equipe não tem medidor; hoje o orçamento usa datasheet e limite calculado, e a suficiência vem da operação de 30 min) |
| 2 | 2.3 | [CONFIRMAR] energia em Wh impressa na etiqueta da power bank (o cálculo de autonomia supõe 3,7 V de célula) |
| 3 | 2.4 | [CONFIRMAR] material e dimensões da base da maquete e material das bases dos postes |
| 4 | 2.4 | [CONFIRMAR] forma de fixação do leitor e da NodeMCU na caixa de suco; foto do carrinho montado (a seção 4.12 do TCC não tem) |
| 5 | 5.4.2 | [CONFIRMAR] procedimento de limpeza e inspeção dos sensores adotado pela equipe |
| 6 | 2.2 | Pull-ups de 4,7 kΩ do adaptador I2C: a resposta da equipe descreve a placa FC-113 típica; conferir a marcação `472` na placa |

## 2. A validar em bancada (Fase 4)

- Partida na ordem da seção 5.1.1 e as saídas esperadas de `/health` da ponte e do back-end (5.1.2).
- Calibração em repouso: passagem de cada carrinho em cada tag com `SEM_OCORRENCIA` no LCD e no log (5.1.3).
- Roteiro `bridge.verificar` com a placa (5.1.4).
- Procedimento de gravação dos NodeMCU como descrito em 3.4.4, inclusive a leitura do MAC na saída do gravador.
- Comandos do arduino-cli com versão fixada (3.4.2), num ambiente sem os pacotes instalados.

## 3. Documento (.docx)

- Gerado por `gerador/gerar_docx.mjs` (`npm ci` e `node gerar_docx.mjs` na pasta `gerador/`). Ao abrir no Word, aceitar "atualizar campos" para preencher o sumário.
- O PDF não foi gerado (decisão do Felipe, 2026-11-05: a conversão pelo Word demora). Para gerar: abrir o .docx no Word e salvar como PDF, ou rodar `gerador/converter_pdf.ps1`.
- A conversão para PDF pelo Word (`ExportAsFixedFormat`) trava nesta máquina, sem diálogo; abrir, repaginar, atualizar o sumário e salvar funciona em poucos segundos. A conferência visual página a página foi feita em outra sessão (2026-11-05). Ajustes aplicados depois dela: tabelas que cabem numa página não se dividem e ficam junto da "Fonte:" (Tabelas 4, 10 e 14); a Tabela 25, maior que uma página, divide-se sem linha órfã; a Figura 9 passou para depois da Tabela 7, para preencher a página da seção 2.3. Posições conferidas pelo Word (página de cada legenda, tabela e fonte); o documento ficou com 49 páginas. Falta a revisão visual depois desses ajustes.
- Tabelas em numeração corrida (1 a 25). Figuras 1, 8 e 9 em página paisagem.
- A Figura 5 (foto do circuito do cruzamento, Figura 20 do TCC) foi usada como está no documento final, por decisão do Felipe (2026-11-05).
- Itens da seção 1 que o guia NÃO marca mais (decisão de 2026-11-05: só fica marcado o que é necessário): medição de corrente (o texto declara que não houve), Wh da power bank (o texto declara a suposição de 3,7 V), procedimento de limpeza da equipe (o texto traz um procedimento) e conferência do `472` no adaptador.

## 4. Já resolvido

- Configuração de referência: esta máquina (resposta 11).
- Declaração de IA assistiva: só Claude Code e Claude (resposta 12).
- Enquadramento da IA fora da bancada e métricas no treino e na validação (resposta 13).
- Hardware (respostas 1 a 10, 2026-11-05): módulos de semáforo genéricos com 330/220/470 Ω; LCD com PCF8574T em 0x27; três NodeMCU com CH340G e uma com CP2102 (a da ambulância, então o receptor é CH340G); nenhum componente discreto externo; protoboard de 400 pontos só para o GND dos semáforos; power banks BASIKE 10000 mAh; sem medidor de corrente; tags coladas por baixo da cartolina e leitor numa caixa de suco; `esp8266` 3.1.2 para regravação.
- Fotos: as da seção 4.12 do TCC (Figuras 17 a 21), por decisão do Felipe; as duas fotos enviadas em 2026-11-05 foram descartadas.
- Correntes de datasheet conferidas nos PDFs: ESP8266EX v7.1 (Tabela 5-3), MFRC522 Rev. 3.9 (Tabela 1), ATmega328P 7810D (VIH e máximos absolutos), esquemático NodeMCU DevKit v1.0 (resistores de boot, regulador, capacitores). O datasheet do UNO deixa o consumo em branco ("xx mA").
- Matriz de confusão gerada por script: `analysis/metricas_politica.py`.
- Comando de reajuste da §3.6 do v1.2 que sobrescrevia os pesos: corrigido na seção 4.6 e testado numa pasta temporária.
