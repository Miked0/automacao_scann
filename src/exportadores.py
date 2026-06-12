"""Exportadores de resultado para Excel.

Gera arquivo .xlsx com:
- Aba 'Resultado': todos os casos com status
- Aba 'Erros': apenas casos com status ERRO_* para revisão rápida
- Aba 'Alertas': casos OK com alertas ou REVISAR
"""
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

COLUMNS_ORDER = [
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


def _reorder(df: pd.DataFrame) -> pd.DataFrame:
    existing = [c for c in COLUMNS_ORDER if c in df.columns]
    extra = [c for c in df.columns if c not in COLUMNS_ORDER]
    return df[existing + extra]


def export_results(results: List[Dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(results)
    df = _reorder(df)

    erros = df[df["status_final"].str.startswith("ERRO", na=False)]
    alertas_revisar = df[df["status_final"].isin(["ALERTA", "REVISAR"])]

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Resultado", index=False)
        if not erros.empty:
            erros.to_excel(writer, sheet_name="Erros", index=False)
        if not alertas_revisar.empty:
            alertas_revisar.to_excel(writer, sheet_name="Alertas", index=False)

    print(f"[INFO] Abas geradas: Resultado ({len(df)}), Erros ({len(erros)}), Alertas ({len(alertas_revisar)})")
