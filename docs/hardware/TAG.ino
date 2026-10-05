#include <SPI.h>
#include <MFRC522.h>
// Definição dos pinos para o NodeMCU ESP8266
#define RST_PIN D3  // Pino RST do RC522 ligado ao D3
#define SS_PIN  D8  // Pino SDA (SS) do RC522 ligado ao D8
MFRC522 mfrc522(SS_PIN, RST_PIN);  // Cria instância do MFRC522
void setup() {
  Serial.begin(9600);   // Inicializa a comunicação serial
  SPI.begin();            // Inicializa o barramento SPI
  mfrc522.PCD_Init();     // Inicializa o leitor RC522
  Serial.println(F("Aproxime o cartao ou tag RFID do leitor..."));
}
void loop() {
  // Verifica se há um novo cartão presente
  if ( ! mfrc522.PICC_IsNewCardPresent()) {
    return;
  }
  // Seleciona um dos cartões
  if ( ! mfrc522.PICC_ReadCardSerial()) {
    return;
  }
  // Mostra o UID (identificador único) do cartão no Monitor Serial
  Serial.print("UID da Tag:");
  String conteudo = "";
  for (byte i = 0; i < mfrc522.uid.size; i++) {
    Serial.print(mfrc522.uid.uidByte[i] < 0x10 ? " 0" : " ");
    Serial.print(mfrc522.uid.uidByte[i], HEX);
    conteudo.concat(String(mfrc522.uid.uidByte[i] < 0x10 ? " 0" : " "));
    conteudo.concat(String(mfrc522.uid.uidByte[i], HEX));
  }
  Serial.println();
  // Atraso para evitar leituras duplicadas muito rápidas
  delay(1000);
}
