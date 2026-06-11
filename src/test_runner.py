"""
Módulo 5 — TestRunner
Responsabilidade: Orquestra a validação linha a linha do roteiro.

Fix v2:
  - Busca flexível do número do cupom: tenta múltiplos nomes de coluna
    (numero_cupom, n° cupom, cupom, numero, nº cupom, sat, ecf, nfce, coo)
    para ser resistente a variações de layout do TEMPLATE.
  - Busca flexível de EANs: aceita colunas ean, eans, codigo_barras, cod_barra.
  - Busca flexível de total, desconto, meio_pagamento, observacao.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from .audit_parser import AuditParser
from .coupon_pdf_parser import CouponPDFParser, Coupon
from .promo_engine import PromoEngine

logger = logging.getLogger(__name__)

TOLERANCE = 0.05

# Aliases aceitos para cada campo do roteiro
_ALIAS_NUMERO = [
    "numero_cupom", "n° cupom", "nº cupom", "cupom", "numero",
    "sat", "ecf", "nfce", "coo", "n cupom", "num cupom",
    "número cupom", "n.cupom", "num.cupom",
]
_ALIAS_EANS   = ["ean", "eans", "codigo_barras", "cod_barra", "codigo barras", "ean/upc"]
_ALIAS_TOTAL  = ["total", "valor total", "vl total", "vl. total", "total venda"]
_ALIAS_DESC   = ["desconto", "desc", "desconto total", "vl desconto", "descuento"]
_ALIAS_PAGO   = ["meio_pagamento", "meio pagamento", "pagamento", "forma pagamento",
                 "forma de pagamento", "tipo pagamento", "meio pag"]
_ALIAS_OBS    = ["observacao", "observação", "obs", "observacoes", "observações",
                 "detalhes", "nota"]
_ALIAS_ETAPA  = ["etapa", "fase", "step", "cenário", "cenario", "teste"]


def _get(row: dict, aliases: list, default=None):
    """Busca o primeiro alias que existir no dicionário row (case-insensitive)."""
    row_lower = {str(k).strip().lower(): v for k, v in row.items()}
    for alias in aliases:
        val = row_lower.get(alias.lower())
        if val is not None:
            return val
    return default


@dataclass
class CheckResult:
    check: str
    ok: bool
    detalhe: str = ""


@dataclass
class TestResult:
    etapa: str
    linha: int
    cupom_numero: Optional[str]
    checks: list = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def motivo_erro(self) -> str:
        for c in self.checks:
            if not c.ok:
                return c.detalhe[:100]
        return ""


class TestRunner:
    """Executa os 10 checks em sequência para cada linha do roteiro."""

    def __init__(
        self,
        audit: AuditParser,
        pdf: CouponPDFParser,
        promo: PromoEngine,
    ):
        self.audit = audit
        self.pdf   = pdf
        self.promo = promo

    def run(self, row: dict, linha: int) -> TestResult:
        etapa  = str(_get(row, _ALIAS_ETAPA, "") or "")
        result = TestResult(etapa=etapa, linha=linha, cupom_numero=None)

        # --- Check 1: Cupom localizado ---
        # Aceita múltiplos aliases para o número do cupom
        numero_raw = _get(row, _ALIAS_NUMERO, "")
        numero     = str(numero_raw).strip() if numero_raw is not None else ""
        # Remove None/nan textual
        if numero.lower() in ("none", "nan", ""):
            numero = ""

        # EANs: suporta string separada por vírgula ou valor único
        eans_raw = _get(row, _ALIAS_EANS, "")
        if isinstance(eans_raw, str):
            eans = [e.strip() for e in eans_raw.split(",") if e.strip()]
        elif eans_raw is not None:
            eans = [str(eans_raw).strip()]
        else:
            eans = []

        coupon: Optional[Coupon] = None
        movements: list = []

        if numero:
            coupon    = self.pdf.get_by_numero(numero)
            movements = self.audit.get_by_numero(numero)
            logger.debug("Buscando cupom '%s': pdf=%s audit=%d",
                         numero, coupon is not None, len(movements))

        if not coupon and eans:
            coupon = self.pdf.get_by_eans(eans)
            logger.debug("Fallback EAN %s: pdf=%s", eans, coupon is not None)

        if not movements and eans:
            movements = self.audit.get_by_eans(eans)
            logger.debug("Fallback EAN %s: audit=%d", eans, len(movements))

        found = coupon is not None or len(movements) > 0
        result.cupom_numero = (
            coupon.get_numero() if coupon
            else (movements[0].get("numero") if movements else None)
        )
        result.checks.append(CheckResult(
            "cupom_localizado", found,
            "" if found else f"Cupom não localizado: '{numero}' (EANs={eans})"
        ))
        if not found:
            return result  # falha rápida

        mov = movements[0] if movements else {}

        # --- Check 2: HTTP 200 ---
        status  = int(mov.get("status", mov.get("httpStatus", 0)))
        ok_http = status == 200
        result.checks.append(CheckResult(
            "http_200", ok_http,
            "" if ok_http else f"Status HTTP: {status}"
        ))

        # --- Check 3: Cancelamento ---
        obs               = str(_get(row, _ALIAS_OBS, "") or "").lower()
        cancelado_esperado= "cancelado" in obs or "cancelacion" in obs
        cancelado_real    = bool(mov.get("cancelacion", False))
        ok_cancel         = cancelado_esperado == cancelado_real
        result.checks.append(CheckResult(
            "cancelamento", ok_cancel,
            "" if ok_cancel else (
                f"Cancelamento esperado={cancelado_esperado} real={cancelado_real}"
            )
        ))

        # --- Check 4: Total ---
        total_rot = float(_get(row, _ALIAS_TOTAL, 0) or 0)
        total_mov = float(mov.get("total", 0))
        ok_total  = abs(total_rot - total_mov) <= TOLERANCE
        result.checks.append(CheckResult(
            "total", ok_total,
            "" if ok_total else (
                f"Total roteiro={total_rot:.2f} movimento={total_mov:.2f}"
            )
        ))

        # --- Check 5: Desconto ---
        desc_rot = float(_get(row, _ALIAS_DESC, 0) or 0)
        desc_mov = float(mov.get("descuentoTotal", 0))
        ok_desc  = abs(desc_rot - desc_mov) <= TOLERANCE
        result.checks.append(CheckResult(
            "desconto", ok_desc,
            "" if ok_desc else (
                f"Desconto roteiro={desc_rot:.2f} mov={desc_mov:.2f}"
            )
        ))

        # --- Check 6: Meio de pagamento ---
        tipo_pag_rot = str(_get(row, _ALIAS_PAGO, "") or "")
        tipo_pag_mov = str(mov.get("codigoTipoPago", ""))
        res_pag = self.promo.validate_pagamento(tipo_pag_mov, tipo_pag_rot)
        result.checks.append(CheckResult("pagamento", res_pag.ok, res_pag.detalhe))

        # --- Check 7: BIN ---
        bin_esp = str(_get(row, ["bin"], "") or "").strip()
        if bin_esp and bin_esp.lower() not in ("none", "nan"):
            res_bin = self.promo.validate_bin(mov, bin_esp)
            result.checks.append(CheckResult("bin", res_bin.ok, res_bin.detalhe))

        # --- Check 8: Promoção + Check 9: Desconto manual ---
        tipo_promo = str(_get(row, ["tipo_promo", "tipo promo", "promo", "promoção",
                                    "promocao", "tipo promocao", "tipo promoção"], "") or "").strip()
        if tipo_promo and tipo_promo.lower() not in ("none", "nan", "-", ""):
            promo_ativa = bool(_get(row, ["promo_ativa", "promo ativa"], True))
            res_promo   = self.promo.validate(tipo_promo, mov, row)
            result.checks.append(CheckResult("promocao", res_promo.ok, res_promo.detalhe))

            res_dm = self.promo.validate_desconto_manual(mov, obs, promo_ativa)
            result.checks.append(CheckResult("desconto_manual", res_dm.ok, res_dm.detalhe))

        # --- Check 10: Schema JSON ---
        res_schema = self.promo.validate_schema(mov)
        result.checks.append(CheckResult("schema_json", res_schema.ok, res_schema.detalhe))

        return result
