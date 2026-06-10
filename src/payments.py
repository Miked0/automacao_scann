"""Normalização de formas de pagamento.

Mapeia textos livres da planilha para codigoTipoPago da API:
  9  = Efetivo (Dinheiro)
  10 = Crédito
  11 = Cheque
  12 = Vale
  13 = Débito
  14 = QR / PIX
  15 = Finalizadora

Para cenários múltiplos, marca is_multiplo=True e não resolve no MVP.
"""
from typing import Any, Dict, Optional

# Ordem importa: mais específico primeiro
NORMALIZACAO: Dict[str, int] = {
    "cartao credito": 10,
    "cartão credito": 10,
    "cartao de credito": 10,
    "cartão de credito": 10,
    "cartao crédito": 10,
    "credito": 10,
    "crédito": 10,
    "cartao debito": 13,
    "cartão debito": 13,
    "cartao de debito": 13,
    "cartão de débito": 13,
    "debito": 13,
    "débito": 13,
    "pix": 14,
    "qr": 14,
    "cheque": 11,
    "vale": 12,
    "dinheiro": 9,
    "efetivo": 9,
    "dinero": 9,
    "cash": 9,
}

# Indicadores de múltiplos meios de pagamento
MULTIPLO_PATTERNS = ["+", " e ", " y ", "veces", "tercero", "duas", "dois", "tres", "tres vezes"]


def _normalize_text(text: str) -> str:
    import unicodedata
    s = text.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s


def normalize_pagamento(pagamento_raw: Any) -> Dict[str, Any]:
    """Normaliza forma de pagamento e retorna dict com campos enriquecidos."""
    if pagamento_raw is None or str(pagamento_raw).strip() in ("", "nan", "None"):
        return {
            "pagamento_normalizado": None,
            "codigo_tipo_pago": None,
            "is_multiplo": False,
            "requires_bin": False,
        }

    texto = _normalize_text(str(pagamento_raw))

    # Detecta múltiplos meios
    if any(p in texto for p in MULTIPLO_PATTERNS):
        return {
            "pagamento_normalizado": "MULTIPLO",
            "codigo_tipo_pago": None,
            "is_multiplo": True,
            "requires_bin": False,
        }

    # Busca mapeamento
    codigo_tipo: Optional[int] = None
    for chave, codigo in NORMALIZACAO.items():
        if chave in texto:
            codigo_tipo = codigo
            break

    requires_bin = any(k in texto for k in ("credito", "crédito", "cartao", "cartão"))

    return {
        "pagamento_normalizado": texto,
        "codigo_tipo_pago": codigo_tipo,
        "is_multiplo": False,
        "requires_bin": requires_bin,
    }
