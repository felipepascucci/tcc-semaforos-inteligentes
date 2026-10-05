#include <Wire.h>
#include <LiquidCrystal_I2C.h>

LiquidCrystal_I2C lcd(0x27, 16, 2);

const int s1R = 13, s1Y = 12, s1G = 11; 
const int s2R = 10, s2Y = 9,  s2G = 8;  
const int s3R = 7,  s3Y = 6,  s3G = 5;  
const int s4R = 4,  s4Y = 3,  s4G = 2;  

unsigned long tempoAnterior = 0;
int estadoCiclo = 0; 

bool emEmergencia = false;
unsigned long tempoInicioEmergencia = 0;
unsigned long duracaoEmergencia = 7000; 

// Variáveis para guardar QUEM ESTÁ PASSANDO AGORA
String ruaAtual = "";
String veiculoAtual = "";
int prioridadeAtual = 99;

// Variáveis para a FILA
String ruaPendente = "";
String veiculoPendente = "";
int prioridadePendente = 99;
bool temEmergenciaPendente = false;

void setup() {
  Serial.begin(9600);

  pinMode(s1R, OUTPUT); pinMode(s1Y, OUTPUT); pinMode(s1G, OUTPUT);
  pinMode(s2R, OUTPUT); pinMode(s2Y, OUTPUT); pinMode(s2G, OUTPUT);
  pinMode(s3R, OUTPUT); pinMode(s3Y, OUTPUT); pinMode(s3G, OUTPUT);
  pinMode(s4R, OUTPUT); pinMode(s4Y, OUTPUT); pinMode(s4G, OUTPUT);

  lcd.init();
  lcd.backlight();
  retornarCicloNormal();
}

void loop() {
  // 1. Lê os dados que chegam pela Serial
  if (Serial.available() > 0) {
    String comando = Serial.readStringUntil('\n');
    comando.trim();

    int virgula = comando.indexOf(',');
    if (virgula != -1) {
      String rua = comando.substring(0, virgula);      
      String veiculo = comando.substring(virgula + 1);  
      
      // Limpa possíveis espaços vazios na digitação
      rua.trim();
      veiculo.trim();

      int prioridade = 3;
      if (veiculo == "AMBULANCIA") prioridade = 1;      
      else if (veiculo == "BOMBEIRO") prioridade = 2;   
      else if (veiculo == "POLICIA") prioridade = 3;    

      processarChegadaVeiculo(rua, veiculo, prioridade);
    }
  }

  // 2. Controla o tempo da emergência atual
  if (emEmergencia) {
    if (millis() - tempoInicioEmergencia >= duracaoEmergencia) {
      if (temEmergenciaPendente) {
        // Pega quem estava na fila antes de resetar a fila
        String proxRua = ruaPendente;
        String proxVeiculo = veiculoPendente;
        int proxPrioridade = prioridadePendente;
        
        // Limpa a fila, pois ele vai passar agora
        temEmergenciaPendente = false; 
        ruaPendente = "";
        veiculoPendente = "";
        prioridadePendente = 99;

        ativarEmergenciaExclusiva(proxRua, proxVeiculo, proxPrioridade);
      } else {
        retornarCicloNormal();
      }
    }
  } else {
    executarCicloNormal();
  }
}

String formatarRuaCurta(String rua) {
  if (rua == "RUA1" || rua == "1") return "R1";
  if (rua == "RUA2" || rua == "2") return "R2";
  if (rua == "RUA3" || rua == "3") return "R3";
  if (rua == "RUA4" || rua == "4") return "R4";
  return rua;
}

String formatarVeiculoCompleto(String veiculo) {
  if (veiculo == "AMB") return "AMBULANCIA";
  if (veiculo == "BOMB") return "BOMBEIRO";
  if (veiculo == "POLI") return "POLICIA";
  return veiculo;
}

String formatarVeiculoCurto(String veiculo) {
  if (veiculo == "AMBULANCIA") return "AMBU";
  if (veiculo == "BOMBEIRO") return "BOMB";
  if (veiculo == "POLICIA") return "POLI";
  return veiculo;
}

void processarChegadaVeiculo(String rua, String veiculo, int prioridade) {
  if (!emEmergencia) {
    ativarEmergenciaExclusiva(rua, veiculo, prioridade);
  } else {
    // Se o novo veículo tem uma prioridade MAIOR (número menor) que o atual
    if (prioridade < prioridadeAtual) {
      
      // Joga o veículo que estava passando ATUALMENTE para a fila
      ruaPendente = ruaAtual;
      veiculoPendente = veiculoAtual;
      prioridadePendente = prioridadeAtual;
      temEmergenciaPendente = true;

      // Ativa o novo veículo imediatamente (interrompe o anterior)
      ativarEmergenciaExclusiva(rua, veiculo, prioridade);
      
    } 
    // Se a prioridade for igual ou menor, o novo veículo vai para a fila
    else if (prioridade < prioridadePendente || !temEmergenciaPendente) {
      ruaPendente = rua;
      veiculoPendente = veiculo;
      prioridadePendente = prioridade;
      temEmergenciaPendente = true;
      
      lcd.setCursor(0, 1);
      lcd.print("                "); // Limpa a linha
      lcd.setCursor(0, 1);
      lcd.print("Fila:" + formatarVeiculoCurto(veiculoPendente) + " na " + formatarRuaCurta(ruaPendente));
    }
  }
}

void executarCicloNormal() {
  unsigned long tempoAtual = millis();

  if (estadoCiclo == 0 && tempoAtual - tempoAnterior >= 5000) { 
    digitalWrite(s1G, HIGH); digitalWrite(s1R, LOW); digitalWrite(s1Y, LOW);
    digitalWrite(s2G, HIGH); digitalWrite(s2R, LOW); digitalWrite(s2Y, LOW);
    digitalWrite(s3R, HIGH); digitalWrite(s3G, LOW); digitalWrite(s3Y, LOW);
    digitalWrite(s4R, HIGH); digitalWrite(s4G, LOW); digitalWrite(s4Y, LOW);
    estadoCiclo = 1; tempoAnterior = tempoAtual;
  }
  else if (estadoCiclo == 1 && tempoAtual - tempoAnterior >= 2000) { 
    digitalWrite(s1G, LOW);  digitalWrite(s1Y, HIGH);
    digitalWrite(s2G, LOW);  digitalWrite(s2Y, HIGH);
    estadoCiclo = 2; tempoAnterior = tempoAtual;
  }
  else if (estadoCiclo == 2 && tempoAtual - tempoAnterior >= 5000) { 
    digitalWrite(s1Y, LOW);  digitalWrite(s1R, HIGH);
    digitalWrite(s2Y, LOW);  digitalWrite(s2R, HIGH);
    digitalWrite(s3R, LOW);  digitalWrite(s3G, HIGH);
    digitalWrite(s4R, LOW);  digitalWrite(s4G, HIGH);
    estadoCiclo = 3; tempoAnterior = tempoAtual;
  }
  else if (estadoCiclo == 3 && tempoAtual - tempoAnterior >= 2000) { 
    digitalWrite(s3G, LOW);  digitalWrite(s3Y, HIGH);
    digitalWrite(s4G, LOW);  digitalWrite(s4Y, HIGH);
    estadoCiclo = 0; tempoAnterior = tempoAtual;
  }
}

void ativarEmergenciaExclusiva(String rua, String veiculo, int prioridade) {
  emEmergencia = true;
  tempoInicioEmergencia = millis(); 

  // Atualiza as variáveis globais de quem está no controle agora
  ruaAtual = rua;
  veiculoAtual = veiculo;
  prioridadeAtual = prioridade;

  if (prioridade == 1) duracaoEmergencia = 9000;      
  else if (prioridade == 2) duracaoEmergencia = 8000; 
  else duracaoEmergencia = 7000;                     

  String ruaCurta = formatarRuaCurta(rua);

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(formatarVeiculoCompleto(veiculo) + " na " + ruaCurta); 

  // Imprime quem está na fila
  if (temEmergenciaPendente) {
    lcd.setCursor(0, 1);
    lcd.print("Fila:" + formatarVeiculoCurto(veiculoPendente) + " na " + formatarRuaCurta(ruaPendente));
  }

  // Segurança: Fecha todos os semáforos primeiro
  digitalWrite(s1R, HIGH); digitalWrite(s1Y, LOW); digitalWrite(s1G, LOW);
  digitalWrite(s2R, HIGH); digitalWrite(s2Y, LOW); digitalWrite(s2G, LOW);
  digitalWrite(s3R, HIGH); digitalWrite(s3Y, LOW); digitalWrite(s3G, LOW);
  digitalWrite(s4R, HIGH); digitalWrite(s4Y, LOW); digitalWrite(s4G, LOW);

  // Agora abre o verde usando o nome já formatado (R1, R2, etc.), garantindo que não falhe!
  if (ruaCurta == "R1") { digitalWrite(s1R, LOW); digitalWrite(s1G, HIGH); }
  else if (ruaCurta == "R2") { digitalWrite(s2R, LOW); digitalWrite(s2G, HIGH); }
  else if (ruaCurta == "R3") { digitalWrite(s3R, LOW); digitalWrite(s3G, HIGH); }
  else if (ruaCurta == "R4") { digitalWrite(s4R, LOW); digitalWrite(s4G, HIGH); }
}

void retornarCicloNormal() {
  emEmergencia = false;
  temEmergenciaPendente = false;
  prioridadeAtual = 99;
  
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Semaforo: Normal");
  lcd.setCursor(0, 1);
  lcd.print("Aguardando Sinal");
  
  tempoAnterior = millis(); 
  estadoCiclo = 0; 
}