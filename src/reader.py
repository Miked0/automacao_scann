from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from models import TestCase

COLUMN_ALIASES = {
    'teste': ['teste'],
    'tipo_promo': ['tipo promo', 'tipo promocion', 'promo'],
    'itens_raw': ['itens da venda', 'articulos movimiento', 'articulos', 'items'],
    'pagamento_raw': ['pagamento', 'pago', 'forma de pagamento'],
    'observacoes_raw': ['observacoes', 'observações', 'obs', 'observacion', 'observaciones'],
    'subtotal_raw': ['sub-total', 'subtotal'],
    'desconto_raw': ['desconto', 'descuento'],
    'total_raw': ['total'],
    'status_tecnico_raw': ['status tecnico', 'status técnico', 'status'],
}
REQUIRED_FIELDS = {'teste', 'total_raw', 'itens_raw'}


def _normalize_text(value: Any) -> str:
    if value is None:
        return ''
    text = str(value).strip().lower()
    return ' '.join(text.split())


def _row_values(row: pd.Series) -> List[str]:
    return [_normalize_text(v) for v in row.tolist()]


def _match_columns(header_row: List[Any]) -> Dict[str, int]:
    normalized = [_normalize_text(c) for c in header_row]
    mapping: Dict[str, int] = {}
    for internal, aliases in COLUMN_ALIASES.items():
        for i, col in enumerate(normalized):
            if any(alias in col for alias in aliases):
                mapping[internal] = i
                break
    return mapping if REQUIRED_FIELDS.issubset(mapping.keys()) else {}


def _is_new_header(row: pd.Series) -> bool:
    return bool(_match_columns(row.tolist()))


def _looks_like_test_id(value: Any) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    text = str(value).strip()
    if not text:
        return False
    return any(ch.isdigit() for ch in text)


def _extract_block_name(df: pd.DataFrame, header_row_index: int) -> str:
    start = max(0, header_row_index - 3)
    for idx in range(header_row_index - 1, start - 1, -1):
        row_text = ' | '.join([t for t in _row_values(df.iloc[idx]) if t])
        if row_text and 'teste' not in row_text and len(row_text) > 3:
            return row_text[:120]
    return f'Bloco_{header_row_index + 1}'


def find_blocks(df: pd.DataFrame) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    for idx, row in df.iterrows():
        mapping = _match_columns(row.tolist())
        if mapping:
            blocks.append({
                'bloco_nome': _extract_block_name(df, idx),
                'header_row_index': idx,
                'column_mapping': mapping,
            })
    return blocks


def _safe_get(row: pd.Series, idx: Optional[int]) -> Any:
    if idx is None:
        return None
    if idx >= len(row):
        return None
    return row.iloc[idx]


def load_roteiro_tests(path: Path, sheet_name: int | str = 0) -> Tuple[List[TestCase], List[Dict[str, Any]]]:
    df = pd.read_excel(path, header=None, sheet_name=sheet_name, dtype=object)
    blocks = find_blocks(df)
    tests: List[TestCase] = []

    for block in blocks:
        bloco_nome = block['bloco_nome']
        header_row_index = block['header_row_index']
        col_map = block['column_mapping']

        for idx in range(header_row_index + 1, len(df)):
            row = df.iloc[idx]
            if row.isna().all():
                break
            if _is_new_header(row):
                break

            teste_val = _safe_get(row, col_map.get('teste'))
            itens_val = _safe_get(row, col_map.get('itens_raw'))
            total_val = _safe_get(row, col_map.get('total_raw'))

            if not _looks_like_test_id(teste_val):
                continue
            if all(v is None or str(v).strip() == '' or (isinstance(v, float) and pd.isna(v)) for v in [itens_val, total_val]):
                continue

            known_indices = set(col_map.values())
            extra_fields = {}
            for c_idx, value in enumerate(row.tolist()):
                if c_idx not in known_indices and value is not None and str(value).strip() != '':
                    extra_fields[f'extra_col_{c_idx}'] = value

            tests.append(TestCase(
                bloco=bloco_nome,
                row_index=idx,
                teste=teste_val,
                tipo_promo=_safe_get(row, col_map.get('tipo_promo')),
                itens_raw=_safe_get(row, col_map.get('itens_raw')),
                pagamento_raw=_safe_get(row, col_map.get('pagamento_raw')),
                observacoes_raw=_safe_get(row, col_map.get('observacoes_raw')),
                subtotal_raw=_safe_get(row, col_map.get('subtotal_raw')),
                desconto_raw=_safe_get(row, col_map.get('desconto_raw')),
                total_raw=_safe_get(row, col_map.get('total_raw')),
                status_tecnico_raw=_safe_get(row, col_map.get('status_tecnico_raw')),
                extra_fields=extra_fields,
            ))

    return tests, blocks
