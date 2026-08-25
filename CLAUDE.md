# CLAUDE.md — Instruções permanentes do projeto

Projeto: **Modelo Inteligente de Controle Dinâmico de Semáforos Baseado em Dados de Tráfego para Priorização de Veículos de Emergência em Ambientes Urbanos** (TCC — Ciência da Computação, UNIP, 2026).

## Antes de qualquer tarefa

Leia, nesta ordem, os arquivos em `context/`:

1. `context/00-visao-geral.md` — o que é o projeto, objetivos, hipóteses, escopo e o que está **fora** de escopo.
2. `context/01-arquitetura-sistema.md` — componentes, contratos e algoritmo de priorização.
3. O arquivo específico do domínio da tarefa (infra, banco, simulação, hardware, testes, resultados).
4. `context/09-pendencias-e-decisoes.md` — **sempre**. Contém as inconsistências ainda não resolvidas entre o texto do TCC e o sistema real. Nunca "resolva" sozinho uma pendência marcada como `DECISÃO DO GRUPO`; pergunte.

## Regras de ouro

- **Este é um trabalho acadêmico.** Todo número que aparecer no texto do TCC precisa ter sido produzido por código versionado neste repositório, a partir de execuções reais. Nunca gere, invente, arredonde "para ficar bonito" ou fixe (hardcode) resultados experimentais. Se um dado ainda não existe, o correto é escrever o script que o produz.
- **Segurança viária é invariante, não requisito negociável.** Nenhuma otimização pode violar as invariantes de `context/01-arquitetura-sistema.md` §6 (nunca dois verdes conflitantes; nunca verde → vermelho sem amarelo; sempre all-red entre fases).
- **Reprodutibilidade.** Toda execução de simulação recebe uma seed explícita e grava um registro em `execucao_simulacao`. Rodar duas vezes com a mesma seed e a mesma configuração deve dar o mesmo resultado.
- **Idioma:** código, identificadores e nomes de arquivo em português quando forem termos de domínio (`semaforo`, `veiculo_emergencia`, `priorizacao`); palavras-chave técnicas em inglês (`router`, `service`, `test`). Comentários, docstrings e documentação em português.
- **Escopo enxuto.** Este é um TCC com prazo, não um produto. Prefira sempre a solução mais simples que sustente a defesa. Antes de introduzir uma dependência nova, verifique se ela está listada em `context/02-arquitetura-infraestrutura.md`.

## Estrutura do repositório

```
/backend      API FastAPI + motor de decisão
/sim          Cenários SUMO + controlador TraCI
/firmware     Sketches Arduino UNO R3 e NodeMCU ESP8266
/bridge       Ponte serial (backend <-> Arduino UNO)
/frontend     Dashboard React
/db           Migrations (Alembic) e seeds
/analysis     Notebooks e scripts de estatística/gráficos
/docs         Artefatos entregáveis do TCC (relatórios, diagramas)
/context      Este pacote de contexto (fonte da verdade do escopo)
```

## Definition of Done (qualquer entrega)

- Código roda com `docker compose up` sem passo manual não documentado.
- Testes automatizados da parte alterada passam (`pytest` no backend, `vitest` no front).
- Se a entrega gera dado experimental, existe um CSV em `analysis/data/` e o script que o gerou.
- Se a entrega muda o comportamento do sistema, `context/` foi atualizado no mesmo commit.
