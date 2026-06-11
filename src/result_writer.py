"""
M6 — ResultWriter
Preenche as colunas de resultado (R, S, T, U) no workbook e salva o xlsx.

Regras:
  - Detecta colunas de resultado pelo índice do cabeçalho dinâmico.
  - Escreve 'Ok' (verde #C6EFCE) ou 'Erro' (vermelho #FFC7CE).
  - Em caso de ERRO, preenche coluna U com justificativa ≤ 100 chars.
  - Não altera nenhuma célula fora das colunas de resultado.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, Tuple

from openpyxl import Workbook
from openpyxl.styles import PatternFill

from .models import TestResult

log = logging.getLogger(__name__)

# Cores de preenchimento
_FILL_OK  = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
_FILL_ERR = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")

# Palavras-chave para encontrar as colunas de resultado no cabeçalho
_RESULT_COLS = {
    "col_sat":    ("sat",  "resultado sat",  "json sat"),
    "col_ecf":    ("ecf",  "resultado ecf",  "json ecf"),
    "col_nfce":   ("nfce", "resultado nfce", "json nfce"),
    "col_just":   ("justificativa", "motivo", "observ resultado"),
}

# Palavras-chave para detectar linha de cabeçalho
_HEADER_KW = {"teste", "tipo", "promo", "cupom", "total", "desconto", "resultado"}


class ResultWriter:
    """Escreve resultados nas colunas corretas do roteiro XLSX."""

    def __init__(self, wb: Workbook) -> None:
        self.wb      = wb
        self.ws      = self._get_main_sheet()
        self._header_row, self._col_indices = self._detect_result_columns()

    # ── Escrita ──────────────────────────────────────────────────────────────
    def write(self, results: List[TestResult]) -> None:
        idx = self._col_indices
        if not idx:
            log.warning("Colunas de resultado não detectadas — nada será escrito.")
            return

        for res in results:
            row = res.linha
            status = "Ok" if res.overall_ok else "Erro"
            fill   = _FILL_OK if res.overall_ok else _FILL_ERR

            for col_key in ("col_sat", "col_ecf", "col_nfce"):
                col = idx.get(col_key)
                if col is not None:
                    cell = self.ws.cell(row=row, column=col)
                    cell.value = status
                    cell.fill  = fill

            if not res.overall_ok:
                col_just = idx.get("col_just")
                if col_just is not None:
                    cell_j = self.ws.cell(row=row, column=col_just)
                    cell_j.value = res.col_justificativa[:100]
                    cell_j.fill  = _FILL_ERR

        log.info("ResultWriter: %d linhas preenchidas.", len(results))

    def save(self, output_path: str) -> None:
        self.wb.save(output_path)
        log.info("Workbook salvo em: %s", output_path)

    # ── Detecção dinâmica das colunas ────────────────────────────────────────
    def _get_main_sheet(self):
        for name in self.wb.sheetnames:
            if any(k in name.lower() for k in ("roteiro", "teste", "planilha")):
                return self.wb[name]
        return self.wb.active

    def _detect_result_columns(self) -> Tuple[int, Dict[str, int]]:
        """Varre linhas em busca do cabeçalho e mapeia colunas de resultado."""
        for row in self.ws.iter_rows():
            texts = [str(c.value or "").lower().strip() for c in row]
            n_kw  = sum(1 for t in texts if any(kw in t for kw in _HEADER_KW))
            if n_kw < 2:
                continue

            col_map: Dict[str, int] = {}
            for cell in row:
                t = str(cell.value or "").lower().strip()
                for result_key, keywords in _RESULT_COLS.items():
                    if any(kw in t for kw in keywords) and result_key not in col_map:
                        col_map[result_key] = cell.column  # 1-based

            # Se não encontrou col_sat/ecf/nfce pelo nome, usa colunas R/S/T/U (18-21)
            for i, default_key in enumerate(["col_sat", "col_ecf", "col_nfce", "col_just"], start=18):
                if default_key not in col_map:
                    col_map[default_key] = i

            log.info("Colunas de resultado detectadas: %s", col_map)
            return row[0].row, col_map

        # Fallback total: colunas R/S/T/U
        log.warning("Cabeçalho não detectado. Usando colunas padrão R/S/T/U.")
        return 1, {"col_sat": 18, "col_ecf": 19, "col_nfce": 20, "col_just": 21}
