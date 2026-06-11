# src/promo_engine.py
"""
Módulo 4 — PromoEngine
Responsabilidade: Motor de validação por tipo de promoção.
Correções v2:
- Mapa codigoTipoPago corrigido com códigos OFICIAIS da API Scanntech:
    9=Efetivo/Dinheiro, 10=Crédito, 11=Cheque, 12=Vale,
    13=Débito, 14=PIX/QR, 15=Finalizadora
- validate_bin lê pagos[0].bin
- validate_pagamento compara inteiros (codigoTipoPago é int na API)
- Suporte a detalleFinalizadora como fallback de texto
"""

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

TOLERANCE = 0.05  # R$ 0,05

# Mapa OFICIAL da API Scanntech (doc seção 3.1.2 Vendas, campo pagos[].codigoTipoPago)
PAGAMENTO_MAP: dict[str, list[int]] = {
    "dinheiro":    [9],
    "efetivo":     [9],
    "credito":     [10],
    "crédito":     [10],
    "cheque":      [11],
    "vale":        [12],
    "refeição":    [12],
    "refeicao":    [12],
    "debito":      [13],
    "débito":      [13],
    "pix":         [14],
    "qr":          [14],
    "finalizadora":[15],
}

# Mapa reverso: codigoTipoPago (int) → descrição legível
CODIGO_TIPO_PAGO_DESC: dict[int, str] = {
    9:  "Dinheiro/Efetivo",
    10: "Crédito",
    11: "Cheque",
    12: "Vale/Ticket Refeição",
    13: "Débito",
    14: "PIX/QR",
    15: "Finalizadora",
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

    def validate(
        self,
        tipo: str,
        movement: dict,
        roteiro_row: dict,
    ) -> PromoResult:
        tipo_upper = str(tipo).upper().strip().replace(" ", "_")
        dispatch = {
            "LLEVA_PAGA":          self._llevapaga,
            "LLEVAPAGA":           self._llevapaga,
            "DESCUENTO_VARIABLE":  self._descuento_variable,
            "DESCUENTOVARIABLE":   self._descuento_variable,
            "PRECIO_FIJO":         self._precio_fijo,
            "PRECIOFIJO":          self._precio_fijo,
            "ADICIONAL_REGALO":    self._adicional_regalo,
            "ADICIONALREGALO":     self._adicional_regalo,
            "ADICIONAL_DESCUENTO": self._adicional_descuento,
            "ADICIONALDESCUENTO":  self._adicional_descuento,
            "DESCUENTO_FIJO":      self._descuento_fijo,
            "DESCUENTOFIJO":       self._descuento_fijo,
        }
        fn = dispatch.get(tipo_upper)
        if not fn:
            return PromoResult(ok=False, detalhe=f"Tipo de promoção desconhecido: {tipo}")
        return fn(movement, roteiro_row)

    # ------------------------------------------------------------------
    # Validadores por tipo
    # ------------------------------------------------------------------

    def _llevapaga(self, mov: dict, row: dict) -> PromoResult:
        """Leva M Paga N: lotes × (trigger − paga) × preço_unit ≈ descuentoTotal."""
        try:
            qtd        = float(row.get("qtd", 0))
            trigger    = float(row.get("trigger", 0))
            paga       = float(row.get("paga", trigger))
            preco_unit = float(row.get("preco_unit", 0))
            descuento  = float(mov.get("descuentoTotal", 0))

            if trigger <= 0:
                return PromoResult(ok=False, detalhe="trigger inválido para LLEVA_PAGA")

            lotes = int(qtd // trigger)
            esperado = lotes * (trigger - paga) * preco_unit
            diff = abs(esperado - descuento)
            ok = diff <= TOLERANCE
            return PromoResult(
                ok=ok,
                detalhe="" if ok else (
                    f"LLEVA_PAGA: esperado R${esperado:.2f} "
                    f"descuentoTotal={descuento:.2f} diff={diff:.2f}"
                ),
            )
        except (TypeError, ValueError) as e:
            return PromoResult(ok=False, detalhe=f"LLEVA_PAGA erro: {e}")

    def _descuento_variable(self, mov: dict, row: dict) -> PromoResult:
        """Pack com desconto porcentual. Sem qtd mínima → desconto deve ser zero."""
        try:
            pct       = float(row.get("pct_promo", 0)) / 100
            subtotal  = float(row.get("subtotal_promo", 0))
            descuento = float(mov.get("descuentoTotal", 0))
            qtd_min   = float(row.get("qtd_min", 0))

            if qtd_min == 0 or subtotal == 0:
                ok = abs(descuento) <= TOLERANCE
                return PromoResult(
                    ok=ok,
                    detalhe="" if ok else "DESCUENTO_VARIABLE: sem qtd mínima, desconto deve ser zero"
                )

            esperado = subtotal * pct
            diff = abs(esperado - descuento)
            ok = diff <= TOLERANCE
            return PromoResult(
                ok=ok,
                detalhe="" if ok else (
                    f"DESCUENTO_VARIABLE: esperado R${esperado:.2f} "
                    f"descuentoTotal={descuento:.2f}"
                ),
            )
        except (TypeError, ValueError) as e:
            return PromoResult(ok=False, detalhe=f"DESCUENTO_VARIABLE erro: {e}")

    def _precio_fijo(self, mov: dict, row: dict) -> PromoResult:
        """Produto a preço fixo: lotes × preco_fixo ≈ valor cobrado nos itens participantes."""
        try:
            qtd        = float(row.get("qtd", 0))
            trigger    = float(row.get("trigger", 1))
            preco_fixo = float(row.get("preco_fixo", 0))
            lotes      = int(qtd // trigger)
            esperado   = lotes * preco_fixo

            cobrado = sum(
                float(d.get("valorCobrado", d.get("importe", 0)))
                for d in mov.get("detalles", [])
                if d.get("participante", True)  # sem flag = todos participam
            )
            diff = abs(esperado - cobrado)
            ok = diff <= TOLERANCE
            return PromoResult(
                ok=ok,
                detalhe="" if ok else (
                    f"PRECIO_FIJO: esperado R${esperado:.2f} cobrado={cobrado:.2f}"
                ),
            )
        except (TypeError, ValueError) as e:
            return PromoResult(ok=False, detalhe=f"PRECIO_FIJO erro: {e}")

    def _adicional_regalo(self, mov: dict, row: dict) -> PromoResult:
        """Produto de presente: descuentoTotal > 0 quando presente esperado."""
        presente = str(row.get("presente_esperado", "")).strip().lower()
        descuento = float(mov.get("descuentoTotal", 0))
        if presente in ("sim", "yes", "1", "true", "s"):
            ok = descuento > 0
            return PromoResult(
                ok=ok,
                detalhe="" if ok else "ADICIONAL_REGALO: presente esperado mas descuentoTotal=0",
            )
        return PromoResult(ok=True)

    def _adicional_descuento(self, mov: dict, row: dict) -> PromoResult:
        """Desconto % sobre itens do pack: descuento_item / importeUnitario ≈ pct_promo ± 2%."""
        try:
            pct_esperado = float(row.get("pct_promo", 0)) / 100
            detalhes = mov.get("detalles", [])
            resultados = []
            for d in detalhes:
                # importeUnitario = preço unitário sem desconto (campo oficial da API)
                preco = float(d.get("importeUnitario", d.get("precio", 0)))
                desc  = float(d.get("descuento", 0))
                if preco == 0 or desc == 0:
                    continue
                pct_real = desc / preco
                resultados.append(abs(pct_real - pct_esperado) <= 0.02)

            if not resultados:
                return PromoResult(ok=False, detalhe="ADICIONAL_DESCUENTO: sem itens com desconto")

            ok = all(resultados)
            return PromoResult(
                ok=ok,
                detalhe="" if ok else (
                    f"ADICIONAL_DESCUENTO: pct esperado={pct_esperado*100:.1f}% — divergência"
                ),
            )
        except (TypeError, ValueError) as e:
            return PromoResult(ok=False, detalhe=f"ADICIONAL_DESCUENTO erro: {e}")

    def _descuento_fijo(self, mov: dict, row: dict) -> PromoResult:
        """Pack com desconto fixo: descuentoTotal ≈ valor_fixo."""
        try:
            valor_fixo = float(row.get("valor_fixo", 0))
            descuento  = float(mov.get("descuentoTotal", 0))
            diff = abs(valor_fixo - descuento)
            ok = diff <= TOLERANCE
            return PromoResult(
                ok=ok,
                detalhe="" if ok else (
                    f"DESCUENTO_FIJO: esperado R${valor_fixo:.2f} "
                    f"descuentoTotal={descuento:.2f}"
                ),
            )
        except (TypeError, ValueError) as e:
            return PromoResult(ok=False, detalhe=f"DESCUENTO_FIJO erro: {e}")

    # ------------------------------------------------------------------
    # Validações auxiliares
    # ------------------------------------------------------------------

    def validate_pagamento(self, movimento_codigo: Any, roteiro_tipo: str) -> PromoResult:
        """
        Valida meio de pagamento comparando codigoTipoPago (int) da API.
        movimento_codigo: valor de pagos[0].codigoTipoPago (inteiro)
        roteiro_tipo: texto do roteiro (ex: 'Dinheiro', 'Crédito', 'Débito', 'PIX')
        """
        try:
            codigo_mov = int(movimento_codigo)
        except (TypeError, ValueError):
            return PromoResult(
                ok=False,
                detalhe=f"Pagamento: codigoTipoPago inválido → '{movimento_codigo}'"
            )

        roteiro_norm = str(roteiro_tipo).lower().strip()
        # Remove acentos simples para comparação
        roteiro_norm = (
            roteiro_norm
            .replace("é", "e").replace("ê", "e")
            .replace("ó", "o").replace("ô", "o")
            .replace("ã", "a").replace("ç", "c")
            .replace("í", "i").replace("á", "a")
        )

        for label, codigos in PAGAMENTO_MAP.items():
            label_norm = (
                label
                .replace("é", "e").replace("ê", "e")
                .replace("ó", "o").replace("ô", "o")
                .replace("ã", "a").replace("ç", "c")
                .replace("í", "i").replace("á", "a")
            )
            if label_norm in roteiro_norm or roteiro_norm in label_norm:
                ok = codigo_mov in codigos
                desc_real = CODIGO_TIPO_PAGO_DESC.get(codigo_mov, str(codigo_mov))
                return PromoResult(
                    ok=ok,
                    detalhe="" if ok else (
                        f"Pagamento: esperado '{label}' (código {codigos}), "
                        f"recebido código {codigo_mov} ({desc_real})"
                    ),
                )

        return PromoResult(
            ok=False,
            detalhe=f"Tipo pagamento não mapeado no roteiro: '{roteiro_tipo}'"
        )

    def validate_bin(
        self, movement: dict, bin_esperado: str
    ) -> PromoResult:
        """
        Valida BIN do cartão lendo pagos[0].bin.
        BIN pode ter 6 ou 8 dígitos conforme a API.
        """
        pagos = movement.get("pagos", [])
        bin_mov = ""
        if pagos:
            bin_mov = str(pagos[0].get("bin", "")).strip()

        bin_esp = str(bin_esperado).strip()
        ok = bin_esp in bin_mov or bin_mov.startswith(bin_esp[:6])
        return PromoResult(
            ok=ok,
            detalhe="" if ok else f"BIN esperado {bin_esp}, encontrado {bin_mov}",
        )

    def validate_schema(self, movement: dict) -> PromoResult:
        """Valida campos obrigatórios da API: total, numero, detalles, pagos."""
        campos = ["total", "numero", "detalles", "pagos"]
        faltando = [c for c in campos if c not in movement]
        ok = len(faltando) == 0
        return PromoResult(
            ok=ok,
            detalhe="" if ok else f"Schema: campos ausentes {faltando}",
        )

    def validate_desconto_manual(
        self, movement: dict, obs: str, promo_ativa: bool
    ) -> PromoResult:
        """Rejeita desconto manual quando promoção Scanntech ativa e obs='sem desconto manual'."""
        if not promo_ativa:
            return PromoResult(ok=True)
        if "sem desconto manual" in str(obs).lower():
            descuento = float(movement.get("descuentoManual", 0))
            ok = abs(descuento) <= TOLERANCE
            return PromoResult(
                ok=ok,
                detalhe="" if ok else f"Desconto manual indevido: R${descuento:.2f}",
            )
        return PromoResult(ok=True)
