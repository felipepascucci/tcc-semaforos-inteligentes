# Questionário do hardware — Bloco 5

Vamos reescrever o programa do Arduino UNO e do NodeMCU. Para isso precisamos saber
exatamente como a bancada está montada hoje. Responda embaixo de cada pergunta;
"não sei" é resposta válida.

## 1. O que já existe

**1.1** O que já funciona hoje? (marque com X)
- [ ] Os 4 semáforos fazem o ciclo sozinhos
- [ ] O leitor RFID (RC522) lê as tags
- [ ] O LCD mostra texto
- [ ] O NodeMCU conecta no Wi-Fi
- [ ] O NodeMCU já enviou dados para algum servidor
- [ ] O Arduino recebe comandos pelo cabo USB (Serial)

**1.2** Pode mandar os arquivos `.ino` que rodam hoje no Arduino e no NodeMCU?

R:

**1.3** Qual programa você usa para gravar as placas? (Arduino IDE 2.x, 1.8.x, PlatformIO…)

R:

**1.4** Quais bibliotecas estão instaladas, e em que versão? Interessam a do RFID
(ex.: `MFRC522`), a do LCD (ex.: `LiquidCrystal I2C`, com o nome do autor) e a versão
do pacote de placas `esp8266`.

R:

## 2. Arduino UNO e semáforos

**2.1** A ligação está igual a esta tabela? Se não, o que muda?

| Semáforo | Via | Vermelho | Amarelo | Verde |
| --- | --- | --- | --- | --- |
| S1 | Principal, sentido A | 13 | 12 | 11 |
| S2 | Principal, sentido B | 10 | 9 | 8 |
| S3 | Transversal, sentido A | 7 | 6 | 5 |
| S4 | Transversal, sentido B | 4 | 3 | 2 |

R:

**2.1b** Tem mais alguma coisa ligada no UNO além dos semáforos (botão, buzzer, LED extra)?

R:

**2.2** O LED acende com `digitalWrite(pino, HIGH)` ou com `LOW`?

R:

**2.3** O UNO é original ou clone (chip CH340 perto do USB)?

R:

**2.4** Como o UNO é alimentado: só pelo cabo USB, ou também por fonte externa/bateria?
Na apresentação vamos puxar o cabo USB para mostrar o semáforo voltando ao ciclo
normal sozinho. Se ele for alimentado só pelo USB, puxar o cabo desliga tudo.
Tem fonte de 7–12 V ou bateria 9 V disponível?

R:

**2.5** Como os semáforos estão dispostos fisicamente (maquete de cruzamento?) e qual
par é a via principal?

R:

## 3. NodeMCU, leitor RFID e LCD

**3.1** Qual é o modelo do NodeMCU: v2 (Amica, mais estreita) ou v3 (LoLin, mais larga)?

R:

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

R:

**3.2b** Tem mais alguma coisa ligada no NodeMCU além do RC522 e do LCD? E como ele é
alimentado (USB do notebook, carregador, power bank)?

R:

**3.3** Teste rápido: com o RC522 ligado, aperte o botão RST do NodeMCU umas 5 vezes
e tire e recoloque o cabo USB umas 5 vezes. O programa volta a rodar todas as vezes?
(O RST do leitor está no D3, que interfere na inicialização do NodeMCU. Se travar,
a correção é passar esse fio para o D0.)

R:

**3.4** Qual é o endereço I2C do LCD? (rodar um "I2C Scanner"; normalmente `0x27` ou `0x3F`)

R:

**3.5** O LCD está em 5 V (VIN) ou 3,3 V? Usa conversor de nível lógico? Mostra o texto
certinho, sem caracteres estranhos, mesmo depois de vários minutos ligado?

R:

**3.6** A que distância o leitor lê a tag com segurança (em cm)?

R:

## 4. Tags RFID

**4.1** Quais tags existem e qual é o UID de cada uma? Uma por linha, no formato
`UID — veículo`. O UID aparece no Monitor Serial com o exemplo **DumpInfo** da
biblioteca MFRC522. Precisamos de pelo menos 4: ambulância, bombeiro, polícia e uma
tag "não cadastrada" (para mostrar o acesso negado).

R:

## 5. Rede

**5.1** Que rede o NodeMCU vai usar na apresentação? (roteador próprio, hotspot do
celular, rede da faculdade…) Lembrando: o NodeMCU só conecta em 2,4 GHz.

R:

## 6. Logística

**6.1** Durante o desenvolvimento, a bancada fica com você ou com o Felipe? Quem vai
gravar e testar os programas novos?

R:

**6.2** Tem componentes extras? (botões, LEDs, cabos USB, fonte, outro NodeMCU/Arduino…)

R:

**6.3** Tem mais alguma coisa que a gente deveria saber? (problemas conhecidos, peças com
defeito, adaptações que você fez)

R:

## 7. Fotos

Mande junto, de perto e nítidas, dando para ver em qual pino cada fio entra:
- a bancada inteira, de cima;
- as ligações no Arduino UNO;
- o NodeMCU com o RC522 e o LCD.
