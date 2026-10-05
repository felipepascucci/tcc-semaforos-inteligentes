"""Bancada como está montada: 2 fases no protótipo e as três placas

Migration **só de dados** (entrega 5.8, `context/03` §5, decisão de
2026-10-05). O schema não muda. Ela existe porque os seeds são idempotentes por
chave natural e nunca apagam nem sobrescrevem: num banco semeado antes desta
data, `PROTO_CRUZ_01` continuaria com as 4 fases de *split phasing* (P13, revista)
e o `LEITOR_CRUZ_01` continuaria cadastrado. Num banco novo ela não encontra
linha nenhuma, e os seeds, que rodam depois dela, criam o cadastro certo.

- `PROTO_CRUZ_01` passa a ciclo de 12 s, com as fases 1 (eixo principal, S1+S2)
  e 2 (eixo transversal, S3+S4). As fases 3 e 4 saem: nenhuma tabela as
  referencia por chave estrangeira.
- `LEITOR_CRUZ_01` sai. Era o NodeMCU que leria a tag do veículo no cruzamento
  e chamaria a API, e essa placa não existe na bancada. Se alguma `deteccao`
  apontar para ele, ele fica, marcado `INATIVO`, para não apagar histórico.
- Os novos dispositivos (`EMISSOR_VE_01`, `RECEPTOR_CRUZ_01`) vêm dos seeds.

Os valores estão escritos aqui, e não lidos de `db/seeds/dados.yaml`, de
propósito: uma migration é uma fotografia, e o YAML pode mudar depois.

Revision ID: 7b2e4d9a1c35
Revises: 3f9c2a71d5e8
Create Date: 2026-10-05 12:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7b2e4d9a1c35"
down_revision: str | None = "3f9c2a71d5e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DO_PROTOTIPO = (
    "fk_semaforo = (SELECT id_semaforo FROM semaforo WHERE codigo_externo = 'PROTO_CRUZ_01')"
)


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE semaforo SET tempo_ciclo = 12, "
            "descricao = 'Protótipo físico — cruzamento de 4 aproximações, ciclo de 2 fases', "
            "atualizado_em = now() "
            "WHERE codigo_externo = 'PROTO_CRUZ_01'"
        )
    )
    op.execute(sa.text(f"DELETE FROM fase_semaforo WHERE {_DO_PROTOTIPO} AND indice_fase > 2"))
    op.execute(
        sa.text(
            "UPDATE fase_semaforo SET descricao = 'Eixo principal (S1+S2)', "
            "movimentos = ARRAY['PRINCIPAL_A', 'PRINCIPAL_B'] "
            f"WHERE {_DO_PROTOTIPO} AND indice_fase = 1"
        )
    )
    op.execute(
        sa.text(
            "UPDATE fase_semaforo SET descricao = 'Eixo transversal (S3+S4)', "
            "movimentos = ARRAY['TRANSVERSAL_A', 'TRANSVERSAL_B'] "
            f"WHERE {_DO_PROTOTIPO} AND indice_fase = 2"
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM dispositivo_iot d WHERE d.codigo = 'LEITOR_CRUZ_01' "
            "AND NOT EXISTS (SELECT 1 FROM deteccao x WHERE x.fk_dispositivo = d.id_dispositivo)"
        )
    )
    op.execute(
        sa.text("UPDATE dispositivo_iot SET status = 'INATIVO' WHERE codigo = 'LEITOR_CRUZ_01'")
    )


def downgrade() -> None:
    # Não restaura: as fases 3 e 4 e o leitor do cruzamento descreviam uma
    # bancada que nunca existiu. O schema é o mesmo nos dois lados.
    pass
