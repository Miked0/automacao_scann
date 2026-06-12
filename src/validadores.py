"""
Validações do MVP.

Status possíveis por caso de teste:
  OK             — tudo validado dentro da tolerância
  ALERTA         — diferença ≤ 0,01 (dentro da tolerância aceitável)
  REVISAR        — caso especial que exige análise humana
  ERRO_PARSE     — falha ao processar itens
  ERRO_VALOR     — subtotal/desconto/total aritmeticamente inconsistente
  ERRO_PAGAMENTO — forma de pagamento não mapeada
"""
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from processador_itens import processar_itens
from pagamentos import normalizar_pagamento

# --- Constantes -----------------------------------------------------------

STATUS_OK             = "OK"
STATUS_ALERTA         = "ALERTA"
STATUS_REVISAR        = "REVISAR"
STATUS_ERRO_PARSE     = "ERRO_PARSE"
STATUS_ERRO_VALOR     = "ERRO_VALOR"
STATUS_ERRO_PAGAMENTO = "ERRO_PAGAMENTO"

TOLERANCIA    = Decimal("0.01")
DECIMAL_CASAS = Decimal("0.01")

DESCONTO_NULO = {None, "", "nan", "None", "0", "0.0", "0,0"}

PALAVRAS_CASO_ESPECIAL = [
    "acrescimo", "acréscimo",
    "nao aplicada", "não aplicada",
    "promoção nao", "promo nao",
    "cancelamento", "limite", "bin",
]

VALORES_NULOS = ("", "nan", "None")

# --------------------------------------------------------------------------


def _converter_para_decimal(valor: Any) -> Dict[str, Any]:
    """
    Converte valor bruto em Decimal.

    Usamos Decimal para evitar ruído de ponto flutuante em comparações monetárias.
    """
    if valor is None or str(valor).strip() in VALORES_NULOS:
        return {"valor": None, "normalizado": None, "erro": True}
    try:
        valor_decimal = Decimal(str(valor).replace(",", ".").strip())
        return {
            "valor": valor_decimal,
            "normalizado": valor_decimal.quantize(DECIMAL_CASAS),
            "erro": False,
        }
    except (InvalidOperation, ValueError):
        return {"valor": None, "normalizado": None, "erro": True}


def _eh_caso_especial(observacao: Optional[str]) -> bool:
    """Detecta se a observação indica cenário que exige revisão manual."""
    if not observacao:
        return False
    observacao_normalizada = observacao.strip().lower()
    return any(palavra in observacao_normalizada for palavra in PALAVRAS_CASO_ESPECIAL)


def _validar_identificador(
    caso: Dict[str, Any],
    status: str,
    motivos: List[str],
) -> str:
    identificador = str(caso.get("teste", "") or "").strip()
    if not identificador:
        motivos.append("Teste sem identificador")
        return STATUS_ERRO_VALOR
    return status


def _validar_itens(
    caso: Dict[str, Any],
    status: str,
    motivos: List[str],
    alertas: List[str],
) -> Tuple[str, Any]:
    itens_bruto = caso.get("itens_raw")
    itens = processar_itens(itens_bruto)
    if itens_bruto and not itens:
        motivos.append("Falha ao processar itens")
        return STATUS_ERRO_PARSE, itens
    if not itens_bruto:
        alertas.append("Campo itens_raw vazio")
    return status, itens


def _validar_pagamento(
    caso: Dict[str, Any],
    status: str,
    motivos: List[str],
    alertas: List[str],
) -> Tuple[str, Dict]:
    pagamento = normalizar_pagamento(caso.get("pagamento_raw"))
    codigo_ausente = pagamento["codigo_tipo_pago"] is None
    nao_multiplo   = not pagamento["is_multiplo"]

    if codigo_ausente and nao_multiplo:
        if pagamento["pagamento_normalizado"] is not None:
            motivos.append(f"Pagamento não mapeado: {pagamento['pagamento_normalizado']}")
            if status == STATUS_OK:
                status = STATUS_ERRO_PAGAMENTO
        else:
            alertas.append("Pagamento ausente")

    return status, pagamento


def _validar_desconto(desconto_bruto: Any) -> Dict[str, Any]:
    """Desconto vazio ou zero é válido — assumimos R$ 0,00."""
    resultado = _converter_para_decimal(desconto_bruto)
    if resultado["erro"] and desconto_bruto in DESCONTO_NULO:
        return {"valor": Decimal("0"), "normalizado": Decimal("0.00"), "erro": False}
    return resultado


def _validar_valores_monetarios(
    caso: Dict[str, Any],
    status: str,
    motivos: List[str],
    alertas: List[str],
) -> Tuple[str, Dict, Dict, Dict]:
    subtotal = _converter_para_decimal(caso.get("subtotal_raw"))
    desconto = _validar_desconto(caso.get("desconto_raw"))
    total    = _converter_para_decimal(caso.get("total_raw"))

    if subtotal["erro"]:
        motivos.append("Subtotal não numérico")
        status = STATUS_ERRO_VALOR
    if desconto["erro"]:
        motivos.append("Desconto não numérico")
        status = STATUS_ERRO_VALOR
    if total["erro"]:
        motivos.append("Total não numérico")
        status = STATUS_ERRO_VALOR

    algum_erro = subtotal["erro"] or desconto["erro"] or total["erro"]
    if not algum_erro:
        total_esperado = subtotal["normalizado"] - desconto["normalizado"]
        diferenca = (total_esperado - total["normalizado"]).copy_abs()

        if diferenca > TOLERANCIA:
            motivos.append(
                f"Total não fecha: esperado={total_esperado}, "
                f"informado={total['normalizado']}, diferença={diferenca}"
            )
            if status == STATUS_OK:
                status = STATUS_ERRO_VALOR
        elif diferenca > Decimal("0"):
            alertas.append(f"Diferença de R$ {diferenca} dentro da tolerância de 0,01")
            if status == STATUS_OK:
                status = STATUS_ALERTA

    return status, subtotal, desconto, total


def validar_caso_de_teste(caso: Dict[str, Any]) -> Dict[str, Any]:
    """Valida um caso de teste e devolve dict com status e campos normalizados."""
    status:  str       = STATUS_OK
    motivos: List[str] = []
    alertas: List[str] = []

    status                = _validar_identificador(caso, status, motivos)
    status, itens         = _validar_itens(caso, status, motivos, alertas)
    status, pagamento     = _validar_pagamento(caso, status, motivos, alertas)
    status, subtotal, desconto, total = _validar_valores_monetarios(
        caso, status, motivos, alertas
    )

    if _eh_caso_especial(caso.get("observacoes_raw")):
        alertas.append("Caso especial detectado na observação — requer análise humana")
        if status == STATUS_OK:
            status = STATUS_REVISAR

    return {
        "status_final":          status,
        "motivo_status":         "; ".join(motivos) if motivos else None,
        "alertas":               "; ".join(alertas) if alertas else None,
        "itens_parseados":       str(itens) if itens else None,
        "codigo_tipo_pago":      pagamento["codigo_tipo_pago"],
        "pagamento_normalizado": pagamento["pagamento_normalizado"],
        "is_multiplo":           pagamento["is_multiplo"],
        "requires_bin":          pagamento["requires_bin"],
        "subtotal_norm":         str(subtotal["normalizado"]) if not subtotal["erro"] else None,
        "desconto_norm":         str(desconto["normalizado"]) if not desconto["erro"] else None,
        "total_norm":            str(total["normalizado"])    if not total["erro"]    else None,
    }


# Alias de compatibilidade — mantido enquanto main.py ainda referencia validate_test_case
validate_test_case = validar_caso_de_teste
