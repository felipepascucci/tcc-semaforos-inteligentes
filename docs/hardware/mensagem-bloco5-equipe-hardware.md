# Bloco 5 — firmware novo do UNO: o que precisamos de vocês

> **Respondida em 2026-10-07 pelo Felipe**, que ficou com a bancada e passou a
> responder também pela parte de hardware. "Ok" nas 8 mudanças da seção 1 e no
> A0 da seção 2. Da seção 3: `MFRC522` 1.4.12 e `LiquidCrystal I2C` 1.1.2;
> faltam o número de versão do pacote `esp8266` e as fotos. Registro em
> `context/09` (decisão de 2026-10-07) e em `docs/contrato-hardware-software.md`
> §15.

Oi, pessoal! O programa novo do Arduino UNO está pronto, na pasta
`firmware/uno/semaforo/`. Ele mantém o que o sketch de vocês já fazia: a mesma
linha vinda do NodeMCU (`RUA3,AMBULANCIA`), os mesmos tempos de verde do VE (9, 8
e 7 s), a fila de um lugar e as mesmas mensagens no LCD. Os dois NodeMCUs **não
mudam**: só foram copiados para `firmware/nodemcu/`, com um comentário no topo.

O que mudou foi a segurança das trocas de luz. No sketch antigo, a emergência
apagava um verde e acendia outro no mesmo instante, sem amarelo e sem todos
vermelhos no meio. Agora toda troca passa por verde mínimo de 3 s, amarelo de
2 s e 1 s com tudo vermelho. Isso não está em discussão, é a regra de segurança
do trabalho.

## 1. Confirmem estas mudanças de comportamento

Respondam "ok" ou "não" em cada uma. Se alguma não fizer sentido para vocês, a
gente conversa.

1. **Tempos do ciclo:** verde 3 s e amarelo 2 s. No sketch estavam invertidos
   (verde 2 s, amarelo 5 s).
2. **O verde do VE conta a partir do momento em que ele fica verde sozinho.**
   Antes contava da leitura da tag, e a ambulância perdia parte dos 9 s esperando
   a troca.
3. **O mesmo veículo lendo a mesma tag de novo renova o verde dele.** Antes ele
   entrava na fila e ganhava um segundo verde depois do primeiro.
4. **Tipo de veículo desconhecido é recusado.** Antes qualquer texto virava
   prioridade 3, então um lixo na serial podia virar uma viatura.
5. **Quando a emergência acaba, o ciclo volta pelo eixo que ficou esperando.**
   Antes voltava sempre pelo eixo principal.
6. **Limite de 30 s de emergência seguida**, contando renovações e fila. Depois
   disso a fila é descartada e o ciclo volta.
7. **Quem perde o lugar na fila aparece no log como DESCARTADO.** Antes sumia sem
   registro. No LCD nada muda.
8. **A Central decide quem pode passar** (novo, de 06/10). O UNO só abre o
   corredor para um tipo de veículo que tenha uma ocorrência aberta na Central do
   sistema. Sem ocorrência, o semáforo não muda, e o LCD mostra
   `SEM OCORRENCIA` por 3 s. E quem passa na frente de quem deixou de ser o tipo
   (ambulância > bombeiro > polícia): passa a ser a **gravidade da ocorrência**
   (risco à vida > risco coletivo > urgência). O tipo continua definindo só o
   tempo de verde (9, 8 e 7 s).

## 2. Uma mudança de fio (06/10)

Para o UNO receber a lista da Central pelo USB, **o fio do TX do NodeMCU
receptor saiu do pino RX (0) do UNO e foi para o pino A0**. Nenhum outro fio
muda, e nenhum NodeMCU precisa ser regravado. De quebra, o UNO agora pode ser
gravado sem soltar fio nenhum.

Se vocês tiverem um motivo para não usar o A0 (outro uso planejado para ele,
por exemplo), avisem.

## 3. Ainda falta de vocês

- **Fotos da bancada**, de perto, dando para ver em que pino entra cada fio: a
  bancada inteira de cima, as ligações no UNO e o NodeMCU com o RC522.
- **Versões** da biblioteca `MFRC522` e do pacote de placas `esp8266` (aparecem
  no Gerenciador de Bibliotecas e no Gerenciador de Placas da IDE).

## 4. A bancada está com o Felipe

A bancada chegou com o Felipe em 06/10, e ele grava e testa o UNO: o roteiro
automático de aceitação, as 100 passagens do carrinho pela tag (que medem a
leitura e a latência, H3), a operação de 30 minutos e o ensaio da
demonstração. Vocês não precisam gravar nada. Se quiserem acompanhar algum
desses testes, combinem com ele.
