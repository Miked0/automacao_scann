"""Validações do MVP (validadores).

Status possíveis por caso de teste:
  OK             - tudo validado dentro da tolerância
  ALERTA         - diferença dentro da tolerância (≤ 0,01)
  REVISAR        - caso especial que exige análise humana
  ERRO_PARSE     - falha ao parsear itens
  ERRO_VALOR     - subtotal/desconto/total com problema aritmético ou não-numérico
  ERRO_PAGAMENTO - forma de pagamento não mapeada
"""
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from processador_itens import parse_itens
from pagamentos import normalize_pagamento

TOLERANCIA = Decimal("0.01")
DECIMAL_PLACES = Decimal("0.01")

SPECIAL_KEYWORDS = [
    "acrescimo",
    "acréscimo",
    "nao aplicada",
    "não aplicada",
    "promoção nao",
    "promo nao",
    "cancelamento",
    "limite",
    "bin",
]


def _to_decimal(value: Any) -> Dict[str, Any]:
    """Converte valor para Decimal com tratamento de ruído floating point."""
    if value is None or str(value).strip() in ("", "nan", "None"):
        return {"raw": None, "norm": None, "error": True}
    try:
        raw = Decimal(str(value).replace(",", ".").strip())
        norm = raw.quantize(DECIMAL_PLACES)
        return {"raw": raw, "norm": norm, "error": False}
    except (InvalidOperation, ValueError):
        return {"raw": None, "norm": None, "error": True}


def _check_special_case(obs: Optional[str]) -> bool:
    """Verifica se a observação indica caso especial que precisa de revisão manual."""
    if not obs:
        return False
    obs_norm = obs.strip().lower()
    return any(kw in obs_norm for kw in SPECIAL_KEYWORDS)


def validate_test_case(test: Dict[str, Any]) -> Dict[str, Any]:
    """Valida um caso de teste e retorna dict com status e campos normalizados."""
    status = "OK"
    motivo: List[str] = []
    alertas: List[str] = []

    if not str(test.get("teste", "") or "").strip():
        status = "ERRO_VALOR"
        motivo.append("Teste sem identificador")

    itens = parse_itens(test.get("itens_raw"))
    itens_raw = test.get("itens_raw")
    if itens_raw and not itens:
        status = "ERRO_PARSE"
        motivo.append("Falha ao parsear itens")
    elif not itens_raw:
        alertas.append("Campo itens_raw vazio")

    pag = normalize_pagamento(test.get("pagamento_raw"))
    if pag["codigo_tipo_pago"] is None and not pag["is_multiplo"]:
        if pag["pagamento_normalizado"] is not None:
            if status == "OK":
                status = "ERRO_PAGAMENTO"
            motivo.append(f"Pagamento não mapeado: {pag['pagamento_normalizado']}")
        else:
            alertas.append("Pagamento ausente")

    sub = _to_decimal(test.get("subtotal_raw"))
    dsc = _to_decimal(test.get("desconto_raw"))
    tot = _to_decimal(test.get("total_raw"))

    if sub["error"]:
        status = "ERRO_VALOR"
        motivo.append("Subtotal não numérico")
    if dsc["error"]:
        if test.get("desconto_raw") not in (None, "", "nan", "None", "0", "0.0", "0,0"):
            status = "ERRO_VALOR"
            motivo.append("Desconto não numérico")
        else:
            dsc = {"raw": Decimal("0"), "norm": Decimal("0.00"), "error": False}
    if tot["error"]:
        status = "ERRO_VALOR"
        motivo.append("Total não numérico")

    if not any([sub["error"], dsc["error"], tot["error"]]):
        esperado = sub["norm"] - dsc["norm"]
        diff = (esperado - tot["norm"]).copy_abs()
        if diff > TOLERANCIA:
            if status == "OK":
                status = "ERRO_VALOR"
            motivo.append(
                f"Total não fecha: esperado={esperado}, informado={tot['norm']}, diferença={diff}"
            )
        elif diff > Decimal("0"):
            if status == "OK":
                status = "ALERTA"
            alertas.append(f"Diferença de R$ {diff} dentro da tolerância de 0,01")

    if _check_special_case(test.get("observacoes_raw")):
        if status == "OK":
            status = "REVISAR"
        alertas.append("Caso especial detectado na observação - requer análise humana")

    return {
        "status_final": status,
        "motivo_status": "; ".join(motivo) if motivo else None,
        "alertas": "; ".join(alertas) if alertas else None,
        "itens_parseados": str(itens) if itens else None,
        "codigo_tipo_pago": pag["codigo_tipo_pago"],
        "pagamento_normalizado": pag["pagamento_normalizado"],
        "is_multiplo": pag["is_multiplo"],
        "requires_bin": pag["requires_bin"],
        "subtotal_norm": str(sub["norm"]) if not sub["error"] else None,
        "desconto_norm": str(dsc["norm"]) if not dsc["error"] else None,
        "total_norm": str(tot["norm"]) if not tot["error"] else None,
    }
