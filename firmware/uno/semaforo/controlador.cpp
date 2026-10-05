// Controlador do cruzamento da bancada — ver controlador.h.
//
// COMO AS LUZES ANDAM (context/05 §8). Em vez de enumerar estados, o
// controlador persegue um DESTINO: o eixo da fase do ciclo, ou a aproximação do
// VE na emergência. Quatro regras, aplicadas até nada mais mudar, levam
// qualquer estado ao destino sem violar I1 a I4:
//
//   1. verde fora do destino cumpre o verde mínimo e vai a amarelo (I4, I2);
//   2. amarelo cumpre o tempo dele e vai a vermelho (I2);
//   3. o destino só abre com TODAS as aproximações em vermelho há o all-red
//      inteiro (I3), e passando pela guarda de I1;
//   4. nunca amarelo -> verde: um destino que muda no meio da troca espera o
//      all-red.
//
// A exceção é o destino já verde: a aproximação do VE que já está em verde fica
// acesa, e só as outras saem (05 §3.4, item 4).
//
// É o mesmo desenho do dublê (backend/adapters/hardware/simulado.py), função a
// função, e os nomes acompanham os de lá. Se um mudar, o outro muda junto.
//
// TEMPO. Toda conta é por diferença de uint32_t (`t_ - desde >= duracao`), que
// atravessa o estouro do millis() a cada ~49 dias sem erro.

#include "controlador.h"

#include <string.h>

namespace bancada {

namespace {

const uint8_t EIXO_DE[N_SEMAFOROS] = {0, 0, 1, 1};     // 0 principal, 1 transversal
const uint8_t FASE_DO_CICLO[2] = {0x03, 0x0C};          // S1+S2, S3+S4
const uint32_t VERDE_DO_TIPO_MS[4] = {0, 9000, 8000, 7000};
const char* const NOME_DO_TIPO[4] = {"", "AMBULANCIA", "BOMBEIRO", "POLICIA"};
const char* const CURTO_DO_TIPO[4] = {"", "AMBU", "BOMB", "POLI"};  // LCD do sketch
const char LETRA_DA_COR[3] = {'R', 'Y', 'G'};
const Ve NINGUEM = {0, NENHUM};

// Monta uma linha num buffer fixo, sem String nem sprintf.
class Texto {
 public:
  Texto() : n_(0) { b_[0] = '\0'; }

  Texto& letra(char c) {
    if (n_ < TAM_SAIDA - 1) {
      b_[n_++] = c;
      b_[n_] = '\0';
    }
    return *this;
  }

  Texto& texto(const char* s) {
    while (*s != '\0') letra(*s++);
    return *this;
  }

  Texto& numero(uint32_t v) {
    char d[10];
    uint8_t k = 0;
    do {
      d[k++] = static_cast<char>('0' + v % 10);
      v /= 10;
    } while (v != 0);
    while (k > 0) letra(d[--k]);
    return *this;
  }

  // Completa com espaços até `largura` e copia para `destino`.
  void copiar(char* destino, uint8_t largura) const {
    for (uint8_t i = 0; i < largura; i++) destino[i] = i < n_ ? b_[i] : ' ';
    destino[largura] = '\0';
  }

  const char* c_str() const { return b_; }
  uint8_t tamanho() const { return n_; }

 private:
  char b_[TAM_SAIDA];
  uint8_t n_;
};

// O que o Python considera espaço em `str.strip()`, na faixa ASCII. O dublê
// apara os campos assim, e o firmware precisa aceitar e recusar exatamente o
// mesmo (05 §3.2).
bool ehEspaco(char c) {
  return c == ' ' || (c >= 9 && c <= 13) || (c >= 28 && c <= 31);
}

void aparar(const char*& inicio, uint8_t& n) {
  while (n > 0 && ehEspaco(inicio[0])) {
    inicio++;
    n--;
  }
  while (n > 0 && ehEspaco(inicio[n - 1])) n--;
}

bool igual(const char* a, uint8_t n, const char* b) {
  for (uint8_t i = 0; i < n; i++) {
    if (b[i] == '\0' || a[i] != b[i]) return false;
  }
  return b[n] == '\0';
}

bool bit(uint8_t mascara, uint8_t i) { return ((mascara >> i) & 1) != 0; }

}  // namespace

Controlador::Controlador(Placa& placa) : placa_(placa) {}

void Controlador::iniciar(uint32_t agora) {
  t_ = agora;
  // Boot em all-red (05 §3.5, item 5): conta como se todos tivessem acabado de
  // ir a vermelho, e a fase 1 só abre depois do all-red inteiro.
  for (uint8_t i = 0; i < N_SEMAFOROS; i++) {
    cor_[i] = VERMELHO;
    desde_[i] = agora;
    placa_.acender(i, VERMELHO);
  }
  tUltimoVermelho_ = agora;

  destino_ = FASE_DO_CICLO[0];
  fechar_ = 0;
  estabelecido_ = false;
  tInicioVerde_ = agora;
  duracaoVerde_ = 0;

  emergencia_ = false;
  tInicioEmergencia_ = agora;
  faseCiclo_ = 0;
  atendido_ = NINGUEM;
  fila_ = NINGUEM;

  proximaSt_ = agora;
  assinatura_[0] = '\0';

  nLinha_ = 0;
  estourou_ = false;
  temVirgula_ = false;
  byteInvalido_ = false;

  lcd1_[0] = '\0';
  lcd2_[0] = '\0';
}

void Controlador::boot(uint32_t agora) {
  iniciar(agora);
  evento("BOOT", 0);
}

// -- entrada ----------------------------------------------------------------

void Controlador::avancar(uint32_t agora) {
  t_ = agora;
  assentar();
}

void Controlador::receber(char c, uint32_t agora) {
  t_ = agora;
  if (c == '\n') {
    processarLinha();
    return;
  }
  if (c == ',') temVirgula_ = true;
  const uint8_t b = static_cast<uint8_t>(c);
  if (b == 0 || b >= 0x80) byteInvalido_ = true;  // o dublê exige ASCII
  if (nLinha_ < TAM_LINHA) {
    linha_[nLinha_++] = c;
  } else {
    estourou_ = true;
  }
}

void Controlador::processarLinha() {
  const bool virgula = temVirgula_;
  const bool invalida = estourou_ || byteInvalido_;
  const uint8_t n = nLinha_;
  nLinha_ = 0;
  temVirgula_ = false;
  estourou_ = false;
  byteInvalido_ = false;

  // Sem vírgula: é o lixo que o ESP8266 imprime no próprio boot, a 74880 baud.
  // Ignorado em silêncio (05 §3.2).
  if (!virgula) return;

  // O que venceu até agora vem antes da decisão, como no dublê. No laço do
  // UNO é nada: o loop() acabou de chamar avancar() com o mesmo instante.
  assentar();
  Ve ve = NINGUEM;
  if (invalida || !interpretar(n, ve)) {
    // Com vírgula e conteúdo inválido: um texto corrompido não vira viatura.
    evento("RECUSADO", 0);
    return;
  }
  decidir(ve);
  assentar();
}

// `<RUA>,<VEICULO>` — RUA1..RUA4 ou 1..4; AMBULANCIA, BOMBEIRO ou POLICIA.
// Exatamente a regra de bridge.protocolo.interpretar_deteccao.
bool Controlador::interpretar(uint8_t n, Ve& ve) const {
  uint8_t virgulas = 0;
  uint8_t k = 0;
  for (uint8_t i = 0; i < n; i++) {
    if (linha_[i] == ',') {
      virgulas++;
      k = i;
    }
  }
  if (virgulas != 1) return false;

  const char* rua = linha_;
  uint8_t nRua = k;
  aparar(rua, nRua);
  const char* tipo = linha_ + k + 1;
  uint8_t nTipo = static_cast<uint8_t>(n - k - 1);
  aparar(tipo, nTipo);

  if (nRua >= 3 && rua[0] == 'R' && rua[1] == 'U' && rua[2] == 'A') {
    rua += 3;
    nRua -= 3;
  }
  if (nRua == 0) return false;
  uint8_t numero = 0;
  bool grande = false;
  for (uint8_t i = 0; i < nRua; i++) {
    if (rua[i] < '0' || rua[i] > '9') return false;
    if (!grande) {
      numero = static_cast<uint8_t>(numero * 10 + (rua[i] - '0'));
      grande = numero > N_SEMAFOROS;
    }
  }
  if (grande || numero == 0) return false;

  for (uint8_t t = AMBULANCIA; t <= POLICIA; t++) {
    if (igual(tipo, nTipo, NOME_DO_TIPO[t])) {
      ve.rua = numero;
      ve.tipo = static_cast<Tipo>(t);
      return true;
    }
  }
  return false;
}

// -- decisão (05 §3.3) ------------------------------------------------------

// A regra do sketch, com exatamente uma linha de decisão por detecção, escrita
// antes de qualquer outra (05 §4.2).
void Controlador::decidir(Ve novo) {
  if (atendido_.rua == 0) {
    atender(novo);  // 1. sem emergência
  } else if (novo.rua == atendido_.rua && novo.tipo == atendido_.tipo) {
    // 2. o mesmo VE relendo a mesma rua: o verde recomeça a contar.
    if (estabelecido_) tInicioVerde_ = t_;
    evento("RENOVADO", &novo);
  } else if (novo.tipo < atendido_.tipo) {
    // 3. prioridade maior: o atendido vai para a fila.
    const Ve antigo = atendido_;
    atender(novo);
    enfileirar(antigo);
  } else if (fila_.rua == 0 || novo.tipo < fila_.tipo) {
    enfileirar(novo);  // 4.
  } else {
    evento("DESCARTADO", &novo);  // 5.
  }
}

// Fila de um lugar: quem estava nela sai, e sai com DESCARTADO.
void Controlador::enfileirar(Ve ve) {
  const Ve deslocado = fila_;
  fila_ = ve;
  evento("FILA", &ve);
  if (deslocado.rua != 0) evento("DESCARTADO", &deslocado);
}

void Controlador::atender(Ve ve) {
  if (!emergencia_) {
    emergencia_ = true;
    tInicioEmergencia_ = t_;
  }
  atendido_ = ve;
  evento("PREEMP_INI", &ve);
  mirar(static_cast<uint8_t>(1 << (ve.rua - 1)));
}

// O verde do VE acabou: atende a fila ou volta ao ciclo pelo eixo oposto.
void Controlador::encerrarAtendimento() {
  const Ve atendido = atendido_;
  evento("PREEMP_FIM", &atendido);
  atendido_ = NINGUEM;
  if (fila_.rua != 0) {
    const Ve proximo = fila_;
    fila_ = NINGUEM;
    atender(proximo);
  } else {
    voltarAoCiclo(atendido);
  }
}

void Controlador::estourarTeto() {
  const Ve atendido = atendido_;
  evento("TIMEOUT", 0);
  evento("PREEMP_FIM", &atendido);
  atendido_ = NINGUEM;
  fila_ = NINGUEM;
  voltarAoCiclo(atendido);
}

void Controlador::voltarAoCiclo(Ve ultimo) {
  // Recomeça pelo eixo que ficou esperando (05 §3.4, item 6).
  emergencia_ = false;
  faseCiclo_ = static_cast<uint8_t>(1 - EIXO_DE[ultimo.rua - 1]);
  mirar(FASE_DO_CICLO[faseCiclo_]);
}

// Troca o destino. Fica aceso só o que já está verde e cabe nele inteiro.
void Controlador::mirar(uint8_t destino) {
  const uint8_t acesos = verdes();
  const bool cabe = destino != 0 && (destino & static_cast<uint8_t>(~acesos)) == 0;
  const uint8_t manter = cabe ? destino : 0;
  destino_ = destino;
  // Os verdes acesos agora que não podem ficar. Os que o destino abrir depois
  // não entram aqui: esses ficam até o destino mudar de novo.
  fechar_ = static_cast<uint8_t>(acesos & ~manter);
  estabelecido_ = false;
}

bool Controlador::deveFechar(uint8_t i) const {
  return cor_[i] == VERDE && (!bit(destino_, i) || bit(fechar_, i));
}

// -- luzes ------------------------------------------------------------------

// Aplica as regras no instante atual até nada mais mudar, e publica.
void Controlador::assentar() {
  while (umPasso()) {
  }
  char atual[8];
  montarAssinatura(atual);
  const bool publicou = strcmp(atual, assinatura_) != 0;
  if (publicou) telemetria(false);  // a cada mudança de estado: nunca pulada
  if (static_cast<int32_t>(t_ - proximaSt_) >= 0) {
    if (!publicou) telemetria(true);  // uma ST por instante basta
    while (static_cast<int32_t>(t_ - proximaSt_) >= 0) proximaSt_ += PERIODO_ST_MS;
  }
}

bool Controlador::umPasso() {
  if (emergencia_ && t_ - tInicioEmergencia_ >= TETO_MS) {
    estourarTeto();
    return true;
  }
  if (estabelecido_ && t_ - tInicioVerde_ >= duracaoVerde_) {
    if (emergencia_) {
      encerrarAtendimento();
    } else {
      faseCiclo_ = static_cast<uint8_t>(1 - faseCiclo_);
      mirar(FASE_DO_CICLO[faseCiclo_]);
    }
    return true;
  }

  bool mudou = false;
  for (uint8_t i = 0; i < N_SEMAFOROS; i++) {
    if (deveFechar(i)) {
      if (t_ - desde_[i] >= VERDE_MIN_MS) {  // regra 1
        mudar(i, AMARELO);
        mudou = true;
      }
    } else if (cor_[i] == AMARELO && t_ - desde_[i] >= AMARELO_MS) {  // regra 2
      mudar(i, VERMELHO);
      tUltimoVermelho_ = t_;
      mudou = true;
    }
  }
  if (mudou) return true;

  // Regra 3 (e 4: só abre com tudo vermelho, então nunca de um amarelo).
  const uint8_t aAbrir = destino_ & static_cast<uint8_t>(~verdes());
  if (aAbrir != 0 && todosVermelhos() && t_ - tUltimoVermelho_ >= ALL_RED_MS) {
    // Guarda recusou: fica tudo vermelho, que é o estado seguro. Não deveria
    // acontecer nunca — no dublê, é exceção.
    if (!guardaI1(destino_)) return false;
    for (uint8_t i = 0; i < N_SEMAFOROS; i++) {
      if (bit(aAbrir, i)) mudar(i, VERDE);
    }
    return true;
  }

  if (!estabelecido_ && destinoEstabelecido()) {
    // O verde conta de quando o destino está estabelecido: o VE recebe os
    // 9/8/7 s inteiros (05 §3.4, item 5).
    estabelecido_ = true;
    tInicioVerde_ = t_;
    duracaoVerde_ = emergencia_ ? VERDE_DO_TIPO_MS[atendido_.tipo] : VERDE_MS;
    return true;
  }
  return false;
}

bool Controlador::destinoEstabelecido() const {
  for (uint8_t i = 0; i < N_SEMAFOROS; i++) {
    if ((cor_[i] == VERDE) != bit(destino_, i) || cor_[i] == AMARELO) return false;
  }
  return true;
}

uint8_t Controlador::verdes() const {
  uint8_t mascara = 0;
  for (uint8_t i = 0; i < N_SEMAFOROS; i++) {
    if (cor_[i] == VERDE) mascara |= static_cast<uint8_t>(1 << i);
  }
  return mascara;
}

bool Controlador::todosVermelhos() const {
  for (uint8_t i = 0; i < N_SEMAFOROS; i++) {
    if (cor_[i] != VERMELHO) return false;
  }
  return true;
}

// I1 na bancada (01 §6): nunca verde nos dois eixos; em emergência, um verde
// só. Independente da máquina de estados: o que já está aceso vem dos PINOS
// (Placa::verdeAceso), não de cor_[] (05 §3.5, item 4).
bool Controlador::guardaI1(uint8_t novos) {
  uint8_t eixos = 0;
  uint8_t quantos = 0;
  for (uint8_t i = 0; i < N_SEMAFOROS; i++) {
    if (placa_.verdeAceso(i) || bit(novos, i)) {
      eixos |= static_cast<uint8_t>(1 << EIXO_DE[i]);
      quantos++;
    }
  }
  if (eixos == 0x03) return false;
  if (emergencia_ && quantos > 1) return false;
  return true;
}

void Controlador::mudar(uint8_t i, Cor cor) {
  cor_[i] = cor;
  desde_[i] = t_;
  placa_.acender(i, cor);
}

// -- saída (05 §4.2) --------------------------------------------------------

// `EV,<ms>,<tipo>[,<rua>,<veiculo>]`. Nunca pulado: se o buffer de saída
// estiver cheio, a escrita espera.
void Controlador::evento(const char* tipo, const Ve* ve) {
  Texto linha;
  linha.texto("EV,").numero(t_).letra(',').texto(tipo);
  if (ve != 0) linha.letra(',').numero(ve->rua).letra(',').texto(NOME_DO_TIPO[ve->tipo]);
  placa_.escrever(linha.c_str());
}

// `ST,<ms>,<s1s2s3s4>,<C|E>,<rua_ativa>,<rua_fila>`. A periódica (`opcional`)
// é pulada se não couber no buffer de saída (05 §3.5, item 7).
void Controlador::telemetria(bool opcional) {
  char assinatura[8];
  montarAssinatura(assinatura);
  Texto linha;
  linha.texto("ST,").numero(t_).letra(',');
  for (uint8_t i = 0; i < N_SEMAFOROS; i++) linha.letra(assinatura[i]);
  linha.letra(',').letra(assinatura[4]).letra(',').letra(assinatura[5]);
  linha.letra(',').letra(assinatura[6]);
  if (opcional && placa_.espacoNaSaida() < linha.tamanho() + 2) return;  // + "\r\n"
  placa_.escrever(linha.c_str());
  memcpy(assinatura_, assinatura, sizeof assinatura_);
}

// O que a ST publica: luzes, regime, rua ativa e rua da fila. Muda a
// assinatura, sai uma ST.
void Controlador::montarAssinatura(char assinatura[8]) const {
  for (uint8_t i = 0; i < N_SEMAFOROS; i++) assinatura[i] = LETRA_DA_COR[cor_[i]];
  assinatura[4] = emergencia_ ? 'E' : 'C';
  assinatura[5] = static_cast<char>('0' + atendido_.rua);
  assinatura[6] = static_cast<char>('0' + fila_.rua);
  assinatura[7] = '\0';
}

// -- LCD (05 §3.6): as mensagens do sketch -----------------------------------

bool Controlador::lcd(char linha1[17], char linha2[17]) {
  Texto a;
  Texto b;
  if (!emergencia_) {
    a.texto("Semaforo: Normal");
    b.texto("Aguardando Sinal");
  } else {
    a.texto(NOME_DO_TIPO[atendido_.tipo]).texto(" na R").numero(atendido_.rua);
    if (fila_.rua != 0) {
      b.texto("Fila:").texto(CURTO_DO_TIPO[fila_.tipo]).texto(" na R").numero(fila_.rua);
    }
  }
  a.copiar(linha1, 16);
  b.copiar(linha2, 16);
  if (strcmp(linha1, lcd1_) == 0 && strcmp(linha2, lcd2_) == 0) return false;
  memcpy(lcd1_, linha1, 17);
  memcpy(lcd2_, linha2, 17);
  return true;
}

}  // namespace bancada
