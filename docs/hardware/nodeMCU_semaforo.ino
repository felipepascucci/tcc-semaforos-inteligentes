#include <ESP8266WiFi.h>
#include <espnow.h>

typedef struct struct_mensagem {
  char rua[10];
  char veiculo[15];
} struct_mensagem;

struct_mensagem dadosRecebidos;

void OnDataRecv(uint8_t *mac, uint8_t *incomingData, uint8_t len) {
  memcpy(&dadosRecebidos, incomingData, sizeof(dadosRecebidos));
  
  // Pega a rua exata recebida do carrinho (ex: "RUA2") e monta a string para o Arduino Uno
  String ruaDinamica = String(dadosRecebidos.rua);
  String veiculoDinamico = String(dadosRecebidos.veiculo);

  // Envia a mensagem exata pela Serial para o Arduino Uno
  Serial.print(ruaDinamica);
  Serial.print(",");
  Serial.println(veiculoDinamico);
}

void setup() {
  Serial.begin(9600);
  
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();

  if (esp_now_init() != 0) {
    return;
  }

  esp_now_set_self_role(ESP_NOW_ROLE_SLAVE);
  esp_now_register_recv_cb(OnDataRecv);
}

void loop() {
  // Nada aqui, tudo é acionado pelo evento do ESP-NOW
}