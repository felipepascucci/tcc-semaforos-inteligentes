"""Acesso a dados.

A divisão dos módulos segue o **perfil de escrita**, não o de entidade — porque
é o perfil de escrita que a regra crítica de `context/03` §4.1 governa:

* `fila_lote`   — caminho quente. `enfileirar()` nunca toca o banco; a gravação
  sai em lote (500 registros ou 5 s). É o que impede que um `INSERT` por passo
  contamine a medição de latência que sustenta RNF01 e H3.
* `operacao`    — fluxo de tempo real (detecção, log, latência). Volume baixo,
  precisa da chave gerada, portanto síncrono.
* `experimento` — abertura/fechamento de execução e métricas agregadas.
* `cadastro`    — leitura de semáforos, fases, veículos, tags e dispositivos.
"""

from app.repositories.fila_lote import (
    EstatisticasFila,
    FilaEmLote,
    PoliticaDeFlush,
    fila_de_gravacao,
)
from app.repositories.sessao import (
    criar_engine,
    criar_fabrica_sessao,
    sessao_de,
    url_do_banco,
)

__all__ = [
    "EstatisticasFila",
    "FilaEmLote",
    "PoliticaDeFlush",
    "criar_engine",
    "criar_fabrica_sessao",
    "fila_de_gravacao",
    "sessao_de",
    "url_do_banco",
]
