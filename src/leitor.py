"""
Leitor da planilha de roteiro de testes.

Estrutura esperada do TEMPLATE:
  Linha 7  → cabeçalho das colunas
  Linha 8+ → casos de teste (podem ter linhas vazias entre eles)

  Colunas de entrada (preenchidas pelo QA):
    A  → Teste          D  → Pagamento      H  → NFCE
    B  → Tipo Promo     E  → Observações   I  → Sub-Total
    C  → Itens da venda F  → SAT            J  → Desconto
                        G  → ECF            K  → Total

  Colunas de resultado (preenchidas pelo script):
    R-T (18-20) → Ok/Erro por canal (SAT/ECF/NFCE)
    U   (21)    → Justificativa do erro

  SAT/ECF/NFCE são lidos como número de cupom para busca no Audit e no PDF.
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

COLUNAS_OBRIGATORIAS  = {"teste", "total_raw"}
LINHA_CABECALHO_PADRAO = 7
VALORES_CELULA_VAZIA  = ("", "nan", "None")


def _normalizar_coluna(valor: Any) -> str:
    """Remove acentos e normaliza texto para comparação de cabeçalhos."""
    texto = unicodedata.normalize("NFKD", str(valor).strip().lower())
    return "".join(char for char in texto if not unicodedata.combining(char))


def _mapear_colunas(linha: List[Any]) -> Dict[str, int]:
    """
    Tenta mapear as colunas da linha ao modelo interno via ALIASES_COLUNAS.
    Retorna dict vazio se as colunas obrigatórias não forem encontradas.
    """
    colunas_normalizadas = [_normalizar_coluna(col) for col in linha]
    mapeamento: Dict[str, int] = {}

    for campo_interno, aliases in ALIASES_COLUNAS.items():
        for indice, coluna in enumerate(colunas_normalizadas):
            if any(coluna == alias or alias in coluna for alias in aliases):
                if campo_interno not in mapeamento:
                    mapeamento[campo_interno] = indice
                break

    if COLUNAS_OBRIGATORIAS.issubset(mapeamento.keys()):
        return mapeamento
    return {}


def _linha_vazia(linha: pd.Series) -> bool:
    return all(str(celula).strip() in VALORES_CELULA_VAZIA for celula in linha.values)


def _valor_seguro(valor_bruto: Any) -> Optional[str]:
    """Retorna None para células vazias, NaN ou None do pandas."""
    if valor_bruto is None:
        return None
    texto = str(valor_bruto).strip()
    return None if texto in VALORES_CELULA_VAZIA else texto


def _localizar_linha_cabecalho(
    dataframe: pd.DataFrame,
    linha_preferida: int = LINHA_CABECALHO_PADRAO,
) -> int:
    """
    Localiza a linha de cabeçalho no dataframe.

    Tenta primeiro a linha padrão do TEMPLATE (linha 7).
    Faz varredura completa como fallback caso o arquivo seja diferente do padrão.
    """
    indice_preferido = linha_preferida - 1

    if indice_preferido < len(dataframe):
        if _mapear_colunas(list(dataframe.iloc[indice_preferido].values)):
            print(f"[INFO] Cabeçalho na linha {linha_preferida} (padrão do TEMPLATE).")
            return indice_preferido

    for indice in range(len(dataframe)):
        if _mapear_colunas(list(dataframe.iloc[indice].values)):
            print(f"[INFO] Cabeçalho detectado por varredura na linha {indice + 1}.")
            return indice

    raise ValueError(
        f"Nenhum cabeçalho válido encontrado. "
        f"Verifique se as colunas obrigatórias ({COLUNAS_OBRIGATORIAS}) estão presentes."
    )


def _consolidar_numero_cupom(registro: Dict[str, Any]) -> Optional[str]:
    """Retorna o primeiro número de cupom disponível entre SAT, ECF e NFCE."""
    return (
        registro.get("numero_sat")
        or registro.get("numero_ecf")
        or registro.get("numero_nfce")
    )


def _extrair_linhas_de_teste(
    dataframe: pd.DataFrame,
    indice_cabecalho: int,
    mapeamento_colunas: Dict[str, int],
) -> List[Dict[str, Any]]:
    casos: List[Dict[str, Any]] = []
    indice_coluna_teste = mapeamento_colunas["teste"]

    for indice_df in range(indice_cabecalho + 1, len(dataframe)):
        linha     = dataframe.iloc[indice_df]
        linha_xlsx = indice_df + 1

        if _linha_vazia(linha):
            continue

        identificador = _valor_seguro(linha.iloc[indice_coluna_teste])
        if not identificador:
            continue

        registro: Dict[str, Any] = {"xlsx_row": linha_xlsx}

        for campo, indice_col in mapeamento_colunas.items():
            registro[campo] = _valor_seguro(linha.iloc[indice_col])

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
    dataframe         = pd.read_excel(caminho, header=None, dtype=str)
    indice_cabecalho  = _localizar_linha_cabecalho(dataframe, linha_preferida=linha_cabecalho)
    mapeamento_colunas = _mapear_colunas(list(dataframe.iloc[indice_cabecalho].values))

    casos = _extrair_linhas_de_teste(dataframe, indice_cabecalho, mapeamento_colunas)

    print(f"[INFO] {len(casos)} caso(s) de teste carregado(s)")
    if casos:
        amostra = casos[0]
        print(
            f"  Amostra linha {amostra['xlsx_row']}: "
            f"teste={amostra.get('teste')} "
            f"SAT={amostra.get('numero_sat')} "
            f"ECF={amostra.get('numero_ecf')} "
            f"NFCE={amostra.get('numero_nfce')} "
            f"total={amostra.get('total_raw')}"
        )

    return casos


# Alias de compatibilidade — mantido enquanto main.py ainda referencia load_roteiro_tests
load_roteiro_tests = carregar_casos_do_roteiro
