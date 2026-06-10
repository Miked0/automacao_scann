from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pandas as pd

from models import TestCase


def export_results(results: List[TestCase], blocks: List[Dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    consolidado = pd.DataFrame([r.to_export_dict() for r in results])
    erros = consolidado[consolidado['status_final'].isin(['ERRO_PARSE', 'ERRO_VALOR', 'ERRO_PAGAMENTO', 'REVISAR'])].copy() if not consolidado.empty else pd.DataFrame()
    blocos_df = pd.DataFrame(blocks)

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        consolidado.to_excel(writer, sheet_name='consolidado', index=False)
        erros.to_excel(writer, sheet_name='revisao', index=False)
        blocos_df.to_excel(writer, sheet_name='blocos_detectados', index=False)
