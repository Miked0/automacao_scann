"""
Reader da planilha de roteiro de testes.

Estrutura real do TEMPLATE:
  Linha 7  → cabeçalho das colunas.
  Linha 8+ → linhas de teste (não-sequenciais: podem ter vazios entre elas).

  Colunas de entrada (preenchidas pelo QA antes da execução):
    A  → Teste (número/id do caso)
    B  → Tipo Promo
    C  → Itens da venda
    D  → Pagamento
    E  → Observacoes
    F  → SAT   (número do cupom SAT  — preenchido pelo parceiro ou QA)
    G  → ECF   (número ECF/COO)
    H  → NFCE  (número NFC-e)
    I  → Sub-Total
    J  → Desconto
    K  → Total
    L  → Json  (status da requisição)
    ...

  Colunas de resultado (preenchidas pelo script):
    R(18), S(19), T(20) → Ok/Erro por canal (SAT/ECF/NFCE)
    U(21)               → Justificativa do erro

  Os campos SAT/ECF/NFCE das colunas F/G/H são lidos como
  número do cupom para busca no Audit e no PDF.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import unicodedata

import pandas as pd

# ---------------------------------------------------------------------------
# Mapeamento de colunas
# ---------------------------------------------------------------------------

COLUMN_ALIASES: Dict[str, List[str]] = {
    # Identificador do caso de teste
    "teste":           ["teste", "test", "caso", "cenario", "cenário"],
    # Tipo de promoção
    "tipo_promo":      ["tipo promo", "tipo promocion", "tipo promoção", "tipo_promo"],
    # Números dos cupons (lidos para busca, não são as colunas de resultado)
    "numero_sat":      ["sat"],
    "numero_ecf":      ["ecf"],
    "numero_nfce":     ["nfce", "nfc-e", "nfc"],
    # Dados da venda
    "itens_raw":       ["itens da venda", "itens", "articulos", "produtos"],
    "pagamento_raw":   ["pagamento", "pago", "forma de pago", "forma pagamento", "meio pag"],
    "observacoes_raw": ["observacoes", "observações", "obs", "observacion"],
    "subtotal_raw":    ["sub-total", "subtotal", "sub total"],
    "desconto_raw":    ["desconto", "descuento", "desc"],
    "total_raw":       ["total"],
    "json_status":     ["json"],
    # EAN e BIN (opcionais)
    "ean_raw":         ["ean", "eans", "codigo_barras", "cod_barra", "ean/upc"],
    "bin_raw":         ["bin"],
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
    """
    Casa a linha de cabeçalho com os aliases.
    Retorna mapeamento campo → îndiçe 0-based.
    Retorna {} se as colunas obrigatórias não forem encontradas.
    """
    normalized = [_norm(c) for c in row]
    mapping: Dict[str, int] = {}
    for internal, aliases in COLUMN_ALIASES.items():
        for i, col in enumerate(normalized):
            if any(col == alias or alias in col for alias in aliases):
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
    Tenta preferred_row (1-based) primeiro.
    Fallback: varredura completa.
    Retorna îndiçe 0-based.
    """
    preferred_idx = preferred_row - 1
    if preferred_idx < len(df):
        if _match_columns(list(df.iloc[preferred_idx].values)):
            print(f"[INFO] Cabeçalho na linha {preferred_row} (padrão do TEMPLATE).")
            return preferred_idx

    for idx in range(len(df)):
        if _match_columns(list(df.iloc[idx].values)):
            print(f"[INFO] Cabeçalho detectado por varredura na linha {idx + 1}.")
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
      - NÃO para em linha vazia (suporte a linhas não-sequenciais).
      - Inclui a linha só se o campo "teste" estiver preenchido.
      - "xlsx_row" = número real 1-based da linha no Excel.
      - "numero_cupom" = primeiro número válido encontrado entre
        SAT → ECF → NFCE (para usar na busca do Audit e PDF).
    """
    rows: List[Dict[str, Any]] = []
    teste_col = col_map["teste"]

    for df_idx in range(header_idx + 1, len(df)):
        row        = df.iloc[df_idx]
        xlsx_row   = df_idx + 1  # 1-based = número real no Excel

        if _is_empty_row(row):
            continue

        teste_val = _safe_val(row.iloc[teste_col])
        if not teste_val:
            continue  # linha de separador ou título de bloco

        record: Dict[str, Any] = {"xlsx_row": xlsx_row}

        # Copia todos os campos mapeados
        for field, col_idx in col_map.items():
            record[field] = _safe_val(row.iloc[col_idx])

        # Consolida numero_cupom: SAT > ECF > NFCE
        record["numero_cupom"] = (
            record.get("numero_sat")
            or record.get("numero_ecf")
            or record.get("numero_nfce")
        )

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

    Cada registro contém:
      - xlsx_row      : número real da linha no Excel (1-based)
      - numero_cupom  : número consolidado SAT/ECF/NFCE para busca
      - numero_sat    : valor bruto da coluna SAT
      - numero_ecf    : valor bruto da coluna ECF
      - numero_nfce   : valor bruto da coluna NFCE
      - total_raw, desconto_raw, subtotal_raw, pagamento_raw, observacoes_raw...
    """
    df         = pd.read_excel(path, header=None, dtype=str)
    header_idx = _find_header_row(df, preferred_row=header_row)
    col_map    = _match_columns(list(df.iloc[header_idx].values))

    rows = _extract_test_rows(df, header_idx, col_map)

    print(f"[INFO] {len(rows)} caso(s) de teste carregado(s) ")
    if rows:
        sample = rows[0]
        print(f"  Amostra linha {sample['xlsx_row']}: "
              f"teste={sample.get('teste')} "
              f"SAT={sample.get('numero_sat')} "
              f"ECF={sample.get('numero_ecf')} "
              f"NFCE={sample.get('numero_nfce')} "
              f"total={sample.get('total_raw')}")

    return rows
