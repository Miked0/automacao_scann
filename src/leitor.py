"""
Leitor da planilha de roteiro de testes.

Estrutura esperada do TEMPLATE:
  Linha 7  → cabeçalho das colunas
  Linha 8+ → casos de teste (podem ter linhas vazias entre eles)
"""
from pathlib import Path
from typing import Any, Dict, List, Optional
import unicodedata

import pandas as pd

ALIASES_COLUNAS: Dict[str, List[str]] = {
    "teste":           ["teste", "test", "caso", "cenario", "cenário"],
    "tipo_promo":      ["tipo promo", "tipo promocion", "tipo promoção", "tipo_promo"],
    "numero_sat":      ["sat"],
    "numero_ecf":      ["ecf"],
    "numero_nfce":     ["nfce", "nfc-e", "nfc"],
    "itens_raw":       ["itens da venda", "itens", "articulos", "produtos"],
    "pagamento_raw":   ["pagamento", "pago", "forma de pago", "forma pagamento", "meio pag"],
    "observacoes_raw": ["observacoes", "observações", "obs", "observacion"],
    "subtotal_raw":    ["sub-total", "subtotal", "sub total"],
    "desconto_raw":    ["desconto", "descuento", "desc"],
    "total_raw":       ["total"],
    "json_status":     ["json"],
    "ean_raw":         ["ean", "eans", "codigo_barras", "cod_barra", "ean/upc"],
    "bin_raw":         ["bin"],
}

COLUNAS_OBRIGATORIAS   = {"teste", "total_raw"}
LINHA_CABECALHO_PADRAO = 7
VALORES_CELULA_VAZIA   = ("", "nan", "None")


def _normalizar_coluna(valor: Any) -> str:
    texto = unicodedata.normalize("NFKD", str(valor).strip().lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def _mapear_colunas(linha: List[Any]) -> Dict[str, int]:
    colunas_norm = [_normalizar_coluna(col) for col in linha]
    mapeamento: Dict[str, int] = {}
    for campo, aliases in ALIASES_COLUNAS.items():
        for idx, col in enumerate(colunas_norm):
            if any(col == a or a in col for a in aliases):
                if campo not in mapeamento:
                    mapeamento[campo] = idx
                break
    if COLUNAS_OBRIGATORIAS.issubset(mapeamento.keys()):
        return mapeamento
    return {}


def _linha_vazia(linha: pd.Series) -> bool:
    return all(str(c).strip() in VALORES_CELULA_VAZIA for c in linha.values)


def _valor_seguro(valor_bruto: Any) -> Optional[str]:
    if valor_bruto is None:
        return None
    texto = str(valor_bruto).strip()
    return None if texto in VALORES_CELULA_VAZIA else texto


def _localizar_linha_cabecalho(
    dataframe: pd.DataFrame,
    linha_preferida: int = LINHA_CABECALHO_PADRAO,
) -> int:
    idx_pref = linha_preferida - 1
    if idx_pref < len(dataframe):
        if _mapear_colunas(list(dataframe.iloc[idx_pref].values)):
            print(f"[INFO] Cabeçalho na linha {linha_preferida} (padrão do TEMPLATE).")
            return idx_pref
    for idx in range(len(dataframe)):
        if _mapear_colunas(list(dataframe.iloc[idx].values)):
            print(f"[INFO] Cabeçalho detectado por varredura na linha {idx + 1}.")
            return idx
    raise ValueError(
        f"Nenhum cabeçalho válido encontrado. "
        f"Verifique se as colunas obrigatórias ({COLUNAS_OBRIGATORIAS}) estão presentes."
    )


def _consolidar_numero_cupom(registro: Dict[str, Any]) -> Optional[str]:
    return (
        registro.get("numero_sat")
        or registro.get("numero_ecf")
        or registro.get("numero_nfce")
    )


def _extrair_linhas_de_teste(
    dataframe: pd.DataFrame,
    idx_cabecalho: int,
    mapeamento: Dict[str, int],
) -> List[Dict[str, Any]]:
    casos: List[Dict[str, Any]] = []
    idx_col_teste = mapeamento["teste"]
    for idx_df in range(idx_cabecalho + 1, len(dataframe)):
        linha      = dataframe.iloc[idx_df]
        linha_xlsx = idx_df + 1
        if _linha_vazia(linha):
            continue
        identificador = _valor_seguro(linha.iloc[idx_col_teste])
        if not identificador:
            continue
        registro: Dict[str, Any] = {"xlsx_row": linha_xlsx}
        for campo, idx_col in mapeamento.items():
            registro[campo] = _valor_seguro(linha.iloc[idx_col])
        registro["numero_cupom"] = _consolidar_numero_cupom(registro)
        casos.append(registro)
    return casos


def carregar_casos_do_roteiro(
    caminho: Path,
    linha_cabecalho: int = LINHA_CABECALHO_PADRAO,
) -> List[Dict[str, Any]]:
    """
    Carrega o roteiro e devolve lista de casos de teste no modelo interno.

    Cada registro contém:
      xlsx_row     — número real da linha no Excel (base 1)
      numero_cupom — primeiro número disponível entre SAT/ECF/NFCE
      numero_sat, numero_ecf, numero_nfce — valores brutos por canal
      total_raw, desconto_raw, subtotal_raw, pagamento_raw, observacoes_raw
    """
    dataframe     = pd.read_excel(caminho, header=None, dtype=str)
    idx_cabecalho = _localizar_linha_cabecalho(dataframe, linha_preferida=linha_cabecalho)
    mapeamento    = _mapear_colunas(list(dataframe.iloc[idx_cabecalho].values))
    casos         = _extrair_linhas_de_teste(dataframe, idx_cabecalho, mapeamento)
    print(f"[INFO] {len(casos)} caso(s) de teste carregado(s)")
    if casos:
        s = casos[0]
        print(
            f"  Amostra linha {s['xlsx_row']}: "
            f"teste={s.get('teste')} SAT={s.get('numero_sat')} "
            f"ECF={s.get('numero_ecf')} NFCE={s.get('numero_nfce')} "
            f"total={s.get('total_raw')}"
        )
    return casos


# Alias de compatibilidade
load_roteiro_tests = carregar_casos_do_roteiro
