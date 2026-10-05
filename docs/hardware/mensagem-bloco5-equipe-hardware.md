# Bloco 5 — firmware novo do UNO: o que precisamos de vocês

Oi, pessoal! O programa novo do Arduino UNO está pronto, na pasta
`firmware/uno/semaforo/` da branch `feat/bloco5-camada-iot`. Ele mantém o que o
sketch de vocês já fazia: a mesma linha vinda do NodeMCU (`RUA3,AMBULANCIA`), as
mesmas prioridades (ambulância > bombeiro > polícia), os mesmos tempos de verde
do VE (9, 8 e 7 s), a fila de um lugar e as mesmas mensagens no LCD. Os dois
NodeMCUs **não mudam**: só foram copiados para `firmware/nodemcu/`, com um
comentário no topo.

O que mudou foi a segurança das trocas de luz. No sketch antigo, a emergência
apagava um verde e acendia outro no mesmo instante, sem amarelo e sem todos
vermelhos no meio. Agora toda troca passa por verde mínimo de 3 s, amarelo de
2 s e 1 s com tudo vermelho. Isso não está em discussão, é a regra de segurança
do trabalho.

## 1. Confirmem estas 7 mudanças de comportamento

Respondam "ok" ou "não" em cada uma. Se alguma não fizer sentido para vocês, a
gente ajusta antes de gravar.

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

## 2. Ainda falta de vocês

- **Quem está com a bancada** e pode gravar o UNO.
- **Fotos da bancada**, de perto, dando para ver em que pino entra cada fio: a
  bancada inteira de cima, as ligações no UNO e o NodeMCU com o RC522.
- **Versões** da biblioteca `MFRC522` e do pacote de placas `esp8266` (aparecem
  no Gerenciador de Bibliotecas e no Gerenciador de Placas da IDE).

## 3. Quando forem gravar o UNO

1. Na Arduino IDE, instalem a biblioteca **"LiquidCrystal I2C" de Frank de
   Brabander** (talvez já esteja instalada).
2. Abram `firmware/uno/semaforo/semaforo.ino`. Os arquivos `controlador.h` e
   `controlador.cpp` abrem junto, em abas; é para ser assim.
3. **Soltem o fio do TX do NodeMCU do pino RX (0) do UNO**, gravem, e deixem o
   fio solto para o teste abaixo.
4. Com o UNO no USB, rodem no notebook (o Felipe ajuda):
   `python -m bridge.main --porta COM3` e, noutro terminal, logo em seguida,
   `python -m bridge.verificar`. Leva uns 3 minutos e precisa dar **16 de 16**.
5. Recoloquem o fio do NodeMCU no RX e passem o carrinho pela tag: o semáforo
   da rua tem que ir a verde passando por amarelo e por todos vermelhos.

Depois disso falta só medir a latência (H3): o NodeMCU do carrinho fica no USB do
notebook, sem a bateria, e passamos o carrinho pela tag algumas vezes. Combinamos
quando a bancada estiver com alguém.
