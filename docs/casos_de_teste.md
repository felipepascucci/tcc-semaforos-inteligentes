# Especificação dos casos de teste

<!-- Gerado por `python -m analysis.gerar_casos_de_teste`. Não edite à mão: mude
     `context/06` ou os testes e gere de novo. -->

O que se testa e o critério de aprovação vêm de `context/06` (§2, §3 e §6). Os
casos listados em cada requisito são os que existem no código, lidos dos arquivos
de teste. O resultado de cada um está no relatório de validação
(`docs/relatorios/validacao_AAAAMMDD.md`), que roda as suítes.

Marcas que tiram um teste da suíte padrão (`pyproject.toml`): `sumo` (exige o
SUMO) e `hardware` (exige a bancada). `banco` sobe um PostgreSQL efêmero e exige
o Docker. O frontend roda no Vitest (`npm test` em `frontend/`).

## 1. Requisitos

### CT-01 · RF01

- **Caso:** VE a 480 m na rota é detectado; a 520 m não é
- **Critério de aprovação:** Detecção exata no limiar
- **Onde:** `test_deteccao.py`

`backend/tests/core/test_deteccao.py` — 20 caso(s):

- `test_ve_a_480_m_na_rota_e_detectado` — Critério de aceitação do RF01: detecção exata no limiar.
- `test_ve_a_520_m_na_rota_nao_e_detectado` — Do outro lado do limiar, nada é detectado.
- `test_exatamente_no_raio_e_detectado` — 500 m é `<=`, não `<`: o limiar pertence à zona de detecção.
- `test_ve_proximo_em_linha_reta_mas_fora_da_rota_nao_e_detectado` — O erro clássico que `context/01` §5.2 manda evitar pelo nome.
- `test_cruzamento_ja_ultrapassado_nao_e_detectado` — A rota é olhada só para a frente: o que ficou para trás não conta.
- `test_deteccoes_vem_ordenadas_da_mais_proxima`
- `test_movimento_detectado_e_o_par_entrada_saida` — E4 precisa do movimento, não só do cruzamento.
- `test_ultimo_cruzamento_da_rota_nao_gera_deteccao` — Sem via de saída não há movimento, e E4 não teria fase para escolher.
- `test_eta_e_distancia_sobre_velocidade`
- `test_ve_parado_nao_produz_eta_infinito` — O piso de velocidade existe para o veículo que mais precisa de prioridade.
- `test_velocidade_abaixo_do_piso_usa_o_piso`
- `test_janela_de_ativacao_depende_do_tempo_de_transicao` — `TEMPO_ANTECIPACAO = amarelo + all_red + verde_min_residual + MARGEM`.
- `test_preempcao_nao_comeca_cedo_demais` — Preemptar antes da hora trava a transversal de graça — o custo que H2 mede.
- `test_verde_minimo_pendente_antecipa_a_janela` — Verde mínimo pendente adianta o início da preempção.
- `test_fila_no_acesso_antecipa_a_janela` — **Regressão de P16.** Abrir o verde a tempo não basta: a fila tem de escoar.
- `test_sem_fila_a_janela_e_a_mesma_de_antes` — A correção de P16 não muda o comportamento onde não há fila.
- `test_janela_nao_passa_do_teto_derivado_do_timeout` — Antecipar mais que a preempção sobrevive derrubaria o corredor no rosto do VE.
- `test_fila_e_dividida_pelas_faixas_do_acesso` — Doze parados em duas faixas são seis à frente do VE, não doze.
- `test_via_sem_faixa_declarada_conta_como_uma` — Desconhecida vale 1 — o palpite que antecipa mais, não menos.
- `test_raio_de_deteccao_vem_dos_parametros` — Nenhum número mágico no meio da função (`context/08` §4.3).

### CT-02 · RF01

- **Caso:** VE a 100 m em linha reta mas **fora da rota** não é detectado
- **Critério de aprovação:** Distância de rota, não euclidiana
- **Onde:** `test_deteccao.py`

`backend/tests/core/test_deteccao.py` — 20 caso(s):

- `test_ve_a_480_m_na_rota_e_detectado` — Critério de aceitação do RF01: detecção exata no limiar.
- `test_ve_a_520_m_na_rota_nao_e_detectado` — Do outro lado do limiar, nada é detectado.
- `test_exatamente_no_raio_e_detectado` — 500 m é `<=`, não `<`: o limiar pertence à zona de detecção.
- `test_ve_proximo_em_linha_reta_mas_fora_da_rota_nao_e_detectado` — O erro clássico que `context/01` §5.2 manda evitar pelo nome.
- `test_cruzamento_ja_ultrapassado_nao_e_detectado` — A rota é olhada só para a frente: o que ficou para trás não conta.
- `test_deteccoes_vem_ordenadas_da_mais_proxima`
- `test_movimento_detectado_e_o_par_entrada_saida` — E4 precisa do movimento, não só do cruzamento.
- `test_ultimo_cruzamento_da_rota_nao_gera_deteccao` — Sem via de saída não há movimento, e E4 não teria fase para escolher.
- `test_eta_e_distancia_sobre_velocidade`
- `test_ve_parado_nao_produz_eta_infinito` — O piso de velocidade existe para o veículo que mais precisa de prioridade.
- `test_velocidade_abaixo_do_piso_usa_o_piso`
- `test_janela_de_ativacao_depende_do_tempo_de_transicao` — `TEMPO_ANTECIPACAO = amarelo + all_red + verde_min_residual + MARGEM`.
- `test_preempcao_nao_comeca_cedo_demais` — Preemptar antes da hora trava a transversal de graça — o custo que H2 mede.
- `test_verde_minimo_pendente_antecipa_a_janela` — Verde mínimo pendente adianta o início da preempção.
- `test_fila_no_acesso_antecipa_a_janela` — **Regressão de P16.** Abrir o verde a tempo não basta: a fila tem de escoar.
- `test_sem_fila_a_janela_e_a_mesma_de_antes` — A correção de P16 não muda o comportamento onde não há fila.
- `test_janela_nao_passa_do_teto_derivado_do_timeout` — Antecipar mais que a preempção sobrevive derrubaria o corredor no rosto do VE.
- `test_fila_e_dividida_pelas_faixas_do_acesso` — Doze parados em duas faixas são seis à frente do VE, não doze.
- `test_via_sem_faixa_declarada_conta_como_uma` — Desconhecida vale 1 — o palpite que antecipa mais, não menos.
- `test_raio_de_deteccao_vem_dos_parametros` — Nenhum número mágico no meio da função (`context/08` §4.3).

### CT-03 · RF02

- **Caso:** Da detecção ao **início da atuação** < 3 s (decisão P14)
- **Critério de aprovação:** `t_atuacao - t_deteccao < 3000 ms`. Na bancada, `t_atuacao` é a chegada do `EV,PREEMP_INI` do UNO (`05` §4.3)
- **Onde:** `test_e2e_preempcao.py` + checklist HW

`tests/e2e/test_e2e_preempcao.py` — 6 caso(s):

- `test_passagem_vira_preemp_ini_amostra_e_verde_exclusivo`
- `test_passagem_que_vira_fila_nao_e_amostra` — A ambulância com criticidade menor que a do bombeiro em verde vai para a fila.
- `test_janela_do_casamento_e_o_limite_do_rf02` — A janela que encerra a espera pela decisão é o próprio RF02, e não mais curta.
- `test_rf02_na_bancada_toda_preempcao_comeca_em_menos_de_3_s`
- `test_h3_na_bancada_p95_abaixo_de_200_ms`
- `test_amostras_de_h3_sao_os_preemp_ini_das_leituras_da_mesma_sessao` — Os dois CSV da rodada concordam: uma amostra por leitura que virou `PREEMP_INI`.

Bancada: ver o checklist (seção 3).

### CT-04 · RF03

- **Caso:** VE atravessa 8 cruzamentos sem parada
- **Critério de aprovação:** `waitingCount == 0` para o VE
- **Onde:** `test_corredor_verde.py`

`tests/e2e/test_corredor_verde.py` — 3 caso(s):

- `test_nenhum_ve_para_nos_bracos_com_preempcao` — O critério de `06` §2, ao pé da letra, sobre todas as travessias do experimento.
- `test_no_baseline_todo_ve_para` — O contraste que o RF03 pressupõe: sem preempção, o corredor não é verde.
- `test_com_preempcao_o_ve_para_menos_que_no_baseline` — Sem meta declarada, só a direção: nenhum limiar foi escolhido olhando o dado.

### CT-05 · RF04

- **Caso:** WebSocket emite mudança de estado em < 500 ms
- **Critério de aprovação:** Evento recebido no cliente de teste. Na bancada, da `ST` na ponte ao cliente, no ritmo de produção (leitura e difusão a 5 Hz), com o dublê. **No dashboard:** cada mensagem de estado muda a tela, e a conexão perdida é refeita
- **Onde:** `test_ws.py` + `test_bancada_integrada.py` + `frontend/src/stream/*.test.ts(x)`

`backend/tests/api/test_ws.py` — 3 caso(s):

- `test_rf04_mudanca_de_estado_chega_ao_cliente_em_menos_de_500_ms`
- `test_mensagens_seguem_o_contrato_de_context_01`
- `test_rf06_posicao_do_ve_e_publicada_a_pelo_menos_1_hz` — O executor transmite a 5 Hz; o cliente precisa ver a posição a cada ≤ 1 s.

`backend/tests/api/test_bancada_integrada.py` — 4 caso(s):

- `test_cada_decisao_do_uno_vira_uma_linha_de_log` — RF05: ambulância atendida, bombeiro na fila, polícia descartada — três linhas.
- `test_a_central_decide_quem_preempta_na_bancada` — Abrir a ocorrência libera a ambulância no UNO; encerrar volta a negar.
- `test_backend_que_reinicia_nao_regrava_o_historico`
- `test_rf04_mudanca_de_estado_chega_ao_websocket_em_menos_de_500_ms` — Da `ST` na ponte ao cliente, a cada mudança de luz, no ritmo de produção.

`frontend/src/stream/estado.test.ts` — 17 caso(s):

- `estado_semaforo > da bancada guarda as quatro aproximações, o regime, a rua ativa e a fila`
- `estado_semaforo > da simulação é reconhecida pela falta de aproximações e guarda o t simulado`
- `estado_semaforo > a mensagem mais nova substitui a anterior do mesmo cruzamento`
- `estado_semaforo > sinal fora de VERDE, AMARELO e VERMELHO é recusado sem quebrar o estado`
- `posicao_ve > guarda o id do SUMO, lat/lon e a velocidade em m/s`
- `posicao_ve > id numérico do cadastro também serve`
- `posicao_ve > sem coordenada a posição é recusada`
- `posicao_ve > um VE sem posição nova há mais que a validade sai do mapa`
- `evento > entra no topo, com a origem`
- `evento > a lista é limitada, e as chaves não se repetem`
- `metrica > cada transmissão da simulação é uma amostra de latência`
- `metrica > a bancada repete a última amostra de H3 em toda telemetria: só a diferente conta`
- `metrica > latência nula, como no modo FIXO, não vira amostra`
- `trafego (Bloco 7) > guarda a fotografia inteira e a substitui na próxima`
- `trafego (Bloco 7) > descarta posição malformada sem perder as boas`
- `trafego (Bloco 7) > fotografia velha sai do mapa, como o VE`
- `trafego (Bloco 7) > a métrica da simulação traz o tempo simulado e a velocidade`

`frontend/src/stream/useStream.test.tsx` — 4 caso(s):

- `useStream > estado do semáforo e posição do VE chegam à tela a cada mensagem`
- `useStream > conexão que cai é refeita, com espera crescente`
- `useStream > ao desmontar fecha o socket e não reconecta`
- `urlDoStream > segue o protocolo da página: wss atrás do nginx com HTTPS`

Bancada: ver o checklist (seção 3).

### CT-06 · RF05

- **Caso:** Toda preempção gera linha em `log_prioridade`
- **Critério de aprovação:** Contagem bate com nº de eventos. Na bancada, uma linha por evento de decisão do UNO, e o backend que reinicia não regrava
- **Onde:** `test_persistencia.py` + `test_bancada_integrada.py`

`backend/tests/db/test_persistencia.py` — 6 caso(s):

- `test_grava_e_le_log_prioridade_completo` — O critério de pronto do Bloco 1, ponta a ponta.
- `test_latencia_de_decisao_e_calculada_pelo_banco` — `latencia_decisao_ms` é coluna gerada — não pode divergir dos carimbos.
- `test_latencia_total_fica_nula_sem_atuacao` — Preempção abortada não tem `t_atuacao`, e a latência fim-a-fim não existe.
- `test_deteccao_nao_reconhecida_tambem_e_gravada` — UID desconhecido gera registro da tentativa (context/02 §6).
- `test_execucao_recusa_ponto_experimental_duplicado` — (cenário, modo, seed) é único — reexecução exige descarte documentado.
- `test_uid_normaliza_e_tag_inativa_nao_resolve` — Tag inativa é tratada como desconhecida — é como se revoga um cartão.

`backend/tests/api/test_bancada_integrada.py` — 4 caso(s):

- `test_cada_decisao_do_uno_vira_uma_linha_de_log` — RF05: ambulância atendida, bombeiro na fila, polícia descartada — três linhas.
- `test_a_central_decide_quem_preempta_na_bancada` — Abrir a ocorrência libera a ambulância no UNO; encerrar volta a negar.
- `test_backend_que_reinicia_nao_regrava_o_historico`
- `test_rf04_mudanca_de_estado_chega_ao_websocket_em_menos_de_500_ms` — Da `ST` na ponte ao cliente, a cada mudança de luz, no ritmo de produção.

Bancada: ver o checklist (seção 3).

### CT-07 · RF06

- **Caso:** Posição do VE é publicada a ≥ 1 Hz
- **Critério de aprovação:** Intervalo entre eventos ≤ 1 s. **No dashboard:** a posição recebida vai para o mapa, e a que para de chegar sai dele em 5 s
- **Onde:** `test_ws.py` + `frontend/src/stream/*.test.ts(x)`

`backend/tests/api/test_ws.py` — 3 caso(s):

- `test_rf04_mudanca_de_estado_chega_ao_cliente_em_menos_de_500_ms`
- `test_mensagens_seguem_o_contrato_de_context_01`
- `test_rf06_posicao_do_ve_e_publicada_a_pelo_menos_1_hz` — O executor transmite a 5 Hz; o cliente precisa ver a posição a cada ≤ 1 s.

`frontend/src/stream/estado.test.ts` — 17 caso(s):

- `estado_semaforo > da bancada guarda as quatro aproximações, o regime, a rua ativa e a fila`
- `estado_semaforo > da simulação é reconhecida pela falta de aproximações e guarda o t simulado`
- `estado_semaforo > a mensagem mais nova substitui a anterior do mesmo cruzamento`
- `estado_semaforo > sinal fora de VERDE, AMARELO e VERMELHO é recusado sem quebrar o estado`
- `posicao_ve > guarda o id do SUMO, lat/lon e a velocidade em m/s`
- `posicao_ve > id numérico do cadastro também serve`
- `posicao_ve > sem coordenada a posição é recusada`
- `posicao_ve > um VE sem posição nova há mais que a validade sai do mapa`
- `evento > entra no topo, com a origem`
- `evento > a lista é limitada, e as chaves não se repetem`
- `metrica > cada transmissão da simulação é uma amostra de latência`
- `metrica > a bancada repete a última amostra de H3 em toda telemetria: só a diferente conta`
- `metrica > latência nula, como no modo FIXO, não vira amostra`
- `trafego (Bloco 7) > guarda a fotografia inteira e a substitui na próxima`
- `trafego (Bloco 7) > descarta posição malformada sem perder as boas`
- `trafego (Bloco 7) > fotografia velha sai do mapa, como o VE`
- `trafego (Bloco 7) > a métrica da simulação traz o tempo simulado e a velocidade`

`frontend/src/stream/useStream.test.tsx` — 4 caso(s):

- `useStream > estado do semáforo e posição do VE chegam à tela a cada mensagem`
- `useStream > conexão que cai é refeita, com espera crescente`
- `useStream > ao desmontar fecha o socket e não reconecta`
- `urlDoStream > segue o protocolo da página: wss atrás do nginx com HTTPS`

### CT-08 · RF07

- **Caso:** Mudança de rota do VE recalcula os TLS-alvo
- **Critério de aprovação:** Novo conjunto de TLS após reroute
- **Onde:** `test_recalculo.py`

`backend/tests/core/test_recalculo.py` — 5 caso(s):

- `test_rota_nova_troca_os_cruzamentos_alvo` — O critério do RF07: novo conjunto de TLS depois da mudança de rota.
- `test_no_cruzamento_que_continua_na_rota_o_movimento_muda` — Em `CRUZ_A` o VE agora vira: o movimento pedido é outro, logo a fase também.
- `test_motor_recalcula_a_priorizacao_no_passo_seguinte_a_mudanca` — Rota antiga preempta A (em frente) e B; a nova troca a fase de A, solta B e pega C.
- `test_cruzamento_que_saiu_da_rota_nao_fica_preso_ao_ve` — Depois de liberado, `CRUZ_B` não volta a ser pedido pela rota nova.
- `test_mesma_rota_de_volta_recalcula_de_novo` — O recálculo não depende de sentido: voltar à rota antiga refaz a conta antiga.

### CT-09 · RNF01

- **Caso:** p95 de `latencia_decisao_ms` < 100 ms em 10.000 chamadas
- **Critério de aprovação:** Percentil, não média. **Latência de decisão** — só `motor.avaliar()`, sem I/O (decisão P2)
- **Onde:** `test_desempenho.py`

`backend/tests/core/test_desempenho.py` — 5 caso(s):

- `test_p95_da_decisao_fica_sob_100_ms_em_10000_chamadas` — O critério do RNF01, na malha de 8 cruzamentos do experimento.
- `test_p99_tambem_cabe_no_orcamento` — A cauda é o que interessa num sistema crítico.
- `test_escala_para_malha_de_32_cruzamentos` — RNF03 — a malha pode crescer sem estourar o orçamento de latência.
- `test_multiplos_ves_nao_estouram_o_orcamento` — O cenário `multiplas_emergencias` é o mais caro em tempo de decisão.
- `test_politica_aprendida_nao_estoura_o_orcamento` — RNF01 com o braço `PREEMPCAO_ML` (entrega 10.6): a inferência entra no trecho medido.

### CT-10 · H3

- **Caso:** p95 de `latencia_total_ms` (t_deteccao→t_atuacao) < 200 ms em **100 passagens de bancada**
- **Critério de aprovação:** **Latência fim-a-fim**: da leitura da tag no veículo ao `PREEMP_INI` do UNO, os dois carimbados no relógio do notebook pela ponte (`05` §4.3). Inclui ESP-NOW, a serial e a decisão do UNO. **n = 100 desde 2026-10-06** (decisão do grupo): as mesmas passagens do RNF05, com p95 estimável; mín, mediana e máx reportados ao lado, com o n. Antes eram 5 repetições, com o limiar verificado sobre o máximo (decisão de 2026-08-31, superada)
- **Onde:** `test_e2e_preempcao.py` + checklist HW

`tests/e2e/test_e2e_preempcao.py` — 6 caso(s):

- `test_passagem_vira_preemp_ini_amostra_e_verde_exclusivo`
- `test_passagem_que_vira_fila_nao_e_amostra` — A ambulância com criticidade menor que a do bombeiro em verde vai para a fila.
- `test_janela_do_casamento_e_o_limite_do_rf02` — A janela que encerra a espera pela decisão é o próprio RF02, e não mais curta.
- `test_rf02_na_bancada_toda_preempcao_comeca_em_menos_de_3_s`
- `test_h3_na_bancada_p95_abaixo_de_200_ms`
- `test_amostras_de_h3_sao_os_preemp_ini_das_leituras_da_mesma_sessao` — Os dois CSV da rodada concordam: uma amostra por leitura que virou `PREEMP_INI`.

Bancada: ver o checklist (seção 3).

### CT-11 · RNF02

- **Caso:** Sistema opera 60 min contínuos sem vazamento de memória
- **Critério de aprovação:** RSS estável ± 10%
- **Onde:** `test_soak.py`

`sim/tests/test_soak.py` — 2 caso(s):

- `test_rss_e_um_numero_plausivel` — O medidor em si: um processo Python com o pytest carregado tem dezenas de MB.
- `test_uma_hora_de_operacao_sem_vazamento`

### CT-12 · RNF03

- **Caso:** Motor processa malha de 32 TLS mantendo p95 < 100 ms
- **Critério de aprovação:** Escala linear ou melhor
- **Onde:** `test_desempenho.py`

`backend/tests/core/test_desempenho.py` — 5 caso(s):

- `test_p95_da_decisao_fica_sob_100_ms_em_10000_chamadas` — O critério do RNF01, na malha de 8 cruzamentos do experimento.
- `test_p99_tambem_cabe_no_orcamento` — A cauda é o que interessa num sistema crítico.
- `test_escala_para_malha_de_32_cruzamentos` — RNF03 — a malha pode crescer sem estourar o orçamento de latência.
- `test_multiplos_ves_nao_estouram_o_orcamento` — O cenário `multiplas_emergencias` é o mais caro em tempo de decisão.
- `test_politica_aprendida_nao_estoura_o_orcamento` — RNF01 com o braço `PREEMPCAO_ML` (entrega 10.6): a inferência entra no trecho medido.

### CT-13 · RNF04

- **Caso:** POST sem `X-Device-Token` válido → 401; UID não cadastrado → 403
- **Critério de aprovação:** Códigos corretos. Vale para a API; na bancada nenhum dispositivo chama a API, e a ausência de criptografia no ESP-NOW é limitação declarada (`02` §6)
- **Onde:** `backend/tests/api/test_seguranca.py`

`backend/tests/api/test_seguranca.py` — 6 caso(s):

- `test_sem_token_valido_e_401_e_nada_e_gravado`
- `test_token_de_outro_dispositivo_nao_serve` — O token do CTRL_PROTO_01 dos seeds não autentica o leitor de teste.
- `test_dispositivo_desconhecido_e_401`
- `test_dispositivo_inativo_e_401`
- `test_uid_nao_cadastrado_e_403`
- `test_autenticacao_atualiza_o_ultimo_contato`

### CT-14 · RNF04 (dashboard)

- **Caso:** Login certo → token de 8 h; credencial errada → 401 sem dizer qual parte errou; cada escrita do operador sem token, com token vencido, falso ou malformado → 401; com token → passa; GETs e `/simulacoes/transmissao` abertos; sem login configurado → 503; `alg: none` recusado
- **Critério de aprovação:** Códigos corretos. O HTTPS do nginx é conferido de ponta a ponta à mão (`README`), não na suíte
- **Onde:** `backend/tests/api/test_autenticacao.py` + `backend/tests/test_autenticacao.py` + `frontend/src/auth/sessao.test.tsx`

`backend/tests/api/test_autenticacao.py` — 9 caso(s):

- `test_login_com_a_credencial_certa_devolve_um_token_que_abre_a_sessao`
- `test_credencial_errada_e_401_sem_dizer_qual_parte_errou`
- `test_sessao_sem_token_e_401`
- `test_escrita_sem_token_e_401_com_o_desafio_bearer`
- `test_escrita_com_token_expirado_ou_falso_e_401`
- `test_escrita_com_token_valido_passa_da_autenticacao` — Sem banco, quem passa responde 503; o DELETE, que não abre sessão, dá o 409.
- `test_leitura_continua_aberta`
- `test_transmissao_do_executor_continua_aberta`
- `test_sem_login_configurado_o_login_e_as_escritas_dao_503` — Falta de configuração não vira porta aberta.

`backend/tests/test_autenticacao.py` — 12 caso(s):

- `test_a_senha_certa_confere_e_a_errada_nao`
- `test_o_hash_nao_contem_a_senha_e_muda_com_o_sal`
- `test_o_hash_nao_tem_cifrao_para_ir_no_compose_sem_escape`
- `test_hash_malformado_nao_confere_nem_levanta`
- `test_token_emitido_e_validado_devolve_a_sessao`
- `test_token_expirado_e_recusado_com_o_motivo`
- `test_token_assinado_com_outro_segredo_e_recusado`
- `test_token_sem_assinatura_e_recusado` — `alg: none` é o ataque clássico: o token só é aceito em HS256.
- `test_token_sem_o_perfil_operador_e_recusado`
- `test_lixo_no_lugar_do_token_e_recusado`
- `test_segredo_curto_derruba_a_configuracao_na_subida`
- `test_login_so_esta_configurado_com_as_tres_variaveis`

`frontend/src/auth/sessao.test.tsx` — 4 caso(s):

- `sessão do operador > credencial errada mostra o motivo e continua no login`
- `sessão do operador > login certo guarda a sessão, e as requisições seguintes levam o token`
- `sessão do operador > sessão salva e válida abre direto, e o token recusado volta ao login com aviso`
- `sessão do operador > sessão salva vencida é ignorada`

### CT-15 · RF01 (P20, API)

- **Caso:** Tag reconhecida sem ocorrência → 200 `SEM_OCORRENCIA`; com ocorrência → `PREEMPCAO_SOLICITADA` com a criticidade, e `id_correlacao` igual na detecção e no log; repetição em 2 s não grava
- **Critério de aprovação:** Corpo e linhas gravadas
- **Onde:** `backend/tests/api/test_deteccoes.py`

`backend/tests/api/test_deteccoes.py` — 9 caso(s):

- `test_tag_reconhecida_sem_ocorrencia_e_200_sem_prioridade` — P20: a credencial vale, falta o serviço. 200, não 403.
- `test_com_ocorrencia_a_deteccao_autoriza_e_correlaciona_ate_o_log`
- `test_tag_desconhecida_e_403_e_a_tentativa_fica_gravada`
- `test_tag_inativa_e_tratada_como_desconhecida` — As tags dos seeds são placeholders inativos: nenhuma autoriza (context/03 §5).
- `test_veiculo_inativo_e_200_sem_prioridade`
- `test_mesma_tag_dentro_de_2_s_devolve_a_mesma_resposta_sem_gravar` — O RC522 lê a mesma tag várias vezes por segundo: uma passagem, uma linha.
- `test_uid_normalizado_conta_como_a_mesma_tag`
- `test_janela_anti_replay_vence_em_2_s`
- `test_sequencia_repetida_do_mesmo_leitor_e_o_mesmo_pacote` — Um reenvio do mesmo pacote, ainda que com outra tag no corpo, não grava de novo.

### CT-16 · RNF05

- **Caso:** Taxa de reconhecimento de tag ≥ 95% em 100 leituras
- **Critério de aprovação:** Medição manual em bancada
- **Onde:** Checklist HW

Bancada: ver o checklist (seção 3).

### CT-17 · RNF07

- **Caso:** `core/` não importa framework nem I/O
- **Critério de aprovação:** Teste de arquitetura via AST
- **Onde:** `test_arquitetura.py`

`backend/tests/test_arquitetura.py` — 5 caso(s):

- `test_existe_codigo_para_verificar` — Guarda contra o teste passar por não achar arquivo nenhum.
- `test_modulo_do_core_nao_importa_framework_nem_io`
- `test_modulo_do_core_nao_depende_das_camadas_de_fora`
- `test_modulo_do_core_nao_chama_io_direto` — `open()` e `print()` não precisam de import — e escapariam da checagem acima.
- `test_motor_nao_usa_distancia_euclidiana` — E1 exige distância **ao longo da rota** (`context/01` §5.2).

### CT-18 · RF01 (P20)

- **Caso:** Tag reconhecida **sem** ocorrência ativa não é autorizada; com ocorrência, é, e carrega a criticidade
- **Critério de aprovação:** Os quatro desfechos de `autorizar()`: tag desconhecida, veículo inativo, sem ocorrência, autorizado
- **Onde:** `test_autorizacao.py`

`backend/tests/core/test_autorizacao.py` — 4 caso(s):

- `test_tag_desconhecida_nao_autoriza`
- `test_veiculo_inativo_nao_autoriza_nem_com_ocorrencia` — Veículo em manutenção não volta à rua por ter uma ocorrência esquecida aberta.
- `test_tag_reconhecida_sem_ocorrencia_nao_autoriza` — Identidade não é emergência: sem ocorrência aberta, sem prioridade.
- `test_tag_reconhecida_com_ocorrencia_autoriza_com_a_criticidade_dela`

### CT-19 · RF01 (P20)

- **Caso:** Na simulação, VE sem o parâmetro `criticidade` não chega ao motor
- **Critério de aprovação:** Veículo de `vClass` emergência inserido sem o parâmetro fica fora de `veiculos_emergencia`
- **Onde:** `sim/tests/test_adaptador.py` (marca `sumo`)

`sim/tests/test_adaptador.py` — 8 caso(s):

- `test_estado_lido_descreve_a_malha_inteira` — `EstadoMalha` é a única entrada do motor: precisa vir completo.
- `test_ve_e_detectado_pela_classe_e_nao_pelo_nome` — `vClass="emergency"` é o que identifica o VE — não uma convenção de id.
- `test_ve_sem_ocorrencia_nao_chega_ao_motor` — P20 — ser VE não é estar em serviço.
- `test_ve_nunca_anda_para_tras_ao_atravessar_um_cruzamento` — Regressão do defeito de via interna, achado na entrega 10.1.
- `test_preempcao_emite_comandos_e_gera_transicoes` — O caminho completo: estado -> motor -> comando -> sinalização.
- `test_invariantes_valem_no_modo_com_preempcao` — I1 a I5 verificados a cada passo, contra o SUMO de verdade.
- `test_modo_fixo_nao_preempta_nada` — O baseline precisa ser genuinamente sem intervenção (context/04 §8).
- `test_baseline_cumpre_o_ciclo_de_setenta_segundos` — A sequência do `.tll.xml`: verde -> amarelo -> all-red -> próxima fase.

### CT-20 · E8 (P20)

- **Caso:** Criticidade vence tipo; no mesmo nível, a ordem antiga (tipo → ETA → em curso) é preservada
- **Critério de aprovação:** Bombeiro nível 1 vence ambulância nível 2; com criticidade espelhando o tipo, a decisão é idêntica à da chave anterior (Hypothesis)
- **Onde:** `test_conflito.py`

`backend/tests/core/test_conflito.py` — 17 caso(s):

- `test_criticidade_vence_o_tipo` — Incêndio com vítima não espera ambulância com caso leve.
- `test_criticidade_vence_o_eta` — Chegar antes não compensa ser menos crítico.
- `test_criticidade_vence_preempcao_em_curso` — Nível mais crítico toma o verde de quem já o detém.
- `test_criticidade_tipica_decide_como_a_chave_anterior` — A propriedade que garante que nenhum número já medido muda.
- `test_ambulancia_vence_viatura_mesmo_chegando_depois` — Critério 1 tem precedência sobre o 2: tipo antes de ETA.
- `test_entre_iguais_vence_o_menor_eta` — Critério 2, quando o 1 empata.
- `test_preempcao_em_curso_desempata_e_evita_oscilacao` — Critério 3, quando 1 e 2 empatam.
- `test_ordem_de_prioridade_vem_dos_parametros` — `prioridade_tipo` é configurável (`context/01` §5.3), não constante do código.
- `test_fases_conflitantes_nunca_sao_concedidas_juntas` — A regra dura de E8: um espera, e isso vira `CONFLITO_ADIADO`.
- `test_mesma_fase_serve_os_dois_sem_conflito` — Dois VEs pelo mesmo movimento não disputam nada — o mesmo verde os serve.
- `test_sem_disputa_nao_ha_resolucao`
- `test_motivo_explica_o_desempate` — É o texto que vai para `log_prioridade.motivo` e para a banca.
- `test_motivo_nomeia_a_criticidade_quando_ela_decide` — O log precisa dizer qual critério decidiu — e cabe em `motivo VARCHAR(200)`.
- `test_resolucao_sem_adiados_tem_motivo_simples`
- `test_politica_decide_entre_iguais` — No mesmo nível, a proposta da política vence a chave de E8.
- `test_politica_nao_passa_por_cima_da_criticidade` — A criticidade é regra acima de qualquer política (P20): a proposta é ignorada.
- `test_proposta_fora_das_disputas_e_ignorada`

## 2. Invariantes de segurança

### I1 — Nunca dois verdes conflitantes

- **Método:** Property-based (Hypothesis): gerar sequências aleatórias de comandos e verificar o invariante em todo estado alcançado
- **Arquivos:** `backend/tests/core/test_seguranca.py`, `backend/tests/core/test_invariantes_property.py`, `tests/firmware/test_firmware_uno.py`, `bridge/tests/test_verificar.py`

### I2 — Nunca verde → vermelho direto

- **Método:** Analisar a sequência de transições de `estado_semaforo_amostra` (decisão P5: uma linha por troca de fase): nenhum par G→R sem Y intermediário
- **Arquivos:** `backend/tests/core/test_seguranca.py`, `backend/tests/core/test_invariantes_property.py`, `tests/firmware/test_firmware_uno.py`, `bridge/tests/test_verificar.py`

### I3 — All-red entre fases

- **Método:** Idem, sobre a mesma sequência de transições
- **Arquivos:** `backend/tests/core/test_seguranca.py`, `backend/tests/core/test_invariantes_property.py`, `tests/firmware/test_firmware_uno.py`, `bridge/tests/test_verificar.py`

### I4 — Verde mínimo respeitado

- **Método:** `duracao_fase_anterior_s` de toda fase verde ≥ `verde_min`
- **Arquivos:** `backend/tests/core/test_seguranca.py`, `backend/tests/core/test_invariantes_property.py`, `tests/firmware/test_firmware_uno.py`, `bridge/tests/test_verificar.py`

### I5 — Sem starvation

- **Método:** Nenhum acesso em vermelho por > 120 s
- **Arquivos:** `backend/tests/core/test_seguranca.py`, `backend/tests/core/test_motor.py`

### I1–I4 no firmware — Mesmos invariantes, na bancada

- **Método:** Hypothesis contra o dublê (sequências aleatórias de linhas de entrada em instantes aleatórios) e `bridge.verificar` contra a placa, sobre a sequência de `ST` (`05` §4.2)
- **Arquivos:** `tests/firmware/test_firmware_uno.py`, `bridge/tests/test_verificar.py`

### I6 — Emergência termina sozinha (redefinido em 2026-10-05, `01` §6)

- **Método:** Dublê e `bridge.verificar`: o verde do VE acaba na duração do tipo, e renovações sucessivas param no teto de 30 s com `EV,TIMEOUT`
- **Arquivos:** `tests/firmware/test_firmware_uno.py`, `bridge/tests/test_verificar.py`

## 3. Aceitação do protótipo físico

O roteiro de `context/06` §6, sem o registro de cada execução (que fica em `06`
e no relatório de validação). "Pelo dado": o módulo que julga o item sobre a
telemetria gravada; os demais são observação de quem está na bancada.

| # | Verificação | Pelo dado |
| --- | --- | --- |
| 1 | Ciclo alterna os **2 eixos** (ciclo de 12 s) por 5 min sem travar; liga em all-red. | `analysis.checklist_bancada` |
| 2 | Nunca há verde nos dois eixos ao mesmo tempo; em emergência só a aproximação do VE fica verde — 5 min de observação e a telemetria do mesmo período. | `analysis.checklist_bancada` |
| 3 | Toda transição verde→vermelho passa por amarelo, e há all-red antes de todo verde novo, **inclusive na entrada e na saída da emergência**. | `analysis.checklist_bancada` |
| 4 | 100 passagens sobre as tags das ruas: em ≥ 95 a linha chega ao UNO com a rua certa, ou seja, há um evento de decisão com a rua da tag — RNF05. Um `RECUSADO` conta como falha (a linha chegou corrompida). **Medido na mesma rodada do 7b, com o emissor no USB do notebook** (decisão de 2026-10-06): o denominador são as leituras que o emissor imprimiu, e o resultado é declarado nessa condição, que alimenta o emissor melhor que a bateria de 9 V da demonstração. Cada leitura vira uma linha de `analysis/data/deteccoes_bancada.csv`; a taxa sai de `python -m analysis.resumo_bancada`. | `analysis.resumo_bancada` |
| 5 | Tag fora das 4 ruas não gera envio nem mexe no semáforo. **Roteiro (declarado em 2026-10-07, antes da rodada):** ponte com `--porta COM3 --porta-veiculo COM5 --telemetria`, emissor no USB; a ambulância recebe ocorrência (pela Central, ou com o compose parado por `PUT /autorizacoes` na ponte); com o ciclo correndo, a tag fora do mapa passa pelo leitor do carrinho **10 vezes**, com pelo menos 4 s entre uma e outra, ao longo de pelo menos 1 min; por último, uma passagem de **controle** na tag da Rua 1. Julgado por `python -m analysis.checklist_bancada --item5`; o LCD sem mudança nas 10 passagens e a contagem delas são observação. | `analysis.checklist_bancada` |
| 5b | **Tag sem ocorrência** (volta em 2026-10-06): sem ocorrência aberta para a ambulância na Central, a passagem gera `SEM_OCORRENCIA`, não mexe no semáforo, e o LCD mostra `SEM OCORRENCIA` por 3 s; abrindo a ocorrência, a passagem seguinte preempta. | `analysis.checklist_bancada` |
| 6 | LCD mostra o VE e a rua em < 1 s após a leitura. | observação |
| 7 | Preempção iniciada (`PREEMP_INI`) em < 3 s da leitura da tag — RF02. | `analysis.resumo_bancada` |
| 7b | **H3** — p95 de `latencia_total_ms` < 200 ms em **100 passagens** (as do item 4), com o emissor no USB do notebook e a ambulância em serviço na Central; mín/mediana/máx registrados. `python -m bridge.main --porta COM3 --porta-veiculo <COM do emissor>` (COM5 no notebook do Felipe, CP2102); cada passagem atendida vira uma linha de `analysis/data/latencia_bancada.csv` (`05` §6); n, mín, mediana, p95 e máx saem de `python -m analysis.resumo_bancada`. | `analysis.resumo_bancada` |
| 8 | Dashboard mostra o evento em tempo real. | observação |
| 9 | Log gravado no PostgreSQL com `id_correlacao` completo. | `analysis.checklist_bancada` |
| 10 | Com a bancada montada, a injeção pela ponte mostra a regra de prioridade pela criticidade: o VE mais crítico interrompe o outro pelo amarelo e all-red, o interrompido vai para a fila (LCD `Fila:…`) e é atendido depois. | `analysis.checklist_bancada` |
| 11 | Renovações sucessivas param no teto de 30 s (`EV,TIMEOUT`) e o ciclo volta pelo eixo oposto. | `analysis.checklist_bancada` |
| 12 | Operação contínua de 30 min sem travamento ou reboot. | `analysis.checklist_bancada` |
| 13 | Nenhum LED com brilho anômalo ou aquecimento perceptível. | observação |
| 14 | Ponte encerrada no meio de uma emergência → o semáforo segue, e o carrinho continua preemptando com a última lista da Central. | observação |
| 15 | Ponte reiniciada (o UNO reinicia junto) → o UNO volta negando todos, e com o backend no ar a lista da Central volta em até ~1 s. | `analysis.checklist_bancada` |

## 4. Inventário da suíte

| Arquivo | Casos |
| --- | ---: |
| `analysis/tests/test_analise_h4.py` | 8 |
| `analysis/tests/test_carregar.py` | 9 |
| `analysis/tests/test_checklist_bancada.py` | 25 |
| `analysis/tests/test_estatistica.py` | 14 |
| `analysis/tests/test_figuras.py` | 4 |
| `analysis/tests/test_gerar_casos_de_teste.py` | 5 |
| `analysis/tests/test_gerar_relatorio_validacao.py` | 26 |
| `analysis/tests/test_gerar_resultados_tcc.py` | 12 |
| `analysis/tests/test_relatorio_piloto.py` | 17 |
| `analysis/tests/test_resumo_bancada.py` | 8 |
| `analysis/tests/test_resumo_conflitos.py` | 10 |
| `analysis/tests/test_resumo_rotulos.py` | 6 |
| `analysis/tests/test_treino_politica.py` | 16 |
| `backend/tests/adapters/test_hardware_simulado.py` | 43 |
| `backend/tests/api/test_autenticacao.py` | 9 |
| `backend/tests/api/test_bancada_integrada.py` | 4 |
| `backend/tests/api/test_cadastro.py` | 14 |
| `backend/tests/api/test_deteccoes.py` | 9 |
| `backend/tests/api/test_health.py` | 4 |
| `backend/tests/api/test_regras_simulacao.py` | 3 |
| `backend/tests/api/test_seguranca.py` | 6 |
| `backend/tests/api/test_simulacoes.py` | 12 |
| `backend/tests/api/test_ws.py` | 3 |
| `backend/tests/core/test_atributos.py` | 3 |
| `backend/tests/core/test_autorizacao.py` | 4 |
| `backend/tests/core/test_compensacao.py` | 10 |
| `backend/tests/core/test_conflito.py` | 17 |
| `backend/tests/core/test_desempenho.py` | 5 |
| `backend/tests/core/test_deteccao.py` | 20 |
| `backend/tests/core/test_fases.py` | 16 |
| `backend/tests/core/test_invariantes_property.py` | 5 |
| `backend/tests/core/test_motor.py` | 28 |
| `backend/tests/core/test_politica.py` | 31 |
| `backend/tests/core/test_recalculo.py` | 5 |
| `backend/tests/core/test_seguranca.py` | 18 |
| `backend/tests/db/test_atendente.py` | 6 |
| `backend/tests/db/test_migrations_e_seeds.py` | 15 |
| `backend/tests/db/test_ocorrencia.py` | 13 |
| `backend/tests/db/test_persistencia.py` | 6 |
| `backend/tests/test_arquitetura.py` | 5 |
| `backend/tests/test_autenticacao.py` | 12 |
| `backend/tests/test_bancada.py` | 16 |
| `backend/tests/test_configuracao.py` | 15 |
| `backend/tests/test_difusao.py` | 5 |
| `backend/tests/test_fila_lote.py` | 8 |
| `backend/tests/test_logs.py` | 2 |
| `backend/tests/test_parametros.py` | 8 |
| `bridge/tests/test_api.py` | 14 |
| `bridge/tests/test_demo.py` | 19 |
| `bridge/tests/test_gravar_uno.py` | 6 |
| `bridge/tests/test_latencia.py` | 13 |
| `bridge/tests/test_main.py` | 7 |
| `bridge/tests/test_ponte.py` | 21 |
| `bridge/tests/test_protocolo.py` | 20 |
| `bridge/tests/test_registro.py` | 4 |
| `bridge/tests/test_serial_client.py` | 9 |
| `bridge/tests/test_verificar.py` | 12 |
| `frontend/src/App.test.tsx` | 2 |
| `frontend/src/api/cliente.test.ts` | 10 |
| `frontend/src/auth/sessao.test.tsx` | 4 |
| `frontend/src/componentes/MapaMalha.test.ts` | 5 |
| `frontend/src/componentes/PainelBancada.test.tsx` | 7 |
| `frontend/src/componentes/PainelCentral.test.tsx` | 4 |
| `frontend/src/componentes/PainelMetricas.test.ts` | 3 |
| `frontend/src/componentes/PreempcaoManual.test.tsx` | 4 |
| `frontend/src/componentes/TelaLogs.test.tsx` | 3 |
| `frontend/src/componentes/TelaSimulacoes.test.tsx` | 8 |
| `frontend/src/stream/estado.test.ts` | 17 |
| `frontend/src/stream/useStream.test.tsx` | 4 |
| `sim/tests/test_adaptador.py` | 8 |
| `sim/tests/test_ambiente_sumo.py` | 3 |
| `sim/tests/test_calibracao.py` | 13 |
| `sim/tests/test_calibracao_compensacao.py` | 13 |
| `sim/tests/test_conflitos.py` | 19 |
| `sim/tests/test_demanda.py` | 30 |
| `sim/tests/test_executor_ajustes.py` | 11 |
| `sim/tests/test_executor_modos.py` | 7 |
| `sim/tests/test_exportar_mapa.py` | 10 |
| `sim/tests/test_lote.py` | 39 |
| `sim/tests/test_malha.py` | 12 |
| `sim/tests/test_ritmo.py` | 5 |
| `sim/tests/test_rotulagem.py` | 11 |
| `sim/tests/test_soak.py` | 2 |
| `sim/tests/test_traco.py` | 3 |
| `sim/tests/test_transmissor.py` | 11 |
| `sim/tests/test_validacao.py` | 10 |
| `sim/tests/test_versao_do_codigo.py` | 6 |
| `tests/cli/test_saida_utf8.py` | 4 |
| `tests/diagramas/test_bancada.py` | 6 |
| `tests/diagramas/test_caracteres_do_pdf.py` | 2 |
| `tests/diagramas/test_der.py` | 2 |
| `tests/diagramas/test_infraestrutura.py` | 2 |
| `tests/e2e/test_corredor_verde.py` | 3 |
| `tests/e2e/test_e2e_preempcao.py` | 6 |
| `tests/firmware/test_firmware_uno.py` | 24 |
| `tests/firmware/test_sketches_nodemcu.py` | 10 |

96 arquivos, 1008 funções de teste. Um teste parametrizado ou com
Hypothesis conta uma vez aqui e roda várias vezes na suíte.
