"""
Módulo 4 — PromoEngine
Responsabilidade: Motor de validação por tipo de promoção.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

TOLERANCE = 0.05  # R$ 0,05

PAGAMENTO_MAP = {
    "dinheiro": ["1", "01", "DIN", "CASH"],
    "credito":  ["3", "03", "CRE", "CREDITO"],
    "debito":   ["4", "04", "DEB", "DEBITO"],
    "pix":      ["5", "05", "PIX"],
}


@dataclass
class PromoResult:
    ok: bool
    detalhe: str = ""


class PromoEngine:
    """Valida cada tipo de promoção Scanntech."""

    # ------------------------------------------------------------------
    # Dispatcher principal
    # ------------------------------------------------------------------

    def validate(self, tipo: str, movement: dict, roteiro_row: dict) -> PromoResult:
        """Despacha para o validador correto conforme o tipo de promoção."""
        tipo_upper = str(tipo).upper().strip()
        dispatch = {
            "LLEVAPAGA":          self._llevapaga,
            "DESCUENTOVARIABLE":  self._descuento_variable,
            "PRECIOFIJO":         self._precio_fijo,
            "ADICIONALREGALO":    self._adicional_regalo,
            "ADICIONALDESCUENTO": self._adicional_descuento,
            "DESCUENTOFIJO":      self._descuento_fijo,
        }
        fn = dispatch.get(tipo_upper)
        if not fn:
            return PromoResult(ok=False, detalhe=f"Tipo de promoção desconhecido: {tipo}")
        return fn(movement, roteiro_row)

    # ------------------------------------------------------------------
    # Validadores por tipo
    # ------------------------------------------------------------------

    def _llevapaga(self, mov: dict, row: dict) -> PromoResult:
        """Leva X Paga Y: lotes × (trigger − paga) × preço_unit ≈ descuentoTotal."""
        try:
            qtd        = float(row.get("qtd", 0))
            trigger    = float(row.get("trigger", 0))
            paga       = float(row.get("paga", trigger))
            preco_unit = float(row.get("preco_unit", 0))
            descuento  = float(mov.get("descuentoTotal", 0))

            if trigger <= 0:
                return PromoResult(ok=False, detalhe="trigger inválido para LLEVAPAGA")

            lotes    = int(qtd // trigger)
            esperado = lotes * (trigger - paga) * preco_unit
            diff     = abs(esperado - descuento)
            ok       = diff <= TOLERANCE
            return PromoResult(
                ok=ok,
                detalhe="" if ok else (
                    f"LLEVAPAGA: esperado R${esperado:.2f} "
                    f"descuentoTotal={descuento:.2f} diff={diff:.2f}"
                ),
            )
        except (TypeError, ValueError) as e:
            return PromoResult(ok=False, detalhe=f"LLEVAPAGA erro: {e}")

    def _descuento_variable(self, mov: dict, row: dict) -> PromoResult:
        """Descuento Variable: subtotal_promo × pct ≈ descuentoTotal."""
        try:
            pct      = float(row.get("pct_promo", 0)) / 100
            subtotal = float(row.get("subtotal_promo", 0))
            descuento= float(mov.get("descuentoTotal", 0))
            qtd_min  = float(row.get("qtd_min", 0))

            if qtd_min == 0 or subtotal == 0:
                ok = abs(descuento) <= TOLERANCE
                return PromoResult(
                    ok=ok,
                    detalhe="" if ok else "DESCUENTOVARIABLE: sem qtd mínima, desconto deve ser zero"
                )

            esperado = subtotal * pct
            diff     = abs(esperado - descuento)
            ok       = diff <= TOLERANCE
            return PromoResult(
                ok=ok,
                detalhe="" if ok else (
                    f"DESCUENTOVARIABLE: esperado R${esperado:.2f} "
                    f"descuentoTotal={descuento:.2f}"
                ),
            )
        except (TypeError, ValueError) as e:
            return PromoResult(ok=False, detalhe=f"DESCUENTOVARIABLE erro: {e}")

    def _precio_fijo(self, mov: dict, row: dict) -> PromoResult:
        """Precio Fijo: lotes × preco_fixo ≈ valor cobrado nos itens participantes."""
        try:
            qtd        = float(row.get("qtd", 0))
            trigger    = float(row.get("trigger", 1))
            preco_fixo = float(row.get("preco_fixo", 0))
            lotes      = int(qtd // trigger)
            esperado   = lotes * preco_fixo

            cobrado = sum(
                float(d.get("valorCobrado", d.get("total", 0)))
                for d in mov.get("detalles", [])
                if d.get("participante", False)
            )
            diff = abs(esperado - cobrado)
            ok   = diff <= TOLERANCE
            return PromoResult(
                ok=ok,
                detalhe="" if ok else (
                    f"PRECIOFIJO: esperado R${esperado:.2f} cobrado={cobrado:.2f}"
                ),
            )
        except (TypeError, ValueError) as e:
            return PromoResult(ok=False, detalhe=f"PRECIOFIJO erro: {e}")

    def _adicional_regalo(self, mov: dict, row: dict) -> PromoResult:
        """Adicional Regalo: descuentoTotal deve ser > 0 se presente no roteiro."""
        presente  = str(row.get("presente_esperado", "")).strip().lower()
        descuento = float(mov.get("descuentoTotal", 0))
        if presente in ("sim", "yes", "1", "true"):
            ok = descuento > 0
            return PromoResult(
                ok=ok,
                detalhe="" if ok else "ADICIONALREGALO: presente esperado mas descuentoTotal=0",
            )
        return PromoResult(ok=True)

    def _adicional_descuento(self, mov: dict, row: dict) -> PromoResult:
        """Adicional Descuento: descuento_item / preco_item ≈ pct_promo ± 2%."""
        try:
            pct_esperado = float(row.get("pct_promo", 0)) / 100
            detalhes     = mov.get("detalles", [])
            resultados   = []
            for d in detalhes:
                preco = float(d.get("precio", d.get("preco", 0)))
                desc  = float(d.get("descuento", 0))
                if preco == 0:
                    continue
                pct_real = desc / preco
                resultados.append(abs(pct_real - pct_esperado) <= 0.02)

            if not resultados:
                return PromoResult(ok=False, detalhe="ADICIONALDESCUENTO: sem itens para calcular")

            ok = all(resultados)
            return PromoResult(
                ok=ok,
                detalhe="" if ok else (
                    f"ADICIONALDESCUENTO: pct esperado={pct_esperado*100:.1f}% — divergência encontrada"
                ),
            )
        except (TypeError, ValueError) as e:
            return PromoResult(ok=False, detalhe=f"ADICIONALDESCUENTO erro: {e}")

    def _descuento_fijo(self, mov: dict, row: dict) -> PromoResult:
        """Descuento Fijo: descuentoTotal deve bater com valor fixo da promoção."""
        try:
            valor_fixo = float(row.get("valor_fixo", 0))
            descuento  = float(mov.get("descuentoTotal", 0))
            diff       = abs(valor_fixo - descuento)
            ok         = diff <= TOLERANCE
            return PromoResult(
                ok=ok,
                detalhe="" if ok else (
                    f"DESCUENTOFIJO: esperado R${valor_fixo:.2f} "
                    f"descuentoTotal={descuento:.2f}"
                ),
            )
        except (TypeError, ValueError) as e:
            return PromoResult(ok=False, detalhe=f"DESCUENTOFIJO erro: {e}")

    # ------------------------------------------------------------------
    # Validações auxiliares
    # ------------------------------------------------------------------

    def validate_pagamento(self, movimento_tipo: str, roteiro_tipo: str) -> PromoResult:
        """Valida meio de pagamento via mapeamento codigoTipoPago."""
        roteiro_norm = roteiro_tipo.lower().strip()
        for label, codigos in PAGAMENTO_MAP.items():
            if roteiro_norm in label or label in roteiro_norm:
                ok = str(movimento_tipo).upper() in [c.upper() for c in codigos]
                return PromoResult(
                    ok=ok,
                    detalhe="" if ok else (
                        f"Pagamento: esperado {label} (códigos {codigos}), "
                        f"recebido {movimento_tipo}"
                    ),
                )
        return PromoResult(ok=False, detalhe=f"Tipo pagamento não mapeado: {roteiro_tipo}")

    def validate_bin(self, movement: dict, bin_esperado: str) -> PromoResult:
        """Valida presença do BIN específico no campo bin do JSON."""
        bin_mov = str(movement.get("bin", "")).strip()
        ok      = bin_esperado.strip() in bin_mov
        return PromoResult(
            ok=ok,
            detalhe="" if ok else f"BIN esperado {bin_esperado}, encontrado {bin_mov}",
        )

    def validate_schema(self, movement: dict) -> PromoResult:
        """Valida campos obrigatórios: total, numero, detalles, pagos."""
        campos   = ["total", "numero", "detalles", "pagos"]
        faltando = [c for c in campos if c not in movement]
        ok       = len(faltando) == 0
        return PromoResult(
            ok=ok,
            detalhe="" if ok else f"Schema: campos ausentes {faltando}",
        )

    def validate_desconto_manual(
        self, movement: dict, obs: str, promo_ativa: bool
    ) -> PromoResult:
        """Rejeita desconto manual quando promoção Scanntech está ativa e obs='sem desconto manual'."""
        if not promo_ativa:
            return PromoResult(ok=True)
        if "sem desconto manual" in str(obs).lower():
            descuento = float(movement.get("descuentoManual", 0))
            ok        = abs(descuento) <= TOLERANCE
            return PromoResult(
                ok=ok,
                detalhe="" if ok else f"Desconto manual indevido: R${descuento:.2f}",
            )
        return PromoResult(ok=True)
