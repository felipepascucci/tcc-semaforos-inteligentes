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