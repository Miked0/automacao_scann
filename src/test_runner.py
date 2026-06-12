"""
Módulo 5 — TestRunner  (v2 — corrigido BUG-01, BUG-03)
Responsabilidade: Orquestra a validação linha a linha do roteiro.

Fix BUG-01: lê numero_cupom das colunas SAT(C6), ECF(C7) e NFCE(C8) individualmente,
            mapeadas pelo cabeçalho real do TEMPLATE.
Fix BUG-03: guard contra leitura de coluna já preenchida com 'Ok'/'Erro'.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from .audit_parser import AuditParser
from .coupon_pdf_parser import CouponPDFParser, Coupon
from .promo_engine import PromoEngine

logger = logging.getLogger(__name__)

TOLERANCE = 0.05

# Valores que indicam coluna de resultado já preenchida — NÃO usar como número
_RESULT_SENTINEL = {"ok", "erro", "error", "(status)", "n/a", ""}


def _clean_numero(val) -> Optional[str]:
    """
    Sanitiza o valor lido da célula de número do cupom.
    Retorna None se for valor de resultado anterior (BUG-03 guard).
    """
    if val is None:
        return None
    s = str(val).strip()
    if s.lower() in _RESULT_SENTINEL:
        return None
    # Remove decimais de números lidos como float (ex: 79.0 → '79')
    try:
        return str(int(float(s)))
    except (ValueError, TypeError):
        return s if s else None


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
    checks: list[CheckResult] = field(default_factory=list)

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
    """
    Executa os 10 checks em sequência para cada linha do roteiro.

    Espera que 'row' contenha as seguintes chaves (extraídas do TEMPLATE):
      numero_sat, numero_ecf, numero_nfce — número do cupom por tipo (BUG-01 fix)
      eans        — lista de EANs para fallback
      total, desconto, meio_pagamento, observacao, tipo_promo
      etapa, bin, qtd, trigger, paga, preco_unit, pct_promo, etc.
    """

    def __init__(
        self,
        audit: AuditParser,
        pdf: CouponPDFParser,
        promo: PromoEngine,
    ):
        self.audit = audit
        self.pdf   = pdf
        self.promo = promo

    # ------------------------------------------------------------------
    # Execução principal
    # ------------------------------------------------------------------

    def run(self, row: dict, linha: int) -> TestResult:
        etapa = str(row.get("etapa", ""))
        result = TestResult(etapa=etapa, linha=linha, cupom_numero=None)

        # ── Check 1: Cupom localizado ──────────────────────────────────
        # BUG-01 fix: lê os 3 campos de número separadamente
        num_sat  = _clean_numero(row.get("numero_sat"))
        num_ecf  = _clean_numero(row.get("numero_ecf"))
        num_nfce = _clean_numero(row.get("numero_nfce"))
        eans     = [str(e).strip() for e in row.get("eans", []) if e]

        coupon: Optional[Coupon]  = None
        movements: list[dict]     = []

        # Tenta localizar por cada número em ordem de prioridade
        for num in filter(None, [num_sat, num_ecf, num_nfce]):
            c = self.pdf.get_by_numero(num)
            m = self.audit.get_by_numero(num)
            if c or m:
                coupon    = c or coupon
                movements = m or movements
                result.cupom_numero = num
                break

        # Fallback por EANs
        if not coupon and eans:
            coupon = self.pdf.get_by_eans(eans)
        if not movements and eans:
            movements = self.audit.get_by_eans(eans)
            if movements and not result.cupom_numero:
                result.cupom_numero = movements[0].get("numero")

        found = coupon is not None or len(movements) > 0
        nums_str = "/".join(filter(None, [num_sat, num_ecf, num_nfce])) or "(sem número)"
        result.checks.append(CheckResult(
            "cupom_localizado", found,
            "" if found else f"Cupom não localizado: SAT={num_sat} ECF={num_ecf} NFCE={num_nfce} EANs={eans}"
        ))
        if not found:
            return result  # falha rápida

        mov = movements[0] if movements else {}

        # ── Check 2: HTTP 200 ─────────────────────────────────────────
        status = int(mov.get("status", mov.get("httpStatus", 200)))
        ok_http = status == 200
        result.checks.append(CheckResult(
            "http_200", ok_http,
            "" if ok_http else f"Status HTTP: {status}"
        ))

        # ── Check 3: Cancelamento ─────────────────────────────────────
        obs = str(row.get("observacao", "")).lower()
        cancelado_esperado = any(kw in obs for kw in ("cancelado", "cancelacion", "cancelamento"))
        cancelado_real     = bool(mov.get("cancelacion", False))
        ok_cancel = cancelado_esperado == cancelado_real
        result.checks.append(CheckResult(
            "cancelamento", ok_cancel,
            "" if ok_cancel else
            f"Cancelamento esperado={cancelado_esperado} real={cancelado_real}"
        ))

        # ── Check 4: Total ────────────────────────────────────────────
        total_rot = self._safe_float(row, "total")
        total_mov = float(mov.get("total", 0))
        ok_total = abs(total_rot - total_mov) <= TOLERANCE
        result.checks.append(CheckResult(
            "total", ok_total,
            "" if ok_total else
            f"Total roteiro={total_rot:.2f} movimento={total_mov:.2f}"
        ))

        # ── Check 5: Desconto ─────────────────────────────────────────
        desc_rot = self._safe_float(row, "desconto")
        desc_mov = float(mov.get("descuentoTotal", 0))
        ok_desc = abs(desc_rot - desc_mov) <= TOLERANCE
        result.checks.append(CheckResult(
            "desconto", ok_desc,
            "" if ok_desc else
            f"Desconto roteiro={desc_rot:.2f} mov={desc_mov:.2f}"
        ))

        # ── Check 6: Meio de pagamento ────────────────────────────────
        tipo_pag_rot = str(row.get("meio_pagamento", row.get("pagamento", "")))
        tipo_pag_mov = str(mov.get("codigoTipoPago", ""))
        res_pag = self.promo.validate_pagamento(tipo_pag_mov, tipo_pag_rot)
        result.checks.append(CheckResult("pagamento", res_pag.ok, res_pag.detalhe))

        # ── Check 7: BIN ──────────────────────────────────────────────
        bin_esp = str(row.get("bin", "")).strip()
        if bin_esp and bin_esp.lower() not in ("nan", "none", "", "n/a"):
            res_bin = self.promo.validate_bin(mov, bin_esp)
            result.checks.append(CheckResult("bin", res_bin.ok, res_bin.detalhe))

        # ── Check 8: Promoção ─────────────────────────────────────────
        tipo_promo = str(row.get("tipo_promo", row.get("tipo promo", ""))).strip().upper()
        if tipo_promo and tipo_promo not in ("N/A", "NA", "NONE", ""):
            promo_ativa = bool(row.get("promo_ativa", True))
            res_promo = self.promo.validate(tipo_promo, mov, row)
            result.checks.append(CheckResult("promocao", res_promo.ok, res_promo.detalhe))

            # ── Check 9: Desconto manual indevido ─────────────────────
            res_dm = self.promo.validate_desconto_manual(mov, obs, promo_ativa)
            result.checks.append(CheckResult("desconto_manual", res_dm.ok, res_dm.detalhe))

        # ── Check 10: Schema JSON ─────────────────────────────────────
        res_schema = self.promo.validate_schema(mov)
        result.checks.append(CheckResult("schema_json", res_schema.ok, res_schema.detalhe))

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_float(row: dict, key: str, default: float = 0.0) -> float:
        try:
            return float(row.get(key, default) or default)
        except (TypeError, ValueError):
            return default
