"""
Módulo 5 — TestRunner
Responsabilidade: Orquestra a validação linha a linha do roteiro (10 checks).

Colunas do roteiro que identificam o cupom:
  F → "Numero de cupom"  (número genérico / fallback)
  G → "SAT"              (número SAT fiscal)
  H → "ECF"              (número ECF / COO)
  H → "NFCE"             (número NFC-e)

A lógica tenta, em ordem:
  1. Qualquer valor não-nulo dentre SAT > NFCE > ECF > numero_cupom
  2. Fallback por conjunto de EANs quando nenhum número está disponível
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from .audit_parser      import AuditParser
from .coupon_pdf_parser import CouponPDFParser, Coupon
from .promo_engine      import PromoEngine, TOLERANCE

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    check:   str
    ok:      bool
    detalhe: str = ""


@dataclass
class TestResult:
    etapa:        str
    linha:        int
    cupom_numero: Optional[str]
    checks:       list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def motivo_erro(self) -> str:
        for c in self.checks:
            if not c.ok:
                return c.detalhe[:100]
        return ""


def _get_cupom_numero(row: dict) -> Optional[str]:
    """
    Extrai o número identificador do cupom da linha do roteiro.

    Tenta as colunas na seguinte prioridade:
      1. sat          → coluna G  (SAT fiscal)
      2. nfce / nfc-e → coluna H  (NFC-e)
      3. ecf          → coluna H  (ECF/COO)
      4. numero_cupom → coluna F  (genérico)
      5. numero de cupom (variação com espaços)
    """
    # Chaves normalizadas que o orquestrador gera a partir do cabeçalho
    candidates = [
        row.get("sat"),
        row.get("nfce"),
        row.get("nfc-e"),
        row.get("ecf"),
        row.get("numero_cupom"),
        row.get("numero de cupom"),
        row.get("numero"),
    ]
    for val in candidates:
        if val is not None:
            s = str(val).strip()
            if s and s.lower() not in ("", "none", "nan", "0"):
                return s
    return None


class TestRunner:
    """
    Executa os 10 checks em sequência para cada linha do roteiro.
    Aplica falha rápida nos checks mais críticos (cupom e HTTP).
    """

    def __init__(
        self,
        audit:  AuditParser,
        pdf:    CouponPDFParser,
        promo:  PromoEngine,
    ):
        self.audit = audit
        self.pdf   = pdf
        self.promo = promo

    def run(self, row: dict, linha: int) -> TestResult:
        etapa  = str(row.get("etapa", ""))
        result = TestResult(etapa=etapa, linha=linha, cupom_numero=None)

        # ----------------------------------------------------------------
        # Check 1 — Cupom localizado
        # Prioridade: SAT > NFCE > ECF > numero_cupom  (colunas G, H, F)
        # Fallback: busca por EANs
        # ----------------------------------------------------------------
        numero = _get_cupom_numero(row)
        eans   = [str(e).strip() for e in row.get("eans", []) if e]

        coupon:    Optional[Coupon] = None
        movements: list[dict]       = []

        if numero:
            logger.debug("Linha %d: buscando cupom por número '%s'", linha, numero)
            coupon    = self.pdf.get_by_numero(numero)
            movements = self.audit.get_by_numero(numero)

        # Fallback por EANs se não achou pelo número
        if not coupon and eans:
            logger.debug("Linha %d: fallback por EANs %s", linha, eans)
            coupon = self.pdf.get_by_eans(eans)

        if not movements and eans:
            movements = self.audit.get_by_eans(eans)

        found = coupon is not None or len(movements) > 0
        result.cupom_numero = (
            coupon.get_numero() if coupon
            else (movements[0].get("numero") if movements else None)
        )

        result.checks.append(CheckResult(
            "cupom_localizado", found,
            "" if found else f"Cupom não localizado: {numero or eans}"
        ))
        if not found:
            return result  # falha rápida

        mov = movements[0] if movements else {}

        # ----------------------------------------------------------------
        # Check 2 — HTTP 200
        # ----------------------------------------------------------------
        status  = int(mov.get("status", mov.get("httpStatus", 0)))
        ok_http = status == 200
        result.checks.append(CheckResult(
            "http_200", ok_http,
            "" if ok_http else f"Status HTTP: {status}"
        ))

        # ----------------------------------------------------------------
        # Check 3 — Cancelamento
        # ----------------------------------------------------------------
        obs                = str(row.get("observacao", "")).lower()
        cancelado_esperado = "cancelado" in obs or "cancelacion" in obs
        cancelado_real     = bool(mov.get("cancelacion", False))
        ok_cancel          = cancelado_esperado == cancelado_real
        result.checks.append(CheckResult(
            "cancelamento", ok_cancel,
            "" if ok_cancel else (
                f"Cancelamento esperado={cancelado_esperado} real={cancelado_real}"
            ),
        ))

        # ----------------------------------------------------------------
        # Check 4 — Total
        # ----------------------------------------------------------------
        total_rot = float(row.get("total", 0))
        total_mov = float(mov.get("total", 0))
        ok_total  = abs(total_rot - total_mov) <= TOLERANCE
        result.checks.append(CheckResult(
            "total", ok_total,
            "" if ok_total else (
                f"Total roteiro={total_rot:.2f} movimento={total_mov:.2f}"
            ),
        ))

        # ----------------------------------------------------------------
        # Check 5 — Desconto
        # ----------------------------------------------------------------
        desc_rot = float(row.get("desconto", 0))
        desc_mov = float(mov.get("descuentoTotal", 0))
        ok_desc  = abs(desc_rot - desc_mov) <= TOLERANCE
        result.checks.append(CheckResult(
            "desconto", ok_desc,
            "" if ok_desc else (
                f"Desconto roteiro={desc_rot:.2f} mov={desc_mov:.2f}"
            ),
        ))

        # ----------------------------------------------------------------
        # Check 6 — Meio de pagamento
        # ----------------------------------------------------------------
        tipo_pag_rot = str(row.get("meio_pagamento", ""))
        tipo_pag_mov = str(mov.get("codigoTipoPago", ""))
        res_pag      = self.promo.validate_pagamento(tipo_pag_mov, tipo_pag_rot)
        result.checks.append(CheckResult("pagamento", res_pag.ok, res_pag.detalhe))

        # ----------------------------------------------------------------
        # Check 7 — BIN (condicional)
        # ----------------------------------------------------------------
        bin_esp = str(row.get("bin", "")).strip()
        if bin_esp:
            res_bin = self.promo.validate_bin(mov, bin_esp)
            result.checks.append(CheckResult("bin", res_bin.ok, res_bin.detalhe))

        # ----------------------------------------------------------------
        # Check 8 — Promoção (dispatcher por tipo)
        # ----------------------------------------------------------------
        tipo_promo  = str(row.get("tipo_promo", "")).strip()
        promo_ativa = bool(row.get("promo_ativa", True))

        if tipo_promo:
            res_promo = self.promo.validate(tipo_promo, mov, row)
            result.checks.append(CheckResult("promocao", res_promo.ok, res_promo.detalhe))

            # ------------------------------------------------------------
            # Check 9 — Desconto manual indevido
            # ------------------------------------------------------------
            res_dm = self.promo.validate_desconto_manual(mov, obs, promo_ativa)
            result.checks.append(CheckResult("desconto_manual", res_dm.ok, res_dm.detalhe))

        # ----------------------------------------------------------------
        # Check 10 — Schema JSON mínimo
        # ----------------------------------------------------------------
        res_schema = self.promo.validate_schema(mov)
        result.checks.append(CheckResult("schema_json", res_schema.ok, res_schema.detalhe))

        return result
