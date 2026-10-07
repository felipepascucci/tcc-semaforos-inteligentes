// O núcleo do firmware do UNO rodando no PC — para comparar com o dublê.
//
// Compila controlador.cpp, o MESMO arquivo que vai para a placa, com uma Placa
// de mentira no lugar dos pinos e da serial. Quem dirige é
// tests/firmware/test_firmware_uno.py, por um roteiro na entrada padrão:
//
//   B <ms>          boot no instante <ms> (o setup() do .ino)
//   A <ms>          o tempo passa até <ms>, de 1 em 1 ms, como o loop() faria
//   R <ms> <hex>    os bytes <hex> chegam ao RX (o USB, a ponte) no instante <ms>
//   V <ms> <hex>    os bytes <hex> chegam ao A0 (o NodeMCU receptor) em <ms>
//   L               pede o texto do LCD
//   S <n>           o buffer de saída passa a ter <n> bytes livres
//   G <i>           o pino verde da aproximação <i> fica aceso por fora da
//                   máquina de estados (defeito simulado, para a guarda de I1)
//
// Na saída padrão, cada linha que o UNO escreveria na serial, sem "\r\n", e
// linhas começando com '#' para o que não é serial: as luzes acesas (#LUZ),
// o LCD (#LCD) e qualquer verde nos dois eixos nos pinos (#VIOLACAO_I1).

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../semaforo/controlador.h"

using bancada::Cor;

namespace {

const uint8_t EIXO_DE[bancada::N_SEMAFOROS] = {0, 0, 1, 1};
const char LETRA[3] = {'R', 'Y', 'G'};

class PlacaDeTeste : public bancada::Placa {
 public:
  PlacaDeTeste() : espaco_(63) {
    for (uint8_t i = 0; i < bancada::N_SEMAFOROS; i++) verde_[i] = false;
  }

  void acender(uint8_t i, Cor cor) override {
    verde_[i] = cor == bancada::VERDE;
    printf("#LUZ S%u %c\n", i + 1, LETRA[cor]);
    uint8_t eixos = 0;
    for (uint8_t j = 0; j < bancada::N_SEMAFOROS; j++) {
      if (verde_[j]) eixos |= static_cast<uint8_t>(1 << EIXO_DE[j]);
    }
    if (eixos == 0x03) printf("#VIOLACAO_I1\n");
  }

  bool verdeAceso(uint8_t i) override { return verde_[i]; }
  uint8_t espacoNaSaida() override { return espaco_; }
  void escrever(const char* linha) override { printf("%s\n", linha); }

  void forcarVerde(uint8_t i) { verde_[i] = true; }
  void definirEspaco(uint8_t n) { espaco_ = n; }

 private:
  bool verde_[bancada::N_SEMAFOROS];
  uint8_t espaco_;
};

int valorHex(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

}  // namespace

int main() {
  PlacaDeTeste placa;
  bancada::Controlador controlador(placa);
  uint32_t agora = 0;
  static char comando[1024];

  while (fgets(comando, sizeof comando, stdin) != NULL) {
    char* resto = comando + 1;
    switch (comando[0]) {
      case 'B': {
        agora = static_cast<uint32_t>(strtoul(resto, NULL, 10));
        controlador.boot(agora);
        controlador.avancar(agora);  // o primeiro loop()
        break;
      }
      case 'A':
      case 'R':
      case 'V': {
        char* fim = NULL;
        const uint32_t ate = static_cast<uint32_t>(strtoul(resto, &fim, 10));
        while (agora != ate) controlador.avancar(++agora);
        if (comando[0] != 'A') {
          while (*fim == ' ') fim++;
          for (char* p = fim; valorHex(p[0]) >= 0 && valorHex(p[1]) >= 0; p += 2) {
            const char c = static_cast<char>(valorHex(p[0]) * 16 + valorHex(p[1]));
            if (comando[0] == 'R') {
              controlador.receber(c, agora);
            } else {
              controlador.receberDoReceptor(c, agora);
            }
          }
        }
        break;
      }
      case 'L': {
        char linha1[17];
        char linha2[17];
        if (controlador.lcd(linha1, linha2)) {
          printf("#LCD|%s|%s\n", linha1, linha2);
        } else {
          printf("#LCD=\n");
        }
        break;
      }
      case 'S':
        placa.definirEspaco(static_cast<uint8_t>(strtoul(resto, NULL, 10)));
        break;
      case 'G':
        placa.forcarVerde(static_cast<uint8_t>(strtoul(resto, NULL, 10)));
        break;
      default:
        break;
    }
  }
  return 0;
}
