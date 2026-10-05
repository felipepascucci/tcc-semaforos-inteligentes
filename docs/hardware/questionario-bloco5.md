# Questionário do hardware — Bloco 5

Vamos reescrever o programa do Arduino UNO e do NodeMCU. Para isso precisamos saber
exatamente como a bancada está montada hoje. Responda embaixo de cada pergunta;
"não sei" é resposta válida.

> **Respondido pela equipe de hardware em 2026-10-05.** As respostas estão
> transcritas como vieram. Os sketches citados em 1.2 estão nesta pasta:
>
> | Arquivo | Placa | O que faz |
> | --- | --- | --- |
> | `veiculo_ambulancia.ino` | NodeMCU **emissor**, no veículo | Lê a tag da rua com o RC522 e envia `rua` + `veiculo` por ESP-NOW |
> | `nodeMCU_semaforo.ino` | NodeMCU **receptor**, no cruzamento | Recebe o ESP-NOW e repassa `RUA2,AMBULANCIA` pelo TX ao RX (pino 0) do UNO, a 9600 baud |
> | `semaforo.ino` | Arduino UNO | Ciclo dos 4 semáforos, LCD e a decisão de prioridade (fila por tipo de veículo) |
> | `descobrir_ID.ino` | NodeMCU | Utilitário: imprime o UID da tag no Monitor Serial |
> | `TAG.ino` | NodeMCU | Teste antigo da tag; não é mais usado |

## 1. O que já existe

**1.1** O que já funciona hoje? (marque com X)
- [x] Os 4 semáforos fazem o ciclo sozinhos
- [x] O leitor RFID (RC522) lê as tags
- [x] O LCD mostra texto
- [x] O NodeMCU conecta no Wi-Fi — *o código usa o Wi-Fi nativo em modo Station, mas
  executa `WiFi.disconnect()` para operar só por ESP-NOW, MAC a MAC*
- [ ] O NodeMCU já enviou dados para algum servidor — *a comunicação é descentralizada
  e não usa servidor*
- [x] O Arduino recebe comandos pelo cabo USB (Serial) — *recebe pela Serial, mas pelos
  pinos TX/RX ligados ao NodeMCU, e não pelo USB. O USB serve só de alimentação*

**1.2** Pode mandar os arquivos `.ino` que rodam hoje no Arduino e no NodeMCU?

R: Os códigos estão no documento "Protótipo documentado.v3.docx", nas seções de
controle semafórico (Arduino UNO), identificação (NodeMCU emissor) e recepção
(NodeMCU receptor). Os `.ino` foram salvos nesta pasta (ver a tabela acima).

**1.3** Qual programa você usa para gravar as placas? (Arduino IDE 2.x, 1.8.x, PlatformIO…)

R: Arduino IDE 2.3.10.

**1.4** Quais bibliotecas estão instaladas, e em que versão? Interessam a do RFID
(ex.: `MFRC522`), a do LCD (ex.: `LiquidCrystal I2C`, com o nome do autor) e a versão
do pacote de placas `esp8266`.

R: Bibliotecas `MFRC522`, `LiquidCrystal_I2C`, `ESP8266WiFi.h` e `espnow.h`. Pacotes
de placas: "Arduino AVR Boards" para o UNO e "NodeMCU 1.0 (ESP-12E Module)" para o
ESP8266. *(Versões e autores não informados.)*

## 2. Arduino UNO e semáforos

**2.1** A ligação está igual a esta tabela? Se não, o que muda?

| Semáforo | Via | Vermelho | Amarelo | Verde |
| --- | --- | --- | --- | --- |
| S1 | Principal, sentido A | 13 | 12 | 11 |
| S2 | Principal, sentido B | 10 | 9 | 8 |
| S3 | Transversal, sentido A | 7 | 6 | 5 |
| S4 | Transversal, sentido B | 4 | 3 | 2 |

R: Sim, a ligação dos pinos (vermelho, amarelo e verde) dos semáforos 1 a 4 está
exatamente igual à tabela.

**2.1b** Tem mais alguma coisa ligada no UNO além dos semáforos (botão, buzzer, LED extra)?

R: Sim. O LCD 16x2 com módulo I2C está no UNO (SDA no A4, SCL no A5). O pino RX (0)
do UNO recebe o TX do NodeMCU receptor, e o 5V do UNO alimenta esse NodeMCU.

**2.2** O LED acende com `digitalWrite(pino, HIGH)` ou com `LOW`?

R: `HIGH`.

**2.3** O UNO é original ou clone (chip CH340 perto do USB)?

R: Arduino UNO R3, ATmega328P DIP a 16 MHz, **com chip CH340**.

**2.4** Como o UNO é alimentado: só pelo cabo USB, ou também por fonte externa/bateria?
Na apresentação vamos puxar o cabo USB para mostrar o semáforo voltando ao ciclo
normal sozinho. Se ele for alimentado só pelo USB, puxar o cabo desliga tudo.
Tem fonte de 7–12 V ou bateria 9 V disponível?

R: Só pelo cabo USB (A/B) ligado ao computador. *(Não respondido se há fonte de
7–12 V ou bateria 9 V disponível para o UNO.)*

**2.5** Como os semáforos estão dispostos fisicamente (maquete de cruzamento?) e qual
par é a via principal?

R: Simulam um cruzamento: eixo principal com o S1 (sentido A) e o S2 (sentido B), e
eixo transversal com o S3 (sentido A) e o S4 (sentido B).

## 3. NodeMCU, leitor RFID e LCD

**3.1** Qual é o modelo do NodeMCU: v2 (Amica, mais estreita) ou v3 (LoLin, mais larga)?

R: NodeMCU 1.0 (ESP-12E Module). *(É o nome da placa na IDE; v2 ou v3 não informado.)*

**3.2** A ligação está igual a esta tabela? Se não, o que muda?

| Componente | Pino do componente | Pino do NodeMCU |
| --- | --- | --- |
| RC522 | 3.3V | 3V3 |
| RC522 | RST | D3 |
| RC522 | GND | GND |
| RC522 | MISO | D6 |
| RC522 | MOSI | D7 |
| RC522 | SCK | D5 |
| RC522 | SDA/SS | D8 |
| LCD | VCC | VIN (5 V) |
| LCD | GND | GND |
| LCD | SDA | D2 |
| LCD | SCL | D1 |

R: Sim. *(Vale para o RC522, no NodeMCU emissor. O LCD não está no NodeMCU: está no
UNO, ver 2.1b.)*

**3.2b** Tem mais alguma coisa ligada no NodeMCU além do RC522 e do LCD? E como ele é
alimentado (USB do notebook, carregador, power bank)?

R: São dois NodeMCUs, com ligações diferentes:
- **Emissor, no veículo:** ligado só ao RC522, alimentado por bateria de 9 V nos pinos
  VIN e GND.
- **Receptor, no semáforo:** ligado ao UNO (TX dele no RX do UNO), alimentado pelo 5V
  do UNO.

**3.3** Teste rápido: com o RC522 ligado, aperte o botão RST do NodeMCU umas 5 vezes
e tire e recoloque o cabo USB umas 5 vezes. O programa volta a rodar todas as vezes?
(O RST do leitor está no D3, que interfere na inicialização do NodeMCU. Se travar,
a correção é passar esse fio para o D0.)

R: Sim.

**3.4** Qual é o endereço I2C do LCD? (rodar um "I2C Scanner"; normalmente `0x27` ou `0x3F`)

R: `0x27`, o endereço fixado no código. *(Não informado se foi conferido com o I2C
Scanner.)*

**3.5** O LCD está em 5 V (VIN) ou 3,3 V? Usa conversor de nível lógico? Mostra o texto
certinho, sem caracteres estranhos, mesmo depois de vários minutos ligado?

R: 5 V, vindos do UNO. O documento não menciona conversor de nível nem relata
caracteres estranhos.

**3.6** A que distância o leitor lê a tag com segurança (em cm)?

R: 2 a 5 cm.

## 4. Tags RFID

**4.1** Quais tags existem e qual é o UID de cada uma? Uma por linha, no formato
`UID — veículo`. O UID aparece no Monitor Serial com o exemplo **DumpInfo** da
biblioteca MFRC522. Precisamos de pelo menos 4: ambulância, bombeiro, polícia e uma
tag "não cadastrada" (para mostrar o acesso negado).

R: A arquitetura difere da premissa da pergunta. **As tags identificam a rua em que o
veículo está entrando, e não o veículo.** O tipo do veículo (ambulância, bombeiro,
polícia) fica gravado no código do NodeMCU da viatura. UIDs cadastrados:

- `F39BD606` — Rua 1
- `1BD2308E` — Rua 2
- `B7EF8FA0` — Rua 3
- `97ABAFA0` — Rua 4

## 5. Rede

**5.1** Que rede o NodeMCU vai usar na apresentação? (roteador próprio, hotspot do
celular, rede da faculdade…) Lembrando: o NodeMCU só conecta em 2,4 GHz.

R: Nenhuma. O sistema dispensa roteador: usa ESP-NOW, rádio direto ponto a ponto
(MAC a MAC) entre os NodeMCUs.

## 6. Logística

**6.1** Durante o desenvolvimento, a bancada fica com você ou com o Felipe? Quem vai
gravar e testar os programas novos?

R: Não sei.

**6.2** Tem componentes extras? (botões, LEDs, cabos USB, fonte, outro NodeMCU/Arduino…)

R: Tudo o que o protótipo tem está listado no documento.

**6.3** Tem mais alguma coisa que a gente deveria saber? (problemas conhecidos, peças com
defeito, adaptações que você fez)

R:
- O fio do TX do NodeMCU no RX (0) do UNO conflita com o cabo USB. Para gravar o UNO é
  preciso desconectar esse fio; senão o upload falha.
- Os pinos do RC522 precisaram ser soldados para a leitura ficar estável.
- Ao trocar de máquina para gravar o NodeMCU, a porta pode não aparecer até instalar o
  driver serial CH340 / CP210x.

## 7. Fotos

Mande junto, de perto e nítidas, dando para ver em qual pino cada fio entra:
- a bancada inteira, de cima;
- as ligações no Arduino UNO;
- o NodeMCU com o RC522 e o LCD.

R: Pendente — as fotos ainda precisam ser tiradas.
