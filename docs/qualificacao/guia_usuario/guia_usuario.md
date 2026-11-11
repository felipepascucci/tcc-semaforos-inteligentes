---
title: "Guia do Usuário e Manual de Operação do Conjunto Prototipado"
subtitle: "Modelo Inteligente de Controle Dinâmico de Semáforos Baseado em Dados de Tráfego para Priorização de Veículos de Emergência em Ambientes Urbanos"
instituicao: "Universidade Paulista (UNIP)"
curso: "Bacharelado em Ciência da Computação"
vertente: "SmartCity — Cidades Inteligentes e Infraestrutura Urbana"
orientador: "Prof. Marco Gomes"
equipe:
  - "Felipe Rafael Tancredi Pascucci"
  - "Giovanna Santos da Silva"
  - "Isabelle Rosa Moura Ferreira"
versao: "2.0"
data: "novembro de 2026"
lang: pt-BR
---

<!--
FONTE do Guia v2.0. O PDF e o .docx são gerados a partir deste arquivo na Fase 3.
Trechos [COLOCAR AQUI INFORMAÇÕES SOBRE ...] aguardam a equipe; estão listados em PENDENCIAS.md.
Todo número deste texto vem de arquivo versionado, citado na linha "Fonte:" da tabela.
-->

# Apresentação

Este guia orienta a instalação, a operação e o diagnóstico do conjunto prototipado: o protótipo físico de um cruzamento (bancada) e o ambiente de simulação de tráfego, integrados por um back-end, um banco de dados e um painel web. Destina-se a operadores e a responsáveis técnicos que precisem reproduzir o sistema a partir do repositório público do projeto:

```
https://github.com/felipepascucci/tcc-semaforos-inteligentes
```

**Convenções.** Os comandos são de PowerShell, no Windows, executados na raiz do repositório e com o ambiente virtual Python ativado (seção 3.2). Cada passo numerado traz, quando há, o resultado esperado. Portas COM (`COM3`, `COM4`, `COM5`) são as observadas na máquina de referência; em outra máquina, confira-as com `arduino-cli board list` antes de usá-las. Trechos no formato [COLOCAR AQUI INFORMAÇÕES SOBRE ...] indicam informação que a equipe vai inserir.

**Organização.** O guia segue as cinco seções exigidas: 1 Identificação do Ecossistema e Vertente; 2 Manual de Instalação e Montagem do Hardware; 3 Guia de Instalação e Configuração do Software; 4 Módulo de Inteligência Artificial; 5 Manual de Operação e Diagnóstico.

# 1 Identificação do Ecossistema e Vertente

## 1.1 Título da solução e equipe executora

**Solução:** Modelo Inteligente de Controle Dinâmico de Semáforos Baseado em Dados de Tráfego para Priorização de Veículos de Emergência em Ambientes Urbanos.

**Equipe executora:** Felipe Rafael Tancredi Pascucci, Giovanna Santos da Silva e Isabelle Rosa Moura Ferreira. **Orientador:** Prof. Marco Gomes. Universidade Paulista (UNIP), Bacharelado em Ciência da Computação, 2026.

## 1.2 Declaração da vertente

**Este trabalho se enquadra na vertente SmartCity — Cidades Inteligentes e Infraestrutura Urbana**, no domínio da telemetria viária e do controle da infraestrutura semafórica urbana.

O sistema detecta a aproximação de um veículo de emergência (VE) a um cruzamento semaforizado e altera o ciclo do semáforo para abrir passagem a ele (preempção), por transições seguras, e mede o custo dessa prioridade para o tráfego transversal. A preempção só ocorre para um veículo identificado **e** com ocorrência ativa aberta por uma central de despacho; entre VEs em disputa, decide a criticidade da ocorrência e, em empate de criticidade na simulação, uma política aprendida por regressão logística.

## 1.3 Arquitetura de alto nível

A Figura 1 apresenta o ecossistema nas cinco camadas: Borda, Conectividade, Persistência, Inteligência e Interface com o Usuário. A Borda tem duas realizações: a **física**, na bancada, e a **simulada**, no SUMO, que funciona como gêmeo digital de uma malha arterial de oito cruzamentos.

**Figura 1 – Arquitetura de alto nível do ecossistema prototipado**

![](figuras/arquitetura_camadas.png)

Fonte: elaborado pelos autores (2026), a partir de `context/01`, `context/02`, `context/05` e `docker-compose.yml`. Gerada por `python docs/qualificacao/guia_usuario/figuras/arquitetura_camadas.py`.

**Tabela 1 – Camadas do ecossistema**

| Camada | Componentes | Protocolos e interfaces | Onde executa |
| --- | --- | --- | --- |
| Borda | Bancada: 4 tags RFID (uma por rua), 3 carrinhos com NodeMCU ESP8266 e leitor RC522, NodeMCU receptor, Arduino UNO R3 com 4 semáforos de LED e LCD 16x2. Simulação: SUMO 1.27.1, malha CRUZ_01 a CRUZ_08 | RFID 13,56 MHz; GPIO; I2C (LCD); SPI (RC522) | Bancada; processo SUMO no host |
| Conectividade | Rádio entre carrinho e cruzamento; serial do receptor ao UNO; USB do UNO ao computador; ponte serial (`bridge/`); TraCI | ESP-NOW 2,4 GHz; UART 9600 baud; HTTP em `127.0.0.1:8001`; TraCI sobre TCP local | Bancada e host |
| Persistência | Back-end FastAPI (ingestão e API); PostgreSQL 16; arquivos CSV de `analysis/data/` | SQL (psycopg); HTTP | Contêineres Docker; host |
| Inteligência | Motor de decisão em Python (`backend/core/priorizacao`); política aprendida (modo `PREEMPCAO_ML`); regra local do firmware do UNO | Chamada de função no processo do executor; firmware embarcado | Host (simulação); UNO (bancada) |
| Interface com o Usuário | Dashboard React servido por nginx | HTTPS e WebSocket seguro em `:8443` | Contêiner Docker; navegador |

Fonte: elaborado pelos autores (2026).

## 1.4 Delimitação do conjunto prototipado

- **Na bancada, quem decide a preempção é o Arduino UNO**, com uma regra local: só atende o tipo de veículo que tem ocorrência ativa na Central, decide pela criticidade da ocorrência, mantém fila de um lugar e cumpre as invariantes de segurança. O computador não está no caminho da decisão: se a ponte cair, o cruzamento continua operando com a última lista recebida.
- **O motor de decisão e a política aprendida executam na simulação.** A política de desempate (Seção 4) não é executada pelo firmware do UNO.
- O RFID emula a detecção que, numa via real, viria de radar e de comunicação veículo-infraestrutura (V2I). A tag identifica a **rua** de aproximação; o tipo do veículo é fixo no firmware de cada carrinho.
- As invariantes de segurança valem nos dois lados: nunca dois verdes conflitantes, nunca verde direto para vermelho (sempre amarelo) e sempre um intervalo com todos os semáforos em vermelho (*all-red*) antes de abrir um verde.

# 2 Manual de Instalação e Montagem do Hardware

O conjunto físico tem duas partes: o **cruzamento**, uma maquete com quatro semáforos, o controlador Arduino UNO R3, o display LCD e o NodeMCU receptor; e os **veículos**, três carrinhos (ambulância, bombeiro e polícia), cada um com um NodeMCU emissor e um leitor RFID. A Figura 2 mostra a maquete montada.

**Figura 2 – Maquete do cruzamento montada**

![](figuras/foto_maquete.jpg)

Fonte: elaborado pelos autores (2026). Reproduzida do TCC, Figura 17.

## 2.1 Lista de materiais (BOM)

**Tabela 2 – Lista de materiais**

| Componente | Modelo / part number | Qtd. | Tensão operacional | Função no circuito |
| --- | --- | ---: | --- | --- |
| Microcontrolador do cruzamento | Arduino UNO R3: ATmega328P a 16 MHz; conversor USB ATmega16U2 (USB `2341:0043`) | 1 | 5 V, pelo USB; E/S em 5 V | Decide a preempção e aciona os semáforos e o LCD |
| Placa do receptor | NodeMCU 1.0 (módulo ESP-12E, ESP8266EX); conversor USB CH340G | 1 | 5 V no pino VIN; lógica em 3,3 V | Recebe o ESP-NOW dos carrinhos e repassa ao UNO pela serial |
| Placas dos emissores | NodeMCU 1.0 (ESP-12E, ESP8266EX); conversor CP2102 (ambulância) e CH340G (bombeiro e polícia) | 3 | 5 V no micro-USB; lógica em 3,3 V | Lê a tag da rua e envia rua e tipo por ESP-NOW |
| Leitor RFID | Módulo "RFID-RC522" (serigrafia HW-126), chip NXP MFRC522 | 3 | 3,3 V (faixa do chip: 2,5 a 3,6 V); **nunca 5 V** | Lê o UID da tag a 13,56 MHz |
| Tags RFID | Cartão MIFARE Classic 1K (S50), ISO/IEC 14443A, 13,56 MHz | 4 | Passiva, sem alimentação | Identifica a rua de aproximação (uma por rua) |
| Semáforo | Módulo LED 8 mm tipo semáforo, genérico; catodo comum; resistores SMD integrados: vermelho 330 Ω, amarelo 220 Ω, verde 470 Ω | 4 | 5 V (nível alto do UNO) | Sinalização de cada aproximação |
| Display | LCD 16x2 (1602, fundo azul) com adaptador I2C PCF8574T (placa tipo FC-113), endereço `0x27` | 1 | 5 V | Mostra o estado do cruzamento e o VE atendido |
| Protoboard | 400 pontos | 1 | — | Barramento negativo (GND) dos quatro semáforos |
| Power bank | BASIKE 10000 mAh Mini PD 22,5 W, com 2 cabos integrados | 3 | Saída USB 5 V | Alimenta o NodeMCU de cada carrinho |
| Cabo USB | USB A–B | 1 | 5 V | Liga o UNO ao computador: dados e alimentação |
| Jumpers | Fêmea–fêmea e macho–fêmea | um por ligação das Tabelas 3 a 6 | — | Ligações de sinal e alimentação |
| Computador | Configuração da Tabela 9 (seção 3.1) | 1 | — | Ponte serial, back-end, banco e painel |

Fonte: elaborado pelos autores (2026), a partir de `context/05` §1, do TCC (Apêndice B, Quadros 55 e 56), da serigrafia do leitor (TCC, Figura 21) e de NXP (2016).

A placa do receptor foi identificada por exclusão: das quatro NodeMCU, três têm CH340G e uma tem CP2102, e a CP2102 é a do carrinho da ambulância (USB `10C4:EA60`, `context/05` §1). Nenhum componente discreto (resistor, capacitor, regulador ou conversor de nível) foi acrescentado fora dos módulos e das placas. A Figura 3 mostra as tags.

**Figura 3 – Tags RFID das quatro ruas**

![](figuras/foto_tags.jpg)

Fonte: elaborado pelos autores (2026). Reproduzida do TCC, Figura 19.

## 2.2 Pinagem e diagrama esquemático

As tabelas a seguir ligam cada pino do microcontrolador ao pino do módulo. Elas são as mesmas do firmware (`firmware/uno/semaforo/semaforo.ino` e os `#define` dos emissores), e o teste `tests/diagramas/test_esquema_eletrico.py` confere os esquemas das Figuras 4 e 6 contra elas.

**Tabela 3 – Semáforos → Arduino UNO (LED acende com nível alto)**

| Semáforo | Aproximação (tag) | Pino do módulo | Pino do UNO | Cor do fio |
| --- | --- | --- | --- | --- |
| S1 | Principal, sentido A (`RUA1`) | R / Y / G / GND | D13 / D12 / D11 / barramento GND | laranja / amarelo / verde / azul |
| S2 | Principal, sentido B (`RUA2`) | R / Y / G / GND | D10 / D9 / D8 / barramento GND | laranja / amarelo / verde / azul |
| S3 | Transversal, sentido A (`RUA3`) | R / Y / G / GND | D7 / D6 / D5 / barramento GND | vermelho / branco / cinza / preto |
| S4 | Transversal, sentido B (`RUA4`) | R / Y / G / GND | D4 / D3 / D2 / barramento GND | vermelho / branco / cinza / preto |

Fonte: `context/05` §1 e TCC, Quadro 57. O barramento negativo da protoboard é ligado ao GND do UNO.

**Tabela 4 – LCD (adaptador I2C) → Arduino UNO**

| Pino do adaptador | Pino do UNO | Função | Cor do fio |
| --- | --- | --- | --- |
| GND | GND | Terra | preto |
| VCC | 5V | Alimentação | roxo |
| SDA | A4 | Dados I2C | marrom |
| SCL | A5 | Relógio I2C | branco |

Fonte: `context/05` §1 e TCC, Quadro 58.

**Tabela 5 – NodeMCU receptor → Arduino UNO**

| Pino do NodeMCU | Pino do UNO | Função |
| --- | --- | --- |
| TX (GPIO 1) | A0 | Serial a 9600 baud, lida pelo UNO por serial por software |
| VIN | ICSP, pino 2 (5 V) | Alimentação do receptor |
| GND | GND | Terra comum |

Fonte: `context/05` §1 e TCC, Apêndice B. Não usar o pino 5 do ICSP, que é o RESET do ATmega328P: um fio nele mantém o UNO reiniciando.

**Tabela 6 – RC522 → NodeMCU emissor (igual nos três carrinhos, salvo a observação)**

| Pino do RC522 | Pino do NodeMCU | Função | Cor do fio |
| --- | --- | --- | --- |
| 3.3V | 3V3 | Alimentação (nunca 5 V) | azul |
| RST | D3 (GPIO 0) | Reset do leitor | amarelo |
| GND | GND | Terra | preto |
| IRQ | sem ligação | — | — |
| MISO | D6 (GPIO 12) | SPI, dados do leitor para a placa | laranja |
| MOSI | D7 (GPIO 13) | SPI, dados da placa para o leitor | verde |
| SCK | D5 (GPIO 14) | Relógio SPI | vermelho |
| SDA (SS) | D8 (GPIO 15) | Seleção do chip SPI | cinza |

Fonte: `context/05` §1 e TCC, Quadro 59. **No carrinho da polícia, o RST do RC522 vai ao pino 3V3, e não ao D3**, porque o D3 daquela placa não leva o nível ao fio; o firmware não muda, pois a biblioteca faz o reset por software.

**Pinos livres e reservados do UNO.** A1 é o TX exigido pela serial por software e fica sem ligação; A2 e A3 estão livres; RX (0) e TX (1) ficam só para o USB.

**Nível lógico entre receptor e UNO.** O TX do NodeMCU opera em 3,3 V e entra direto no A0 do UNO, alimentado em 5 V, sem conversor de nível. O ATmega328P reconhece nível alto a partir de 0,6 × V<sub>CC</sub> = 3,0 V (ATMEL, 2015), então a ligação funciona com pouca folga. O sentido inverso (5 V entrando num pino de 3,3 V) não existe na montagem.

As Figuras 4 e 5 mostram o cruzamento, e as Figuras 6 e 7, o carrinho: em cada par, o esquema elétrico gerado por código e a fotografia da montagem.

**Figura 4 – Esquema elétrico do cruzamento**

![](../../diagramas/esquema_cruzamento.png)

Fonte: elaborado pelos autores (2026). Gerado por `python docs/diagramas/esquema_eletrico.py`.

**Figura 5 – Circuito do cruzamento montado**

![](figuras/foto_circuito_cruzamento.jpg)

Fonte: elaborado pelos autores (2026). Reproduzida do TCC, Figura 20.

**Figura 6 – Esquema elétrico do carrinho**

![](../../diagramas/esquema_veiculo.png)

Fonte: elaborado pelos autores (2026). Gerado por `python docs/diagramas/esquema_eletrico.py`.

**Figura 7 – Circuito do carrinho: leitor RC522 ligado ao NodeMCU emissor**

![](figuras/foto_circuito_carrinho.jpg)

Fonte: elaborado pelos autores (2026). Reproduzida do TCC, Figura 21.

**Resistores de pull-up e pull-down e desacoplamento.** Os componentes passivos do circuito estão todos dentro dos módulos e das placas (Figura 8):

- **Módulo de semáforo:** um resistor limitador por LED, em série com o anodo, e os três catodos em comum no pino GND do módulo.
- **Adaptador I2C do LCD:** pull-ups de 4,7 kΩ (marcação SMD `472`) de SDA e de SCL para o VCC de 5 V. São os únicos pull-ups do barramento I2C; o UNO não acrescenta outros.
- **NodeMCU:** no projeto de referência da placa (NODEMCU TEAM, 2015), resistores de 12 kΩ mantêm o GPIO0 em nível alto e o GPIO15 em nível baixo, como o ESP8266 exige no boot ("GPIO15 MUST keep LOW, GPIO2 MUST keep HIGH. GPIO0 HIGH -> RUN MODE"). O RC522 está ligado justamente a esses dois pinos (RST no GPIO0, SS no GPIO15), e o boot foi verificado na bancada em 5 de 5 reinícios e religamentos (`context/05` §1, P8).
- **Desacoplamento:** só os capacitores das próprias placas. No projeto de referência da NodeMCU, 10 µF na entrada e na saída do regulador de 3,3 V e 100 nF mais 100 µF junto ao módulo ESP-12E (Figura 9). Nenhum capacitor externo foi acrescentado.

**Figura 8 – Componentes internos dos módulos: resistores e pull-ups**

![](figuras/esquema_componentes_internos.png)

Fonte: elaborado pelos autores (2026), com valores informados pela equipe e do projeto de referência NodeMCU DevKit v1.0 (NODEMCU TEAM, 2015). Gerada por `python docs/qualificacao/guia_usuario/figuras/esquema_detalhe.py`.

## 2.3 Especificações de alimentação elétrica

**Topologia.** O cruzamento inteiro é alimentado pela porta USB do computador, que fornece 5 V e até 500 mA numa porta USB 2.0 (USB IMPLEMENTERS FORUM, 2000): o UNO recebe o USB, o LCD tira 5 V do pino 5V, os módulos de semáforo são acionados pelos pinos D2 a D13, e o NodeMCU receptor tira 5 V do pino 2 do ICSP e regula 3,3 V na própria placa. Cada carrinho é alimentado pela sua power bank, no micro-USB da NodeMCU, e não tem ligação elétrica com o cruzamento. A Figura 9 mostra os dois caminhos.

**Corrente dos semáforos (limite superior).** A corrente de cada LED é (5 V − V<sub>F</sub>) / R. Como a tensão direta V<sub>F</sub> dos LEDs do módulo genérico não é especificada, a Tabela 7 usa V<sub>F</sub> = 0, que dá um limite superior: a corrente real é menor.

**Tabela 7 – Limite superior de corrente por LED**

| Cor | Resistor | Limite superior (5 V / R) |
| --- | ---: | ---: |
| Vermelho | 330 Ω | 15,2 mA |
| Amarelo | 220 Ω | 22,7 mA |
| Verde | 470 Ω | 10,6 mA |

Fonte: elaborado pelos autores (2026), a partir dos valores dos resistores.

O firmware acende exatamente uma cor por módulo (`PlacaUno::acender` apaga as outras duas). O amarelo só aparece num módulo que estava verde, e nunca há verde em mais de dois módulos ao mesmo tempo, porque os dois eixos nunca ficam verdes juntos (invariante I1, verificada em toda a telemetria da bancada). O pior caso é, portanto, dois amarelos e dois vermelhos: 2 × 22,7 + 2 × 15,2 = 75,8 mA. Cada pino fica abaixo de 22,7 mA e o total, abaixo de 75,8 mA, contra os máximos absolutos do ATmega328P de 40 mA por pino de E/S e 200 mA nos pinos de VCC e GND (ATMEL, 2015).

**Figura 9 – Alimentação do cruzamento e do carrinho**

![](figuras/esquema_alimentacao.png)

Fonte: elaborado pelos autores (2026), com regulador e capacitores do projeto de referência NodeMCU DevKit v1.0 (NODEMCU TEAM, 2015). Gerada por `python docs/qualificacao/guia_usuario/figuras/esquema_detalhe.py`.

**Tabela 8 – Orçamento de corrente nos pontos de pico**

| Carga | Corrente | Origem do valor |
| --- | ---: | --- |
| *Cruzamento (5 V da porta USB)* | | |
| Quatro módulos de semáforo | ≤ 75,8 mA | Limite superior calculado (Tabela 7) |
| NodeMCU receptor: ESP8266 recebendo | 50 a 56 mA (típico) | ESPRESSIF (2025), Tabela 5-3 |
| NodeMCU receptor: ESP8266 transmitindo (pico) | 170 mA (típico, 802.11b, +17 dBm) | ESPRESSIF (2025), Tabela 5-3 |
| Placa do UNO (ATmega328P, ATmega16U2, LEDs da placa) | não especificada | O datasheet oficial deixa o consumo máximo em branco ("xx mA") (ARDUINO, 2026); não medida |
| LCD com luz de fundo e adaptador I2C | não especificada | Módulo genérico, sem datasheet; não medida |
| **Picos conhecidos somados** | **245,8 mA** | 75,8 + 170 |
| *Carrinho (5 V da power bank)* | | |
| ESP8266 transmitindo (pico) | 170 mA (típico) | ESPRESSIF (2025), Tabela 5-3 |
| RC522 com o campo ligado | 60 mA típico, 100 mA máximo no transmissor; total abaixo de 100 mA em operação típica | NXP (2016), Tabela 1 e nota 7 |
| **Pico estimado do carrinho** | **≈ 270 mA** | 170 + 100 |

Fonte: elaborado pelos autores (2026). Os reguladores das NodeMCU são lineares, então a corrente de entrada em 5 V é praticamente a de saída em 3,3 V.

**Dimensionamento da fonte do cruzamento.** Os picos conhecidos somam 245,8 mA, o que deixa 254,2 mA dos 500 mA da porta para a placa do UNO e o LCD, cujos consumos não são especificados. Não houve medição de corrente. A suficiência da fonte foi comprovada em operação: 30 minutos contínuos sem travamento nem reinício (item 12 do checklist de bancada) e 100 passagens com o receptor alimentado pelo ICSP sem nenhuma linha recusada (`analysis/data/resumo_bancada_2026-10-07.md`). Antes dessa ligação, o receptor alimentado pelo VIN ou pelo 3,3 V do UNO reiniciava por subtensão (`context/05` §1).

**Dimensionamento da bateria do carrinho.** Em operação contínua, o carrinho consome tipicamente cerca de 130 mA em 5 V: o ESP8266 recebendo (56 mA) mais o RC522 com o campo ligado (6,5 + 7 + 60 = 73,5 mA, valores típicos de NXP, 2016). Supondo a tensão nominal de 3,7 V das células de lítio, a power bank de 10000 mAh guarda cerca de 37 Wh. Mesmo supondo eficiência de conversão de só 50%, a autonomia seria de 18,5 Wh / (5 V × 0,13 A) ≈ 28 h, muito acima de uma sessão de demonstração.

**Considerações térmicas.** Os reguladores lineares das NodeMCU dissipam (5 − 3,3) V × I: cerca de 0,1 W no receptor recebendo e 0,22 W no carrinho em operação típica, com picos breves de até 0,46 W durante a transmissão. Os LEDs operam abaixo de 23 mA. A bancada opera em ambiente interno, sem ventilação forçada. Na verificação de bancada, nenhum LED apresentou brilho anômalo ou aquecimento (item 13 do checklist) e o conjunto operou 30 minutos contínuos sem falha (item 12).

## 2.4 Fixação mecânica, encapsulamento e aterramento

**Montagem da maquete (Figuras 2 e 10).** A base da maquete é uma placa rígida, revestida com cartolina preta na pista, com a sinalização horizontal em fita branca, faixas cinzas nas calçadas e grama sintética nos quatro cantos. Cada semáforo é preso a um palito de madeira fixado numa base branca, junto à sua aproximação. O LCD é aparafusado entre dois palitos horizontais, sustentados por dois palitos verticais, acima do Arduino UNO e da protoboard, que ficam sobre o canto esquerdo do fundo. Os fios dos semáforos passam por furos na base e correm por baixo dela, o que mantém a superfície livre para a passagem dos carrinhos.

[COLOCAR AQUI INFORMAÇÕES SOBRE O MATERIAL E AS DIMENSÕES DA BASE DA MAQUETE]

**Tags.** Cada tag é colada por baixo da cartolina, na rua que ela identifica, antes do cruzamento. A leitura acontece a 2–5 cm, através da cartolina.

**Carrinhos.** O leitor RC522, a NodeMCU e a power bank de cada carrinho são montados numa representação de carrinho feita com uma caixa de suco, com o leitor voltado para o piso.

[COLOCAR AQUI INFORMAÇÕES SOBRE A FIXAÇÃO DO LEITOR RC522, DA NODEMCU E DA POWER BANK NO CARRINHO, COM UMA FOTO DO CARRINHO MONTADO]

 Os pinos do RC522 foram soldados, porque a leitura só ficou estável assim (questionário de hardware, item 6.3); o mau contato do jumper do RST com o carrinho em movimento já causou perda de leituras no carrinho da polícia (`context/05` §5).

**Figura 10 – Fixação do LCD e posição do Arduino UNO e da protoboard**

![](figuras/foto_lcd.jpg)

Fonte: elaborado pelos autores (2026). Reproduzida do TCC, Figura 18.

**Encapsulamento e proteção.** O protótipo é de bancada, para uso em ambiente interno e seco, e não tem caixa nem proteção contra intempéries. As placas ficam expostas, o que facilita a inspeção e a regravação. Uma instalação em via pública exigiria gabinete fechado para o controlador e os módulos, fora do escopo deste protótipo.

**Aterramento.** No cruzamento há um único nó de terra: o GND do UNO, ligado ao terra da porta USB do computador, ao barramento negativo da protoboard (catodos dos quatro semáforos), ao GND do adaptador do LCD e ao GND do receptor. O terra comum entre o receptor e o UNO é obrigatório, porque é a referência da linha serial TX → A0. Os carrinhos não têm ligação elétrica com o cruzamento (a comunicação é por rádio) e usam como referência o terra da própria power bank. Não há ligação ao terra de proteção da rede elétrica além da que o próprio computador tiver.

# 3 Guia de Instalação e Configuração do Software

## 3.1 Requisitos mínimos e dependências

O sistema foi instalado e validado na configuração de referência da Tabela 9, a mesma máquina em que rodaram a bancada e as simulações cujos dados aparecem no TCC. Versões diferentes podem funcionar dentro dos mínimos da Tabela 10, mas a reprodução exata dos dados publicados exige SUMO 1.27.1.

**Tabela 9 – Configuração de referência (testada)**

| Item | Versão |
| --- | --- |
| Sistema operacional | Windows 11 Pro, 64 bits, versão 10.0.26200.9711 |
| Processador e memória | AMD Ryzen 7 5700X (8 núcleos); 32 GB de RAM |
| Docker Desktop | Docker Engine 29.7.2; Docker Compose v5.3.1 |
| Python (host) | 3.12.10 |
| SUMO | Eclipse SUMO 1.27.1 |
| Node.js e npm | 24.19.0 e 11.17.0 (só para desenvolver o painel fora do Compose) |
| Git | 2.55.0.windows.4 |
| arduino-cli | 1.5.1 |
| Pacotes de placas | `arduino:avr` 1.8.8; `esp8266:esp8266` 3.1.2 |
| Bibliotecas de firmware | `MFRC522` 1.4.12 (GithubCommunity); `LiquidCrystal I2C` 1.1.2 (Frank de Brabander) |
| Imagens Docker | `postgres:16-alpine`; `python:3.12-slim`; `node:24-alpine` (build); `nginx:1.27-alpine`; `adminer:5` (opcional) |

Fonte: elaborado pelos autores (2026), a partir da máquina de referência, do `docker-compose.yml` e dos `Dockerfile` do projeto.

**Tabela 10 – Requisitos mínimos e dependências declaradas**

| Dependência | Requisito declarado | Onde está declarado |
| --- | --- | --- |
| Python | ≥ 3.11 | `pyproject.toml` (`requires-python`) |
| SUMO | ≥ 1.19; dados publicados gerados com 1.27.1 | `README.md` |
| Docker Desktop com Compose | Compose com suporte a `depends_on: condition` | `docker-compose.yml` |
| Bibliotecas do back-end | `fastapi>=0.115,<0.116`, `uvicorn[standard]>=0.30`, `sqlalchemy>=2.0`, `alembic>=1.13`, `pydantic>=2.7`, `psycopg[binary]>=3.1`, `pyyaml>=6.0`, `structlog>=24.1`, `python-dotenv>=1.0`, `httpx>=0.27`, `PyJWT>=2.8` | `pyproject.toml` (`dependencies`) |
| Extra `dev` (testes) | `pytest>=8.0`, `pytest-asyncio>=0.23`, `hypothesis>=6.100`, `testcontainers[postgres]>=4.7`, `ruff>=0.6`, `mypy>=1.11`, `ziglang>=0.13` | `pyproject.toml` |
| Extra `analysis` (IA e estatística) | `numpy>=1.26`, `scipy>=1.13`, `pandas>=2.2`, `matplotlib>=3.8`, `schemdraw==0.23` | `pyproject.toml` |
| Extra `hardware` (ponte serial) | `pyserial==3.5` | `pyproject.toml` |
| Painel web | `react` 18.3.1, `vite` 8.3.2, `typescript` 5.9.3, `vitest` 5.0.3 | `frontend/package.json` |
| Cliente TraCI | vem com o SUMO, em `%SUMO_HOME%\tools`; **não** instalar `traci` pelo pip | `pyproject.toml` (comentário) e `README.md` |

Fonte: elaborado pelos autores (2026), a partir dos arquivos citados.

As versões efetivamente instaladas na configuração de referência foram, entre outras: fastapi 0.115.14, uvicorn 0.52.4, SQLAlchemy 2.0.52, alembic 1.19.1, pydantic 2.13.4, psycopg 3.3.4, PyJWT 2.15.1, httpx 0.28.1, numpy 2.5.3, scipy 1.18.1, pandas 3.0.6, matplotlib 3.11.2, pyserial 3.5 e pytest 9.1.1.

Portas usadas: 5432 (PostgreSQL), 8000 (API), 8443 (painel, HTTPS), 8001 (ponte serial, só no host), 8080 (Adminer, opcional, perfil `dev`) e 5173 (painel em modo de desenvolvimento).

## 3.2 Obter o projeto e preparar o Python

1. Clone o repositório e entre na pasta:

   ```powershell
   git clone https://github.com/felipepascucci/tcc-semaforos-inteligentes.git
   cd tcc-semaforos-inteligentes
   ```

2. Crie o arquivo de ambiente a partir do modelo (seção 3.5.1):

   ```powershell
   Copy-Item .env.example .env
   ```

3. Crie o ambiente virtual e instale o projeto com os três extras:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -e ".[dev,analysis,hardware]"
   ```

   O extra `hardware` instala o `pyserial`, sem o qual a ponte da bancada não roda.

4. Ative o ambiente a cada nova sessão do PowerShell:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

   Se a política de execução bloquear a ativação, use `.\.venv\Scripts\python.exe` no lugar de `python` em todos os comandos deste guia.

## 3.3 Conferir o SUMO

1. Instale o SUMO 1.27.1 pelo instalador do Windows (ECLIPSE FOUNDATION, 2026a) e abra um novo terminal.
2. Confira:

   ```powershell
   sumo --version
   $env:SUMO_HOME
   Test-Path "$env:SUMO_HOME\tools"
   ```

   Deve exibir `Eclipse SUMO sumo 1.27.1`, o diretório de instalação e `True`. Confira se `SUMO_HOME` no `.env` aponta para o mesmo diretório.

O cliente TraCI (WEGENER et al., 2008) vem em `tools` com o SUMO; não o instale pelo pip, para não haver duas versões diferentes do cliente e do simulador.

## 3.4 Configuração de borda (firmware)

### 3.4.1 Protocolos de comunicação

**As placas não usam Wi-Fi, MQTT, broker, SSID nem endereço IP.** Os NodeMCU colocam o rádio em modo estação (`WiFi.mode(WIFI_STA)`), desconectam-se de qualquer rede (`WiFi.disconnect()`) e trocam mensagens por ESP-NOW, protocolo da Espressif que entrega quadros diretamente de um dispositivo a outro, pelo endereço MAC, sem roteador (ESPRESSIF, 2026). Não há, portanto, credencial de rede a configurar. A Tabela 11 substitui os "parâmetros MQTT" pelos parâmetros dos enlaces realmente usados.

**Tabela 11 – Parâmetros dos enlaces de comunicação**

| Enlace | Meio e parâmetros | Formato da mensagem | Autenticação e criptografia |
| --- | --- | --- | --- |
| Carrinho → receptor | ESP-NOW, 2,4 GHz, canal 1; emissor `ESP_NOW_ROLE_CONTROLLER`, receptor `ESP_NOW_ROLE_SLAVE`; destino fixo: MAC do receptor `40:91:51:58:A8:E1` | Estrutura binária de 25 bytes: `char rua[10]` (`RUA1`..`RUA4`) e `char veiculo[15]` (`AMBULANCIA`, `BOMBEIRO` ou `POLICIA`); no máximo um envio a cada 3 s por carrinho | Nenhuma: ESP-NOW sem criptografia (limitação declarada) |
| Receptor → UNO | UART 9600 baud, 8N1; TX do NodeMCU no pino A0 do UNO (serial por software) | Texto ASCII `RUA3,AMBULANCIA` + `\r\n` | — |
| UNO ↔ computador | USB serial 9600 baud, 8N1 (`COM3` na referência) | Entrada: `AUT,<VEICULO>,<0..3>` (lista da Central) e `<RUA>,<VEICULO>` (injeção de teste). Saída: `ST,...` (estado, a 2 Hz e a cada mudança) e `EV,...` (eventos) | — |
| Ponte → back-end | HTTP em `127.0.0.1:8001`; o back-end lê `GET /estado` a 5 Hz e escreve `PUT /autorizacoes` | JSON | Só local (`127.0.0.1`) |
| Simulação → back-end | HTTP em `localhost:8000`, a 5 Hz, quando o executor transmite | JSON | Rede local do host |
| Painel ↔ back-end | HTTPS e WebSocket seguro em `:8443` (nginx), repassados ao back-end | JSON | TLS com certificado autoassinado; escritas exigem login (token JWT de 8 h) |

Fonte: elaborado pelos autores (2026), a partir dos sketches de `firmware/`, de `context/05` §4 e §6 e do `docker-compose.yml`.

As linhas de saída do UNO estão na Tabela 12. Elas são a telemetria que a ponte interpreta e que o back-end grava.

**Tabela 12 – Linhas que o UNO escreve no USB**

| Linha | Quando |
| --- | --- |
| `ST,<ms>,<s1><s2><s3><s4>,<regime>,<rua_ativa>,<rua_fila>,<aut>` | A 2 Hz e a cada mudança de estado. Luzes `R`, `Y`, `G` de S1 a S4; regime `C` (ciclo) ou `E` (emergência); ruas `1`..`4` ou `0`; `<aut>` = criticidade em serviço para ambulância, bombeiro e polícia (`0` = sem ocorrência) |
| `EV,<ms>,BOOT` | Ao ligar |
| `EV,<ms>,PREEMP_INI,<rua>,<veiculo>` | O VE passa a ser atendido |
| `EV,<ms>,RENOVADO,<rua>,<veiculo>` | O mesmo VE releu a mesma rua; o verde recomeça |
| `EV,<ms>,FILA,<rua>,<veiculo>` | O VE entra na fila (de um lugar) |
| `EV,<ms>,DESCARTADO,<rua>,<veiculo>` | O VE não coube na fila ou perdeu o lugar |
| `EV,<ms>,PREEMP_FIM,<rua>,<veiculo>` | Fim do verde do VE |
| `EV,<ms>,TIMEOUT` | Teto de 30 s de emergência contínua |
| `EV,<ms>,RECUSADO` | Linha com vírgula e conteúdo inválido |
| `EV,<ms>,SEM_OCORRENCIA,<rua>,<veiculo>` | O tipo do VE não tem ocorrência ativa na Central |

Fonte: `context/05` §4.2 e `firmware/uno/semaforo/`.

### 3.4.2 Preparar o arduino-cli

1. Instale o arduino-cli 1.5.1 e os drivers USB-serial das placas: CH340 e CP210x (os carrinhos da referência usam os dois conversores; sem o driver, a porta não aparece).
2. Registre o índice de placas do ESP8266 e instale os pacotes e as bibliotecas nas versões de referência:

   ```powershell
   arduino-cli config add board_manager.additional_urls https://arduino.esp8266.com/stable/package_esp8266com_index.json
   arduino-cli core update-index
   arduino-cli core install arduino:avr@1.8.8
   arduino-cli core install esp8266:esp8266@3.1.2
   arduino-cli lib install "LiquidCrystal I2C@1.1.2"
   arduino-cli lib install "MFRC522@1.4.12"
   ```

3. Confira:

   ```powershell
   arduino-cli core list
   arduino-cli lib list
   ```

   Deve listar `arduino:avr 1.8.8`, `esp8266:esp8266 3.1.2`, `LiquidCrystal I2C 1.1.2` e `MFRC522 1.4.12`.

O emissor da ambulância e o receptor foram gravados pela equipe com a Arduino IDE 2.3.10 e um pacote `esp8266` cuja versão não foi registrada; os do bombeiro e da polícia, com o `esp8266` 3.1.2. Toda regravação usa a versão 3.1.2, que é a da configuração de referência.

### 3.4.3 Gravar o Arduino UNO

1. Feche a ponte serial, se estiver aberta (ela disputa a porta com o gravador).
2. Ligue o UNO pelo USB e identifique a porta:

   ```powershell
   arduino-cli board list
   ```

   O UNO da referência aparece em `COM3`, como `Arduino Uno`.
3. Compile, grave e confira a gravação:

   ```powershell
   python -m bridge.gravar_uno --porta COM3
   ```

   Deve terminar com `Gravado e conferido: <n> bytes de semaforo.ino.hex em COM3.` O gravador do projeto relê a flash inteira e acusa erro se algum byte diferir.

**Não use `arduino-cli upload` no UNO.** Na máquina de referência, o envio padrão gravou errado os bytes 60 a 63 de cada página de 128 bytes sem acusar falha (`context/05` §3.7). Com o receptor no pino A0, não é preciso desconectar nenhum fio para gravar.

### 3.4.4 Gravar os NodeMCU

Os quatro sketches estão em `firmware/nodemcu/`: `nodeMCU_semaforo` (receptor) e `veiculo_ambulancia`, `veiculo_bombeiro` e `veiculo_policia` (emissores, que diferem só na linha `tipoVeiculoAtual`). A placa é `NodeMCU 1.0 (ESP-12E Module)`, identificada no arduino-cli como `esp8266:esp8266:nodemcuv2`.

1. Ligue **um** NodeMCU por vez ao USB e identifique a porta com `arduino-cli board list` (o Windows pode atribuir outro número a cada entrada USB).
2. Compile e grave; exemplo para o carrinho do bombeiro em `COM4`:

   ```powershell
   arduino-cli compile --fqbn esp8266:esp8266:nodemcuv2 firmware/nodemcu/veiculo_bombeiro
   arduino-cli upload  --fqbn esp8266:esp8266:nodemcuv2 -p COM4 firmware/nodemcu/veiculo_bombeiro
   ```

   O gravador do ESP8266 confere o hash da flash ao final. Na placa da polícia, a gravação só funcionou a 57600 baud: use `--fqbn esp8266:esp8266:nodemcuv2:baud=57600`.
3. **MAC do receptor.** Os três emissores enviam para o MAC fixo `40:91:51:58:A8:E1`, gravado em `enderecoReceptor[]`. Se a placa do receptor for trocada, leia o MAC da nova placa (o gravador o imprime durante o envio) e altere esse vetor **nos três** emissores antes de regravá-los.
4. **Novas tags.** O mapa UID → rua está no sketch do emissor (Tabela 13). Para descobrir o UID de uma tag nova, grave em um NodeMCU com RC522 o utilitário `docs/hardware/descobrir_ID.ino`, abra o monitor serial a 9600 baud e aproxime a tag: deve exibir `UID da Tag / Cartao: ...`.

**Tabela 13 – Mapa de tags RFID**

| UID | Rua | Semáforo | Eixo |
| --- | --- | --- | --- |
| `F39BD606` | `RUA1` | S1 | Principal, sentido A |
| `1BD2308E` | `RUA2` | S2 | Principal, sentido B |
| `B7EF8FA0` | `RUA3` | S3 | Transversal, sentido A |
| `97ABAFA0` | `RUA4` | S4 | Transversal, sentido B |

Fonte: `firmware/nodemcu/veiculo_ambulancia/veiculo_ambulancia.ino` e `context/05` §1.

### 3.4.5 Conferir a gravação

- **UNO:** ao religar, os quatro semáforos ficam em vermelho por cerca de 1 s, o LCD exibe `Semaforo: Normal` / `Aguardando Sinal`, e o ciclo começa pelo eixo principal (S1 e S2 verdes). A conferência completa é o roteiro da seção 5.1.4.
- **Emissor:** com o NodeMCU no USB, abra o monitor serial a 9600 baud e aproxime uma tag cadastrada. Deve exibir `Tag <UID> lida -> Enviando RUAn`. Tag fora da Tabela 13 não gera linha nem envio.
- **Receptor:** não há saída própria a observar. A conferência é a chegada da passagem ao UNO (seção 5.1.3).

## 3.5 Subida do back-end e do banco de dados

### 3.5.1 Variáveis de ambiente

O arquivo `.env` é criado a partir de `.env.example` (passo 2 da seção 3.2) e **nunca** é versionado. A Tabela 14 descreve as variáveis.

**Tabela 14 – Variáveis de ambiente (`.env.example`)**

| Variável | Valor de desenvolvimento | Uso |
| --- | --- | --- |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `tcc` / `senha` / `semaforo` | Credenciais do serviço `db`. Troque a senha antes de expor o ambiente |
| `DATABASE_URL` | `postgresql+psycopg://tcc:senha@localhost:5432/semaforo` | Conexão dos processos do **host** (Alembic, seeds, simulação, ponte). Dentro do Compose, o `docker-compose.yml` a redefine apontando para o serviço `db` |
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8000` | Endereço e porta da API |
| `CORS_ORIGINS` | `http://localhost:5173` | Origem do painel em modo de desenvolvimento |
| `LOG_LEVEL` | `INFO` | Nível dos logs estruturados |
| `OPERADOR_USUARIO` | `operador` | Login do painel |
| `OPERADOR_SENHA_HASH` | hash PBKDF2 da senha `operador` | Senha do operador, só como hash (seção 3.5.3) |
| `JWT_SEGREDO` | texto de desenvolvimento | Segredo dos tokens; no mínimo 32 caracteres, senão o back-end não sobe |
| `PERFIL_PARAMETROS` | `simulacao` | `simulacao` usa `backend/config/parametros.yaml`; `hardware` acrescenta `parametros.hardware.yaml` (ciclo de 12 s da bancada) |
| `SUMO_HOME` / `SUMO_BINARY` | diretório do SUMO / `sumo` | Simulação no host |
| `SERIAL_PORT` / `SERIAL_BAUDRATE` | `COM3` / `9600` | Porta e velocidade do UNO, usadas pela ponte |
| `SERIAL_PORT_VEICULO` | `COM4` | Porta do NodeMCU emissor, só na medição de latência (seção 5.2.6) |
| `BRIDGE_HOST` / `BRIDGE_PORT` | `127.0.0.1` / `8001` | API HTTP da ponte |
| `PONTE_URL` | `http://localhost:8001` | Ponte vista por um back-end rodando no host; vazia desliga a leitura |
| `PONTE_URL_CONTEINER` | `http://host.docker.internal:8001` (padrão, comentada) | Ponte vista de dentro do Compose |
| `BACKEND_URL` | `http://localhost:8000` | Para onde o executor e o atendente transmitem o estado da simulação |

Fonte: `.env.example` e `docker-compose.yml`.

### 3.5.2 Subir os serviços, migrações e seeds

1. Inicie o Docker Desktop e aguarde o mecanismo ficar ativo.
2. Construa e suba os serviços:

   ```powershell
   docker compose up -d --build
   ```

3. Confira o estado:

   ```powershell
   docker compose ps -a
   docker compose logs migracoes
   ```

   Devem aparecer `db`, `backend` e `frontend` em execução (`healthy`), e `migracoes` encerrado com código 0. O serviço `migracoes` aplica o DDL do banco (`alembic upgrade head`, scripts em `db/migrations/`) e carrega os dados de cadastro (`python -m db.seeds.carregar`), e então termina; isso é esperado. As duas operações são idempotentes: subir de novo não duplica dados.
4. Confira a API:

   ```powershell
   Invoke-RestMethod http://localhost:8000/api/v1/health
   ```

   Deve exibir `estado: ok` e `banco: ok`. Sem a bancada ligada, `ponte` aparece como `falha` e `uno_respondendo` vazio; isso não impede a operação da simulação. Sem acesso ao banco, a resposta é HTTP 503 com `estado: degradado`.

A documentação interativa da API fica em `http://localhost:8000/docs`. O Adminer, opcional, sobe com `docker compose --profile dev up -d adminer` em `http://localhost:8080`.

### 3.5.3 Trocar a credencial do operador

O login de desenvolvimento é `operador` com senha `operador`. Troque-o antes de qualquer apresentação ou acesso por terceiros:

1. Gere o hash da nova senha:

   ```powershell
   docker compose exec backend python -m app.services.autenticacao
   ```

2. Copie o hash para `OPERADOR_SENHA_HASH` no `.env` e troque `JWT_SEGREDO` por um texto próprio com pelo menos 32 caracteres.
3. Recrie o back-end: `docker compose up -d backend`. Trocar o segredo encerra as sessões abertas.

### 3.5.4 Rotinas de ingestão

O back-end recebe dados por duas rotas, ambas iniciadas no host:

- **Bancada:** a ponte serial lê o UNO e expõe o estado; o back-end consulta `GET /estado` da ponte a 5 Hz e grava os eventos em `log_prioridade` e as amostras de latência em `metrica_latencia`. A ponte é iniciada na partida da bancada (seção 5.1.2).
- **Simulação:** o executor transmite o estado ao back-end a 5 Hz e grava cada execução em `execucao_simulacao`. A simulação exige a malha e a demanda geradas (seção 3.5.5) e o atendente de pedidos (seção 3.5.6).

### 3.5.5 Gerar a malha e a demanda da simulação

Num clone novo, os arquivos de rede e demanda precisam ser construídos. Na raiz do projeto, execute na ordem, aguardando cada etapa terminar sem erro:

```powershell
python -m sim.rede.construir
python -m sim.calibracao.fluxo_saturacao
python -m sim.calibracao.cenarios
python -m sim.demanda.gerar_fluxos
python -m sim.validacao.malha --cenario leve
```

A sequência constrói a rede, mede o fluxo de saturação na própria malha, deriva os cenários e gera a demanda; o último comando valida a malha num cenário. Se a rede ou o mapa de fases mudar, atualize o mapa do painel com `python -m sim.rede.exportar_mapa`.

### 3.5.6 Iniciar o atendente de pedidos

```powershell
python -m sim.controlador.atendente
```

Mantenha o terminal aberto. O atendente roda no host porque depende do binário do SUMO: um pedido de simulação feito no painel entra numa fila no banco, e o atendente o executa e transmite o estado. Sem atendente, o pedido permanece `PENDENTE`. Para atender só o que houver na fila e sair, use `--uma-vez`.

Alternativa sem o painel, pelo terminal:

```powershell
python -m sim.controlador.executor --cenario leve --modo PREEMPCAO `
    --seed 900 --duracao 900 --sem-banco --transmitir --velocidade 5
```

`--transmitir` envia o estado ao back-end; `--sem-banco` dispensa o registro da execução; `--velocidade 5` roda a cinco vezes o tempo real, só para acompanhamento, sem mudar o resultado.

## 3.6 Instalação e inicialização do painel

O painel é construído e servido pelo serviço `frontend` do Compose (seção 3.5.2), por nginx, em HTTPS com certificado autoassinado gerado na primeira subida.

1. Abra `https://localhost:8443` no navegador.
2. Aceite a exceção do certificado autoassinado **somente** nesse endereço local.
3. Entre com a credencial do operador (seção 3.5.3).

   Deve exibir as abas **Ao vivo**, **Central**, **Logs**, **Métricas** e **Simulações**. A aba Ao vivo mostra o mapa da malha simulada e o cartão **Bancada — PROTO_CRUZ_01**.

O token de sessão vale 8 h e protege as escritas; leituras e o WebSocket são abertos. Para desenvolver o painel com recarga a quente, fora do Compose:

```powershell
cd frontend
npm ci
npm run dev
```

O painel de desenvolvimento abre em `http://localhost:5173` e repassa `/api` ao back-end da porta 8000.

## 3.7 Conferência após a instalação

1. Rode a suíte automatizada padrão (exige o Docker ativo para os testes de banco):

   ```powershell
   python -m pytest
   ```

   Deve terminar sem falhas. Por padrão ela exclui os testes marcados `sumo` e `hardware`.
2. Com a malha gerada, rode os testes que exigem o SUMO: `python -m pytest -m sumo`.
3. Rode os testes do painel: `cd frontend; npm test`.
4. Peça uma simulação pelo painel (seção 5.2.2) e confirme a passagem de `PENDENTE` para `RODANDO` e `CONCLUIDA`.

# 4 Módulo de Inteligência Artificial

## 4.1 Objetivo operacional

O módulo de IA é um **classificador binário par a par** que resolve disputas entre dois veículos de emergência que pedem fases conflitantes no mesmo cruzamento e têm a **mesma criticidade** de ocorrência. Dada a disputa entre os VEs A e B, o modelo escolhe qual dos dois recebe a preempção. O objetivo é reduzir o tempo de travessia do VE mais prejudicado da disputa (critério minimax).

O modelo atua dentro de um motor de regras, e não no lugar dele. Não são aprendidos: a exigência de ocorrência ativa, a criticidade (1 `RISCO_VIDA`, 2 `RISCO_COLETIVO`, 3 `URGENCIA`; o menor número tem precedência), a guarda que mantém uma preempção em curso no mesmo nível e as invariantes de segurança. O modelo só é consultado no modo `PREEMPCAO_ML` da simulação; nos demais modos, a disputa é resolvida pela regra determinística E8. Não há aprendizado durante a operação: os pesos são fixos e versionados.

## 4.2 Dataset de treinamento e validação

**Origem.** Os dados são **sintéticos**, gerados pelo SUMO usado como gêmeo digital da malha arterial (LOPEZ et al., 2018), no cenário `treino_multiplas`, separado do cenário de avaliação. Não há dado de sensor real nem dataset público. Cada disputa observada numa execução é **bifurcada**: a execução é refeita a partir daquele instante duas vezes, uma favorecendo A e outra favorecendo B. O rótulo é a escolha cujo ramo resultou no menor tempo de travessia do VE mais prejudicado; quando os dois ramos empatam, a disputa é excluída e contada como empate. O código que gera os rótulos é `sim/controlador/rotulagem.py`, e os rótulos versionados estão em `analysis/data/bloco10_rotulos/rotulos.csv` (versão do código `48fff16`).

**Volume.** A Tabela 15 resume o conjunto.

**Tabela 15 – Volume do dataset por divisão**

| Divisão | Seeds | Disputas | Empates (excluídos) | Exemplos | Rótulo A | Rótulo B |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Treino | 201 a 240 | 529 | 12 | 517 | 376 (72,7%) | 141 (27,3%) |
| Validação | 241 a 250 | 139 | 4 | 135 | 86 (63,7%) | 49 (36,3%) |

Fonte: `analysis/data/bloco10_rotulos/rotulos.csv`.

**Pré-processamento e engenharia de atributos.** Cada VE é descrito por quatro atributos medidos no instante da disputa: ETA ao cruzamento (s), velocidade (m/s), fila à frente por faixa (veículos) e número de cruzamentos semaforizados restantes na rota. O vetor de entrada do modelo é a **diferença A − B** desses quatro atributos. As mesmas funções calculam os atributos no treino e na inferência. O tipo do veículo não é atributo: a relevância entra pela criticidade, como regra.

**Normalização.** Cada atributo é dividido pelo seu valor RMS no conjunto de treino, **sem subtrair a média**, porque centralizar criaria um intercepto escondido e quebraria a simetria descrita na seção 4.3. Os fatores de escala ficam registrados no arquivo de pesos.

**Ponderação.** Cada exemplo pesa a margem do minimax entre as duas escolhas, em segundos: errar uma disputa em que a escolha vale 60 s custa mais do que errar uma que vale 1 s. O desbalanceamento entre A e B não foi reamostrado (seção 4.4.3).

## 4.3 Arquitetura do modelo e treinamento

**Algoritmo.** Regressão logística par a par, sem intercepto:

```
score(A, B) = w1·ΔETA + w2·Δvelocidade + w3·Δfila_por_faixa + w4·Δcruzamentos_restantes
escolhe A se score > 0; senão, B
```

**Justificativa frente às alternativas.**

- **Simetria por construção.** Sem intercepto e sobre diferenças, `score(B, A) = −score(A, B)`: trocar a ordem dos VEs troca a escolha. Árvores de decisão e redes neurais não garantem isso sem restrição adicional.
- **Explicabilidade.** Quatro pesos com unidade física; o sinal e a magnitude de cada um podem ser inspecionados e discutidos (RUSSELL; NORVIG, 2022).
- **Volume de dados.** São 517 exemplos de treino, cada um custando duas reexecuções do SUMO. Modelos com mais parâmetros, como redes neurais, teriam alto risco de sobreajuste nesse volume.
- **Custo de inferência.** A decisão é um produto escalar de quatro termos, sem framework de aprendizado de máquina no núcleo do motor; o requisito de latência de decisão do motor (inferior a 100 ms) não é afetado.

**Bibliotecas.** O ajuste usa NumPy e SciPy (otimizador L-BFGS-B, `scipy.optimize.minimize`), já presentes na pilha de análise do projeto. O roteiro do orientador cita Scikit-Learn, TensorFlow e PyTorch como exemplos; nenhum deles foi necessário: a perda logística ponderada com penalidade L2 sobre os pesos escalados é escrita em poucas linhas, com gradiente analítico verificado por teste, e evita acrescentar dependência ao projeto.

**Hiperparâmetros.** Regularização L2 com λ escolhido numa grade declarada antes do treino: {0; 0,0001; 0,001; 0,01; 0,1; 1}. O critério é a menor perda logística ponderada na validação; em empate, vence o maior λ. O modelo final é ajustado somente no treino. λ escolhido: **0,01**.

**Tabela 16 – Seleção da regularização**

| λ | Perda (treino) | Perda (validação) | Acerto (validação) | Custo médio na validação (s) |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 0,3993 | 0,5187 | 66,7% | 4,30 |
| 0,0001 | 0,3993 | 0,5183 | 66,7% | 4,30 |
| 0,001 | 0,3996 | 0,5158 | 66,7% | 4,30 |
| **0,01** | 0,4103 | **0,5118** | 66,7% | 4,30 |
| 0,1 | 0,4992 | 0,5671 | 63,7% | 4,83 |
| 1 | 0,6383 | 0,6596 | 63,7% | 4,83 |

Fonte: `analysis/data/bloco10_treino/relatorio.md`.

**Tabela 17 – Pesos do modelo (unidades originais)**

| Atributo (A − B) | Peso | Fator de escala (RMS do treino) |
| --- | ---: | ---: |
| ETA (s) | −0,0396944 | 35,357 |
| Velocidade (m/s) | −0,152886 | 7,173 |
| Fila por faixa (veículos) | +0,000681437 | 2,700 |
| Cruzamentos restantes | +0,522932 | 3,493 |

Fonte: `backend/config/politica_desempate.yaml`.

**Divisão treino/teste e método de validação.** A divisão é um *hold-out* por faixa de seeds: treino nas seeds 201 a 240, validação nas seeds 241 a 250, e o teste final da política (hipótese H4) nas seeds 1 a 50 de **outro** cenário, `multiplas_emergencias`. A divisão foi declarada antes de qualquer treino (`sim/config/cenarios.yaml`, `seeds_treino_ml`). Não foi usada validação cruzada *k-fold*, pelos seguintes motivos:

1. **Vazamento entre disputas da mesma seed.** As disputas de uma mesma execução compartilham a mesma realização do tráfego e, muitas vezes, os mesmos VEs em instantes próximos. Um *k-fold* por exemplo colocaria disputas quase idênticas no treino e na validação e superestimaria o acerto. Separar por seed elimina esse vazamento.
2. **Custo de rotulagem.** Cada exemplo exige duas reexecuções do SUMO a partir do instante da disputa. O conjunto é fixo e pequeno, e a validação serve a uma única escolha (o λ), numa grade de seis valores.
3. **Teste independente.** A avaliação que decide a utilidade da política não é o acerto na validação, mas H4: a política executando de verdade no motor, em seeds e cenário que o treino nunca viu, comparada pareadamente com a regra E8.

Uma validação cruzada agrupada por seed seria a alternativa compatível com o motivo 1, e não foi realizada. Como a validação também escolheu o λ, ela não é um teste cego; a escolha mexe pouco no acerto (66,7% para todo λ ≤ 0,01, Tabela 16).

## 4.4 Resultados e métricas empíricas

### 4.4.1 Matriz de confusão e métricas por classe

As métricas foram calculadas sobre as predições do modelo versionado, exemplo a exemplo, pelo script `analysis/metricas_politica.py`. A classe A é o VE do corredor (o primeiro da disputa) e B, o outro.

**Tabela 18 – Matriz de confusão na validação (135 exemplos)**

| Rótulo \ escolha do modelo | A | B | Total |
| --- | ---: | ---: | ---: |
| A | 85 | 1 | 86 |
| B | 44 | 5 | 49 |
| Total | 129 | 6 | 135 |

Fonte: `analysis/data/bloco10_treino_metricas/matriz_confusao.csv`.

**Tabela 19 – Métricas por classe**

| Divisão | Classe | Precisão | Revocação | F1 | Suporte |
| --- | --- | ---: | ---: | ---: | ---: |
| Treino | A | 73,9% | 95,7% | 83,4% | 376 |
| Treino | B | 46,7% | 9,9% | 16,4% | 141 |
| Treino | média macro | 60,3% | 52,8% | 49,9% | 517 |
| Validação | A | 65,9% | 98,8% | 79,1% | 86 |
| Validação | B | 83,3% | 10,2% | 18,2% | 49 |
| Validação | média macro | 74,6% | 54,5% | 48,6% | 135 |

Fonte: `analysis/data/bloco10_treino_metricas/metricas.csv`. Acurácia: 72,3% no treino e 66,7% na validação.

A matriz de confusão do treino está no mesmo arquivo (360, 16, 127 e 14, na ordem A→A, A→B, B→A, B→B).

### 4.4.2 Comparação com as regras de referência

**Tabela 20 – Acerto e custo na validação, por política**

| Política | Acerto | Custo médio (s) |
| --- | ---: | ---: |
| Modelo aprendido | 66,7% | 4,30 |
| Sempre o VE do corredor (A) | 63,7% | 4,83 |
| Regra E8 determinística | 60,7% | 7,19 |
| Menor ETA | 56,3% | 6,43 |

Fonte: `analysis/data/bloco10_treino/avaliacao.csv`. O custo médio é a margem do minimax perdida nas escolhas erradas, por exemplo.

### 4.4.3 Discussão

- **O modelo raramente escolhe B.** Ele escolheu B em 6 de 135 disputas da validação e acertou 5 delas (precisão de B de 83,3%), mas deixou passar 44 das 49 disputas em que B era a melhor escolha (revocação de B de 10,2%; F1 de 18,2%). Na prática, o modelo se aproxima da regra "sempre A", com 3 pontos percentuais a mais de acerto e 0,53 s a menos de custo médio.
- **O desbalanceamento não foi corrigido, por decisão.** A vence em 72,7% do treino porque o VE do corredor costuma ter mais cruzamentos pela frente, e o critério minimax o favorece: é sinal do problema, não defeito da amostra. Reamostrar ou repesar as classes trocaria o critério (minimizar o pior tempo) por outro (acertar B), e a ponderação pela margem já faz cada erro custar o que custa em segundos.
- **O ganho sobre a E8 se concentra num cruzamento.** No CRUZ_08, o modelo acerta 87,0% na validação, contra 64,8% da E8 e 83,3% de "sempre A"; no CRUZ_02, acerta 53,1%, contra 58,0% da E8 e 50,6% de "sempre A" (`analysis/data/bloco10_treino/relatorio.md`).

### 4.4.4 Teste independente (H4)

Na avaliação final, com a política executando no motor (modo `PREEMPCAO_ML`) contra a regra E8 (modo `PREEMPCAO`), pareada por seed nas seeds 1 a 50 do cenário `multiplas_emergencias`, a mediana da diferença do tempo do VE mais prejudicado foi de **−4,6 s**, com intervalo de confiança de 95% de −11,0 a 2,6 s, δ de Cliff de −0,22 e p de Holm de 0,174. O veredito, por regra declarada antes dos dados, é **nulo**: a política aprendida não superou a regra determinística de forma significativa. O modelo decidiu 429 disputas e divergiu da E8 em 323. A diferença entre os modos inclui a posição da guarda de oscilação, que no modo `PREEMPCAO_ML` atua antes do modelo; os dois efeitos não foram isolados. Fonte: `analysis/saida/h4.md`.

## 4.5 Limitações

- Uma única geometria de encontro entre VEs e rótulos predominantemente favoráveis ao VE do corredor.
- Dados sintéticos com detecção ideal: o simulador entrega posição, velocidade e rota sem ruído. Não há garantia de generalização para outra malha nem para sensores reais.
- A criticidade é atribuída pelo cenário, e não por um despacho real.
- A política não executa na bancada física (seção 1.4).

## 4.6 Reproduzir as métricas e o ajuste

O sistema opera com os pesos versionados. Para regenerar as métricas da seção 4.4.1, que só leem o modelo e os rótulos:

```powershell
python -m analysis.metricas_politica
```

Deve reproduzir as Tabelas 18 e 19 em `analysis/data/bloco10_treino_metricas/relatorio.md`.

Para refazer o ajuste **sem sobrescrever** os pesos e as tabelas versionados, aponte as três saídas para uma pasta de trabalho:

```powershell
python -m analysis.treino_politica --pesos work/politica_desempate.yaml `
    --saida-dados work/treino --relatorio work/relatorio_treino.md
```

Sem `--pesos` e `--saida-dados`, o script grava sobre `backend/config/politica_desempate.yaml` e `analysis/data/bloco10_treino/`. O ajuste é determinístico: os pesos de `work/` devem coincidir com os versionados, o que o teste `analysis/tests/test_treino_politica.py` também confere. A geração dos rótulos (`sim/controlador/rotulagem.py`) é custosa e não faz parte da operação.

## 4.7 Declaração formal de uso de IA assistiva

A equipe declara que utilizou o modelo de linguagem Claude (Anthropic), por meio da ferramenta Claude Code, como apoio em três frentes:

- **Codificação:** geração e revisão de trechos de código do back-end, da integração com o SUMO, da ponte serial, do painel web, do firmware do controlador, dos testes automatizados e dos scripts de análise, incluindo o script de métricas da seção 4.4.
- **Documentação:** leitura do repositório, organização e redação preliminar deste guia e da documentação técnica do projeto.
- **Diagramação:** elaboração dos códigos-fonte que geram os diagramas e os esquemas elétricos (PlantUML e schemdraw).

Nenhum outro modelo de linguagem foi utilizado. A arquitetura, os requisitos e as decisões de projeto foram definidos pela equipe, que executou e validou o sistema na bancada física e na simulação. Os números apresentados neste guia foram produzidos pela execução de scripts versionados sobre dados reais das execuções, e não gerados pela ferramenta. A equipe executora assume inteira responsabilidade técnica por todos os artefatos, em conformidade com a Portaria CNPq nº 2.664/2026 (CONSELHO NACIONAL DE DESENVOLVIMENTO CIENTÍFICO E TECNOLÓGICO, 2026). O desempate semafórico em operação usa exclusivamente a regressão logística descrita nesta seção; nenhum modelo de linguagem participa das decisões do sistema.

# 5 Manual de Operação e Diagnóstico

## 5.1 Partida e calibração

### 5.1.1 Ordem de partida

Ligue na ordem abaixo. O back-end vem antes da bancada porque é ele que leva ao UNO a lista da Central, e o UNO sempre liga negando todos os veículos.

1. **Serviços:** inicie o Docker Desktop, rode `docker compose up -d` e confira o `/api/v1/health` (seção 3.5.2).
2. **Cruzamento:** ligue o cabo USB do Arduino UNO ao computador. O UNO é alimentado só por esse cabo, e o NodeMCU receptor recebe 5 V do UNO, então ambos ligam juntos. Deve-se observar: os quatro semáforos em vermelho por cerca de 1 s; o LCD com `Semaforo: Normal` / `Aguardando Sinal`; em seguida, o ciclo pelo eixo principal; e o LED da placa do receptor aceso.
3. **Ponte serial:** num terminal no host, inicie a ponte (seção 5.1.2).
4. **Carrinhos:** ligue a power bank de cada carrinho ao micro-USB do NodeMCU.
5. **Painel:** abra `https://localhost:8443`, entre como operador e confira o cartão da bancada na aba Ao vivo.

### 5.1.2 Iniciar a ponte e verificar o handshake

1. Inicie a ponte com a porta do UNO:

   ```powershell
   python -m bridge.main --porta COM3
   ```

   Abrir a porta **reinicia o UNO**, que volta pelo all-red e negando todos. Isso é esperado.
2. Confira a ponte:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8001/health
   ```

   Deve exibir `estado: ok`, `conectada: True`, `uno_respondendo: True`, `ultima_telemetria_ha_s` abaixo de 2 e `telemetrias_violando_i1: 0`. Com o UNO calado, a resposta é HTTP 503 com `estado: degradado`.
3. Confira o back-end: em `http://localhost:8000/api/v1/health`, `ponte` deve estar `ok` e `uno_respondendo`, `True`.
4. Confira o painel: o cartão **Bancada — PROTO_CRUZ_01** deve mostrar as luzes de S1 a S4 mudando a cada fase, `Regime: Ciclo normal` e `Em serviço no UNO: ninguém (nenhum VE preempta)`, enquanto não houver ocorrência aberta.

O ESP-NOW não estabelece conexão: não há handshake entre carrinho e receptor. O enlace é verificado por uma passagem de teste (seção 5.1.3).

### 5.1.3 Calibração em repouso

O protótipo não tem sensores analógicos a zerar. A calibração em repouso consiste em confirmar que cada leitura e cada indicação está dentro do esperado antes de operar:

1. **Ciclo:** no painel ou no LCD, confirme o ciclo de 12 s: eixo principal verde por 3 s, amarelo por 2 s, all-red por 1 s, e o mesmo no eixo transversal.
2. **Leitura das tags:** sem ocorrência aberta, passe cada carrinho sobre cada tag, com o leitor a 2–5 cm. Para cada passagem deve-se observar: o LCD com `SEM OCORRENCIA` na primeira linha e o veículo e a rua na segunda (por exemplo, `AMBULANCIA na R3`) por 3 s; o semáforo **sem** alteração; e, na aba Logs, um registro `Bancada: SEM_OCORRENCIA` com o tipo e a rua corretos. Uma passagem sem registro indica falha de leitura ou de enlace (seção 5.3).
3. **LCD:** se o visor acender sem caracteres, ajuste o potenciômetro de contraste no módulo I2C, atrás do LCD.
4. **Lista da Central:** abra uma ocorrência na aba Central (seção 5.2.3). Em até cerca de 1 s, o cartão da bancada deve mostrar o tipo em `Em serviço no UNO`.

### 5.1.4 Conferência completa (aceitação)

Depois de manutenção, regravação de firmware ou troca de componente, rode o roteiro de aceitação, com o **back-end parado** (`docker compose stop backend`), porque ele substituiria a lista da Central que o roteiro envia:

```powershell
python -m bridge.main --porta COM3      # terminal 1
python -m bridge.verificar              # terminal 2, logo em seguida
```

O roteiro leva cerca de 4 min e confere, pela telemetria do UNO: boot em all-red e ciclo de 12 s; chegada da lista da Central; verde exclusivo em até 6 s; duração por tipo (9, 8 e 7 s); renovação, interrupção por criticidade maior, fila e descarte; volta pelo eixo oposto; teto de 30 s; `RECUSADO`; `SEM_OCORRENCIA`; e as invariantes I1 a I4 em toda a telemetria. Cada conferência é impressa como `[ok  ]`, `[FALHA]` ou `[n/o ]` (não observada), e o roteiro termina com `<n> de <n> conferências ok.` e código de saída 0. O LCD, a leitura das tags, o ESP-NOW e o receptor ficam fora do alcance do roteiro e são conferidos na seção 5.1.3. Ao final, suba o back-end de novo (`docker compose start backend`).

## 5.2 Operação diária

### 5.2.1 Operar a bancada

1. Na aba **Central**, abra uma ocorrência para o veículo que vai circular e escolha a criticidade (seção 5.2.3).
2. Confira no cartão da bancada que o tipo aparece em `Em serviço no UNO`, com a criticidade.
3. Passe o carrinho sobre a tag da rua de aproximação. Deve-se observar: o eixo aberto passa pelo amarelo e pelo all-red; só o semáforo da rua do carrinho fica verde; o LCD mostra o veículo e a rua (`AMBULANCIA na R3`); e o painel registra o evento.
4. Ao fim do verde do tipo (9 s para ambulância, 8 s para bombeiro, 7 s para polícia), o ciclo volta pelo eixo oposto ao do último VE, que ficou esperando.
5. Encerre a ocorrência na Central quando o atendimento terminar. Encerrar não corta um verde já concedido: ele termina pela duração do tipo.

**Interpretar o cartão da bancada.** `Regime` indica ciclo normal ou emergência; `Eixo aberto`, principal (S1+S2) ou transversal (S3+S4); `Rua atendida`, a aproximação com verde exclusivo; `Fila`, o VE que aguarda; `Em serviço no UNO`, a lista da Central que o UNO tem de fato, lida da telemetria.

**Tabela 21 – Mensagens do LCD**

| Situação | Linha 1 | Linha 2 |
| --- | --- | --- |
| Ciclo normal | `Semaforo: Normal` | `Aguardando Sinal` |
| VE atendido | `AMBULANCIA na R3` | (vazia) |
| VE atendido com fila | `AMBULANCIA na R3` | `Fila:BOMB na R1` |
| Tipo sem ocorrência (3 s) | `SEM OCORRENCIA` | `AMBULANCIA na R3` |

Fonte: `context/05` §3.6 e `firmware/uno/semaforo/controlador.cpp`.

**Disputa entre veículos.** Com dois carrinhos em serviço, vence o de criticidade estritamente mais alta (número menor); no mesmo nível, fica quem chegou primeiro, e o segundo vai para a fila de um lugar. Um terceiro VE de mesmo nível, com a fila ocupada, é descartado.

**Preempção manual (teste).** No cartão de preempção manual da aba Ao vivo, ou por `POST /api/v1/semaforos/PROTO_CRUZ_01/preempcao` com `{"rua": 3, "veiculo": "AMBULANCIA"}`, a ponte injeta no UNO a mesma linha que o receptor enviaria. A decisão continua sendo do UNO e passa pela Central. Para os cruzamentos da simulação (CRUZ_01 a CRUZ_08), a preempção manual responde HTTP 409, porque o motor roda no processo do executor; escolha o modo na aba Simulações.

**Demonstração guiada.** Com o Compose, a ponte e o painel no ar, `python -m bridge.demo` conduz o apresentador em seis passos (ciclo normal, tag sem ocorrência, despacho pela Central, preempção, disputa por criticidade com os carrinhos e autonomia do cruzamento sem a ponte). `--sem-carrinho` substitui o carrinho pela injeção da ponte. O roteiro não é medição: nenhum número dele vai para resultados.

### 5.2.2 Pedir uma simulação

1. Na aba **Simulações**, escolha o cenário (`leve`, `moderado`, `intenso` ou `multiplas_emergencias`) e o modo (Tabela 22). Para observar a política aprendida, use `multiplas_emergencias` com `PREEMPCAO_ML`.
2. Informe a seed, a duração e a velocidade. Para demonstração: seed 900, 900 s e velocidade 5x ou 10x. As seeds 1 a 50 (experimento), 101 a 105 (calibração) e 201 a 250 (treino e validação do modelo) são reservadas e recusadas; o painel exibe as faixas ao lado do campo.
3. Clique em **Pedir** e acompanhe em Pedidos recentes: `PENDENTE`, `RODANDO`, `CONCLUIDA` ou `FALHA`.
4. Na aba **Ao vivo**, acompanhe o mapa, os semáforos e os eventos. O primeiro VE entra depois do aquecimento de 300 s simulados.
5. Ao concluir, leia o resumo: viagens, travessia média, paradas, latência p95, colisões e violações. Sem viagem concluída, zero não é um tempo medido.

**Tabela 22 – Modos de controle**

| Modo | Comportamento |
| --- | --- |
| `FIXO` | Temporização fixa, sem preempção |
| `PREEMPCAO` | Preempção com desempate pela regra determinística E8 |
| `PREEMPCAO_COMPENSADA` | Preempção e compensação posterior do ciclo para o fluxo transversal |
| `PREEMPCAO_ML` | Preempção com a política aprendida nos conflitos de mesma criticidade, sem compensação |

Fonte: `context/01` e `sim/config/cenarios.yaml`.

Para comparar modos, mantenha cenário, seed, duração e parâmetros. As saídas de cada pedido ficam em `sim/saida/<cenario>_<modo>_<seed>/`.

**Decisões do módulo preditivo.** O painel não exibe a decisão individual do modelo. Em cada execução do modo `PREEMPCAO_ML`, o arquivo `sim/saida/<ponto>/conflitos_por_execucao.csv` registra cada disputa, com as colunas `decidida_pelo_modelo` e `modelo_divergiu_do_e8`. O efeito agregado da política está em `analysis/saida/h4.md` (seção 4.4.4).

### 5.2.3 Usar a Central

1. Na aba **Central**, selecione um veículo ativo e livre em Abrir ocorrência.
2. Escolha a criticidade: risco de vida, risco coletivo ou urgência. A descrição é opcional, com até 200 caracteres.
3. Clique em **Abrir ocorrência** e confirme o registro em Em serviço e a situação da Frota.
4. Ao terminar, clique em **Encerrar** no registro e confira que ele saiu de Em serviço.

Na bancada, a lista chega ao UNO pelo back-end em até cerca de 1 s. Na simulação, os VEs em serviço e as criticidades vêm do cenário; abrir uma ocorrência na Central não altera uma simulação.

### 5.2.4 Consultar os logs

Na aba **Logs**, filtre por semáforo, status, veículo, correlação ou período; clique em **Filtrar** para aplicar e em **Limpar** para zerar. Cada página exibe até 50 registros. Clique no identificador de correlação para reunir os registros da mesma priorização. Os horários do formulário são convertidos para UTC. Os eventos da bancada aparecem com o motivo iniciado por `Bancada:`.

**Tabela 23 – Status dos registros de priorização**

| Status | Significado | Eventos da bancada |
| --- | --- | --- |
| `SUCESSO` | Priorização concluída | `PREEMP_INI`, `RENOVADO` |
| `CONFLITO_ADIADO` | Pedido adiado pela resolução de conflito | `FILA` |
| `FALHA` | Pedido não atendido; leia o motivo | `SEM_OCORRENCIA`, `DESCARTADO` |
| `TIMEOUT` | Encerrado pelo teto de tempo | `TIMEOUT` (teto de 30 s) |
| `ABORTADO_SEGURANCA` | Proteção interrompeu a ação; preserve o registro e investigue antes de repetir | — |

Fonte: `backend/app/services/bancada.py` e `backend/app/models/enums.py`.

Na simulação, as transições detalhadas só são gravadas em execuções com `--exemplar`.

### 5.2.5 Interpretar as métricas

Na aba **Métricas**, acompanhe a latência de decisão em milissegundos e o tamanho da amostra. O p95 é o valor abaixo do qual estão 95% das amostras; o p99, 99%. O requisito de decisão do motor é inferior a 100 ms. Quando o painel indicar "sem dado ao vivo", inicie uma execução e confira a transmissão. Ao registrar evidências, anote cenário, seed, modo e número de amostras.

### 5.2.6 Registro de evidências da bancada

Para gravar a telemetria crua (checklist) e medir a latência da leitura da tag até a decisão do UNO, o NodeMCU do carrinho fica no USB do computador no lugar da power bank, e a ponte abre as duas portas:

```powershell
python -m bridge.main --porta COM3 --porta-veiculo COM5 --telemetria
```

Os registros vão para `analysis/data/` (`telemetria_bancada.csv`, `deteccoes_bancada.csv` e `latencia_bancada.csv`), e os resumos saem de `python -m analysis.resumo_bancada --sessao <sessão>` e `python -m analysis.checklist_bancada --todas --banco`. Na rodada de 7 de outubro de 2026, as 100 leituras chegaram ao UNO com a rua certa, e o p95 da latência fim a fim foi de 31,6 ms (`analysis/data/resumo_bancada_2026-10-07.md`).

## 5.3 Resolução de problemas

**Tabela 24 – Troubleshooting: serviços e simulação**

| Sintoma | Causa provável | Procedimento corretivo |
| --- | --- | --- |
| Painel não abre em `https://localhost:8443` | `frontend` parado, porta ocupada, ou `backend` não saudável (o nginx só sobe depois dele) | `docker compose ps -a`; `docker compose logs frontend backend`; libere a porta 8443 ou ajuste `DASHBOARD_PORT` |
| `/api/v1/health` retorna 503 | Banco inacessível ou credencial errada | Leia `docker compose logs db backend migracoes`; compare as credenciais do `.env`. Não apague o volume para tentar corrigir |
| `migracoes` termina com código diferente de 0 | Falha de conexão ou de DDL | `docker compose logs migracoes`; corrija a causa e rode `docker compose up -d` de novo |
| Back-end não sobe e cita `JWT_SEGREDO` | Segredo com menos de 32 caracteres | Use um segredo com pelo menos 32 caracteres no `.env` |
| Escrita retorna 401 | Sessão expirada (8 h) ou segredo trocado | Entre de novo no painel |
| Pedido de simulação fica `PENDENTE` | Atendente parado | Inicie `python -m sim.controlador.atendente`; confira `BACKEND_URL` |
| Pedido termina em `FALHA` | SUMO ausente ou malha não gerada | Leia a mensagem do pedido; confira `sumo --version` e gere a malha (seção 3.5.5) |
| Seed recusada | Seed numa faixa reservada | Use uma seed fora de 1–50, 101–105 e 201–250, como 900 |
| "Sem dado ao vivo" no painel | Nenhum executor transmitindo | Peça uma simulação com o atendente no ar, ou use `--transmitir` no executor |
| Nenhum VE no início da simulação | Aquecimento de 300 s do cenário | Aguarde; use duração que permita concluir viagens |
| Preempção manual retorna 409 | Cruzamento da simulação, sem atuador ligado à API | Mude o comportamento pelo modo, na aba Simulações |

Fonte: elaborado pelos autores (2026).

**Tabela 25 – Troubleshooting: bancada (comunicação, sensores e alimentação)**

| Sintoma | Causa provável | Procedimento corretivo |
| --- | --- | --- |
| Passagem do carrinho não gera evento (perda de mensagem) | Tag fora do alcance (2–5 cm); tag fora do mapa; envio menos de 3 s depois do anterior (o emissor ignora); receptor desligado; carrinho com o MAC de outro receptor | Passe de novo, mais perto e 3 s depois; confira com o emissor no USB a linha `Tag <UID> lida -> Enviando RUAn` a 9600 baud; confira o LED do receptor; confira `enderecoReceptor[]` (seção 3.4.4) |
| Carrinho não responde e o LED da NodeMCU está apagado | Power bank descarregada, desligada ou com o cabo solto | Recarregue ou religue a power bank e confira o cabo no micro-USB |
| O emissor não imprime nada ao aproximar a tag | Leitor RC522 não lê: jumper solto, leitor reiniciando, ou power bank desligada | Refaça as conexões do RC522 (os pinos do leitor foram soldados para leitura estável); confira se o leitor está em 3,3 V, nunca 5 V; no carrinho da polícia, o RST do RC522 deve estar no 3V3 |
| `EV,RECUSADO` no log da ponte (leitura fora de faixa) | Linha corrompida na serial, ou tipo/rua desconhecidos | Linhas sem vírgula (lixo de boot do ESP8266, a 74880 baud) são ignoradas pelo UNO. `RECUSADO` repetido junto com reinícios do receptor indica alimentação insuficiente (linha abaixo) |
| Passagem gera `SEM_OCORRENCIA` | O tipo do carrinho não tem ocorrência aberta, ou o UNO reiniciou e ainda não recebeu a lista | Abra a ocorrência na Central; confira `Em serviço no UNO` no cartão da bancada |
| `Em serviço no UNO` não acompanha a Central | Ponte ou back-end fora do ar; UNO reiniciado | Confira `ponte: ok` no `/api/v1/health`; o back-end reenvia a lista sozinho quando ela difere da do UNO (no máximo uma vez por segundo) |
| Ponte com `uno_respondendo: False` ou HTTP 503 (desconexão) | Cabo USB solto, porta errada, ou outro programa usando a porta | Confira `arduino-cli board list`; feche o monitor serial e o gravador; a ponte reconecta sozinha quando a porta volta (contador `reconexoes`) |
| Ponte não abre a porta | Porta ocupada pelo gravador, pelo monitor serial ou por outra ponte | Feche o outro processo e reinicie a ponte |
| Saturação de buffer: `ST` periódicas faltando ou `bytes_em_espera` alto | A saída serial do UNO (64 bytes a 9600 baud) ficou cheia; a `ST` periódica é pulada de propósito, e eventos nunca são pulados | Não é falha: as `ST` de mudança de estado não se perdem. Se persistir, reduza a carga do computador; não aumente a taxa de leitura |
| Passagem perdida sem `RECUSADO` correspondente | Pedaço de linha seguido de mais de 100 ms de silêncio é descartado; linha maior que o buffer (32 bytes no A0, 72 no USB) é recusada | Comportamento de proteção: um VE nunca nasce de texto corrompido. Repita a passagem |
| Receptor reinicia, LED fraco, ou o UNO reinicia ao ligar o receptor (subtensão) | Receptor alimentado pelo VIN ou pelo 3,3 V do UNO | Alimente o receptor pelo pino 2 (5 V) do ICSP do UNO, ligado ao VIN do NodeMCU. **Nunca ligue fio ao pino 5 do ICSP (RESET)**: ele mantém o UNO reiniciando |
| LCD aceso sem caracteres | Contraste desajustado | Ajuste o potenciômetro atrás do módulo I2C |
| LCD sem resposta | Fiação I2C (A4/A5) ou endereço diferente de `0x27` | Confira as ligações SDA→A4 e SCL→A5 e a alimentação em 5 V |
| Gravação do UNO falha ou o UNO se comporta de forma estranha depois de gravado | Gravação com `arduino-cli upload` (bytes corrompidos), ou ponte aberta durante a gravação | Feche a ponte e regrave com `python -m bridge.gravar_uno --porta COM3` |
| Porta do NodeMCU não aparece | Driver CH340 ou CP210x ausente, ou cabo só de carga | Instale o driver do conversor da placa; troque o cabo |
| Gravação do NodeMCU com ruído | Velocidade de gravação alta para a placa | Grave a 57600 baud (`:baud=57600` no FQBN) |
| Semáforo continua operando com a ponte encerrada | Comportamento esperado: o UNO decide sozinho com a última lista recebida | Nenhum; só o painel e a Central deixam de alcançar o UNO |

Fonte: elaborado pelos autores (2026), a partir de `context/05`, `context/09` e dos registros das sessões de bancada de outubro de 2026.

## 5.4 Desligamento seguro e manutenção preventiva

### 5.4.1 Desligamento

1. Encerre as ocorrências abertas na Central.
2. Aguarde o fim das simulações em andamento e anote os pedidos em `FALHA`.
3. Encerre o atendente e a ponte com Ctrl+C. Se interromper uma execução, confira o status do pedido antes de reenviar.
4. Desligue as power banks dos carrinhos.
5. Desconecte o USB do UNO. Fechar a ponte não reinicia o UNO; desconectar o cabo o desliga, junto com o receptor, e ao religar ele volta negando todos.
6. Pare os serviços preservando os dados: `docker compose stop`. `docker compose down` também preserva o volume do banco. **Não use `-v`**, que apaga o banco.

### 5.4.2 Manutenção preventiva

- **Sensores e conexões:** com tudo desligado, mantenha as tags e a face do leitor RC522 limpas e secas, sem objetos metálicos entre elas; confira jumpers frouxos, em especial os do RC522 nos carrinhos, cujo mau contato com o carrinho em movimento já causou perda de leituras.
- **Inspeção visual:** confira se algum LED está com brilho anômalo ou aquecimento (item 13 do checklist da bancada).
- **Atualização de firmware:** regrave pelos procedimentos da seção 3.4 e rode a aceitação da seção 5.1.4. Trocar a placa do receptor exige regravar os três emissores com o novo MAC.
- **Software:** antes de atualizar, finalize os pedidos e faça backup; obtenha a revisão aprovada pela equipe e rode `docker compose up -d --build`, conferindo as migrações. Mudanças na rede ou na dinâmica dos veículos exigem refazer a calibração (seção 3.5.5); mudanças na política exigem revisar relatório e pesos (seção 4.6).
- **Disco e logs:** confira o espaço em disco e os logs dos serviços periodicamente.

### 5.4.3 Backup

Com o banco ativo:

```powershell
New-Item -ItemType Directory -Force backups
docker compose exec -T db pg_dump -U tcc -d semaforo -Fc -f /tmp/semaforo.dump
$dbId = docker compose ps -q db
docker cp "${dbId}:/tmp/semaforo.dump" .\backups\semaforo.dump
```

O arquivo é gerado dentro do contêiner e copiado como binário, o que evita o redirecionamento textual do PowerShell. Substitua `tcc` e `semaforo` se tiver alterado as credenciais. Guarde também, com acesso restrito: o `.env`, a revisão do código e os arquivos de `analysis/data/` e `sim/saida/` necessários.

### 5.4.4 Testar a recuperação

Restaure num banco separado e vazio, nunca sobre o banco em operação:

```powershell
docker compose exec -T db createdb -U tcc semaforo_restaurado
$dbId = docker compose ps -q db
docker cp .\backups\semaforo.dump "${dbId}:/tmp/restaurar.dump"
docker compose exec -T db pg_restore -U tcc -d semaforo_restaurado --no-owner /tmp/restaurar.dump
```

Se `semaforo_restaurado` já existir, escolha outro nome.

# Referências

ARDUINO. **Arduino UNO R3**: product reference manual. SKU A000066. Rev. 4, 20 out. 2026. Disponível em: https://docs.arduino.cc/resources/datasheets/A000066-datasheet.pdf. Acesso em: 5 nov. 2026.

ATMEL. **ATmega328P**: 8-bit AVR microcontroller with 32K bytes in-system programmable flash, automotive. 7810D-AVR-01/15. San Jose: Atmel, 2015. Disponível em: https://ww1.microchip.com/downloads/en/DeviceDoc/Atmel-7810-Automotive-Microcontrollers-ATmega328P_Datasheet.pdf. Acesso em: 5 nov. 2026.

CONSELHO NACIONAL DE DESENVOLVIMENTO CIENTÍFICO E TECNOLÓGICO (Brasil). Portaria CNPq nº 2.664, de 6 de março de 2026. Institui a Política de Integridade na Atividade Científica do CNPq. **Diário Oficial da União**: seção 1, Brasília, DF, n. 47, p. 4, 11 mar. 2026.

ECLIPSE FOUNDATION. **Eclipse SUMO**: Simulation of Urban MObility. 2026a. Disponível em: https://eclipse.dev/sumo/. Acesso em: 10 out. 2026.

ESPRESSIF. **ESP8266EX datasheet**. Version 7.1. Shanghai: Espressif Systems, 2025. Disponível em: https://documentation.espressif.com/0a-esp8266ex_datasheet_en.pdf. Acesso em: 5 nov. 2026.

ESPRESSIF. **ESP-NOW**. 2026. Disponível em: https://www.espressif.com/en/solutions/low-power-solutions/esp-now. Acesso em: 10 out. 2026.

LOPEZ, P. A. et al. Microscopic traffic simulation using SUMO. *In*: IEEE INTERNATIONAL CONFERENCE ON INTELLIGENT TRANSPORTATION SYSTEMS, 21., 2018, Maui. **Proceedings** [...]. Piscataway: IEEE, 2018. p. 2575-2582.

NODEMCU TEAM. **NodeMCU DevKit v1.0**: schematic. 2015. Disponível em: https://github.com/nodemcu/nodemcu-devkit-v1.0. Acesso em: 5 nov. 2026.

NXP SEMICONDUCTORS. **MFRC522**: standard performance MIFARE and NTAG frontend. Product data sheet, Rev. 3.9. Eindhoven: NXP, 27 abr. 2016. Disponível em: https://www.nxp.com/docs/en/data-sheet/MFRC522.pdf. Acesso em: 5 nov. 2026.

RUSSELL, S. J.; NORVIG, P. **Artificial intelligence**: a modern approach. 4. ed. Harlow: Pearson, 2022.

USB IMPLEMENTERS FORUM. **Universal Serial Bus specification**: revision 2.0. [S. l.]: USB-IF, 2000.

WEGENER, A. et al. TraCI: an interface for coupling road traffic and network simulators. *In*: COMMUNICATIONS AND NETWORKING SIMULATION SYMPOSIUM, 11., 2008, Ottawa. **Proceedings** [...]. San Diego: SCS, 2008. p. 155-160.
