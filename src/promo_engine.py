"""
Módulo 4 — PromoEngine
Responsabilidade: Motor de validação por tipo de promoção.
"""
import logging
import math
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

TOLERANCE = 0.05  # R$ 0,05


def _round2(v) -> float:
    try:
        return round(float(v or 0), 2)
    except (TypeError, ValueError):
        return 0.0


class PromoEngine:
    """
    Motor de validação de promoções Scanntech.
    Cada método recebe o movimento (dict do Audit) e parâmetros do roteiro.
    Retorna (ok: bool, detalhe: str).
    """

    @staticmethod
    def validate_llevapaga(
        mov: dict,
        qtd_compra: float,
        qtd_paga: float,
        preco_unit: float,
        roteiro_desconto: float,
    ) -> Tuple[bool, str]:
        """Leva M paga N: desconto = lotes × (M - N) × preço_unit"""
        descuento_mov = _round2(mov.get("descuentoTotal", 0))
        if qtd_compra <= 0 or qtd_paga <= 0 or qtd_paga >= qtd_compra:
            return False, f"Parâmetros LLEVAPAGA inválidos: M={qtd_compra}, N={qtd_paga}"
        desconto_esperado = _round2(roteiro_desconto)
        ok = abs(descuento_mov - desconto_esperado) <= TOLERANCE
        detalhe = (
            f"LLEVAPAGA OK: descuento={descuento_mov} ≈ esperado={desconto_esperado}"
            if ok else
            f"LLEVAPAGA ERRO: descuento={descuento_mov} ≠ esperado={desconto_esperado} (Δ={abs(descuento_mov-desconto_esperado):.2f})"
        )
        return ok, detalhe

    @staticmethod
    def validate_descuentovariable(
        mov: dict,
        subtotal_promo: float,
        pct: float,
        qtd_minima: Optional[float],
        qtd_comprada: Optional[float],
        roteiro_desconto: float,
    ) -> Tuple[bool, str]:
        """Pack com desconto percentual fixo."""
        descuento_mov = _round2(mov.get("descuentoTotal", 0))
        atingiu = True
        if qtd_minima and qtd_comprada is not None:
            atingiu = qtd_comprada >= qtd_minima
        if not atingiu:
            ok = abs(descuento_mov) <= TOLERANCE
            detalhe = (
                f"DESCUENTOVARIABLE: qtd={qtd_comprada} < min={qtd_minima} → desconto=0. "
                f"Mov: {descuento_mov}"
            )
            return ok, detalhe
        desconto_esperado = _round2(subtotal_promo * pct / 100)
        ok = abs(descuento_mov - desconto_esperado) <= TOLERANCE
        detalhe = (
            f"DESCUENTOVARIABLE OK: {subtotal_promo}×{pct}%={desconto_esperado} vs mov={descuento_mov}"
            if ok else
            f"DESCUENTOVARIABLE ERRO: esperado={desconto_esperado} vs mov={descuento_mov}"
        )
        return ok, detalhe

    @staticmethod
    def validate_preciofijo(
        mov: dict,
        lotes: int,
        preco_fixo: float,
        roteiro_total_itens: float,
    ) -> Tuple[bool, str]:
        """Preço fixo: lotes × preço_fixo vs valor cobrado nos itens participantes."""
        valor_esperado = _round2(lotes * preco_fixo)
        ok = abs(roteiro_total_itens - valor_esperado) <= TOLERANCE
        detalhe = (
            f"PRECIOFIJO OK: {lotes}×{preco_fixo}={valor_esperado} vs roteiro={roteiro_total_itens}"
            if ok else
            f"PRECIOFIJO ERRO: esperado={valor_esperado} vs roteiro={roteiro_total_itens}"
        )
        return ok, detalhe

    @staticmethod
    def validate_adicionalregalo(
        mov: dict,
        presente_esperado: bool,
    ) -> Tuple[bool, str]:
        """Produto de presente: quando presente esperado, descuentoTotal > 0."""
        descuento_mov = _round2(mov.get("descuentoTotal", 0))
        if presente_esperado:
            ok = descuento_mov > 0
            detalhe = (
                f"ADICIONALREGALO OK: descuento={descuento_mov} > 0"
                if ok else
                f"ADICIONALREGALO ERRO: presente esperado mas descuento={descuento_mov}"
            )
        else:
            ok = abs(descuento_mov) <= TOLERANCE
            detalhe = (
                f"ADICIONALREGALO OK: sem presente, descuento={descuento_mov}≈0"
                if ok else
                f"ADICIONALREGALO ERRO: sem presente mas descuento={descuento_mov}"
            )
        return ok, detalhe

    @staticmethod
    def validate_adicionaldescuento(
        mov: dict,
        descuento_item: float,
        preco_item: float,
        pct_promo: float,
    ) -> Tuple[bool, str]:
        """Desconto percentual sobre item específico. descuento_item / preco_item ≈ pct_promo ± 2%"""
        if preco_item <= 0:
            return False, f"ADICIONALDESCUENTO: preço_item inválido ({preco_item})"
        pct_real = (descuento_item / preco_item) * 100
        ok = abs(pct_real - pct_promo) <= 2.0
        detalhe = (
            f"ADICIONALDESCUENTO OK: {descuento_item}/{preco_item}={pct_real:.1f}% ≈ {pct_promo}%"
            if ok else
            f"ADICIONALDESCUENTO ERRO: real={pct_real:.1f}% vs esperado={pct_promo}% (Δ={abs(pct_real-pct_promo):.1f}%)"
        )
        return ok, detalhe

    @staticmethod
    def validate_descuentofijo(
        mov: dict,
        valor_fixo: float,
    ) -> Tuple[bool, str]:
        """Pack com desconto fixo: descuentoTotal deve bater com valor fixo."""
        descuento_mov = _round2(mov.get("descuentoTotal", 0))
        ok = abs(descuento_mov - _round2(valor_fixo)) <= TOLERANCE
        detalhe = (
            f"DESCUENTOFIJO OK: descuento={descuento_mov} ≈ fixo={valor_fixo}"
            if ok else
            f"DESCUENTOFIJO ERRO: descuento={descuento_mov} ≠ fixo={valor_fixo}"
        )
        return ok, detalhe

    @classmethod
    def validate(cls, tipo_promo: str, mov: dict, params: dict) -> Tuple[bool, str]:
        """Dispatcher principal por tipo de promoção."""
        tipo = str(tipo_promo).upper().strip()
        try:
            if tipo in ("LLEVAPAGA", "LLEVA_PAGA"):
                return cls.validate_llevapaga(
                    mov,
                    params.get("qtd_compra", 0),
                    params.get("qtd_paga", 0),
                    params.get("preco_unit", 0),
                    params.get("roteiro_desconto", 0),
                )
            elif tipo in ("DESCUENTOVARIABLE", "DESCUENTO_VARIABLE"):
                return cls.validate_descuentovariable(
                    mov,
                    params.get("subtotal_promo", 0),
                    params.get("pct", 0),
                    params.get("qtd_minima"),
                    params.get("qtd_comprada"),
                    params.get("roteiro_desconto", 0),
                )
            elif tipo in ("PRECIOFIJO", "PRECIO_FIJO"):
                return cls.validate_preciofijo(
                    mov,
                    params.get("lotes", 1),
                    params.get("preco_fixo", 0),
                    params.get("roteiro_total_itens", 0),
                )
            elif tipo in ("ADICIONALREGALO", "ADICIONAL_REGALO"):
                return cls.validate_adicionalregalo(
                    mov,
                    params.get("presente_esperado", True),
                )
            elif tipo in ("ADICIONALDESCUENTO", "ADICIONAL_DESCUENTO"):
                return cls.validate_adicionaldescuento(
                    mov,
                    params.get("descuento_item", 0),
                    params.get("preco_item", 0),
                    params.get("pct_promo", 0),
                )
            elif tipo in ("DESCUENTOFIJO", "DESCUENTO_FIJO"):
                return cls.validate_descuentofijo(
                    mov,
                    params.get("valor_fixo", 0),
                )
            else:
                return False, f"Tipo de promoção desconhecido: {tipo_promo}"
        except Exception as e:
            logger.error(f"Erro ao validar promoção {tipo_promo}: {e}")
            return False, f"Exceção em validate({tipo_promo}): {e}"
