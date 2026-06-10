from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, List

from models import NumericField, TestCase, ValidationResult
from parser_items import parse_itens
from payments import normalize_pagamento

TOLERANCIA = Decimal('0.01')
TWOPLACES = Decimal('0.01')


def to_decimal_field(value: Any) -> NumericField:
    if value is None:
        return NumericField(raw=value, norm=None, error=True)
    text = str(value).strip()
    if text == '':
        return NumericField(raw=value, norm=None, error=True)
    try:
        cleaned = text.replace(',', '.')
        raw = Decimal(cleaned)
        norm = raw.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        return NumericField(raw=value, norm=norm, error=False)
    except (InvalidOperation, ValueError):
        return NumericField(raw=value, norm=None, error=True)


def validate_test_case(test: TestCase) -> TestCase:
    motivos: List[str] = []
    alertas: List[str] = []
    status = 'OK'

    if not str(test.teste).strip():
        status = 'ERRO_VALOR'
        motivos.append('Teste sem identificador')

    itens, item_alerts = parse_itens(test.itens_raw)
    test.itens_parseados = itens
    alertas.extend(item_alerts)
    if test.itens_raw and not itens:
        status = 'ERRO_PARSE'
        motivos.append('Falha ao parsear itens')

    test.pagamento_info = normalize_pagamento(test.pagamento_raw)
    if test.pagamento_raw and test.pagamento_info.codigo_tipo_pago is None and not test.pagamento_info.is_multiplo:
        status = 'ERRO_PAGAMENTO'
        motivos.append('Pagamento não mapeado')
    if test.pagamento_info.is_multiplo:
        if status == 'OK':
            status = 'REVISAR'
        alertas.append('Pagamento com múltiplos meios requer revisão controlada')

    test.subtotal = to_decimal_field(test.subtotal_raw)
    test.desconto = to_decimal_field(test.desconto_raw)
    test.total = to_decimal_field(test.total_raw)

    if test.subtotal.error:
        status = 'ERRO_VALOR'
        motivos.append('Subtotal não numérico')
    if test.desconto.error:
        status = 'ERRO_VALOR'
        motivos.append('Desconto não numérico')
    if test.total.error:
        status = 'ERRO_VALOR'
        motivos.append('Total não numérico')

    if not test.subtotal.error and not test.desconto.error and not test.total.error:
        esperado = (test.subtotal.norm - test.desconto.norm).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        diff = abs(esperado - test.total.norm)
        if diff > TOLERANCIA:
            status = 'ERRO_VALOR'
            motivos.append(f'Total não fecha com subtotal - desconto (dif {diff})')
        elif diff > Decimal('0'):
            if status == 'OK':
                status = 'ALERTA'
            alertas.append(f'Diferença de {diff} dentro da tolerância')

    obs = str(test.observacoes_raw or '').lower()
    if '0,01' in obs or '0.01' in obs:
        alertas.append('Observação menciona tolerância de 0,01')
    if 'ratead' in obs or 'rateio' in obs:
        alertas.append('Observação indica desconto rateado')
    if 'não aplicada' in obs or 'nao aplicada' in obs:
        if status == 'OK':
            status = 'REVISAR'
        alertas.append('Observação indica promoção não aplicada')

    test.validation = ValidationResult(
        status_final=status,
        motivo_status='; '.join(dict.fromkeys(motivos)) if motivos else None,
        alertas=list(dict.fromkeys(alertas)),
    )
    return test
