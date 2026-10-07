/*
 * NodeMCU RECEPTOR — fica no cruzamento (entrega 5.6; context/05 §1 e §5).
 *
 * VERSIONADO COMO ESTÁ. Abaixo deste cabeçalho está o sketch da equipe de
 * hardware, byte a byte igual a docs/hardware/nodeMCU_semaforo.ino: os sketches
 * dos NodeMCUs não mudam (decisão de 2026-10-05). Só este comentário foi
 * acrescentado, e tests/firmware/test_sketches_nodemcu.py confere o corpo.
 *
 * Placa: NodeMCU 1.0 (ESP-12E Module), pacote de placas "esp8266".
 * Bibliotecas: ESP8266WiFi e espnow (versões não informadas; contrato §12).
 *
 * MAC desta placa: 40:91:51:58:A8:E1. É o endereço gravado no emissor
 *   (veiculo_ambulancia.ino, enderecoReceptor[]).
 *
 * Tipo do veículo: não é decidido aqui. Repassa o que o emissor mandar (hoje,
 *   sempre AMBULANCIA).
 *
 * Mapa UID -> rua: não existe aqui. A rua chega resolvida pelo emissor; o mapa
 *   está no cabeçalho de veiculo_ambulancia.ino.
 *
 * O que faz: recebe { rua, veiculo } por ESP-NOW e escreve "RUA3,AMBULANCIA"
 * com println (chega "\r\n") no TX, a 9600 baud, sem interpretar. O UNO é quem
 * decide. No reset o ESP8266 imprime lixo a 74880 baud; chega ao UNO sem
 * vírgula e é ignorado (context/05 §3.2).
 *
 * Pinagem:
 *   TX  -> A0 do UNO, desde 2026-10-06 (context/09): o UNO o lê numa serial por
 *          software, e o RX (0) ficou só para o USB. Antes ia ao RX (0), onde
 *          prevalecia sobre o conversor USB e impedia a ponte de escrever.
 *   5V e GND do UNO -> alimentação deste NodeMCU (o pino do lado do NodeMCU
 *          não foi informado no questionário; VIN é o que aceita 5 V).
 */

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