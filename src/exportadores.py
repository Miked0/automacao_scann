"""
Exportação de resultados para Excel.

Gera arquivo .xlsx com três abas:
  Resultado — todos os casos
  Erros     — apenas casos com status ERRO_*
  Alertas   — casos com status ALERTA ou REVISAR
"""
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

COLUNAS_ORDEM = [
    "bloco",
    "teste",
    "tipo_promo",
    "itens_raw",
    "itens_parseados",
    "pagamento_raw",
    "pagamento_normalizado",
    "codigo_tipo_pago",
    "is_multiplo",
    "requires_bin",
    "subtotal_raw",
    "subtotal_norm",
    "desconto_raw",
    "desconto_norm",
    "total_raw",
    "total_norm",
    "status_final",
    "motivo_status",
    "alertas",
    "observacoes_raw",
]

NOMES_ABAS = {
    "resultado": "Resultado",
    "erros":     "Erros",
    "alertas":   "Alertas",
}

PREFIXO_ERRO   = "ERRO"
STATUS_REVISAR = ("ALERTA", "REVISAR")


def _reordenar_colunas(dataframe: pd.DataFrame) -> pd.DataFrame:
    colunas_presentes = [col for col in COLUNAS_ORDEM if col in dataframe.columns]
    colunas_extras    = [col for col in dataframe.columns if col not in COLUNAS_ORDEM]
    return dataframe[colunas_presentes + colunas_extras]


def _filtrar_erros(dataframe: pd.DataFrame) -> pd.DataFrame:
    return dataframe[dataframe["status_final"].str.startswith(PREFIXO_ERRO, na=False)]


def _filtrar_alertas_e_revisao(dataframe: pd.DataFrame) -> pd.DataFrame:
    return dataframe[dataframe["status_final"].isin(STATUS_REVISAR)]


def _gravar_abas(
    writer: pd.ExcelWriter,
    resultado: pd.DataFrame,
    erros: pd.DataFrame,
    alertas: pd.DataFrame,
) -> None:
    resultado.to_excel(writer, sheet_name=NOMES_ABAS["resultado"], index=False)
    if not erros.empty:
        erros.to_excel(writer, sheet_name=NOMES_ABAS["erros"], index=False)
    if not alertas.empty:
        alertas.to_excel(writer, sheet_name=NOMES_ABAS["alertas"], index=False)


def exportar_resultados(resultados: List[Dict[str, Any]], caminho_saida: Path) -> None:
    """Grava os resultados de validação em arquivo Excel com abas separadas."""
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)

    dataframe = _reordenar_colunas(pd.DataFrame(resultados))
    erros     = _filtrar_erros(dataframe)
    alertas   = _filtrar_alertas_e_revisao(dataframe)

    with pd.ExcelWriter(caminho_saida, engine="openpyxl") as writer:
        _gravar_abas(writer, dataframe, erros, alertas)

    print(
        f"[INFO] Abas geradas: "
        f"Resultado ({len(dataframe)}), "
        f"Erros ({len(erros)}), "
        f"Alertas ({len(alertas)})"
    )


# Alias de compatibilidade — mantido enquanto main.py ainda referencia export_results
export_results = exportar_resultados
