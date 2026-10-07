# 06 — Testes e Relatórios de Validação

## 1. Pirâmide de testes

| Nível | Onde | O que cobre | Ferramenta |
| --- | --- | --- | --- |
| Unitário | `backend/tests/core/` | Motor de decisão, invariantes, compensação, conflito | pytest |
| Unitário | `bridge/tests/` | Protocolo serial, ponte, carimbo no primeiro byte, casamento de H3 | pytest + Hypothesis |
| Unitário | `tests/firmware/` | Núcleo do firmware do UNO contra o dublê, linha por linha; sketches dos NodeMCUs iguais aos da equipe; compilação para o UNO | pytest + Hypothesis + `ziglang` + `arduino-cli` |
| Integração | `backend/tests/api/` | Rotas, persistência, WebSocket | pytest + httpx + testcontainers |
| Integração | `sim/tests/` | Adaptador TraCI em cenário curto (60 s) | pytest |
| Unitário / componente | `frontend/src/**/*.test.ts(x)` | Estado ao vivo do WebSocket (reducer), cliente HTTP, sessão do operador, painéis (bancada, central, preempção manual, logs), o `App` inteiro com API e WebSocket falsos | Vitest + Testing Library (jsdom) |
| Sistema | `tests/e2e/` | Fluxo completo com adaptador simulado | pytest |
| Aceitação | Manual roteirizado | Protótipo físico | Checklist assinado |

O motor de decisão precisa de **cobertura alta e testes rápidos**, porque é o que a banca vai questionar. Testes que exigem SUMO ou hardware ligado devem ser marcados (`@pytest.mark.sumo`, `@pytest.mark.hardware`) e ficar fora da execução padrão.

## 2. Casos de teste por requisito

Cada RF/RNF vira pelo menos um teste automatizado. Esta tabela é a rastreabilidade requisito → teste que o TCC precisa apresentar.

| Req. | Caso de teste | Critério de aprovação | Arquivo |
| --- | --- | --- | --- |
| RF01 | VE a 480 m na rota é detectado; a 520 m não é | Detecção exata no limiar | `test_deteccao.py` |
| RF01 | VE a 100 m em linha reta mas **fora da rota** não é detectado | Distância de rota, não euclidiana | `test_deteccao.py` |
| RF02 | Da detecção ao **início da atuação** < 3 s (decisão P14) | `t_atuacao - t_deteccao < 3000 ms`. Na bancada, `t_atuacao` é a chegada do `EV,PREEMP_INI` do UNO (`05` §4.3) | `test_e2e_preempcao.py` + checklist HW |
| RF03 | VE atravessa 8 cruzamentos sem parada | `waitingCount == 0` para o VE | `test_corredor_verde.py` |
| RF04 | WebSocket emite mudança de estado em < 500 ms | Evento recebido no cliente de teste. Na bancada, da `ST` na ponte ao cliente, no ritmo de produção (leitura e difusão a 5 Hz), com o dublê. **No dashboard:** cada mensagem de estado muda a tela, e a conexão perdida é refeita | `test_ws.py` + `test_bancada_integrada.py` + `frontend/src/stream/*.test.ts(x)` |
| RF05 | Toda preempção gera linha em `log_prioridade` | Contagem bate com nº de eventos. Na bancada, uma linha por evento de decisão do UNO, e o backend que reinicia não regrava | `test_persistencia.py` + `test_bancada_integrada.py` |
| RF06 | Posição do VE é publicada a ≥ 1 Hz | Intervalo entre eventos ≤ 1 s. **No dashboard:** a posição recebida vai para o mapa, e a que para de chegar sai dele em 5 s | `test_ws.py` + `frontend/src/stream/*.test.ts(x)` |
| RF07 | Mudança de rota do VE recalcula os TLS-alvo | Novo conjunto de TLS após reroute | `test_recalculo.py` |
| RNF01 | p95 de `latencia_decisao_ms` < 100 ms em 10.000 chamadas | Percentil, não média. **Latência de decisão** — só `motor.avaliar()`, sem I/O (decisão P2) | `test_desempenho.py` |
| H3 | p95 de `latencia_total_ms` (t_deteccao→t_atuacao) < 200 ms em **100 passagens de bancada** | **Latência fim-a-fim**: da leitura da tag no veículo ao `PREEMP_INI` do UNO, os dois carimbados no relógio do notebook pela ponte (`05` §4.3). Inclui ESP-NOW, a serial e a decisão do UNO. **n = 100 desde 2026-10-06** (decisão do grupo): as mesmas passagens do RNF05, com p95 estimável; mín, mediana e máx reportados ao lado, com o n. Antes eram 5 repetições, com o limiar verificado sobre o máximo (decisão de 2026-08-31, superada) | `test_e2e_preempcao.py` + checklist HW |
| RNF02 | Sistema opera 60 min contínuos sem vazamento de memória | RSS estável ± 10% | `test_soak.py` |
| RNF03 | Motor processa malha de 32 TLS mantendo p95 < 100 ms | Escala linear ou melhor | `test_desempenho.py` |
| RNF04 | POST sem `X-Device-Token` válido → 401; UID não cadastrado → 403 | Códigos corretos. Vale para a API; na bancada nenhum dispositivo chama a API, e a ausência de criptografia no ESP-NOW é limitação declarada (`02` §6) | `backend/tests/api/test_seguranca.py` |
| RNF04 (dashboard) | Login certo → token de 8 h; credencial errada → 401 sem dizer qual parte errou; cada escrita do operador sem token, com token vencido, falso ou malformado → 401; com token → passa; GETs e `/simulacoes/transmissao` abertos; sem login configurado → 503; `alg: none` recusado | Códigos corretos. O HTTPS do nginx é conferido de ponta a ponta à mão (`README`), não na suíte | `backend/tests/api/test_autenticacao.py` + `backend/tests/test_autenticacao.py` + `frontend/src/auth/sessao.test.tsx` |
| RF01 (P20, API) | Tag reconhecida sem ocorrência → 200 `SEM_OCORRENCIA`; com ocorrência → `PREEMPCAO_SOLICITADA` com a criticidade, e `id_correlacao` igual na detecção e no log; repetição em 2 s não grava | Corpo e linhas gravadas | `backend/tests/api/test_deteccoes.py` |
| RNF05 | Taxa de reconhecimento de tag ≥ 95% em 100 leituras | Medição manual em bancada | Checklist HW |
| RNF07 | `core/` não importa framework nem I/O | Teste de arquitetura via AST | `test_arquitetura.py` |
| RF01 (P20) | Tag reconhecida **sem** ocorrência ativa não é autorizada; com ocorrência, é, e carrega a criticidade | Os quatro desfechos de `autorizar()`: tag desconhecida, veículo inativo, sem ocorrência, autorizado | `test_autorizacao.py` |
| RF01 (P20) | Na simulação, VE sem o parâmetro `criticidade` não chega ao motor | Veículo de `vClass` emergência inserido sem o parâmetro fica fora de `veiculos_emergencia` | `sim/tests/test_adaptador.py` (marca `sumo`) |
| E8 (P20) | Criticidade vence tipo; no mesmo nível, a ordem antiga (tipo → ETA → em curso) é preservada | Bombeiro nível 1 vence ambulância nível 2; com criticidade espelhando o tipo, a decisão é idêntica à da chave anterior (Hypothesis) | `test_conflito.py` |

`test_arquitetura.py` é barato e evita a erosão da regra principal do §1 de `01-arquitetura-sistema.md`. Vale a pena.

> **Estado em 2026-08-25 (fim do Bloco 3).** Já implementados: **RF01**
> (`backend/tests/core/test_deteccao.py`), **RNF01** e **RNF03**
> (`backend/tests/core/test_desempenho.py`), **RNF07**
> (`backend/tests/test_arquitetura.py`) e os invariantes **I1 a I5**
> (`test_seguranca.py` e `test_invariantes_property.py`).
>
> **RF03 ganhou evidência no Bloco 3**, ainda que não como teste automatizado:
> `waitingCount == 0` para o VE em execução de simulação real, contra 5,5 paradas
> no baseline pareado (mesma seed, mesmo cenário). Falta transformar a medição em
> `test_corredor_verde.py`, o que depende de definir quantas seeds o teste roda —
> um teste que sobe o SUMO por 3.600 s não cabe numa suíte.
>
> **Integração `sim/` implementada** (`context/06` §1, linha "Adaptador TraCI em
> cenário curto"): `sim/tests/test_adaptador.py` roda os 60 s de
> `teste_60s.sumocfg` nos dois modos e verifica leitura de estado, detecção de VE
> por `vClass`, emissão de comandos, transições e I1–I5 contra o SUMO de verdade.
> Somam-se `test_malha.py` (geometria, mapa de fases, detectores),
> `test_calibracao.py` e `test_demanda.py` (pareamento por seed) e
> `test_validacao.py` (critérios de descarte).
>
> Os demais dependem de blocos ainda por fazer: RF02, RF07 e H3 exigem a camada
> IoT e a API (Blocos 5 e 6); RF04, RF05, RF06 e RNF04 exigem a API e o WebSocket
> (Bloco 6); RNF02 e RNF05 exigem execução longa e bancada (Blocos 8 e 5).
>
> **Estado em 2026-10-05 (Bloco 6).** RF04, RF05, RNF04 e RF06 ganharam teste
automatizado na API (`backend/tests/api/`). RF06 mede o caminho da simulação: a
posição do VE chega ao cliente a cada ≤ 1 s com o executor transmitindo a 5 Hz.
Os testes da bancada usam o dublê, e **nenhum número deles é dado
experimental**. RF02, RF07 e H3 continuam dependendo da bancada e da simulação
longa.
>
> **Estado em 2026-10-05 (Bloco 7).** O dashboard tem 70 testes no Vitest. No
> backend, a suíte padrão foi de 575 para 645 (autenticação, ritmo, tráfego na
> transmissão, desenho da malha, rota secundária), e a de banco, de 89 para 103
> (velocidade do pedido). As 23 do SUMO passam. RF04 e RF06 passam a ter evidência também no cliente: o reducer do
> WebSocket e o hook de conexão. O RNF04 passa a cobrir o dashboard (login e
> HTTPS). Os dados dos testes do frontend são artificiais (`TST1A01`,
> `ve_teste_0`), e nenhum é dado experimental.
>
> **Conferido também fora da suíte, no mesmo dia:**
> - o dashboard aberto num Chrome sem janela, com captura de cada aba,
>   durante uma simulação real transmitida a 10x;
> - o fluxo do operador com digitação e cliques de verdade, no mesmo navegador:
>   senha errada (mostra o motivo), login, abrir ocorrência com descrição,
>   encerrar, filtrar os logs pela correlação clicada e sair, sem erro no console;
> - o ritmo e a leitura do tráfego **não mudam o resultado**: `moderado`,
>   `PREEMPCAO`, seed 900, 700 s, rodado sem transmissão e a 10x com tráfego,
>   deu as mesmas 472 transições, os mesmos 754 veículos concluídos e a mesma
>   viagem de VE (327,3 s, 0 paradas). A conferência não virou teste da suíte
>   porque leva ~80 s de relógio com o SUMO.

`RNF03` foi realocado de `test_escala.py` para `test_desempenho.py`: as duas
> medições compartilham o mesmo aparato de medição de percentil, e separá-las em
> dois arquivos duplicaria o código sem separar conceito nenhum.

## 3. Testes de invariantes de segurança

Estes são os testes mais importantes do projeto. Falha aqui é falha crítica, não bug.

| ID | Teste | Método |
| --- | --- | --- |
| I1 | Nunca dois verdes conflitantes | Property-based (Hypothesis): gerar sequências aleatórias de comandos e verificar o invariante em todo estado alcançado |
| I2 | Nunca verde → vermelho direto | Analisar a sequência de transições de `estado_semaforo_amostra` (decisão P5: uma linha por troca de fase): nenhum par G→R sem Y intermediário |
| I3 | All-red entre fases | Idem, sobre a mesma sequência de transições |
| I4 | Verde mínimo respeitado | `duracao_fase_anterior_s` de toda fase verde ≥ `verde_min` |
| I5 | Sem starvation | Nenhum acesso em vermelho por > 120 s |
| I1–I4 no firmware | Mesmos invariantes, na bancada | Hypothesis contra o dublê (sequências aleatórias de linhas de entrada em instantes aleatórios) e `bridge.verificar` contra a placa, sobre a sequência de `ST` (`05` §4.2) |
| I6 | Emergência termina sozinha (redefinido em 2026-10-05, `01` §6) | Dublê e `bridge.verificar`: o verde do VE acaba na duração do tipo, e renovações sucessivas param no teto de 30 s com `EV,TIMEOUT` |

Property-based testing para I1 é altamente recomendado: gerar milhares de sequências de comandos aleatórios e verificar que o invariante nunca quebra. É um argumento forte de qualidade para a banca — muito mais convincente que "testamos manualmente".

## 4. Verificação estrutural das execuções

Antes de aceitar qualquer conjunto de dados como válido:

```python
def validar_execucao(execucao) -> list[str]:
    """Retorna lista de problemas. Vazia = execução válida."""
    # colisões == 0
    # nenhum veículo teleportado
    # todos os VEs planejados completaram a rota
    # duração real == duração planejada
    # nenhuma violação de invariante registrada
    # latência p99 dentro do orçamento
```

Execução que falhe qualquer item é **descartada e reexecutada com a mesma seed**, e o descarte é registrado. Descarte silencioso de execução ruim é má prática científica; descarte documentado com critério pré-definido é metodologia.

> **Implementado em `sim/validacao/execucao.py`** (Bloco 3), com os seis itens e
> mais um: a **cauda** da latência. O p99 acima do dobro do orçamento reprova
> mesmo com o p95 dentro — sistema crítico se avalia pela cauda (`04` §9.3).
>
> A função é pura: recebe o `ResultadoExecucao` já consolidado e não toca em
> SUMO, banco ou disco. Isso é o que permite testá-la na suíte padrão, e testar o
> critério de descarte **antes** de os dados existirem é o que separa metodologia
> de racionalização a posteriori (`sim/tests/test_validacao.py`).
>
> A verificação da **malha** (`04` §12), que roda uma vez antes de experimentar,
> é outra coisa e mora em `sim/validacao/malha.py`.
>
> **Ligada ao lote no Bloco 4.** `sim/controlador/lote.py` chama
> `validar_execucao()` em **toda** execução. A que reprova não entra nos CSV de
> `analysis/data/`: fica na própria pasta de `sim/saida/`, com a evidência bruta,
> e o motivo — mais o caminho da evidência — vai para
> `analysis/data/descartes.csv`. Reexecutar exige apagar a linha de
> `execucao_simulacao` (a restrição única em cenário/modo/seed a bloqueia), o que
> se faz com `--repetir MOTIVO`; a remoção também é registrada no mesmo arquivo.
>
> **`ves_planejados` fica desligado no lote, de propósito.** Quantos VEs completam
> a rota depende do braço: o último parte perto do fim do horizonte e, no
> baseline — que é mais lento —, pode não chegar dentro dos 3.600 s. Exigir um
> número fixo reprovaria execuções legítimas de `FIXO`, justamente o controle. O
> pareamento é feito **por id de VE** na análise, sobre a interseção dos três
> braços (`analysis/relatorio_piloto.py`), e o relatório declara quantos VEs a
> interseção descartou.

## 5. Relatório de validação (entregável 6 do escopo)

Gerado por `analysis/gerar_relatorio_validacao.py` → `docs/relatorios/validacao_YYYYMMDD.md` (+ PDF).

Estrutura obrigatória:

1. **Identificação** — data, versão do código (`git rev-parse`), versão do SUMO, hash dos parâmetros.
2. **Ambiente de teste** — hardware, SO, versões de dependências.
3. **Matriz de execuções** — quantas planejadas, quantas válidas, quantas descartadas e por quê.
4. **Rastreabilidade requisito → teste → resultado** — a tabela do §2 preenchida com PASSOU/FALHOU e a evidência.
5. **Resultados dos invariantes de segurança** — I1 a I6, com contagem de violações (esperado: zero).
6. **Latências** — tabela com mín / média / p95 / p99 / máx, por ambiente (simulação e hardware).
7. **Casos de falha observados** — o que quebrou durante o desenvolvimento e como foi corrigido. **Não omitir.** Uma seção honesta de falhas e correções vale mais na banca que um relatório imaculado, e é o que diferencia um relatório de engenharia de um folheto.
8. **Checklist do protótipo físico** — assinado pela equipe, com data da execução.
9. **Anexos** — logs relevantes, capturas do dashboard, fotos da bancada.

## 6. Checklist de aceitação do protótipo físico

Executar e registrar antes da apresentação. Marcar data, executor e resultado.

Reescrito em 2026-10-05 para a arquitetura da bancada (`05`). Os itens que
dependiam do notebook comandar o UNO, de Wi-Fi ou de ocorrência (P20) saíram;
ver a nota abaixo da tabela.

| # | Verificação | OK |
| --- | --- | --- |
| 1 | Ciclo alterna os **2 eixos** (ciclo de 12 s) por 5 min sem travar; liga em all-red | ☐ |
| 2 | Nunca há verde nos dois eixos ao mesmo tempo; em emergência só a aproximação do VE fica verde — 5 min de observação e a telemetria do mesmo período | ☐ |
| 3 | Toda transição verde→vermelho passa por amarelo, e há all-red antes de todo verde novo, **inclusive na entrada e na saída da emergência** | ☐ |
| 4 | 100 passagens sobre as tags das ruas: em ≥ 95 a linha chega ao UNO com a rua certa, ou seja, há um evento de decisão com a rua da tag — RNF05. Um `RECUSADO` conta como falha (a linha chegou corrompida). **Medido na mesma rodada do 7b, com o emissor no USB do notebook** (decisão de 2026-10-06): o denominador são as leituras que o emissor imprimiu, e o resultado é declarado nessa condição, que alimenta o emissor melhor que a bateria de 9 V da demonstração. Cada leitura vira uma linha de `analysis/data/deteccoes_bancada.csv`; a taxa sai de `python -m analysis.resumo_bancada`. **2026-10-07: 100 de 100** (25 por rua), todas `PREEMP_INI`; duas linhas do emissor que chegaram ilegíveis ao notebook ficaram fora do denominador e foram repostas (`09`, 2026-10-07) | ☑ |
| 5 | Tag fora das 4 ruas não gera envio nem mexe no semáforo | ☐ |
| 5b | **Tag sem ocorrência** (volta em 2026-10-06): sem ocorrência aberta para a ambulância na Central, a passagem gera `SEM_OCORRENCIA`, não mexe no semáforo, e o LCD mostra `SEM OCORRENCIA` por 3 s; abrindo a ocorrência, a passagem seguinte preempta | ☐ |
| 6 | LCD mostra o VE e a rua em < 1 s após a leitura | ☐ |
| 7 | Preempção iniciada (`PREEMP_INI`) em < 3 s da leitura da tag — RF02. **2026-10-07:** nas 100 passagens do 7b, máximo de 46,3 ms | ☑ |
| 7b | **H3** — p95 de `latencia_total_ms` < 200 ms em **100 passagens** (as do item 4), com o emissor no USB do notebook e a ambulância em serviço na Central; mín/mediana/máx registrados. `python -m bridge.main --porta COM3 --porta-veiculo <COM do emissor>` (COM5 no notebook do Felipe, CP2102); cada passagem atendida vira uma linha de `analysis/data/latencia_bancada.csv` (`05` §6); n, mín, mediana, p95 e máx saem de `python -m analysis.resumo_bancada`. **2026-10-07: p95 31,6 ms** (n = 100; sem as 2 de carimbo atrasado, n = 98 e p95 33,0 ms), `analysis/data/resumo_bancada_2026-10-07.md` | ☑ |
| 8 | Dashboard mostra o evento em tempo real | ☐ |
| 9 | Log gravado no PostgreSQL com `id_correlacao` completo | ☐ |
| 10 | Com a bancada montada, a injeção pela ponte mostra a regra de prioridade pela criticidade: o VE mais crítico interrompe o outro pelo amarelo e all-red, o interrompido vai para a fila (LCD `Fila:…`) e é atendido depois | ☐ |
| 11 | Renovações sucessivas param no teto de 30 s (`EV,TIMEOUT`) e o ciclo volta pelo eixo oposto | ☐ |
| 12 | Operação contínua de 30 min sem travamento ou reboot | ☐ |
| 13 | Nenhum LED com brilho anômalo ou aquecimento perceptível | ☐ |
| 14 | Ponte encerrada no meio de uma emergência → o semáforo segue, e o carrinho continua preemptando com a última lista da Central | ☐ |
| 15 | Ponte reiniciada (o UNO reinicia junto) → o UNO volta negando todos, e com o backend no ar a lista da Central volta em até ~1 s | ☐ |

> **O que saiu em 2026-10-05:** o 5 antigo (tag não cadastrada → negação) e o 5b
> (P20, sem ocorrência), porque o UNO não consulta cadastro nem ocorrência; o 10
> antigo (USB desconectado → watchdog), porque o UNO não depende do notebook e o
> USB é a alimentação dele; o 11 antigo (queda do Wi-Fi), porque não há Wi-Fi.
>
> **O que voltou e entrou em 2026-10-06:** o 5b, reescrito, porque a Central
> passou a valer na bancada (`05` §3.3); o 15, porque a lista da Central vive na
> RAM do UNO e se perde a cada reinício. O 10 deixou de pedir o fio solto.

**Como o checklist é registrado (desde 2026-10-07).** A ponte sobe com
`--telemetria` (`python -m bridge.main --porta COM3 --porta-veiculo COM5
--telemetria`) e grava cada linha do USB do UNO, nos dois sentidos, crua e
carimbada, em `analysis/data/telemetria_bancada.csv`. `python -m
analysis.checklist_bancada --banco` tira dela, por sessão da ponte, o veredito dos
itens que o dado julga. Os critérios abaixo foram declarados **antes** da
medição; as durações são do `millis()` do UNO, com a folga de 60 ms de
`bridge.verificar`:

- **1** — depois de cada `BOOT`, a primeira `ST` é `RRRR` e o primeiro verde é o
  do eixo principal, com all-red de pelo menos 1 s. Todo ciclo puro (só regime
  `C` entre duas aberturas do eixo principal) dura 12 s, e há um trecho contínuo
  desses ciclos de pelo menos 5 min.
- **2** — nenhuma `ST` com verde nos dois eixos; em regime `E`, nenhum verde acende
  fora da aproximação da rua ativa; todo VE atendido até o `PREEMP_FIM` chega ao
  verde exclusivo.
- **3** — nenhum achado de `bridge.verificar.violacoes` (I2, I3, I4) na sessão
  inteira, com pelo menos uma entrada e uma saída de emergência.
- **5b** — regime, rua ativa e fila iguais antes e depois do `SEM_OCORRENCIA`; se
  em ciclo, o ciclo que o contém dura 12 s. A primeira decisão do tipo depois de
  a lista do UNO lhe dar ocorrência é `PREEMP_INI`. O LCD é observação.
- **9** — todo evento de decisão da sessão tem exatamente uma linha em
  `log_prioridade` com o mesmo carimbo, e todas têm `id_correlacao`; toda amostra
  de H3 em `metrica_latencia` está ligada a uma linha com o mesmo `id_correlacao`.
- **10** — em toda interrupção, quem interrompe tem criticidade estritamente mais
  alta (número menor) que o interrompido, e este é atendido no `PREEMP_FIM` do
  outro. O `Fila:…` do LCD é observação.
- **11** — `TIMEOUT` a 30 s do `PREEMP_INI` que abriu a emergência, e o primeiro
  verde depois é do eixo oposto ao do último VE, em ciclo.
- **12** — pelo menos 30 min da primeira à última `ST`, nenhum reinício do UNO no
  meio, e nenhum intervalo entre duas `ST` maior que 2 s, o silêncio a partir do
  qual a ponte dá o UNO por calado.
- **15** — a cada abertura da porta, a primeira `ST` traz `000`, e a lista da
  Central, **inteira** como a ponte a escreveu no primeiro envio depois do
  `BOOT`, chega à `ST` em até **2 s** do `BOOT`. É a leitura de "~1 s":
  enquanto a ponte esteve fora, o backend a procura só a cada 1 s.

"Não atende" quer dizer que o dado mostra uma falha. Sessão curta demais para
o item, sem falha (as sessões de 20 s do item 15, para os itens 1 e 12), sai
"sem veredito" (ajuste de 2026-10-07, depois da rodada; `09`).
- **14** — o dado mostra só que a sessão terminou em emergência; o resto é
  observação, como 5, 6, 8 e 13, registrados com data e executor.

O item 5 espera uma tag fora do mapa das 4 ruas, que a bancada não tem
(2026-10-07; o Felipe vai providenciar).

Item 12 é o que pega: sketches com `String` travam depois de ~20 min. Rodar esse teste **antes** do dia da apresentação, não no dia.

> **Decidido pelo grupo em 2026-10-06: 100 passagens.** O item 7b mede H3 nas
> mesmas 100 passagens do item 4, com p95 estimável. O registro abaixo é o
> histórico da questão.
>
> **Observação sobre o n de H3 (2026-08-31), a decidir no Bloco 5.** O item 7b
> pedia 5 repetições, e 5 amostras não sustentam um percentil — o "p95" de cinco
> valores é o máximo com nome de percentil. Mas o **item 4 já exige 100
> aproximações de tag** para o RNF05. Se o firmware carimbar `t_deteccao` e
> `t_atuacao` nessas mesmas 100 leituras, H3 ganha um **p95 de verdade sem uma
> única repetição extra** — é instrumentação, não experimento novo. As 5
> repetições do item 7b ficam então como verificação roteirizada, e as 100 como a
> amostra que vai para T2 e F2. `DECISÃO DO GRUPO — avaliar ao escrever o firmware
> do Bloco 5.`
>
> **Com a arquitetura de 2026-10-05, o custo ficou concreto.** Basta fazer as 100
> passagens com o emissor no USB do notebook e a ponte gravando
> `latencia_bancada.csv`. Só conta como amostra a passagem que gera
> `PREEMP_INI`; uma passagem durante a emergência anterior vira `RENOVADO` e não
> mede atuação. Por isso cada passagem espera o ciclo voltar, ~20 s cada, ~35 min
> no total. A decisão continua com o grupo.

## 7. Estratégia de dados de teste

- **Fixtures determinísticas** para testes unitários — `EstadoMalha` construído à mão, sem SUMO.
- **Cenário curto** (`sim/config/teste_60s.sumocfg`) para testes de integração: 60 s, 1 VE, 2 cruzamentos. Roda em segundos. O VE de `teste_60s.rou.xml` é escrito à mão e por isso traz o `<param key="criticidade">` explicitamente (P20) — sem ele o adaptador o trataria como fora de serviço.
- **Banco de teste** efêmero via `testcontainers` ou schema separado, nunca o banco de desenvolvimento.
