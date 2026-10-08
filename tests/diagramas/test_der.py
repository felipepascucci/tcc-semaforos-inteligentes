"""O DER versionado é o que os models geram (`db/der.py`, `context/08` §5)."""

from __future__ import annotations

from db.der import DESTINO, gerar


def test_der_versionado_esta_em_dia() -> None:
    """Mudou um model e não regerou o DER? Rode `python -m db.der`."""
    assert DESTINO.read_text(encoding="utf-8") == gerar()


def test_der_tem_as_tabelas_da_p20_e_do_bloco_6() -> None:
    texto = gerar()

    assert "entity ocorrencia {" in texto
    assert "entity pedido_simulacao {" in texto
    assert "ocorrencia ||--o{ deteccao : fk_ocorrencia" in texto
