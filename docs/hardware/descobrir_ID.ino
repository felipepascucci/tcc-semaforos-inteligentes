#include <SPI.h>
#include <MFRC522.h>

// Definição dos pinos para o NodeMCU (ajuste se estiver usando o Arduino Uno)
#define RST_PIN D3
#define SS_PIN  D8

MFRC522 mfrc522(SS_PIN, RST_PIN); // Cria instância do MFRC522

void setup() {
  Serial.begin(9600);   // Inicializa a serial
  SPI.begin();          // Inicializa o barramento SPI
  mfrc522.PCD_Init();   // Inicializa o leitor MFRC522
  
  Serial.println();
  Serial.println("Aproxime o cartao ou tag RFID do leitor...");
  Serial.println();
}

void loop() {
  // Verifica se há um novo cartão presente
  if (!mfrc522.PICC_IsNewCardPresent()) {
    return;
  }

  // Seleciona um dos cartões
  if (!mfrc522.PICC_ReadCardSerial()) {
    return;
  }

  // Mostra UID na serial
  Serial.print("UID da Tag / Cartao: ");
  String conteudo = "";
  
  for (byte i = 0; i < mfrc522.uid.size; i++) {
    // Adiciona um zero à esquerda caso o byte seja menor que 0x10
    if (mfrc522.uid.uidByte[i] < 0x10) {
      conteudo.concat(F("0"));
    }
    conteudo.concat(String(mfrc522.uid.uidByte[i], HEX));
  }
  
  conteudo.toUpperCase(); // Deixa todas as letras em maiúsculo
  Serial.println(conteudo);
  
  Serial.println();
  
  // Para a leitura atual para permitir ler o cartão novamente
  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();
  
  delay(1000); // Pausa de 1 segundo para evitar leituras repetidas muito rápidas
}