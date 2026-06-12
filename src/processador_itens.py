"""
Processamento dos itens da venda.

Transforma o campo itens_bruto em lista estruturada de dicts.

Formatos suportados:
  '3 x 7891000010860'     → quantidade=3, tipo=ean
  '7891000010860'         → quantidade=1, tipo=ean
  '3.579 x PESAVEL'       → quantidade=3.579, tipo=pesavel
  'item1 + item2 + item3' → múltiplos itens
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

PADRAO_ITEM = re.compile(
    r"^\s*(?P<quantidade>[0-9]+(?:[.,][0-9]+)?)\s*x\s*(?P<codigo>.+)$",
    re.IGNORECASE,
)

SEPARADOR_ITENS   = "+"
QUANTIDADE_PADRAO = 1.0
VALORES_NULOS     = ("nan", "none", "")


def _detectar_tipo(codigo: str) -> str:
    codigo_limpo = codigo.strip()
    if "pesable" in codigo_limpo.lower() or "pesavel" in codigo_limpo.lower():
        return "pesavel"
    if re.fullmatch(r"[0-9]+", codigo_limpo):
        return "ean"
    return "texto"


def _converter_quantidade(quantidade_str: str) -> float:
    return float(quantidade_str.replace(",", "."))


def _parse_parte(parte: str) -> Dict[str, Any]:
    correspondencia = PADRAO_ITEM.match(parte)
    if correspondencia:
        quantidade = _converter_quantidade(correspondencia.group("quantidade"))
        codigo = correspondencia.group("codigo").strip()
    else:
        quantidade = QUANTIDADE_PADRAO
        codigo = parte.strip()

    return {
        "codigo": codigo,
        "quantidade": quantidade,
        "tipo": _detectar_tipo(codigo),
        "valor_original": parte,
    }


def processar_itens(itens_bruto: Any) -> List[Dict[str, Any]]:
    """Converte itens_bruto em lista de dicts estruturados."""
    if itens_bruto is None:
        return []
    texto = str(itens_bruto).strip()
    if texto.lower() in VALORES_NULOS:
        return []
    partes = [p.strip() for p in texto.split(SEPARADOR_ITENS) if p.strip()]
    return [_parse_parte(p) for p in partes]


# Alias de compatibilidade
parse_itens = processar_itens
