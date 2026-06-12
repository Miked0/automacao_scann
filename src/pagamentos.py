"""
Normalização de formas de pagamento.

Mapeia texto livre da planilha para codigoTipoPago da API Scanntech.
Cenários com múltiplos meios são sinalizados mas não resolvidos no MVP.
"""
from typing import Any, Dict, Optional

# Mapeamento texto normalizado → codigoTipoPago
# Ordem importa: termos mais específicos antes dos genéricos.
MAPEAMENTO_PAGAMENTO: Dict[str, int] = {
    "cartao credito":    10,
    "cartão credito":    10,
    "cartao de credito": 10,
    "cartão de credito": 10,
    "cartao crédito":    10,
    "credito":           10,
    "crédito":           10,
    "cartao debito":     13,
    "cartão debito":     13,
    "cartao de debito":  13,
    "cartão de débito":  13,
    "debito":            13,
    "débito":            13,
    "pix":               14,
    "qr":                14,
    "cheque":            11,
    "vale":              12,
    "dinheiro":           9,
    "efetivo":            9,
    "dinero":             9,
    "cash":               9,
}

INDICADORES_MULTIPLOS = ["+", " e ", " y ", "veces", "tercero",
                         "duas", "dois", "tres", "tres vezes"]

TERMOS_CREDITO = ("credito", "crédito", "cartao", "cartão")

VALORES_NULOS = ("", "nan", "none")


def _remover_acentos(texto: str) -> str:
    import unicodedata
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(char for char in normalizado if not unicodedata.combining(char))


def _normalizar_texto(texto: str) -> str:
    return _remover_acentos(texto.strip().lower())


def _eh_valor_nulo(texto: str) -> bool:
    return texto.lower() in VALORES_NULOS


def _detectar_multiplos(texto: str) -> bool:
    return any(indicador in texto for indicador in INDICADORES_MULTIPLOS)


def _buscar_codigo_tipo(texto: str) -> Optional[int]:
    for chave, codigo in MAPEAMENTO_PAGAMENTO.items():
        if chave in texto:
            return codigo
    return None


def _requer_bin(texto: str) -> bool:
    """Crédito e cartão exigem validação de BIN nos checks subsequentes."""
    return any(termo in texto for termo in TERMOS_CREDITO)


def normalizar_pagamento(pagamento_bruto: Any) -> Dict[str, Any]:
    """Normaliza a forma de pagamento e devolve campos enriquecidos."""
    RESULTADO_NULO = {
        "pagamento_normalizado": None,
        "codigo_tipo_pago": None,
        "is_multiplo": False,
        "requires_bin": False,
    }

    if pagamento_bruto is None:
        return RESULTADO_NULO

    texto = _normalizar_texto(str(pagamento_bruto))

    if _eh_valor_nulo(texto):
        return RESULTADO_NULO

    if _detectar_multiplos(texto):
        return {
            "pagamento_normalizado": "MULTIPLO",
            "codigo_tipo_pago": None,
            "is_multiplo": True,
            "requires_bin": False,
        }

    return {
        "pagamento_normalizado": texto,
        "codigo_tipo_pago": _buscar_codigo_tipo(texto),
        "is_multiplo": False,
        "requires_bin": _requer_bin(texto),
    }
