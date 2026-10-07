# 08 — Roadmap e Convenções

## 1. Sprints do pré-projeto → entregas de código

O pré-projeto define 8 sprints. Abaixo, o que cada uma significa em termos de artefato executável. A ordem foi ajustada em um ponto: **o banco (Sprint 5) sobe antes**, porque a simulação já precisa persistir métricas desde a Sprint 2. Registrar essa alteração no texto.

| Sprint | Objetivo (pré-projeto) | Entrega de código | Pronto quando |
| --- | --- | --- | --- |
| 1 | Modelagem da malha urbana | `sim/rede/*.xml` + `malha.net.xml` gerada; detectores; 3 arquivos de demanda | `sumo-gui` roda 60 min sem colisão nem teleporte |
| 2 | Integração SUMO + Python | `sim/controlador/adaptador_traci.py`, `executor.py`; esqueleto de `core/modelos.py` | `python -m sim.controlador.executor --cenario leve --modo FIXO --seed 1` produz `tripinfo.xml` |
| 3 | Lógica de priorização | `core/priorizacao/` completo (E1–E8) + `core/seguranca.py` + testes unitários | Testes de I1–I5 passam; corredor verde visível na GUI |
| 4 | Camada IoT | Firmware UNO reescrito com transição segura e decisão local; sketches dos NodeMCUs versionados como estão; `bridge/` que escuta o UNO e mede H3 (`05`, 2026-10-05) | Tag aproxima → semáforo físico preempta em < 3 s |
| 5 | Banco de dados | Migrations Alembic, models, repositories, seeds | Execução de simulação grava `execucao_simulacao` + `log_prioridade` |
| 6 | Dashboard | React + mapa + WebSocket + telas de log e métricas | Estado dos semáforos e VEs em tempo real |
| 7 | Testes integrados | Suite E2E, `sim/controlador/lote.py`, validador de execução | Lote de 600 execuções roda sem intervenção manual |
| 8 | Validação e análise | `analysis/` completo, tabelas e figuras | `gerar_resultados_tcc.py` produz o capítulo 5 inteiro |

**Ordem de implementação recomendada para o agente**, quando houver liberdade de escolha: 5 → 2 → 3 → 1 → 7 → 4 → 6 → 8. Motivo: banco e núcleo de decisão são pré-requisito de tudo; o dashboard é o item mais visível mas o menos crítico para a validação científica, e é onde mais se perde tempo com detalhe visual.

## 2. Escopo

O escopo declarado em `00-visao-geral.md` é entregue **por inteiro**: motor de decisão, invariantes de segurança, matriz de execuções, análise estatística, protótipo físico, API, dashboard (incluindo o painel "Central" de P20), compensação E7 e o modelo de P19. Decisão da equipe, 2026-10-01.

## 3. Convenções de código

### Python

- Formatação: `ruff format` (linha 100). Lint: `ruff check`. Tipos: `mypy --strict` em `core/`.
- Type hints obrigatórios em todas as funções públicas.
- Docstrings em português, formato Google, com **unidade explícita** em toda grandeza física:

```python
def calcular_eta(distancia_m: float, velocidade_ms: float) -> float:
    """Estima o tempo até o cruzamento.

    Args:
        distancia_m: Distância ao longo da rota, em metros.
        velocidade_ms: Velocidade atual do veículo, em m/s.

    Returns:
        Tempo estimado de chegada, em segundos.
    """
```

Unidade no nome do parâmetro (`_m`, `_ms`, `_s`) evita a classe de bug mais cara deste projeto: confundir km/h com m/s, ou segundos com milissegundos. O SUMO trabalha em m/s; o texto do TCC fala em km/h. A conversão precisa acontecer numa fronteira única e explícita.

- `dataclass(frozen=True)` para todo objeto de estado. Estado imutável elimina uma classe inteira de bug de concorrência entre o loop de simulação e o broadcast do WebSocket.
- Exceções de domínio próprias em `core/excecoes.py` (`PreempcaoInvalidaError`, `FaseInexistenteError`, `InvarianteVioladoError`).

### Nomenclatura

| Contexto | Convenção | Exemplo |
| --- | --- | --- |
| Módulos e funções Python | `snake_case`, português para domínio | `calcular_compensacao()` |
| Classes | `PascalCase` | `MotorDecisao` |
| Constantes | `UPPER_SNAKE` | `RAIO_DETECCAO_M` |
| Tabelas e colunas SQL | `snake_case` singular | `log_prioridade` |
| Endpoints REST | plural, kebab quando composto | `/api/v1/veiculos`, `/api/v1/logs/prioridade` |
| Componentes React | `PascalCase` | `PainelSemaforos.tsx` |
| Branches | `feat/sprint3-motor-decisao` | — |

### Commits

Conventional Commits em português:

```
feat(core): implementa compensação de ciclo pós-evento
fix(bridge): corrige parsing de telemetria com fase inválida
test(core): adiciona property-based test para invariante I1
docs(context): atualiza pendência P3 após decisão do orientador
```

## 4. Regras específicas para o agente de código

1. **Antes de implementar, verifique `09-pendencias-e-decisoes.md`.** Se o que você vai fazer depende de uma pendência aberta, pergunte em vez de escolher.
2. **Nunca gere dados sintéticos que pareçam resultados experimentais.** Se precisar de dados para testar, use fixtures obviamente artificiais (valores redondos, nomes como `SEMAFORO_TESTE`) e mantenha-as em `tests/`.
3. **Toda constante numérica de comportamento vai para `parametros.yaml`.** Se você digitou um número no meio de uma função de decisão, ele está no lugar errado.
4. **Ao alterar o algoritmo de decisão, rode a suite de invariantes antes de considerar concluído.**
5. **Ao criar um endpoint, crie o schema Pydantic e o teste no mesmo commit.**
6. **Ao mexer no firmware, verifique se não introduziu `delay()` no loop nem `String` no ATmega.**
7. **Ao terminar uma tarefa que muda arquitetura, comportamento ou escopo, atualize o arquivo correspondente em `context/` no mesmo commit.** Contexto desatualizado é pior que contexto ausente, porque induz ao erro com confiança.
8. **Não instale dependência fora da lista de `02-arquitetura-infraestrutura.md` §2** sem registrar a decisão.
9. **Não proponha redução de escopo** (ver §2). Atraso se resolve no planejamento, não tirando entregas.

## 5. Artefatos acadêmicos a produzir

Além do código, o TCC exige (pré-projeto §2.7):

| Artefato | Ferramenta | Destino |
| --- | --- | --- |
| Diagrama de Casos de Uso | draw.io / PlantUML | `docs/diagramas/casos_uso.puml` |
| Diagrama de Componentes | PlantUML | `docs/diagramas/componentes.puml` |
| Diagrama de Sequência (fluxo de preempção) | PlantUML | `docs/diagramas/sequencia_preempcao.puml` |
| DER | eralchemy2, a partir do banco | `docs/diagramas/der.pdf` |
| Diagrama de Infraestrutura | draw.io | `docs/diagramas/infraestrutura.png` |
| Máquina de estados do semáforo | PlantUML | `docs/diagramas/maquina_estados.puml` |
| Especificação de casos de teste | Markdown | `docs/casos_de_teste.md` |
| Relatório de validação | Gerado | `docs/relatorios/` |
| Esquema elétrico do protótipo | Fritzing | `docs/hardware/esquema.fzz` |

Preferir PlantUML a diagrama desenhado à mão: fica versionado, regenerável e consistente com o código. Um diagrama que diverge do sistema é passivo, não ativo.

> **P20 (2026-09-29) — o que os diagramas precisam mostrar quando forem feitos.**
> Casos de uso: o ator **Central de despacho** (simulada), com "abrir ocorrência"
> e "encerrar ocorrência". Sequência de preempção: a consulta da ocorrência ativa
> **entre** a resolução da tag e o motor, com o ramo "sem ocorrência → sem
> preempção". DER: a tabela `ocorrencia`.

## 6. Riscos do projeto

| Risco | Impacto | Mitigação |
| --- | --- | --- |
| Resultados reais não confirmam H1 (≥30%) | Alto | Rodar experimento piloto **cedo** (Sprint 3), com 5 seeds, para conhecer a ordem de grandeza antes de comprometer o texto |
| Protótipo trava durante a apresentação | Alto | Teste de 30 min obrigatório (feito em 2026-10-07: 33 min sem reinício, `06` §6 item 12); sem `String`; emergência que termina sozinha e teto de 30 s (I6); roteiro ensaiado (`bridge/demo.py`, 19 de 19) com plano B `--sem-carrinho`; ter vídeo gravado de backup (**ainda não gravado**) |
| 600 execuções não cabem no prazo | Médio | `traci` com 6 processos em paralelo: medido no piloto, as 600 levam ~6 h (P15). O braço `PREEMPCAO_ML` (10.7) acrescenta execuções nos cenários com múltiplos VEs |
| ~~Rede da faculdade bloqueia o ESP8266~~ | — | **Não se aplica desde 2026-10-05:** o protótipo não usa rede; os NodeMCUs falam por ESP-NOW, MAC a MAC (`05`). Resta a interferência em 2,4 GHz: testar no local antes |
| Divergência entre texto do TCC e sistema | Médio | Regra do §4.7: `context/` atualizado no mesmo commit |
| Escopo cresce além do declarado | Alto | Lista de não-escopo em `00-visao-geral.md` §8 é vinculante |

O primeiro risco é o mais subestimado. Rodar o piloto cedo custa um dia e evita descobrir na última semana que o texto inteiro precisa ser reescrito.
