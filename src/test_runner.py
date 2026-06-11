"""
Módulo 5 — TestRunner
Responsabilidade: Orquestra a validação linha a linha do roteiro.

Estratégia de localização do cupom (Check 1)
============================================
O roteiro possui TRÊS colunas separadas para o número do cupom físico:
  • Coluna SAT  (col F) — número do cupom SAT
  • Coluna ECF  (col G) — número do cupom ECF
  • Coluna NFCE (col H) — número do cupom NFC-e  ← geralmente preenchido

A busca é feita em cascata:
  1. Tenta SAT  → audit.get_by_numero() + pdf.get_by_numero()
  2. Tenta ECF  → mesma lógica
  3. Tenta NFCE → mesma lógica
  4. Fallback por EANs extraídos da coluna 'Itens da venda'
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from .audit_parser import AuditParser
from .coupon_pdf_parser import CouponPDFParser, Coupon
from .promo_engine import PromoEngine

logger = logging.getLogger(__name__)

TOLERANCE = 0.05

# ---------------------------------------------------------------------------
# Aliases de colunas do roteiro (case-insensitive, strip)
# ---------------------------------------------------------------------------

# Número do cupom — coluna genérica (legado) OU colunas separadas SAT/ECF/NFCE
_ALIAS_SAT  = ["sat", "num. sat", "numero sat", "nº sat", "n° sat", "cupom sat"]
_ALIAS_ECF  = ["ecf", "num. ecf", "numero ecf", "nº ecf", "n° ecf", "cupom ecf"]
_ALIAS_NFCE = [
    "nfce", "nfc-e", "nfce.1", "num. nfce", "numero nfce", "nº nfce",
    "o de\nnfce", "o de nfce", "numero de\nnfce", "n. nfce", "cupom nfce",
    "numero nfc-e", "nfc_e",
]
# Coluna genérica (roteiros mais antigos)
_ALIAS_NUMERO = [
    "numero_cupom", "n° cupom", "nº cupom", "cupom", "numero",
    "n cupom", "num cupom", "número cupom", "n.cupom", "num.cupom", "número",
]

_ALIAS_EANS  = ["ean", "eans", "itens da venda", "articulos movimiento",
                "codigo_barras", "cod_barra", "codigo barras", "ean/upc",
                "itens", "produtos", "artigos"]
_ALIAS_TOTAL = ["total", "valor total", "vl total", "vl. total", "total venda"]
_ALIAS_DESC  = ["desconto", "desc", "desconto total", "vl desconto",
                "descuento", "acréscimo", "acrescimo"]
_ALIAS_PAGO  = ["meio_pagamento", "meio pagamento", "pagamento",
                "forma pagamento", "forma de pagamento", "tipo pagamento", "meio pag"]
_ALIAS_OBS   = ["observacao", "observação", "obs", "observacoes", "observações",
                "detalhes", "nota", "observacoes.1"]
_ALIAS_ETAPA = ["etapa", "fase", "step", "cenário", "cenario", "teste"]
_ALIAS_TIPO  = ["tipo promo", "tipo_promo", "tipopromo", "tipo de promo",
                "tipo promocao", "tipo promoção", "promo"]


def _get(row: dict, aliases: list, default=None):
    """Busca o primeiro alias encontrado no dicionário row (case-insensitive)."""
    row_lower = {str(k).strip().lower(): v for k, v in row.items()}
    for alias in aliases:
        val = row_lower.get(alias.lower())
        if val is not None:
            return val
    return default


def _clean_numero(raw) -> str:
    """Normaliza o número do cupom: strip, remove None/nan, converte float→int."""
    if raw is None:
        return ""
    # openpyxl pode retornar float para células numéricas (ex: 79.0)
    if isinstance(raw, float):
        raw = int(raw) if raw == int(raw) else raw
    s = str(raw).strip()
    return "" if s.lower() in ("none", "nan", "") else s


def _extract_eans_from_text(text: str) -> list[str]:
    """
    Extrai EANs (7-14 dígitos) do texto livre da coluna 'Itens da venda'.
    Ex: '2 x 7891000010860 + 3.579 * PESABLE' → ['7891000010860']
    """
    return re.findall(r'\b(\d{7,14})\b', str(text or ""))


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
        self, row: dict
    ) -> tuple[Optional[Coupon], list[dict], str]:
        """
        Tenta localizar o cupom na ordem:
          1. Coluna NFCE  (col H — mais preenchida na Etapa 1)
          2. Coluna SAT   (col F)
          3. Coluna ECF   (col G)
          4. Campo genérico 'numero_cupom' (legado)
          5. Fallback por EANs extraídos do texto 'Itens da venda'
        """
        coupon: Optional[Coupon] = None
        movements: list[dict] = []
        resolved: str = ""

        # Candidatos de número na ordem de prioridade
        candidatos = [
            ("NFCE", _clean_numero(_get(row, _ALIAS_NFCE))),
            ("SAT",  _clean_numero(_get(row, _ALIAS_SAT))),
            ("ECF",  _clean_numero(_get(row, _ALIAS_ECF))),
            ("NUM",  _clean_numero(_get(row, _ALIAS_NUMERO))),
        ]

        for fonte, numero in candidatos:
            if not numero:
                continue

            movs = self.audit.get_by_numero(numero)
            cup  = self.pdf.get_by_numero(numero)

            if movs or cup:
                logger.debug(
                    "Cupom localizado via %s='%s' (movs=%d, pdf=%s)",
                    fonte, numero, len(movs), cup is not None
                )
                coupon    = coupon or cup
                movements = movements or movs
                resolved  = resolved or numero
                # Não para: pode ter PDF num e Audit noutro
                if coupon and movements:
                    break

        # --- Fallback por EANs ---
        itens_texto = str(_get(row, _ALIAS_EANS, "") or "")
        eans = _extract_eans_from_text(itens_texto)

        if not coupon and eans:
            coupon = self.pdf.get_by_eans(eans)
            if coupon:
                resolved = resolved or coupon.get_numero() or ""
                logger.debug("PDF localizado via EANs: %s", eans)

        if not movements and eans:
            movements = self.audit.get_by_eans(eans)
            if movements:
                resolved = resolved or str(movements[0].get("numero", ""))
                logger.debug("Audit localizado via EANs: %s", eans)

        return coupon, movements, resolved

    # ------------------------------------------------------------------
    # Execução principal
    # ------------------------------------------------------------------

    def run(self, row: dict, linha: int) -> TestResult:
        etapa  = str(_get(row, _ALIAS_ETAPA, "") or "")
        result = TestResult(etapa=etapa, linha=linha, cupom_numero=None)

        # --- Check 1: Cupom localizado ---
        coupon, movements, resolved = self._locate_coupon(row)
        found = coupon is not None or len(movements) > 0
        result.cupom_numero = resolved or None

        # Reconstrói EANs para log de erro
        itens_texto = str(_get(row, _ALIAS_EANS, "") or "")
        eans = _extract_eans_from_text(itens_texto)

        # Candidatos para mensagem de erro
        num_nfce = _clean_numero(_get(row, _ALIAS_NFCE))
        num_sat  = _clean_numero(_get(row, _ALIAS_SAT))
        num_ecf  = _clean_numero(_get(row, _ALIAS_ECF))

        result.checks.append(CheckResult(
            "cupom_localizado", found,
            "" if found else (
                f"Cupom não localizado: "
                f"NFCE='{num_nfce}' SAT='{num_sat}' ECF='{num_ecf}' "
                f"EANs={eans[:3]}"
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
        cancelado_esperado = "cancelado" in obs or "cancelacion" in obs or "cancelar" in obs
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
        tipo_promo = str(_get(row, _ALIAS_TIPO, "") or "").strip()
        if tipo_promo and tipo_promo.upper() not in ("N/A", "NA", "NONE", ""):
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
