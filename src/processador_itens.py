"""Processador dos itens da venda (processador_itens).

Transforma o campo itens_raw em lista estruturada.

Formatos suportados:
  - '3 x 7891000010860'          → qtd=3, ean
  - '7891000010860'              → qtd=1, ean
  - '3.579 x PESABLE'            → qtd=3.579, pesavel
  - 'item1 + item2 + item3'      → vários itens
  - '3 x 789... + 1 x 789...'   → lista mista
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

# Padrão: <quantidade> x <codigo>  (quantidade pode ter ponto ou vírgula decimal)
ITEM_PATTERN = re.compile(
    r"^\s*(?P<qtd>[0-9]+(?:[.,][0-9]+)?)\s*x\s*(?P<codigo>.+)$",
    re.IGNORECASE,
)


def _detect_tipo(codigo: str) -> str:
    codigo_strip = codigo.strip()
    if "pesable" in codigo_strip.lower():
        return "pesavel"
    if re.fullmatch(r"[0-9]+", codigo_strip):
        return "ean"
    return "texto"


def _parse_qtd(qtd_str: str) -> float:
    return float(qtd_str.replace(",", "."))


def parse_itens(itens_raw: Any) -> List[Dict[str, Any]]:
    """Converte itens_raw em lista de dicts estruturados.

    Retorna lista vazia se o campo for nulo ou não reconhecido.
    """
    if itens_raw is None:
        return []
    raw_str = str(itens_raw).strip()
    if not raw_str or raw_str.lower() in ("nan", "none", ""):
        return []

    partes = [p.strip() for p in raw_str.split("+") if p.strip()]
    itens: List[Dict[str, Any]] = []

    for parte in partes:
        m = ITEM_PATTERN.match(parte)
        if m:
            qtd = _parse_qtd(m.group("qtd"))
            codigo = m.group("codigo").strip()
        else:
            qtd = 1.0
            codigo = parte.strip()

        tipo = _detect_tipo(codigo)
        itens.append(
            {
                "codigo": codigo,
                "quantidade": qtd,
                "tipo": tipo,
                "raw_parte": parte,
            }
        )

    return itens
