from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, List, Tuple

from models import ParsedItem

ITEM_PATTERN = re.compile(r'^\s*(?P<qtd>[0-9]+(?:[\.,][0-9]+)?)\s*x\s*(?P<codigo>.+)$', re.IGNORECASE)
SPECIAL_KEYWORDS = ['pesable', 'acrescimo', 'acréscimo', 'desconto no subtotal', 'subtotal']


def _to_decimal(text: str) -> Decimal:
    return Decimal(text.replace(',', '.').strip())


def _classify_codigo(codigo: str) -> str:
    lower = codigo.lower().strip()
    if 'pesable' in lower:
        return 'pesavel'
    if codigo.strip().isdigit():
        return 'ean'
    if any(k in lower for k in SPECIAL_KEYWORDS):
        return 'contexto'
    return 'texto'


def parse_itens(itens_raw: Any) -> Tuple[List[ParsedItem], List[str]]:
    if itens_raw is None:
        return [], []
    raw_str = str(itens_raw).strip()
    if not raw_str:
        return [], []

    partes = [p.strip() for p in raw_str.split('+') if p.strip()]
    itens: List[ParsedItem] = []
    alertas: List[str] = []

    for parte in partes:
        m = ITEM_PATTERN.match(parte)
        try:
            if m:
                qtd = _to_decimal(m.group('qtd'))
                codigo = m.group('codigo').strip()
            else:
                qtd = Decimal('1')
                codigo = parte.strip()
        except (InvalidOperation, ValueError):
            alertas.append(f'Quantidade inválida no item: {parte}')
            continue

        tipo = _classify_codigo(codigo)
        if tipo == 'contexto':
            alertas.append(f'Item com contexto especial detectado: {parte}')

        itens.append(ParsedItem(
            codigo=codigo,
            quantidade=qtd,
            tipo=tipo,
            original=parte,
        ))

    return itens, alertas
