from __future__ import annotations

import re
import unicodedata
from typing import Any

from models import PaymentInfo

NORMALIZACAO_PAGAMENTO = {
    'dinheiro': 9,
    'efetivo': 9,
    'cash': 9,
    'credito': 10,
    'credito a vista': 10,
    'cartao credito': 10,
    'cartao de credito': 10,
    'debito': 13,
    'cartao debito': 13,
    'cartao de debito': 13,
    'pix': 14,
    'qr': 14,
    'qr code': 14,
}
MULTIPLO_MARKERS = [' + ', ' e ', ' y ', 'dos veces', 'tercero', 'terceiro', 'multipl', 'duas vezes']


def _clean_text(value: str) -> str:
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'\s+', ' ', value.strip().lower())
    return value


def normalize_pagamento(pagamento_raw: Any) -> PaymentInfo:
    if pagamento_raw is None:
        return PaymentInfo(None, None, False, False, None)

    original = str(pagamento_raw).strip()
    if not original:
        return PaymentInfo(None, None, False, False, original)

    texto = _clean_text(original)
    if any(marker in texto for marker in MULTIPLO_MARKERS):
        return PaymentInfo('MULTIPLO', None, True, False, original)

    codigo_tipo = None
    pagamento_normalizado = texto
    for chave, codigo in NORMALIZACAO_PAGAMENTO.items():
        if chave in texto:
            codigo_tipo = codigo
            pagamento_normalizado = chave
            break

    requires_bin = codigo_tipo == 10 or 'bin' in texto
    return PaymentInfo(pagamento_normalizado, codigo_tipo, False, requires_bin, original)
