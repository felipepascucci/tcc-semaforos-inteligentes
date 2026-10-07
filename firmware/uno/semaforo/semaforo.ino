/*
 * Arduino UNO da bancada — controlador do cruzamento (entrega 5.3).
 * Especificação: context/05 §3 e §4. Modelo de referência: o dublê em
 * backend/adapters/hardware/simulado.py, contra o qual o núcleo (controlador.h
 * e .cpp) é testado linha por linha em tests/firmware/test_firmware_uno.py.
 *
 * Reescreve docs/hardware/semaforo.ino, da equipe de hardware, PRESERVANDO o
 * comportamento: a mesma entrada ("RUA3,AMBULANCIA" do NodeMCU receptor), as
 * mesmas prioridades (ambulância 1, bombeiro 2, polícia 3), as mesmas durações
 * (9, 8 e 7 s), a fila de um lugar e as mesmas mensagens no LCD. O que muda
 * (context/09, decisão de 2026-10-05):
 *   1. transição segura em toda troca: verde mínimo, amarelo, all-red; nunca
 *      amarelo -> verde (I1 a I4);
 *   2. o verde do VE conta a partir do verde exclusivo estabelecido;
 *   3. o mesmo VE relendo a mesma rua RENOVA o verde, em vez de ir para a fila;
 *   4. tipo desconhecido é RECUSADO, em vez de virar prioridade 3;
 *   5. fim da emergência volta ao ciclo pelo eixo OPOSTO ao do último VE;
 *   6. teto de 30 s de emergência contínua (EV,TIMEOUT);
 *   7. boot em all-red;
 *   8. sem String: só char[];
 *   9. quem perde o lugar na fila sai com EV,DESCARTADO.
 * Os itens 3 a 6 mudam o comportamento do sketch e aguardam a confirmação da
 * equipe de hardware (contrato §15, item 1).
 *
 * A CENTRAL VALE NA BANCADA (context/09, decisão de 2026-10-06):
 *  10. o receptor passou do RX (0) para o A0, numa serial por software, e o
 *      USB ficou livre para a ponte mandar AUT,<VEICULO>,<0..3>: a criticidade
 *      da ocorrência ativa de cada tipo, que a Central decide (P20);
 *  11. o UNO liga negando todos; VE de tipo sem ocorrência recebe
 *      EV,SEM_OCORRENCIA, e o LCD mostra "SEM OCORRENCIA" por 3 s;
 *  12. quem interrompe quem é a CRITICIDADE, e não mais o tipo; o tipo só fixa
 *      a duração do verde (9, 8 e 7 s).
 *
 * Placa: Arduino UNO R3, core arduino:avr 1.8.8. Bibliotecas: "LiquidCrystal
 * I2C" 1.1.2, de Frank de Brabander (a que tem lcd.init()), e SoftwareSerial,
 * que vem com o core. Compilar sem a IDE:
 *   arduino-cli compile --fqbn arduino:avr:uno firmware/uno/semaforo
 *
 * GRAVAR: python -m bridge.gravar_uno --porta COM3 (com a ponte fechada). Ele
 * compila, grava em pedaços de 16 bytes e relê a flash inteira. NÃO use o
 * arduino-cli upload: na bancada ele grava errado os bytes 60..63 de cada
 * página e não percebe (context/05 §3.7). Com o receptor no A0, o RX (0) é só
 * do USB, e a gravação não pede para soltar fio nenhum.
 *
 * Pinagem (LEDs acendem com HIGH; os módulos já têm resistor):
 *   S1  Principal, sentido A    (RUA1)   R 13  Y 12  G 11
 *   S2  Principal, sentido B    (RUA2)   R 10  Y  9  G  8
 *   S3  Transversal, sentido A  (RUA3)   R  7  Y  6  G  5
 *   S4  Transversal, sentido B  (RUA4)   R  4  Y  3  G  2
 *   LCD 16x2 I2C, endereço 0x27, 5 V:    SDA A4 · SCL A5
 *   A0     <- TX do NodeMCU receptor (serial por software, só recepção).
 *   A1     reservado: é o TX que a SoftwareSerial exige; nada ligado.
 *   RX (0) <- USB (a ponte).             TX (1) -> USB.
 *
 * Tudo a 9600 baud. Entram a linha do receptor (A0) e as da ponte (USB); saem
 * as linhas ST e EV de context/05 §4.2.
 *
 * ACEITAÇÃO (context/05 §6), com o backend PARADO (ele reenvia a lista da
 * Central e atrapalharia o roteiro):
 *   python -m bridge.main --porta COM3
 *   python -m bridge.verificar           (noutro terminal, logo em seguida)
 */

#include <LiquidCrystal_I2C.h>
#include <SoftwareSerial.h>
#include <Wire.h>

#include "controlador.h"

static const unsigned long BAUD = 9600;

// O receptor fala a 9600, como sempre. A SoftwareSerial do core desliga as
// interrupções enquanto recebe cada byte (~1 ms a 9600): o millis() não perde
// tique (o estouro do Timer0 fica pendente e é atendido em seguida), e a UART
// do USB guarda até 2 bytes nesse meio-tempo.
static const uint8_t PINO_RECEPTOR = A0;
static const uint8_t PINO_TX_SEM_USO = A1;

// Tabela de pinos e índice, não estados enumerados um a um (05 §3.1).
static const uint8_t VERDE_DE[bancada::N_SEMAFOROS] = {11, 8, 5, 2};
static const uint8_t AMAR_DE[bancada::N_SEMAFOROS] = {12, 9, 6, 3};
static const uint8_t VERM_DE[bancada::N_SEMAFOROS] = {13, 10, 7, 4};

class PlacaUno : public bancada::Placa {
 public:
  void acender(uint8_t i, bancada::Cor cor) override {
    // Apaga as outras duas antes de acender: um módulo nunca mostra duas cores.
    if (cor != bancada::VERDE) digitalWrite(VERDE_DE[i], LOW);
    if (cor != bancada::AMARELO) digitalWrite(AMAR_DE[i], LOW);
    if (cor != bancada::VERMELHO) digitalWrite(VERM_DE[i], LOW);
    if (cor == bancada::VERDE) digitalWrite(VERDE_DE[i], HIGH);
    if (cor == bancada::AMARELO) digitalWrite(AMAR_DE[i], HIGH);
    if (cor == bancada::VERMELHO) digitalWrite(VERM_DE[i], HIGH);
  }

  // Lido do pino: é o que a guarda de I1 consulta, e não a máquina de estados.
  bool verdeAceso(uint8_t i) override { return digitalRead(VERDE_DE[i]) == HIGH; }

  uint8_t espacoNaSaida() override {
    const int livre = Serial.availableForWrite();
    return livre > 255 ? 255 : static_cast<uint8_t>(livre);
  }

  void escrever(const char* linha) override { Serial.println(linha); }
};

static PlacaUno placa;
static bancada::Controlador controlador(placa);
static LiquidCrystal_I2C lcd(0x27, 16, 2);
static SoftwareSerial receptor(PINO_RECEPTOR, PINO_TX_SEM_USO);

static void atualizarLcd() {
  char linha1[17];
  char linha2[17];
  if (!controlador.lcd(linha1, linha2)) return;
  // Sem lcd.clear(): ele espera 2 ms e pisca. O texto já vem com 16 colunas.
  lcd.setCursor(0, 0);
  lcd.print(linha1);
  lcd.setCursor(0, 1);
  lcd.print(linha2);
}

void setup() {
  for (uint8_t i = 0; i < bancada::N_SEMAFOROS; i++) {
    pinMode(VERM_DE[i], OUTPUT);
    pinMode(AMAR_DE[i], OUTPUT);
    pinMode(VERDE_DE[i], OUTPUT);
  }
  Serial.begin(BAUD);
  receptor.begin(BAUD);
  controlador.boot(millis());  // all-red e EV,BOOT; o all-red de 1 s conta daqui
  lcd.init();                  // pode bloquear: no setup() pode (05 §3.5, item 1)
  lcd.backlight();
  atualizarLcd();
}

// Nenhum delay(). As duas entradas são lidas a cada volta, e o LCD é
// atualizado por último: o evento de decisão já saiu quando a escrita I2C
// começa (05 §3.5).
void loop() {
  const uint32_t agora = millis();
  controlador.avancar(agora);
  while (receptor.available() > 0) {
    controlador.receberDoReceptor(static_cast<char>(receptor.read()), agora);
  }
  while (Serial.available() > 0) {
    controlador.receber(static_cast<char>(Serial.read()), agora);
  }
  atualizarLcd();
}
