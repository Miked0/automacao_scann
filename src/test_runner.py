"""
Módulo 5 — TestRunner
Responsabilidade: Orquestra a validação linha a linha do roteiro.

Estratégia de localização do cupom (Check 1)
============================================
Fonte 1 — campo "numero" do JSON da API (coluna do roteiro):
  O roteiro deve conter uma coluna com o número do cenário de venda.
  Esse número é o campo "numero" presente no JSON enviado à API Scanntech
  e também impresso nos cupons fiscais físicos.
  Aliases aceitos na planilha: numero_cupom, n° cupom, nº cupom, cupom,
  numero, n cupom, num cupom, número cupom, n.cupom, num.cupom.

Fonte 2 — número físico do cupom impresso (SAT / NFC-e / ECF):
  Se a coluna acima não estiver preenchida, ou o número não for encontrado,
  o mesmo valor é pesquisado nos índices SAT, NFC-e e ECF do PDF.

Fonte 3 — nome do arquivo PDF:
  O CouponPDFParser aceita o nome do arquivo na construção e extrai o
  número do cupom do padrão  <numero>_resto.pdf  ou  cupom_<numero>.pdf.

Fonte 4 (fallback final) — EANs:
  Caso nenhuma das fontes acima localize o cupom, a busca é feita pelos
  EANs dos itens da venda (coluna ean/eans/codigo_barras na planilha).
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from .audit_parser import AuditParser
from .coupon_pdf_parser import CouponPDFParser, Coupon
from .promo_engine import PromoEngine

logger = logging.getLogger(__name__)

TOLERANCE = 0.05

# Aliases de colunas do roteiro
_ALIAS_NUMERO = [
    "numero_cupom", "n° cupom", "nº cupom", "cupom", "numero",
    "n cupom", "num cupom", "número cupom", "n.cupom", "num.cupom",
    "número",
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


def _clean_numero(raw) -> str:
    """Normaliza o número do cupom: remove espaços, None, nan textuais."""
    s = str(raw).strip() if raw is not None else ""
    return "" if s.lower() in ("none", "nan", "") else s


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
    """Executa os checks em sequência para cada linha do roteiro."""

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
    # Localização do cupom — lógica centralizada
    # ------------------------------------------------------------------

    def _locate_coupon(
        self, numero: str, eans: list[str]
    ) -> tuple[Optional[Coupon], list[dict], str]:
        """
        Retorna (coupon_pdf, movimentos_audit, numero_resolvido).

        Ordem de tentativas:
          1. campo "numero" do JSON → busca direta em audit e pdf
          2. mesmo valor buscado nos índices SAT / NFC-e / ECF do PDF
          3. nome do arquivo PDF (delegado ao CouponPDFParser)
          4. EANs como fallback final
        """
        coupon: Optional[Coupon] = None
        movements: list[dict] = []
        resolved: str = numero

        if numero:
            # --- Fonte 1: campo "numero" do JSON ---
            movements = self.audit.get_by_numero(numero)
            coupon    = self.pdf.get_by_numero(numero)  # tenta todos os sub-índices

            if coupon:
                logger.debug("Cupom localizado via numero='%s' no PDF", numero)
            if movements:
                logger.debug("Cupom localizado via numero='%s' no Audit (%d mov)",
                             numero, len(movements))

            # --- Fonte 2: tenta outros índices do Audit (nfce/sat/ecf) ---
            if not movements:
                movements = self.audit.get_by_nfce(numero)
                if movements:
                    logger.debug("Cupom localizado via NFC-e='%s' no Audit", numero)
            if not movements:
                movements = self.audit.get_by_sat(numero)
                if movements:
                    logger.debug("Cupom localizado via SAT='%s' no Audit", numero)
            if not movements:
                movements = self.audit.get_by_ecf(numero)
                if movements:
                    logger.debug("Cupom localizado via ECF='%s' no Audit", numero)

        # --- Fonte 3: nome do arquivo ---
        if not coupon and self.pdf.pdf_filename:
            coupon = self.pdf.get_by_filename(self.pdf.pdf_filename)
            if coupon:
                resolved = coupon.get_numero() or numero
                logger.debug("Cupom localizado via nome do arquivo: %s", self.pdf.pdf_filename)

        # --- Fonte 4: fallback por EANs ---
        if not coupon and eans:
            coupon = self.pdf.get_by_eans(eans)
            if coupon:
                resolved = coupon.get_numero() or numero
                logger.debug("Cupom localizado via EANs: %s", eans)

        if not movements and eans:
            movements = self.audit.get_by_eans(eans)
            if movements:
                logger.debug("Audit localizado via EANs: %s", eans)

        # Sincroniza numero resolvido
        if not resolved and coupon:
            resolved = coupon.get_numero() or ""
        if not resolved and movements:
            resolved = str(movements[0].get("numero", ""))

        return coupon, movements, resolved

    # ------------------------------------------------------------------
    # Execução principal
    # ------------------------------------------------------------------

    def run(self, row: dict, linha: int) -> TestResult:
        etapa  = str(_get(row, _ALIAS_ETAPA, "") or "")
        result = TestResult(etapa=etapa, linha=linha, cupom_numero=None)

        # Coleta número e EANs do roteiro
        numero = _clean_numero(_get(row, _ALIAS_NUMERO, ""))
        eans_raw = _get(row, _ALIAS_EANS, "")
        if isinstance(eans_raw, str):
            eans = [e.strip() for e in eans_raw.split(",") if e.strip()]
        elif eans_raw is not None:
            eans = [str(eans_raw).strip()]
        else:
            eans = []

        # --- Check 1: Cupom localizado ---
        coupon, movements, resolved = self._locate_coupon(numero, eans)
        found = coupon is not None or len(movements) > 0
        result.cupom_numero = resolved or None

        result.checks.append(CheckResult(
            "cupom_localizado", found,
            "" if found else (
                f"Cupom não localizado: numero='{numero}' EANs={eans} "
                f"arquivo='{self.pdf.pdf_filename or 'N/A'}'"
            )
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
        obs                = str(_get(row, _ALIAS_OBS, "") or "").lower()
        cancelado_esperado = "cancelado" in obs or "cancelacion" in obs
        cancelado_real     = bool(mov.get("cancelacion", False))
        ok_cancel          = cancelado_esperado == cancelado_real
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
        if tipo_pag_rot:
            res_pag = self.promo.validate_pagamento(tipo_pag_mov, tipo_pag_rot)
            result.checks.append(CheckResult("pagamento", res_pag.ok, res_pag.detalhe))

        # --- Check 7: BIN ---
        bin_esp = str(row.get("bin", "") or "").strip()
        if bin_esp:
            res_bin = self.promo.validate_bin(mov, bin_esp)
            result.checks.append(CheckResult("bin", res_bin.ok, res_bin.detalhe))

        # --- Check 8: Promoção ---
        tipo_promo = str(row.get("tipo_promo", "") or "").strip()
        if tipo_promo:
            promo_ativa = bool(row.get("promo_ativa", True))
            res_promo   = self.promo.validate(tipo_promo, mov, row)
            result.checks.append(CheckResult("promocao", res_promo.ok, res_promo.detalhe))

            # --- Check 9: Desconto manual indevido ---
            res_dm = self.promo.validate_desconto_manual(mov, obs, promo_ativa)
            result.checks.append(CheckResult("desconto_manual", res_dm.ok, res_dm.detalhe))

        # --- Check 10: Schema JSON ---
        res_schema = self.promo.validate_schema(mov)
        result.checks.append(CheckResult("schema_json", res_schema.ok, res_schema.detalhe))

        return result
