/*
 * NodeMCU EMISSOR — vai no veículo (entrega 5.6; context/05 §1, §4.3 e §5).
 *
 * VERSIONADO COMO ESTÁ. Abaixo deste cabeçalho está o sketch da equipe de
 * hardware, byte a byte igual a docs/hardware/veiculo_ambulancia.ino: os
 * sketches dos NodeMCUs não mudam (decisão de 2026-10-05). Só este comentário
 * foi acrescentado, e tests/firmware/test_sketches_nodemcu.py confere as duas
 * coisas: o corpo idêntico e este cabeçalho de acordo com o código.
 *
 * Placa: NodeMCU 1.0 (ESP-12E Module), pacote de placas "esp8266".
 * Bibliotecas: MFRC522 1.4.12 (GithubCommunity); ESP8266WiFi e espnow vêm
 * com o pacote esp8266, de versão não informada (contrato §12). Gravado com
 * a Arduino IDE 2.3.10.
 *
 * MAC do receptor (o NodeMCU do cruzamento): 40:91:51:58:A8:E1
 *   Está em enderecoReceptor[]. Trocar a placa do receptor exige trocar aqui.
 *
 * Tipo do veículo: AMBULANCIA, fixo no código (tipoVeiculoAtual). Desde
 *   2026-10-08 há um carrinho por tipo: veiculo_bombeiro/ e veiculo_policia/
 *   são este sketch com só essa linha trocada (context/09).
 *
 * Mapa UID -> rua. As tags ficam na pista e identificam a aproximação:
 *   F39BD606 -> RUA1 (S1, eixo principal)
 *   1BD2308E -> RUA2 (S2, eixo principal)
 *   B7EF8FA0 -> RUA3 (S3, eixo transversal)
 *   97ABAFA0 -> RUA4 (S4, eixo transversal)
 *   Tag fora da lista é ignorada aqui mesmo, sem envio.
 *
 * Pinagem do RC522 (3,3 V; nunca 5 V):
 *   3.3V   -> 3V3
 *   RST    -> D3 (GPIO 0)   P8 fechada: o boot funciona em 5 de 5 resets
 *   GND    -> GND
 *   MISO   -> D6 (GPIO 12)
 *   MOSI   -> D7 (GPIO 13)
 *   SCK    -> D5 (GPIO 14)
 *   SDA/SS -> D8 (GPIO 15)
 * Alimentação: power bank no micro-USB (corrigido em 2026-10-10; o registro
 * anterior dizia bateria de 9 V em VIN/GND). Na medição de H3, USB do
 * notebook, no lugar da power bank.
 *
 * Serial a 9600 baud. Depois de cada esp_now_send imprime
 * "Tag <UID> lida -> Enviando RUAn": o primeiro byte dessa linha é o
 * t_deteccao de H3 (context/05 §4.3). No máximo um envio a cada 3 s.
 *
 * Limitação a declarar: o ESP-NOW vai sem criptografia (contrato §11).
 */

#include <SPI.h>
#include <MFRC522.h>
#include <ESP8266WiFi.h>
#include <espnow.h>

#define RST_PIN D3
#define SS_PIN  D8

MFRC522 mfrc522(SS_PIN, RST_PIN);

// Substitua pelo MAC Address do NodeMCU receptor do semáforo
uint8_t enderecoReceptor[] = {0x40, 0x91, 0x51, 0x58, 0xA8, 0xE1}; 

String tipoVeiculoAtual = "AMBULANCIA"; 

typedef struct struct_mensagem {
  char rua[10];
  char veiculo[15];
} struct_mensagem;

struct_mensagem meuEnvio;
unsigned long ultimaLeitura = 0;

void setup() {
  Serial.begin(9600);
  SPI.begin();
  mfrc522.PCD_Init();

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();

  if (esp_now_init() != 0) {
    return;
  }

  esp_now_set_self_role(ESP_NOW_ROLE_CONTROLLER);
  esp_now_add_peer(enderecoReceptor, ESP_NOW_ROLE_SLAVE, 1, NULL, 0);
}

void loop() {
  if (!mfrc522.PICC_IsNewCardPresent() || !mfrc522.PICC_ReadCardSerial()) {
    return;
  }

  // Lê o UID da tag e converte para String Hexadecimal em maiúsculo
  String uidTag = "";
  for (byte i = 0; i < mfrc522.uid.size; i++) {
    if (mfrc522.uid.uidByte[i] < 0x10) uidTag += "0";
    uidTag += String(mfrc522.uid.uidByte[i], HEX);
  }
  uidTag.toUpperCase();

  String ruaDetectada = "";
  
  // Mapeamento exato das suas tags
  if (uidTag == "F39BD606") {
    ruaDetectada = "RUA1";
  } 
  else if (uidTag == "1BD2308E") {
    ruaDetectada = "RUA2";
  }
  else if (uidTag == "B7EF8FA0") {
    ruaDetectada = "RUA3";
  }
  else if (uidTag == "97ABAFA0") {
    ruaDetectada = "RUA4";
  }

  // Se encontrou uma rua válida e passou o tempo de debounce (3 segundos)
  if (ruaDetectada != "" && (millis() - ultimaLeitura > 3000)) {
    ultimaLeitura = millis();

    ruaDetectada.toCharArray(meuEnvio.rua, 10);
    tipoVeiculoAtual.toCharArray(meuEnvio.veiculo, 15);

    // Envia o pacote correto via ESP-NOW
    esp_now_send(enderecoReceptor, (uint8_t *) &meuEnvio, sizeof(meuEnvio));
    
    Serial.println("Tag " + uidTag + " lida -> Enviando " + ruaDetectada);
  }

  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();
}