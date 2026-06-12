"""
Motor de validação por tipo de promoção.

Tipos suportados: LLEVA_PAGA, DESCUENTO_VARIABLE, PRECIO_FIJO,
                  ADICIONAL_REGALO, ADICIONAL_DESCUENTO, DESCUENTO_FIJO.

Códigos de tipo de pagamento (campo pagos[].codigoTipoPago):
  9=Dinheiro/Efetivo, 10=Crédito, 11=Cheque, 12=Vale,
  13=Débito, 14=PIX/QR, 15=Finalizadora
"""
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

TOLERANCIA = 0.05  # R$ 0,05

MAPA_PAGAMENTO: dict[str, list[int]] = {
    "dinheiro":    [9],
    "efetivo":     [9],
    "credito":     [10],
    "cheque":      [11],
    "vale":        [12],
    "refeicao":    [12],
    "debito":      [13],
    "pix":         [14],
    "qr":          [14],
    "finalizadora":[15],
}

DESC_CODIGO_TIPO_PAGO: dict[int, str] = {
    9:  "Dinheiro/Efetivo",
    10: "Crédito",
    11: "Cheque",
    12: "Vale/Ticket Refeição",
    13: "Débito",
    14: "PIX/QR",
    15: "Finalizadora",
}


def _remover_acentos(texto: str) -> str:
    import unicodedata
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normalizado if not unicodedata.combining(c))


def _normalizar_label(texto: str) -> str:
    return _remover_acentos(str(texto).lower().strip())


@dataclass
class ResultadoPromo:
    ok: bool
    detalhe: str = ""


class MotorPromocoes:
    """Valida cada tipo de promoção do PDV."""

    def validar(self, tipo: str, movimento: dict, linha_roteiro: dict) -> ResultadoPromo:
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
            return ResultadoPromo(ok=False, detalhe=f"Tipo de promoção desconhecido: {tipo}")
        return fn(movimento, linha_roteiro)

    # Alias de compatibilidade
    def validate(self, tipo, movement, roteiro_row):
        return self.validar(tipo, movement, roteiro_row)

    def _llevapaga(self, mov: dict, row: dict) -> ResultadoPromo:
        try:
            qtd        = float(row.get("qtd", 0))
            trigger    = float(row.get("trigger", 0))
            paga       = float(row.get("paga", 0))
            preco_unit = float(row.get("preco_unit", 0))
            if trigger == 0:
                return ResultadoPromo(ok=False, detalhe="LLEVA_PAGA: trigger=0")
            lotes    = int(qtd // trigger)
            esperado = lotes * (trigger - paga) * preco_unit
            desconto = float(mov.get("descuentoTotal", 0))
            diff     = abs(esperado - desconto)
            ok       = diff <= TOLERANCIA
            return ResultadoPromo(
                ok=ok,
                detalhe="" if ok else
                    f"LLEVA_PAGA: esperado R${esperado:.2f} descuentoTotal={desconto:.2f}",
            )
        except (TypeError, ValueError) as e:
            return ResultadoPromo(ok=False, detalhe=f"LLEVA_PAGA erro: {e}")

    def _descuento_variable(self, mov: dict, row: dict) -> ResultadoPromo:
        try:
            pct      = float(row.get("pct_promo", 0)) / 100
            subtotal = float(mov.get("subtotal", mov.get("importe", 0)))
            desconto = float(mov.get("descuentoTotal", 0))
            qtd_min  = float(row.get("qtd_min", 0))
            if qtd_min == 0 or subtotal == 0:
                ok = abs(desconto) <= TOLERANCIA
                return ResultadoPromo(
                    ok=ok,
                    detalhe="" if ok else "DESCUENTO_VARIABLE: sem qtd mínima, desconto deve ser zero",
                )
            esperado = subtotal * pct
            diff     = abs(esperado - desconto)
            ok       = diff <= TOLERANCIA
            return ResultadoPromo(
                ok=ok,
                detalhe="" if ok else
                    f"DESCUENTO_VARIABLE: esperado R${esperado:.2f} descuentoTotal={desconto:.2f}",
            )
        except (TypeError, ValueError) as e:
            return ResultadoPromo(ok=False, detalhe=f"DESCUENTO_VARIABLE erro: {e}")

    def _precio_fijo(self, mov: dict, row: dict) -> ResultadoPromo:
        try:
            qtd        = float(row.get("qtd", 0))
            trigger    = float(row.get("trigger", 1))
            preco_fixo = float(row.get("preco_fixo", 0))
            lotes      = int(qtd // trigger)
            esperado   = lotes * preco_fixo
            cobrado = sum(
                float(d.get("valorCobrado", d.get("importe", 0)))
                for d in mov.get("detalles", [])
                if d.get("participante", True)
            )
            diff = abs(esperado - cobrado)
            ok   = diff <= TOLERANCIA
            return ResultadoPromo(
                ok=ok,
                detalhe="" if ok else
                    f"PRECIO_FIJO: esperado R${esperado:.2f} cobrado={cobrado:.2f}",
            )
        except (TypeError, ValueError) as e:
            return ResultadoPromo(ok=False, detalhe=f"PRECIO_FIJO erro: {e}")

    def _adicional_regalo(self, mov: dict, row: dict) -> ResultadoPromo:
        presente = str(row.get("presente_esperado", "")).strip().lower()
        desconto = float(mov.get("descuentoTotal", 0))
        if presente in ("sim", "yes", "1", "true", "s"):
            ok = desconto > 0
            return ResultadoPromo(
                ok=ok,
                detalhe="" if ok else "ADICIONAL_REGALO: presente esperado mas descuentoTotal=0",
            )
        return ResultadoPromo(ok=True)

    def _adicional_descuento(self, mov: dict, row: dict) -> ResultadoPromo:
        try:
            pct_esperado = float(row.get("pct_promo", 0)) / 100
            detalhes     = mov.get("detalles", [])
            resultados   = []
            for d in detalhes:
                preco = float(d.get("importeUnitario", d.get("precio", 0)))
                desc  = float(d.get("descuento", 0))
                if preco == 0 or desc == 0:
                    continue
                pct_real = desc / preco
                resultados.append(abs(pct_real - pct_esperado) <= 0.02)
            if not resultados:
                return ResultadoPromo(ok=False, detalhe="ADICIONAL_DESCUENTO: sem itens com desconto")
            ok = all(resultados)
            return ResultadoPromo(
                ok=ok,
                detalhe="" if ok else
                    f"ADICIONAL_DESCUENTO: pct esperado={pct_esperado*100:.1f}% — divergência",
            )
        except (TypeError, ValueError) as e:
            return ResultadoPromo(ok=False, detalhe=f"ADICIONAL_DESCUENTO erro: {e}")

    def _descuento_fijo(self, mov: dict, row: dict) -> ResultadoPromo:
        try:
            valor_fixo = float(row.get("valor_fixo", 0))
            desconto   = float(mov.get("descuentoTotal", 0))
            diff       = abs(valor_fixo - desconto)
            ok         = diff <= TOLERANCIA
            return ResultadoPromo(
                ok=ok,
                detalhe="" if ok else
                    f"DESCUENTO_FIJO: esperado R${valor_fixo:.2f} descuentoTotal={desconto:.2f}",
            )
        except (TypeError, ValueError) as e:
            return ResultadoPromo(ok=False, detalhe=f"DESCUENTO_FIJO erro: {e}")

    # ------------------------------------------------------------------
    # Validações auxiliares
    # ------------------------------------------------------------------

    def validar_pagamento(self, codigo_movimento: Any, tipo_roteiro: str) -> ResultadoPromo:
        try:
            codigo_mov = int(codigo_movimento)
        except (TypeError, ValueError):
            return ResultadoPromo(
                ok=False,
                detalhe=f"Pagamento: codigoTipoPago inválido → '{codigo_movimento}'",
            )
        roteiro_norm = _normalizar_label(tipo_roteiro)
        for label, codigos in MAPA_PAGAMENTO.items():
            label_norm = _normalizar_label(label)
            if label_norm in roteiro_norm or roteiro_norm in label_norm:
                ok        = codigo_mov in codigos
                desc_real = DESC_CODIGO_TIPO_PAGO.get(codigo_mov, str(codigo_mov))
                return ResultadoPromo(
                    ok=ok,
                    detalhe="" if ok else
                        f"Pagamento: esperado '{label}' (código {codigos}), "
                        f"recebido código {codigo_mov} ({desc_real})",
                )
        return ResultadoPromo(
            ok=False,
            detalhe=f"Tipo pagamento não mapeado no roteiro: '{tipo_roteiro}'",
        )

    def validate_pagamento(self, codigo_movimento, tipo_roteiro):
        return self.validar_pagamento(codigo_movimento, tipo_roteiro)

    def validar_bin(self, movimento: dict, bin_esperado: str) -> ResultadoPromo:
        pagos   = movimento.get("pagos", [])
        bin_mov = str(pagos[0].get("bin", "")).strip() if pagos else ""
        bin_esp = str(bin_esperado).strip()
        ok = bin_esp in bin_mov or bin_mov.startswith(bin_esp[:6])
        return ResultadoPromo(
            ok=ok,
            detalhe="" if ok else f"BIN esperado {bin_esp}, encontrado {bin_mov}",
        )

    def validate_bin(self, movimento, bin_esperado):
        return self.validar_bin(movimento, bin_esperado)

    def validar_schema(self, movimento: dict) -> ResultadoPromo:
        campos   = ["total", "numero", "detalles", "pagos"]
        faltando = [c for c in campos if c not in movimento]
        ok       = len(faltando) == 0
        return ResultadoPromo(
            ok=ok,
            detalhe="" if ok else f"Schema: campos ausentes {faltando}",
        )

    def validate_schema(self, movimento):
        return self.validar_schema(movimento)

    def validar_desconto_manual(
        self, movimento: dict, obs: str, promo_ativa: bool
    ) -> ResultadoPromo:
        if not promo_ativa:
            return ResultadoPromo(ok=True)
        if "sem desconto manual" in str(obs).lower():
            desconto = float(movimento.get("descuentoManual", 0))
            ok       = abs(desconto) <= TOLERANCIA
            return ResultadoPromo(
                ok=ok,
                detalhe="" if ok else f"Desconto manual indevido: R${desconto:.2f}",
            )
        return ResultadoPromo(ok=True)

    def validate_desconto_manual(self, movimento, obs, promo_ativa):
        return self.validar_desconto_manual(movimento, obs, promo_ativa)


# Aliases de compatibilidade
PromoEngine = MotorPromocoes
PromoResult = ResultadoPromo
