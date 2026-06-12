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
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from .processador_itens import processar_itens
from .pagamentos        import normalizar_pagamento

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


def _converter_para_decimal(valor: Any) -> Dict[str, Any]:
    if valor is None or str(valor).strip() in VALORES_NULOS:
        return {"valor": None, "normalizado": None, "erro": True}
    try:
        d = Decimal(str(valor).replace(",", ".").strip())
        return {"valor": d, "normalizado": d.quantize(DECIMAL_CASAS), "erro": False}
    except (InvalidOperation, ValueError):
        return {"valor": None, "normalizado": None, "erro": True}


def _eh_caso_especial(observacao: Optional[str]) -> bool:
    if not observacao:
        return False
    obs_norm = observacao.strip().lower()
    return any(p in obs_norm for p in PALAVRAS_CASO_ESPECIAL)


def _validar_identificador(
    caso: Dict[str, Any], status: str, motivos: List[str]
) -> str:
    if not str(caso.get("teste", "") or "").strip():
        motivos.append("Teste sem identificador")
        return STATUS_ERRO_VALOR
    return status


def _validar_itens(
    caso: Dict[str, Any], status: str, motivos: List[str], alertas: List[str]
) -> Tuple[str, Any]:
    itens_bruto = caso.get("itens_raw")
    itens       = processar_itens(itens_bruto)
    if itens_bruto and not itens:
        motivos.append("Falha ao processar itens")
        return STATUS_ERRO_PARSE, itens
    if not itens_bruto:
        alertas.append("Campo itens_raw vazio")
    return status, itens


def _validar_pagamento(
    caso: Dict[str, Any], status: str, motivos: List[str]
) -> Tuple[str, Dict[str, Any]]:
    pag = normalizar_pagamento(caso.get("pagamento_raw"))
    if pag["pagamento_normalizado"] is None:
        motivos.append("Pagamento não informado")
        return STATUS_ERRO_PAGAMENTO, pag
    if pag["codigo_tipo_pago"] is None and not pag["is_multiplo"]:
        motivos.append(f"Pagamento não mapeado: {caso.get('pagamento_raw')}")
        return STATUS_ERRO_PAGAMENTO, pag
    return status, pag


def _validar_valores_monetarios(
    caso: Dict[str, Any], status: str, motivos: List[str], alertas: List[str]
) -> Tuple[str, Dict[str, Any]]:
    subtotal_r = _converter_para_decimal(caso.get("subtotal_raw"))
    desconto_r = _converter_para_decimal(caso.get("desconto_raw"))
    total_r    = _converter_para_decimal(caso.get("total_raw"))

    if total_r["erro"]:
        motivos.append(f"Total inválido: {caso.get('total_raw')}")
        return STATUS_ERRO_VALOR, {}

    subtotal = subtotal_r["normalizado"]
    desconto = desconto_r["normalizado"] if not desconto_r["erro"] else Decimal("0")
    total    = total_r["normalizado"]

    tem_desconto = str(caso.get("desconto_raw", "")).strip() not in DESCONTO_NULO

    if subtotal is not None and tem_desconto:
        esperado = subtotal - desconto
        diff     = abs(esperado - total)
        if diff > TOLERANCIA:
            motivos.append(
                f"Aritmética inconsistente: subtotal({subtotal}) "
                f"- desconto({desconto}) = {esperado} ≠ total({total})"
            )
            return STATUS_ERRO_VALOR, {}
        if Decimal("0") < diff <= TOLERANCIA:
            alertas.append(f"Diferença de R$ {diff} dentro da tolerância")
            if status == STATUS_OK:
                status = STATUS_ALERTA

    return status, {
        "subtotal_norm": float(subtotal) if subtotal is not None else None,
        "desconto_norm": float(desconto),
        "total_norm":    float(total),
    }


def _montar_resultado(
    status: str,
    motivos: List[str],
    alertas: List[str],
    itens: Any,
    pag: Dict[str, Any],
    valores: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "status_final":          status,
        "motivo_status":         "; ".join(motivos) if motivos else "",
        "alertas":               "; ".join(alertas) if alertas else "",
        "itens_parseados":       itens,
        "pagamento_normalizado": pag.get("pagamento_normalizado"),
        "codigo_tipo_pago":      pag.get("codigo_tipo_pago"),
        "is_multiplo":           pag.get("is_multiplo", False),
        "requires_bin":          pag.get("requires_bin", False),
        "subtotal_norm":         valores.get("subtotal_norm"),
        "desconto_norm":         valores.get("desconto_norm"),
        "total_norm":            valores.get("total_norm"),
    }


def validar_caso_de_teste(caso: Dict[str, Any]) -> Dict[str, Any]:
    """Valida um caso de teste do roteiro e retorna dict com status e detalhes."""
    status  : str       = STATUS_OK
    motivos : List[str] = []
    alertas : List[str] = []

    obs = caso.get("observacoes_raw", "")
    if _eh_caso_especial(obs):
        return {
            "status_final": STATUS_REVISAR,
            "motivo_status": f"Caso especial: {obs}",
            "alertas":       "",
            "itens_parseados": [],
            "pagamento_normalizado": None,
            "codigo_tipo_pago": None,
            "is_multiplo": False,
            "requires_bin": False,
            "subtotal_norm": None,
            "desconto_norm": None,
            "total_norm":    None,
        }

    status = _validar_identificador(caso, status, motivos)
    if status != STATUS_OK:
        return _montar_resultado(status, motivos, alertas, [], {}, {})

    status, itens = _validar_itens(caso, status, motivos, alertas)
    if status == STATUS_ERRO_PARSE:
        return _montar_resultado(status, motivos, alertas, itens, {}, {})

    status, pag = _validar_pagamento(caso, status, motivos)
    if status == STATUS_ERRO_PAGAMENTO:
        return _montar_resultado(status, motivos, alertas, itens, pag, {})

    status, valores = _validar_valores_monetarios(caso, status, motivos, alertas)
    return _montar_resultado(status, motivos, alertas, itens, pag, valores)
