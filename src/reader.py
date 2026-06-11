"""
Reader da planilha de roteiro de testes.

Regras fixas (alinhadas com o TEMPLATE real):
  - Linha 7 (row_number=7)  → título / cabeçalho das colunas.
  - Linha 8 em diante       → linhas de teste (não são sequenciais).
  - Uma linha é considerada teste válido quando a coluna-índi ce
    mapeada para "teste" estiver preenchida.
  - Linhas totalmente vazias e linhas de separador/título de bloco
    (sem valor na coluna "teste") são ignoradas sem interromper a
    varredura — o loop NÃO para no primeiro vazio.
  - O número real da linha na planilha (índi ce Excel 1-based) é
    preservado no campo "xlsx_row" de cada registro.

Isoómero de _detect_blocks: como o cabeçalho é FIXO na linha 7,
  não precisamos mais varrer blocos múltiplos. Mantemos
  _detect_blocks como fallback caso a linha 7 não case.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import unicodedata

import pandas as pd

# ---------------------------------------------------------------------------
# Mapeamento de colunas
# ---------------------------------------------------------------------------

COLUMN_ALIASES: Dict[str, List[str]] = {
    "teste":           ["teste", "test", "caso", "cenario", "cenário"],
    "tipo_promo":      ["tipo promo", "tipo promocion", "tipo promoção", "tipo_promo"],
    "numero_cupom":    [
        "numero", "numero_cupom", "n cupom", "n° cupom", "nº cupom",
        "num cupom", "número cupom", "n.cupom",
    ],
    "itens_raw":       ["itens da venda", "itens", "articulos", "produtos"],
    "pagamento_raw":   ["pagamento", "pago", "forma de pago", "forma pagamento", "meio pag"],
    "observacoes_raw": ["observacoes", "observações", "obs", "observacion"],
    "subtotal_raw":    ["sub-total", "subtotal", "sub total"],
    "desconto_raw":    ["desconto", "descuento", "desc"],
    "total_raw":       ["total"],
    "ean_raw":         ["ean", "eans", "codigo_barras", "cod_barra", "ean/upc"],
    "bin_raw":         ["bin"],
    "promo_ativa_raw": ["promo ativa", "promo_ativa", "ativa"],
}

# Colunas obrigatórias para validar linha de cabeçalho
REQUIRED_COLS = {"teste", "total_raw"}

# Linha de cabeçalho padrão do TEMPLATE (1-based, igual ao número no Excel)
DEFAULT_HEADER_ROW = 7


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm(value: Any) -> str:
    s = str(value).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def _match_columns(row: List[Any]) -> Dict[str, int]:
    """Casa a linha com os aliases e retorna mapeamento campo→índiçe."""
    normalized = [_norm(c) for c in row]
    mapping: Dict[str, int] = {}
    for internal, aliases in COLUMN_ALIASES.items():
        for i, col in enumerate(normalized):
            if any(alias in col for alias in aliases):
                if internal not in mapping:
                    mapping[internal] = i
                break
    if REQUIRED_COLS.issubset(mapping.keys()):
        return mapping
    return {}


def _is_empty_row(row: pd.Series) -> bool:
    return all(str(v).strip() in ("", "nan", "None") for v in row.values)


def _safe_val(raw) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip()
    return None if s in ("", "nan", "None") else s


# ---------------------------------------------------------------------------
# Detecção de cabeçalho
# ---------------------------------------------------------------------------

def _find_header_row(df: pd.DataFrame, preferred_row: int = DEFAULT_HEADER_ROW) -> int:
    """
    Tenta usar a linha preferred_row (1-based) como cabeçalho.
    Se não casar com REQUIRED_COLS, faz varredura completa.
    Retorna o índiçe 0-based do DataFrame.
    """
    preferred_idx = preferred_row - 1  # converte para 0-based

    if preferred_idx < len(df):
        mapping = _match_columns(list(df.iloc[preferred_idx].values))
        if mapping:
            print(f"[INFO] Cabeçalho encontrado na linha {preferred_row} (padrão do TEMPLATE).")
            return preferred_idx

    # Fallback: varredura linha a linha
    for idx in range(len(df)):
        if _match_columns(list(df.iloc[idx].values)):
            row_num = idx + 1
            print(f"[INFO] Cabeçalho detectado por varredura na linha {row_num}.")
            return idx

    raise ValueError(
        f"Nenhum cabeçalho válido encontrado. "
        f"Verifique se as colunas obrigatórias ({REQUIRED_COLS}) estão presentes."
    )


# ---------------------------------------------------------------------------
# Extracção de linhas de teste
# ---------------------------------------------------------------------------

def _extract_test_rows(
    df: pd.DataFrame,
    header_idx: int,
    col_map: Dict[str, int],
) -> List[Dict[str, Any]]:
    """
    Varre TODAS as linhas abaixo do cabeçalho.

    Regras:
      - NÃÃO para em linha vazia (linhas não são sequenciais).
      - Inclui a linha somente se o campo "teste" estiver preenchido.
      - Linhas de separador, título de bloco ou totalmente vazias
        são simplesmente ignoradas e a varredura continua.
      - xlsx_row = índiçe 1-based real na planilha (header_idx+1 é a
        linha do cabeçalho no Excel; a primeira linha de dado é
        header_idx+2 em 1-based).
    """
    rows: List[Dict[str, Any]] = []
    teste_col = col_map["teste"]

    for df_idx in range(header_idx + 1, len(df)):
        row = df.iloc[df_idx]
        xlsx_row = df_idx + 1  # converte para 1-based (número real no Excel)

        # Linha totalmente vazia → ignora, mas NÃÃO interrompe
        if _is_empty_row(row):
            continue

        # Sem valor na coluna "teste" → linha de título de bloco ou separador
        teste_val = _safe_val(row.iloc[teste_col])
        if not teste_val:
            continue

        # Monta registro com todos os campos mapeados
        record: Dict[str, Any] = {"xlsx_row": xlsx_row}
        for field, col_idx in col_map.items():
            record[field] = _safe_val(row.iloc[col_idx])

        rows.append(record)

    return rows


# ---------------------------------------------------------------------------
# Ponto de entrada pública
# ---------------------------------------------------------------------------

def load_roteiro_tests(
    path: Path,
    header_row: int = DEFAULT_HEADER_ROW,
) -> List[Dict[str, Any]]:
    """
    Carrega o roteiro e devolve lista de registros no modelo interno.

    Parâmetros
    ----------
    path       : caminho do arquivo XLSX
    header_row : linha de título no Excel (padrão=7, 1-based)

    Retorno
    -------
    Lista de dicts, cada um representando um caso de teste.
    Cada dict contém "xlsx_row" com o número real da linha na planilha.
    """
    df = pd.read_excel(path, header=None, dtype=str)
    header_idx = _find_header_row(df, preferred_row=header_row)
    col_map    = _match_columns(list(df.iloc[header_idx].values))

    rows = _extract_test_rows(df, header_idx, col_map)

    print(f"[INFO] {len(rows)} caso(s) de teste carregado(s) "
          f"(linhas não-sequenciais suportadas).")

    return rows
