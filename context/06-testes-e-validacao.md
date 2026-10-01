# 06 — Testes e Relatórios de Validação

## 1. Pirâmide de testes

| Nível | Onde | O que cobre | Ferramenta |
| --- | --- | --- | --- |
| Unitário | `backend/tests/core/` | Motor de decisão, invariantes, compensação, conflito | pytest |
| Unitário | `bridge/tests/` | Serialização do protocolo serial | pytest |
| Integração | `backend/tests/api/` | Rotas, persistência, WebSocket | pytest + httpx + testcontainers |
| Integração | `sim/tests/` | Adaptador TraCI em cenário curto (60 s) | pytest |
| Sistema | `tests/e2e/` | Fluxo completo com adaptador simulado | pytest |
| Aceitação | Manual roteirizado | Protótipo físico | Checklist assinado |

O motor de decisão precisa de **cobertura alta e testes rápidos**, porque é o que a banca vai questionar. Testes que exigem SUMO ou hardware ligado devem ser marcados (`@pytest.mark.sumo`, `@pytest.mark.hardware`) e ficar fora da execução padrão.

## 2. Casos de teste por requisito

Cada RF/RNF vira pelo menos um teste automatizado. Esta tabela é a rastreabilidade requisito → teste que o TCC precisa apresentar.

| Req. | Caso de teste | Critério de aprovação | Arquivo |
| --- | --- | --- | --- |
| RF01 | VE a 480 m na rota é detectado; a 520 m não é | Detecção exata no limiar | `test_deteccao.py` |
| RF01 | VE a 100 m em linha reta mas **fora da rota** não é detectado | Distância de rota, não euclidiana | `test_deteccao.py` |
| RF02 | Da detecção ao **início da atuação** < 3 s (decisão P14) | `t_atuacao - t_deteccao < 3000 ms`, com `t_atuacao` carimbado na chegada do `ACK` | `test_e2e_preempcao.py` |
| RF03 | VE atravessa 8 cruzamentos sem parada | `waitingCount == 0` para o VE | `test_corredor_verde.py` |
| RF04 | WebSocket emite mudança de estado em < 500 ms | Evento recebido no cliente de teste | `test_ws.py` |
| RF05 | Toda preempção gera linha em `log_prioridade` | Contagem bate com nº de eventos | `test_persistencia.py` |
| RF06 | Posição do VE é publicada a ≥ 1 Hz | Intervalo entre eventos ≤ 1 s | `test_ws.py` |
| RF07 | Mudança de rota do VE recalcula os TLS-alvo | Novo conjunto de TLS após reroute | `test_recalculo.py` |
| RNF01 | p95 de `latencia_decisao_ms` < 100 ms em 10.000 chamadas | Percentil, não média. **Latência de decisão** — só `motor.avaliar()`, sem I/O (decisão P2) | `test_desempenho.py` |
| H3 | `latencia_total_ms` (t_deteccao→t_atuacao) < 200 ms em **5 repetições de bancada** | **Latência fim-a-fim**, inclui rede e atuação. Medida no fluxo de hardware e no e2e. Com n = 5 o p95 **não é estimável**: reportar mín/mediana/máx com o n declarado e verificar o limiar sobre o **máximo observado** (decisão de 2026-08-31) | `test_e2e_preempcao.py` + checklist HW |
| RNF02 | Sistema opera 60 min contínuos sem vazamento de memória | RSS estável ± 10% | `test_soak.py` |
| RNF03 | Motor processa malha de 32 TLS mantendo p95 < 100 ms | Escala linear ou melhor | `test_desempenho.py` |
| RNF04 | POST sem `X-Device-Token` válido → 401; UID não cadastrado → 403 | Códigos corretos | `test_seguranca.py` |
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
> `RNF03` foi realocado de `test_escala.py` para `test_desempenho.py`: as duas
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
| I6 | Watchdog do firmware | Teste manual: desconectar USB durante preempção, cronometrar retorno ao ciclo fixo (< 3 s) |

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

| # | Verificação | OK |
| --- | --- | --- |
| 1 | Ciclo fixo alterna corretamente as **4 fases** (ciclo de 24 s, decisão P13) por 5 min sem travar | ☐ |
| 2 | Nenhuma combinação com verdes conflitantes em 5 min de observação — sob *split phasing* I1 é `contar_verdes() <= 1` | ☐ |
| 3 | Toda transição verde→vermelho passa por amarelo | ☐ |
| 4 | Tag da ambulância reconhecida em 100 aproximações (≥ 95 sucessos) — **com ocorrência aberta**, para que cada leitura também exercite a preempção | ☐ |
| 5 | Tag não cadastrada gera negação e não preempta | ☐ |
| 5b | **P20** — tag cadastrada **sem ocorrência aberta** → LCD `SEM OCORRENCIA`, nenhuma preempção, tentativa gravada em `deteccao` com `autorizado = false` | ☐ |
| 6 | LCD atualiza em < 1 s após a leitura | ☐ |
| 7 | Preempção ocorre em < 3 s da leitura da tag | ☐ |
| 7b | **H3** — `latencia_total_ms` < 200 ms em **5 repetições**, com mín/mediana/máx registrados | ☐ |
| 8 | Dashboard mostra o evento em tempo real | ☐ |
| 9 | Log gravado no PostgreSQL com `id_correlacao` completo | ☐ |
| 10 | Desconexão do USB → retorno ao ciclo fixo em < 3 s | ☐ |
| 11 | Queda do Wi-Fi → LCD mostra "SEM CONEXAO", semáforos seguem em ciclo | ☐ |
| 12 | Operação contínua de 30 min sem travamento ou reboot | ☐ |
| 13 | Nenhum LED com brilho anômalo ou aquecimento perceptível | ☐ |

Item 12 é o que pega: sketches com `String` travam depois de ~20 min. Rodar esse teste **antes** do dia da apresentação, não no dia.

> **Observação sobre o n de H3 (2026-08-31), a decidir no Bloco 5.** O item 7b
> pede 5 repetições, e 5 amostras não sustentam um percentil — o "p95" de cinco
> valores é o máximo com nome de percentil. Mas o **item 4 já exige 100
> aproximações de tag** para o RNF05. Se o firmware carimbar `t_deteccao` e
> `t_atuacao` nessas mesmas 100 leituras, H3 ganha um **p95 de verdade sem uma
> única repetição extra** — é instrumentação, não experimento novo. As 5
> repetições do item 7b ficam então como verificação roteirizada, e as 100 como a
> amostra que vai para T2 e F2. `DECISÃO DO GRUPO — avaliar ao escrever o firmware
> do Bloco 5.`

## 7. Estratégia de dados de teste

- **Fixtures determinísticas** para testes unitários — `EstadoMalha` construído à mão, sem SUMO.
- **Cenário curto** (`sim/config/teste_60s.sumocfg`) para testes de integração: 60 s, 1 VE, 2 cruzamentos. Roda em segundos. O VE de `teste_60s.rou.xml` é escrito à mão e por isso traz o `<param key="criticidade">` explicitamente (P20) — sem ele o adaptador o trataria como fora de serviço.
- **Banco de teste** efêmero via `testcontainers` ou schema separado, nunca o banco de desenvolvimento.
