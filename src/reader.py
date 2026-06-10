"""Reader da planilha de roteiro de testes.

Responsabilidades:
- Abrir o arquivo XLSX sem assumir posição de cabeçalho
- Localizar automaticamente linhas de cabeçalho úteis
- Identificar blocos de teste (Venda Normal, Cancelamento, etc.)
- Extrair apenas linhas que são casos de teste reais
- Montar o modelo interno base com campos brutos
"""
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

# Mapeamento interno -> lista de aliases aceitos (lowercase, sem acentos)
COLUMN_ALIASES: Dict[str, List[str]] = {
    "teste": ["teste", "test", "caso"],
    "tipo_promo": ["tipo promo", "tipo promocion", "tipo promoção", "tipo_promo"],
    "itens_raw": [
        "itens da venda",
        "itens",
        "articulos movimiento",
        "articulos",
        "produtos",
    ],
    "pagamento_raw": ["pagamento", "pago", "forma de pago", "forma pagamento"],
    "observacoes_raw": [
        "observacoes",
        "observações",
        "obs",
        "observacion",
        "observaciones",
    ],
    "subtotal_raw": ["sub-total", "subtotal", "sub total"],
    "desconto_raw": ["desconto", "descuento", "desc"],
    "total_raw": ["total"],
}

# Colunas obrigatórias para considerar uma linha como cabeçalho válido
REQUIRED_COLS = {"teste", "total_raw"}


def _norm(value: Any) -> str:
    """Normaliza valor para comparação: lowercase, sem espaços extras."""
    import unicodedata
    s = str(value).strip().lower()
    # remove acentos
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s


def _match_columns(row: List[Any]) -> Dict[str, int]:
    """Tenta casar a linha com os aliases e retorna mapeamento campo->índice."""
    normalized = [_norm(c) for c in row]
    mapping: Dict[str, int] = {}
    for internal, aliases in COLUMN_ALIASES.items():
        for i, col in enumerate(normalized):
            if any(alias in col for alias in aliases):
                if internal not in mapping:  # primeiro match vence
                    mapping[internal] = i
                break
    if REQUIRED_COLS.issubset(mapping.keys()):
        return mapping
    return {}


def _detect_blocks(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Percorre o dataframe procurando linhas que parecem cabeçalho.

    Retorna lista de blocos com nome, índice da linha de cabeçalho
    e mapeamento de colunas.
    """
    blocks: List[Dict[str, Any]] = []
    for idx in range(len(df)):
        row = list(df.iloc[idx].values)
        mapping = _match_columns(row)
        if mapping:
            # tenta capturar nome do bloco a partir de linhas acima
            bloco_nome = _infer_block_name(df, idx, len(blocks) + 1)
            blocks.append(
                {
                    "bloco_nome": bloco_nome,
                    "header_row_index": idx,
                    "column_mapping": mapping,
                }
            )
    return blocks


def _infer_block_name(df: pd.DataFrame, header_idx: int, fallback_num: int) -> str:
    """Tenta encontrar o nome do bloco nas linhas anteriores ao cabeçalho."""
    for lookback in range(1, 5):
        candidate_idx = header_idx - lookback
        if candidate_idx < 0:
            break
        row_vals = [str(v).strip() for v in df.iloc[candidate_idx].values if str(v).strip() not in ("", "nan", "None")]
        if row_vals:
            name = row_vals[0]
            # só aceita como nome se parecer título (sem números puros, tamanho razoável)
            if len(name) > 3 and not name.replace(".", "").replace(",", "").isdigit():
                return name
    return f"Bloco_{fallback_num}"


def _is_empty_row(row: pd.Series) -> bool:
    return row.isna().all() or all(str(v).strip() in ("", "nan", "None") for v in row.values)


def _extract_rows(df: pd.DataFrame, block: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extrai as linhas de teste de um bloco."""
    col_map = block["column_mapping"]
    header_idx = block["header_row_index"]
    bloco_nome = block["bloco_nome"]
    rows: List[Dict[str, Any]] = []

    for idx in range(header_idx + 1, len(df)):
        row = df.iloc[idx]
        if _is_empty_row(row):
            break
        # ignora linhas sem identificador de teste
        teste_val = row.iloc[col_map["teste"]]
        if pd.isna(teste_val) or str(teste_val).strip() in ("", "nan", "None"):
            continue

        record: Dict[str, Any] = {"bloco": bloco_nome}
        for field, col_idx in col_map.items():
            raw_val = row.iloc[col_idx]
            record[field] = None if pd.isna(raw_val) or str(raw_val).strip() in ("nan", "None") else str(raw_val).strip()
        rows.append(record)
    return rows


def load_roteiro_tests(path: Path) -> List[Dict[str, Any]]:
    """Carrega o roteiro e devolve lista de registros no modelo interno base."""
    df = pd.read_excel(path, header=None, dtype=str)
    blocks = _detect_blocks(df)

    if not blocks:
        raise ValueError("Nenhum bloco de teste encontrado na planilha. Verifique os cabeçalhos.")

    print(f"[INFO] {len(blocks)} bloco(s) detectado(s): {[b['bloco_nome'] for b in blocks]}")

    all_tests: List[Dict[str, Any]] = []
    for block in blocks:
        rows = _extract_rows(df, block)
        print(f"  → {block['bloco_nome']}: {len(rows)} caso(s)")
        all_tests.extend(rows)
    return all_tests
