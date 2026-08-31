# 00 — Visão Geral do Projeto

## 1. Identificação

| Campo | Valor |
| --- | --- |
| Título | Modelo Inteligente de Controle Dinâmico de Semáforos Baseado em Dados de Tráfego para Priorização de Veículos de Emergência em Ambientes Urbanos |
| Instituição | Universidade Paulista (UNIP) — Instituto de Ciências Exatas e Tecnologia |
| Curso | Bacharelado em Ciência da Computação |
| Orientador | Prof. Marco Gomes |
| Equipe | Felipe Rafael Tancredi Pascucci (T895HG3), Giovanna Santos da Silva (G828HA5), Isabelle Rosa Moura Ferreira (N075465) |
| Ano | 2026 |

## 2. Problema

Congestionamento urbano atrasa a chegada de ambulâncias, viaturas policiais e veículos do Corpo de Bombeiros. Semáforos de tempo fixo não reagem ao tráfego real, e sistemas atuados tradicionais respondem apenas ao próprio cruzamento, sem coordenação na malha.

## 3. Proposta

Sistema que detecta o veículo de emergência (VE) na aproximação, calcula quais semáforos da rota devem ser alterados e executa a preempção semafórica de forma coordenada, criando um corredor verde ("onda verde") à frente do veículo — e, após a passagem, compensa o ciclo para reduzir o impacto nas vias transversais.

A validação ocorre em **duas frentes complementares**:

- **Frente A — Simulação (SUMO + TraCI):** produz os dados quantitativos que sustentam as hipóteses. É a fonte dos resultados estatísticos do TCC.
- **Frente B — Protótipo físico (Arduino + ESP8266 + RFID):** prova de conceito tangível da camada V2I e do atuador semafórico. É demonstração de viabilidade, **não** fonte de dados estatísticos.

Ambas são controladas pelo **mesmo motor de decisão** (`backend/core/priorizacao/`). Essa é a decisão arquitetural central do projeto: o algoritmo é agnóstico ao atuador. Trocar SUMO por hardware é trocar um adaptador, não reescrever a lógica. Isso é o que torna defensável a afirmação de que "o modelo validado em simulação é o mesmo que roda no protótipo".

## 4. Objetivos

**Geral:** desenvolver e validar um modelo de controle dinâmico de semáforos que priorize veículos de emergência reduzindo seu tempo de travessia, sem degradar de forma inaceitável o fluxo transversal.

> **A palavra "inaceitável" não tem definição — e virou pendência P18 em
> 2026-08-31.** Até então era abstrata; depois da correção de P16 a degradação
> transversal medida no cenário `intenso` passou de +24,6% para **+43,6%**, e o
> objetivo geral promete um critério que o trabalho não tem. Ou se declara um
> teto numérico na metodologia, **antes** do Bloco 8, ou se reescreve o objetivo
> para não prometer um limiar. Ver P18 em `09-pendencias-e-decisoes.md`.

**Específicos:**

1. Modelar uma malha urbana arterial simulada com 4 a 8 cruzamentos semaforizados.
2. Implementar o algoritmo de detecção e preempção com integração Python + TraCI.
3. Implementar a camada de identificação V2I (radar + RFID no protótipo físico).
4. Persistir eventos e métricas em PostgreSQL para auditoria e análise.
5. Disponibilizar dashboard web de monitoramento em tempo real.
6. Comparar estatisticamente o modelo proposto com o baseline de temporização fixa.
7. Demonstrar o funcionamento fim-a-fim no protótipo físico de 4 semáforos.

## 5. Hipóteses de pesquisa

| ID | Hipótese | Como será testada |
| --- | --- | --- |
| H1 | A fusão radar + V2I reduz em **no mínimo 25%** o tempo total de travessia do VE, em cenários de saturação **moderada a intensa**, em relação à temporização estática | Comparação pareada por seed, baseline vs. proposto. O cenário `leve` é medido e discutido, mas **sem meta numérica** |
| H2 | É possível mitigar em **no mínimo 15%** o impacto negativo nas vias transversais com compensação dinâmica de ciclo pós-evento | Três braços: baseline / preempção sem compensação / preempção com compensação |
| H3 | A infraestrutura em borda sustenta latência operacional **fim-a-fim inferior a 200 ms** | Instrumentação `t_deteccao → t_decisao → t_atuacao`, medida no **protótipo**, com **5 repetições** roteirizadas no checklist |

> **Decisões P1 e P2 tomadas em 2026-08-24** (ver `09-pendencias-e-decisoes.md`):
>
> - **H1 é condicionada à saturação.** A Tabela 1 do próprio pré-projeto mostra 8,3% em fluxo leve; nenhuma meta única sobrevive aos quatro cenários. Meta: ≥ 25% em `moderado` e `intenso`.
>
> **Saturação medida, a partir do Bloco 3** (2026-08-25, ver `04` §5 e `09`): os
> cenários operam a v/c de **0,18** (`leve`), **0,42** (`moderado`) e **0,73**
> (`intenso`). Os dois cenários em que a meta de H1 se aplica ficam, portanto, em
> saturação moderada e moderada-alta. Os nomes dos cenários são rótulos do ponto
> experimental; a caracterização do regime é o v/c medido, e é ele que vai no
> texto.
> - **RNF01 e H3 medem coisas diferentes e coexistem.** RNF01 (< 100 ms) é a latência de *decisão* — do estado recebido à emissão do comando, software puro. H3 (< 200 ms) é a latência *fim-a-fim* — da detecção física à atuação, incluindo rede. Instrumentar as duas separadamente em `metrica_latencia`, reportando p95 e p99 de ambas.

> **Decisões de 2026-08-31** (ver `09-pendencias-e-decisoes.md`):
>
> - **H2 passa de "em até 15%" para "em no mínimo 15%".** A redação antiga era um
>   teto, não uma meta: sob ela, a mitigação de −1,0% a +0,6% medida no piloto do
>   Bloco 4 **cumpriria** a hipótese literalmente. `≥ 15%` é simétrico com H1 e é a
>   única leitura sob a qual H2 pode ser rejeitada. **Continua em aberto o
>   denominador** — se os 15% incidem sobre a espera transversal ou sobre o
>   *acréscimo* que a preempção causou (pendência P17, com recomendação registrada).
> - **A evidência de H3 vem do protótipo, com 5 repetições.** Na simulação
>   `t_atuacao` é o mesmo passo de `t_decisao` — não há atuação física a
>   cronometrar —, então o número de H3 só existe na bancada. Com **n = 5 o p95
>   não é estimável**: reportar mín/mediana/máx com o n declarado, e verificar os
>   200 ms sobre o máximo observado.
> - **A meta de H1 no cenário `intenso` não foi atingida no piloto** (18,1% contra
>   25%). A equipe decidiu **corrigir o mecanismo antes de mexer na hipótese**;
>   reformular H1 é contingência, e passa pelo orientador. Ver P16.

## 6. Requisitos funcionais (do pré-projeto)

| Código | Requisito | Critério de aceitação |
| --- | --- | --- |
| RF01 | Identificar veículos de emergência | Detectar VE em até 500 m do cruzamento |
| RF02 | Priorizar automaticamente a rota emergencial | Alterar semáforos em até 3 s a partir da detecção, medidos **da detecção até o início da atuação** (decisão P14) |
| RF03 | Liberar corredores prioritários | Garantir passagem contínua (VE não para em cruzamento priorizado) |
| RF04 | Exibir o estado dos semáforos | Atualização em tempo real no dashboard |
| RF05 | Registrar eventos no banco | Registro automático de logs de priorização |
| RF06 | Monitorar localização das viaturas | Visualização contínua no dashboard |
| RF07 | Recalcular a priorização | Ajuste dinâmico quando a rota do VE muda |

> **Decisão P14 (2026-08-25) — onde termina a medição do RF02.** O requisito
> original não dizia até que ponto contar os 3 s, e as duas leituras possíveis
> davam resultados opostos. Adotada a leitura **"até o início da atuação"**: o
> marco é o instante em que o semáforo visivelmente muda — o amarelo —, carimbado
> como `t_atuacao` na chegada do `ACK` do atuador.
>
> A alternativa, medir até o **verde final** na fase alvo, faria o RF02 absorver
> o **RF03** (garantir passagem contínua, que é justamente "o VE não para") e
> ainda embutir o verde mínimo no número. Verde mínimo é o invariante de
> segurança **I4**, não latência do sistema: sob essa leitura, um cruzamento que
> acabou de abrir o verde para a transversal seria classificado como "lento" por
> estar obedecendo a uma regra de segurança. Os dois requisitos medem coisas
> diferentes e continuam separados — RF02 mede *reação*, RF03 mede *resultado*.
>
> Esta leitura precisa aparecer **explicitamente** na definição do RF02 no texto
> do TCC. Deixá-la implícita é convidar a pergunta na arguição sem ter a resposta
> preparada.

## 7. Requisitos não funcionais

| Código | Categoria | Requisito |
| --- | --- | --- |
| RNF01 | Desempenho | Tempo de resposta da decisão < 100 ms |
| RNF02 | Disponibilidade | Operação contínua 24/7 |
| RNF03 | Escalabilidade | Suportar expansão da malha |
| RNF04 | Segurança | Comunicação criptografada |
| RNF05 | Confiabilidade | Precisão mínima de 95% na identificação do VE |
| RNF06 | Usabilidade | Dashboard intuitivo para operadores |
| RNF07 | Manutenibilidade | Código modular e documentado |

Como cada um vira teste executável: ver `06-testes-e-validacao.md`.

## 8. Escopo — o que **não** será feito

Registrar isso evita que o agente "melhore" o projeto para fora do prazo:

- ❌ Versão mobile do dashboard (decisão documentada no pré-projeto: operação em estação fixa).
- ❌ Treinamento de modelo de machine learning preditivo. **Decisão P3, 2026-08-24:** a "IA" deste TCC é um **agente reativo com otimização determinística baseada em conhecimento** — técnica clássica de IA, coberta por Russell & Norvig (já na bibliografia). Ver `01-arquitetura-sistema.md` §5. A palavra "IA" fica reservada à caracterização de agente; o restante do texto diz "algoritmo de decisão". Q-learning tabular para a política de compensação (E7) é **trabalho futuro explicitamente descrito**, não entrega deste TCC.
- ❌ Integração com sistemas reais da CET, SAMU ou Corpo de Bombeiros.
- ❌ Radar físico. **Decisão P7, 2026-08-24:** no protótipo, o RFID-RC522 **emula** a função do conjunto radar + V2I, e isso é declarado explicitamente no texto. A validação da fusão de sensores ocorre exclusivamente em ambiente simulado. Sem sensor adicional (HC-SR04 descartado — ampliaria escopo sem sustentar nenhuma das três hipóteses).
- ❌ Autenticação multi-tenant, gestão de usuários, RBAC completo. Um login simples basta.
- ❌ Alta disponibilidade real em AWS (multi-AZ, auto-scaling). A infra em nuvem é **descrita** como arquitetura-alvo e, se houver tempo, demonstrada em instância única.

## 9. Glossário

| Termo | Significado |
| --- | --- |
| **VE** | Veículo de emergência (ambulância, viatura policial, bombeiro) |
| **Preempção** | Interrupção do ciclo semafórico normal para conceder verde à aproximação do VE |
| **Fase** | Combinação de movimentos que recebem verde simultaneamente sem conflito |
| **Ciclo** | Sequência completa de fases de um cruzamento |
| **All-red** | Intervalo em que todos os acessos ficam vermelhos, para limpeza do cruzamento |
| **Min green** | Tempo mínimo que um verde deve permanecer antes de poder ser truncado |
| **V2I** | Vehicle-to-Infrastructure — comunicação do veículo com a infraestrutura viária |
| **TLS** | Traffic Light System — identificador de um cruzamento semaforizado no SUMO |
| **TraCI** | Traffic Control Interface — API de controle em tempo real do SUMO |
| **Baseline** | Cenário de controle: semáforos de temporização fixa, sem preempção |
| **Compensação** | Ajuste de ciclo após a passagem do VE para dissipar filas nas transversais |

## 10. Stakeholders

CET, SAMU, Corpo de Bombeiros, forças policiais, operadores de centros de monitoramento urbano, desenvolvedores/administradores do sistema. Eles definem os perfis de uso do dashboard, não são usuários reais deste TCC.
