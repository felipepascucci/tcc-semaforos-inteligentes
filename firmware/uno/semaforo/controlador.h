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

// Textos fixos (nomes de evento, mensagens do LCD) moram na flash no UNO: no
// AVR um literal comum ocupa RAM, e são ~150 bytes dos 2 KB. No PC, onde o
// núcleo é testado, é um literal comum.
#if defined(__AVR__)
#include <avr/pgmspace.h>
#define FIXO(s) PSTR(s)
#define LER_FIXO(p) static_cast<char>(pgm_read_byte(p))
#else
#define FIXO(s) (s)
#define LER_FIXO(p) (*(p))
#endif

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
const uint32_t AVISO_LCD_MS = 3000;   // "SEM OCORRENCIA" fica no LCD (05 §3.6)
// Fio mudo por mais que isto no meio de uma linha: o pedaço é ruído e é
// descartado. Uma linha de verdade chega inteira em ~26 ms a 9600; o lixo do
// boot do ESP8266 chega segundos antes da linha seguinte e grudaria nela
// (achado da bancada, 2026-10-06). 100 ms cobre a escrita no LCD, que pode
// segurar o loop() por ~45 ms.
const uint32_t LINHA_PARADA_MS = 100;

const uint8_t N_SEMAFOROS = 4;        // S1..S4
const uint8_t TAM_LINHA_USB = 72;     // cabe a maior linha da injeção (64)
// O receptor manda no máximo 25 caracteres ("rua[10]" e "veiculo[15]" do
// sketch dele, mais o '\r'). Linha mais longa é ruído e é recusada.
const uint8_t TAM_LINHA_RECEPTOR = 32;
const uint8_t TAM_SAIDA = 48;         // maior linha de saída: 41 caracteres
// O que a ST publica: 4 cores, regime, rua ativa, rua da fila, 3 criticidades
// e o '\0'.
const uint8_t TAM_ASSINATURA = 11;

enum Cor : uint8_t { VERMELHO = 0, AMARELO = 1, VERDE = 2 };

// O tipo do VE. Desde 2026-10-06 ele só fixa a duração do verde; quem
// interrompe quem é a criticidade da ocorrência (05 §3.3).
enum Tipo : uint8_t { NENHUM = 0, AMBULANCIA = 1, BOMBEIRO = 2, POLICIA = 3 };

// Criticidade da ocorrência, como a Central atribui (P20): 1 é a mais crítica,
// 3 a menos. 0 é "sem ocorrência ativa": não preempta.
const uint8_t SEM_OCORRENCIA = 0;
const uint8_t CRITICIDADE_MAXIMA = 3;

// Um VE: a rua por onde chega (1..4), o tipo e a criticidade que o tipo tinha
// quando ele foi lido. Rua 0 = nenhum.
struct Ve {
  uint8_t rua;
  Tipo tipo;
  uint8_t criticidade;
};

// Uma linha sendo recebida, numa das duas entradas. O buffer é de quem a
// declara: cada entrada tem o seu tamanho.
struct Entrada {
  char* linha;
  uint8_t capacidade;
  uint8_t n;
  bool estourou;
  bool temVirgula;
  bool byteInvalido;
  uint32_t ultimoByte;  // quando chegou o último byte, para LINHA_PARADA_MS
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

  // Boot: tudo em vermelho, `EV,<ms>,BOOT` e a primeira ST. O all-red de 1 s
  // conta daqui; na placa ele dura mais, porque o lcd.init() bloqueia.
  void boot(uint32_t agora);
  // Faz o tempo passar até `agora`: aplica o que venceu, publica a telemetria.
  void avancar(uint32_t agora);
  // Um byte chegou ao RX, pelo USB: a ponte. Aceita `AUT,<VEICULO>,<0..3>` e
  // a detecção. A linha é processada no '\n'.
  void receber(char c, uint32_t agora);
  // Um byte chegou ao A0, do NodeMCU receptor: só detecção. Um `AUT` daqui é
  // RECUSADO — um VE não se autoriza pelo rádio.
  void receberDoReceptor(char c, uint32_t agora);
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

  // A lista da Central: a criticidade de cada tipo, por índice de Tipo (o 0
  // não é usado). Começa toda em SEM_OCORRENCIA: o UNO liga negando todos, e
  // a ponte manda a lista de novo a cada reinício (decisão de 2026-10-06).
  uint8_t criticidade_[4];

  // Telemetria: a próxima periódica e o que foi publicado por último.
  uint32_t proximaSt_;
  char assinatura_[TAM_ASSINATURA];

  // As duas entradas: o USB (a ponte) e o A0 (o receptor).
  char linhaUsb_[TAM_LINHA_USB];
  char linhaReceptor_[TAM_LINHA_RECEPTOR];
  Entrada usb_;
  Entrada receptor_;

  // O último VE recusado por falta de ocorrência, para o LCD. Rua 0 = nenhum.
  Ve semOcorrencia_;
  uint32_t tSemOcorrencia_;

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

  // Entrada e decisão (05 §3.3 e §4.1).
  void acumular(Entrada& e, char c, bool doUsb);
  void processarLinha(Entrada& e, bool doUsb);
  bool interpretar(const Entrada& e, uint8_t n, Ve& ve) const;
  bool autorizar(const Entrada& e, uint8_t n);
  void decidir(Ve novo);
  void atender(Ve ve);
  void enfileirar(Ve ve);
  void encerrarAtendimento();
  void estourarTeto();
  void voltarAoCiclo(Ve ultimo);

  // Saída. `tipo` é um texto fixo, escrito com FIXO("...").
  void evento(const char* tipo, const Ve* ve);
  void telemetria(bool opcional);
  void montarAssinatura(char assinatura[TAM_ASSINATURA]) const;
};

}  // namespace bancada

#endif
