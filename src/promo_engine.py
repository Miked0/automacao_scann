"""
M4 — PromoEngine
Motor de validação por tipo de promoção Scanntech.

Tipos suportados:
    LLEVAPAGA         — lotes × (trigger − paga) × preço_unit vs descuentoTotal
    DESCUENTOVARIABLE — subtotal_promo × pct vs descuentoTotal; sem qtd mín → desconto = 0
    PRECIOFIJO        — lotes × preco_fixo vs valor cobrado nos itens participantes
    ADICIONALREGALO   — descuentoTotal > 0 quando presente no roteiro
    ADICIONALDESCUENTO— descuento_item / preco_item ≈ pct_promo ± 2%
    DESCUENTOFIJO     — descuentoTotal == valor_fixo ± R$0,05
"""

from __future__ import annotations
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from .models import AuditMovement, CheckResult

log = logging.getLogger(__name__)

TOLERANCE = 0.05  # R$ 0,05
PCT_TOL   = 0.02  # 2% para ADICIONALDESCUENTO


class PromoEngine:
    """Dispatcher de validação por tipo de promoção."""

    # ── Dispatcher público ───────────────────────────────────────────────────
    def validate(
        self,
        promo_type: str,
        row_data: Dict[str, Any],
        movement: AuditMovement,
    ) -> CheckResult:
        """
        Valida a promoção e retorna CheckResult.
        row_data — dados da linha do roteiro (dict com chaves normalizadas).
        """
        tipo = promo_type.upper().strip()
        handler = {
            "LLEVAPAGA":          self._llevapaga,
            "DESCUENTOVARIABLE":  self._descuento_variable,
            "PRECIOFIJO":         self._precio_fijo,
            "ADICIONALREGALO":    self._adicional_regalo,
            "ADICIONALDESCUENTO": self._adicional_descuento,
            "DESCUENTOFIJO":      self._descuento_fijo,
        }.get(tipo)

        if handler is None:
            return CheckResult(
                check="promo",
                ok=True,
                detalhe=f"Tipo '{promo_type}' não mapeado — check ignorado.",
            )

        try:
            return handler(row_data, movement)
        except Exception as exc:
            log.error("PromoEngine erro em %s: %s", tipo, exc, exc_info=True)
            return CheckResult(check="promo", ok=False, detalhe=f"Erro interno: {exc}")

    # ── LLEVAPAGA ────────────────────────────────────────────────────────────
    def _llevapaga(
        self, row: Dict[str, Any], mv: AuditMovement
    ) -> CheckResult:
        """
        Calcula: lotes × (trigger − paga) × preço_unit.
        Campos esperados no roteiro: qtd, trigger, paga, preco_unit.
        """
        qtd        = _safe_float(row.get("qtd"))
        trigger    = _safe_float(row.get("trigger")  or row.get("leva"))
        paga       = _safe_float(row.get("paga")     or row.get("pagando"))
        preco_unit = _safe_float(row.get("preco_unit") or row.get("valor_unit"))

        if None in (qtd, trigger, paga, preco_unit) or trigger == 0:
            return CheckResult(check="promo", ok=False, detalhe="Dados insuficientes para LLEVAPAGA.")

        lotes          = math.floor(qtd / trigger)  # type: ignore[arg-type]
        desconto_calc  = lotes * (trigger - paga) * preco_unit  # type: ignore[operator]
        desconto_audit = mv.descuento_total or 0.0

        ok = abs(desconto_calc - desconto_audit) <= TOLERANCE
        return CheckResult(
            check="promo",
            ok=ok,
            detalhe=(
                f"LLEVAPAGA: calc={desconto_calc:.2f} audit={desconto_audit:.2f} "
                f"(lotes={lotes}, trigger={trigger}, paga={paga})"
            ),
        )

    # ── DESCUENTOVARIABLE ────────────────────────────────────────────────────
    def _descuento_variable(
        self, row: Dict[str, Any], mv: AuditMovement
    ) -> CheckResult:
        """
        subtotal_promo × pct vs descuentoTotal.
        Se qtd mínima não atingida → desconto deve ser zero.
        """
        subtotal_promo = _safe_float(row.get("subtotal_promo") or row.get("subtotal"))
        pct            = _safe_float(row.get("pct")  or row.get("percentual"))
        qtd            = _safe_float(row.get("qtd"))
        qtd_min        = _safe_float(row.get("qtd_min") or row.get("minimo"))
        desconto_audit = mv.descuento_total or 0.0

        # Sem qtd mínima atingida → desconto deve ser zero
        if qtd is not None and qtd_min is not None and qtd < qtd_min:
            ok = abs(desconto_audit) <= TOLERANCE
            return CheckResult(
                check="promo",
                ok=ok,
                detalhe=f"DESCUENTOVARIABLE: qtd={qtd} < min={qtd_min} → desconto esperado=0, audit={desconto_audit:.2f}",
            )

        if None in (subtotal_promo, pct):
            return CheckResult(check="promo", ok=False, detalhe="Dados insuficientes para DESCUENTOVARIABLE.")

        desconto_calc = subtotal_promo * (pct / 100.0)  # type: ignore[operator]
        ok = abs(desconto_calc - desconto_audit) <= TOLERANCE
        return CheckResult(
            check="promo",
            ok=ok,
            detalhe=(
                f"DESCUENTOVARIABLE: calc={desconto_calc:.2f} audit={desconto_audit:.2f} "
                f"(subtotal={subtotal_promo}, pct={pct}%)"
            ),
        )

    # ── PRECIOFIJO ───────────────────────────────────────────────────────────
    def _precio_fijo(
        self, row: Dict[str, Any], mv: AuditMovement
    ) -> CheckResult:
        """
        lotes × preco_fixo deve ser igual ao valor cobrado nos itens participantes.
        """
        qtd        = _safe_float(row.get("qtd"))
        preco_fixo = _safe_float(row.get("preco_fixo") or row.get("valor_fixo"))
        ean_promo  = str(row.get("ean") or row.get("ean_promo") or "").strip()

        if None in (qtd, preco_fixo):
            return CheckResult(check="promo", ok=False, detalhe="Dados insuficientes para PRECIOFIJO.")

        # Soma itens participantes nos detalles
        valor_cobrado = self._sum_item_value(mv.detalles, ean_promo)
        esperado      = qtd * preco_fixo  # type: ignore[operator]

        ok = abs(esperado - valor_cobrado) <= TOLERANCE
        return CheckResult(
            check="promo",
            ok=ok,
            detalhe=(
                f"PRECIOFIJO: esperado={esperado:.2f} cobrado={valor_cobrado:.2f} "
                f"(qtd={qtd}, preco={preco_fixo}, ean={ean_promo})"
            ),
        )

    # ── ADICIONALREGALO ──────────────────────────────────────────────────────
    def _adicional_regalo(
        self, row: Dict[str, Any], mv: AuditMovement
    ) -> CheckResult:
        """descuentoTotal > 0 quando presente no roteiro."""
        presente       = str(row.get("presente") or row.get("regalo") or "").lower()
        desconto_audit = mv.descuento_total or 0.0

        if "sim" in presente or "yes" in presente or "s" == presente:
            ok = desconto_audit > 0
            return CheckResult(
                check="promo",
                ok=ok,
                detalhe=f"ADICIONALREGALO: presente esperado, descuentoTotal={desconto_audit:.2f}",
            )
        return CheckResult(check="promo", ok=True, detalhe="ADICIONALREGALO: sem presente esperado.")

    # ── ADICIONALDESCUENTO ───────────────────────────────────────────────────
    def _adicional_descuento(
        self, row: Dict[str, Any], mv: AuditMovement
    ) -> CheckResult:
        """descuento_item / preco_item deve ≈ pct_promo ± 2%."""
        pct_promo = _safe_float(row.get("pct") or row.get("percentual"))
        ean_promo = str(row.get("ean") or row.get("ean_promo") or "").strip()

        if pct_promo is None:
            return CheckResult(check="promo", ok=False, detalhe="Dados insuficientes para ADICIONALDESCUENTO.")

        for item in mv.detalles:
            ean_item    = str(item.get("codigoBarras") or item.get("ean") or "").strip()
            if ean_promo and ean_item != ean_promo:
                continue
            preco_item  = _safe_float(item.get("precioUnitario") or item.get("precio"))
            desc_item   = _safe_float(item.get("descuento") or item.get("descuentoItem"))
            if preco_item and desc_item is not None and preco_item > 0:
                pct_real = (desc_item / preco_item) * 100.0
                ok = abs(pct_real - pct_promo) <= PCT_TOL * 100
                return CheckResult(
                    check="promo",
                    ok=ok,
                    detalhe=(
                        f"ADICIONALDESCUENTO: pct_real={pct_real:.2f}% pct_esperado={pct_promo:.2f}% "
                        f"ean={ean_item}"
                    ),
                )

        return CheckResult(
            check="promo",
            ok=False,
            detalhe=f"ADICIONALDESCUENTO: item EAN={ean_promo} não encontrado nos detalles.",
        )

    # ── DESCUENTOFIJO ────────────────────────────────────────────────────────
    def _descuento_fijo(
        self, row: Dict[str, Any], mv: AuditMovement
    ) -> CheckResult:
        """descuentoTotal deve bater com valor fixo da promoção ± R$0,05."""
        valor_fixo     = _safe_float(row.get("valor_desconto") or row.get("desconto_fixo"))
        desconto_audit = mv.descuento_total or 0.0

        if valor_fixo is None:
            return CheckResult(check="promo", ok=False, detalhe="Dados insuficientes para DESCUENTOFIJO.")

        ok = abs(valor_fixo - desconto_audit) <= TOLERANCE
        return CheckResult(
            check="promo",
            ok=ok,
            detalhe=f"DESCUENTOFIJO: esperado={valor_fixo:.2f} audit={desconto_audit:.2f}",
        )

    # ── Helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _sum_item_value(detalles: List[Dict], ean: str) -> float:
        """Soma o valor cobrado dos itens pelo EAN (vazio = todos)."""
        total = 0.0
        for item in detalles:
            if ean:
                item_ean = str(item.get("codigoBarras") or item.get("ean") or "").strip()
                if item_ean != ean:
                    continue
            qtd   = _safe_float(item.get("cantidad") or item.get("qtd") or 1) or 1.0
            preco = _safe_float(item.get("precioUnitario") or item.get("precio") or 0)
            total += qtd * (preco or 0.0)
        return total


# ── Utilitário ────────────────────────────────────────────────────────────────
def _safe_float(val: Any) -> Optional[float]:
    try:
        return float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
