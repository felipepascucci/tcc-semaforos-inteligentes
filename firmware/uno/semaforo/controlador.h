// Controlador do cruzamento da bancada — entrega 5.3, context/05 §3 e §4.
//
// Este é o NÚCLEO do firmware: a decisão, a máquina das luzes e o protocolo
// serial. Não inclui nada do Arduino — nem millis(), nem Serial, nem pinos. O
// que é da placa entra pela interface `Placa`, e o tempo entra como argumento.
// É isso que permite compilar o mesmo código no PC e rodá-lo, linha por linha,
// contra o dublê do UNO (backend/adapters/hardware/simulado.py), que é o modelo
// de referência: tests/firmware/test_firmware_uno.py.
//
// Sem String e sem alocação dinâmica: só char[] de tamanho fixo (05 §3.5).

#ifndef CONTROLADOR_H
#define CONTROLADOR_H

#include <stdint.h>

namespace bancada {

// --- Perfil da bancada: backend/config/parametros.hardware.yaml -------------
// O firmware não lê o YAML; estes números precisam ser os de lá. O roteiro de
// aceitação (bridge/verificar.py) confere as durações na placa.
const uint32_t VERDE_MS = 3000;       // verde de cada fase no ciclo
const uint32_t VERDE_MIN_MS = 3000;   // piso de I4
const uint32_t AMARELO_MS = 2000;     // I2
const uint32_t ALL_RED_MS = 1000;     // I3
const uint32_t TETO_MS = 30000;       // emergência contínua (I6, 05 §3.4 item 7)
const uint32_t PERIODO_ST_MS = 500;   // telemetria a 2 Hz (05 §4.2)

const uint8_t N_SEMAFOROS = 4;        // S1..S4
const uint8_t TAM_LINHA = 72;         // entrada: cabe a maior linha da injeção (64)
const uint8_t TAM_SAIDA = 40;         // maior linha de saída: ~36 caracteres

enum Cor : uint8_t { VERMELHO = 0, AMARELO = 1, VERDE = 2 };

// O valor é a prioridade: 1 é a maior (05 §3.2).
enum Tipo : uint8_t { NENHUM = 0, AMBULANCIA = 1, BOMBEIRO = 2, POLICIA = 3 };

// Um VE: a rua por onde chega (1..4) e o tipo. Rua 0 = nenhum.
struct Ve {
  uint8_t rua;
  Tipo tipo;
};

// O que o núcleo precisa da placa. No UNO, semaforo.ino; no PC, o teste.
class Placa {
 public:
  // Acende uma luz da aproximação `i` (0..3) e apaga as outras duas.
  virtual void acender(uint8_t i, Cor cor) = 0;
  // O verde da aproximação `i` está aceso? Lido do PINO, não da máquina de
  // estados: é o que torna a guarda de I1 independente dela (05 §3.5, item 4).
  virtual bool verdeAceso(uint8_t i) = 0;
  // Quantos bytes cabem no buffer de saída sem bloquear.
  virtual uint8_t espacoNaSaida() = 0;
  // Escreve uma linha; a placa acrescenta o "\r\n".
  virtual void escrever(const char* linha) = 0;
};

class Controlador {
 public:
  // Não toca na placa: é construído antes do setup(). Chame boot() lá.
  explicit Controlador(Placa& placa);

  // Boot: tudo em vermelho e `EV,<ms>,BOOT`. O all-red de 1 s conta daqui.
  void boot(uint32_t agora);
  // Faz o tempo passar até `agora`: aplica o que venceu, publica a telemetria.
  void avancar(uint32_t agora);
  // Um byte chegou ao RX. A linha é processada no '\n'.
  void receber(char c, uint32_t agora);
  // O texto do LCD (16 colunas, completado com espaços). Devolve true se mudou
  // desde a última chamada. Quem escreve no LCD chama isto DEPOIS de tratar a
  // serial: a escrita I2C leva milissegundos e não pode atrasar o evento (05
  // §3.5, item 6).
  bool lcd(char linha1[17], char linha2[17]);

 private:
  Placa& placa_;
  uint32_t t_;  // o instante que está sendo processado

  // Luzes: cor e instante da última mudança de cada aproximação.
  Cor cor_[N_SEMAFOROS];
  uint32_t desde_[N_SEMAFOROS];
  uint32_t tUltimoVermelho_;  // última vez que alguma aproximação foi a vermelho

  // O destino que as luzes perseguem (máscara de aproximações) e os verdes
  // acesos que precisam sair (05 §8).
  uint8_t destino_;
  uint8_t fechar_;
  bool estabelecido_;       // o destino está aceso, e só ele
  uint32_t tInicioVerde_;   // de quando conta o verde estabelecido
  uint32_t duracaoVerde_;

  bool emergencia_;
  uint32_t tInicioEmergencia_;
  uint8_t faseCiclo_;  // 0 eixo principal, 1 eixo transversal
  Ve atendido_;
  Ve fila_;            // um lugar só

  // Telemetria: a próxima periódica e o que foi publicado por último.
  uint32_t proximaSt_;
  char assinatura_[8];

  // Entrada: a linha sendo recebida.
  char linha_[TAM_LINHA];
  uint8_t nLinha_;
  bool estourou_;
  bool temVirgula_;
  bool byteInvalido_;

  // O último texto entregue ao LCD.
  char lcd1_[17];
  char lcd2_[17];

  void iniciar(uint32_t agora);

  // Regras das luzes.
  void assentar();
  bool umPasso();
  void mirar(uint8_t destino);
  bool deveFechar(uint8_t i) const;
  uint8_t verdes() const;
  bool todosVermelhos() const;
  bool destinoEstabelecido() const;
  bool guardaI1(uint8_t novos);
  void mudar(uint8_t i, Cor cor);

  // Decisão (05 §3.3).
  void processarLinha();
  bool interpretar(uint8_t n, Ve& ve) const;
  void decidir(Ve novo);
  void atender(Ve ve);
  void enfileirar(Ve ve);
  void encerrarAtendimento();
  void estourarTeto();
  void voltarAoCiclo(Ve ultimo);

  // Saída.
  void evento(const char* tipo, const Ve* ve);
  void telemetria(bool opcional);
  void montarAssinatura(char assinatura[8]) const;
};

}  // namespace bancada

#endif
