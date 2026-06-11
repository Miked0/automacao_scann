"""
Módulo 6 — ResultWriter
Responsabilidade: Preenche colunas de resultado + salva xlsx.

Fix v4 — Abordagem definitiva para MergedCell read-only:
  - No __init__, varre TODOS os merged ranges da planilha e desfaz
    qualquer um que toque nas colunas de resultado (col_sat/ecf/nfce/just).
  - Isso elimina o erro AttributeError antes de qualquer escrita, pois
    o openpyxl não permite escrever em MergedCell proxy mesmo após
    unmerge_cells chamado line-by-line.
  - _safe_write mantida como segunda linha de defesa.
"""

import logging
from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl.styles import PatternFill
from openpyxl.utils import get_column_letter, column_index_from_string

from .test_runner import TestResult

logger = logging.getLogger(__name__)

FILL_OK   = PatternFill("solid", fgColor="C6EFCE")
FILL_ERRO = PatternFill("solid", fgColor="FFC7CE")
FILL_NONE = PatternFill()

KEYWORDS_HEADER = {"teste", "tipo", "promo", "roteiro", "etapa", "descricao"}


# ---------------------------------------------------------------------------
# Helpers de detecção
# ---------------------------------------------------------------------------

def _detect_header_row(ws) -> int:
    for row in ws.iter_rows():
        for cell in row:
            if cell.value and any(
                kw in str(cell.value).lower() for kw in KEYWORDS_HEADER
            ):
                return cell.row
    return 1


def _find_col_by_keyword(ws, header_row: int, keywords: list) -> Optional[int]:
    """
    Encontra índice da coluna pelo cabeçalho.
    Resolve MergedCell: lê valor da âncora quando cell.value é None.
    """
    col_val: dict[int, str] = {}
    for cell in ws[header_row]:
        val = cell.value
        if val is not None:
            col_val[cell.column] = str(val).lower()

    for mr in ws.merged_cells.ranges:
        if mr.min_row <= header_row <= mr.max_row:
            anchor_val = ws.cell(row=mr.min_row, column=mr.min_col).value
            if anchor_val:
                for c in range(mr.min_col, mr.max_col + 1):
                    col_val.setdefault(c, str(anchor_val).lower())

    for col_idx, val in col_val.items():
        if any(kw in val for kw in keywords):
            return col_idx
    return None


# ---------------------------------------------------------------------------
# Unmerge preventivo global
# ---------------------------------------------------------------------------

def _preemptive_unmerge(ws, result_cols: set[int]) -> None:
    """
    Varre todos os merged ranges e desfaz aqueles que contêm
    qualquer coluna em result_cols.  Deve ser chamado UMA VEZ
    no __init__ antes de qualquer escrita.
    """
    # Snapshot da lista (ws.merged_cells.ranges muda durante iteração)
    ranges_to_remove = []
    for mr in list(ws.merged_cells.ranges):
        if any(mr.min_col <= c <= mr.max_col for c in result_cols):
            ranges_to_remove.append(str(mr))

    for coord in ranges_to_remove:
        try:
            # Preserva valor da âncora
            parts = coord.replace(":", " ").split()
            # get_column_letter inverso: extrai col âncora
            anchor_coord = parts[0]
            anchor = ws[anchor_coord]
            saved_val  = anchor.value if not isinstance(anchor, openpyxl.cell.cell.MergedCell) else None
            ws.unmerge_cells(coord)
            # Reescreve o valor na âncora (agora célula normal)
            try:
                ws[anchor_coord].value = saved_val
            except Exception:
                pass
            logger.debug("Pre-unmerge: %s", coord)
        except Exception as e:
            logger.warning("Falha ao desfazer merge %s: %s", coord, e)


# ---------------------------------------------------------------------------
# Escrita segura (segunda linha de defesa)
# ---------------------------------------------------------------------------

def _safe_write(ws, row: int, col: int, value, fill) -> None:
    try:
        cell = ws.cell(row=row, column=col)
        cell.value = value
        cell.fill  = fill
    except AttributeError:
        # Ainda é MergedCell? Força unmerge pontual e tenta de novo.
        col_letter = get_column_letter(col)
        for mr in list(ws.merged_cells.ranges):
            if mr.min_col <= col <= mr.max_col and mr.min_row <= row <= mr.max_row:
                ws.unmerge_cells(str(mr))
                logger.debug("Unmerge pontual: %s", mr)
                break
        try:
            cell = ws.cell(row=row, column=col)
            cell.value = value
            cell.fill  = fill
        except AttributeError as e:
            logger.warning("Não foi possível escrever em (%d,%d): %s", row, col, e)


# ---------------------------------------------------------------------------
# ResultWriter
# ---------------------------------------------------------------------------

class ResultWriter:
    """Escreve resultados nas colunas corretas do TEMPLATE e salva o xlsx."""

    def __init__(self, workbook: openpyxl.Workbook, output_path: str):
        self.wb          = workbook
        self.output_path = Path(output_path)
        self.ws          = workbook.active

        self.header_row = _detect_header_row(self.ws)

        self.col_sat  = _find_col_by_keyword(
            self.ws, self.header_row, ["sat", "resultado sat", "json sat"]
        )
        self.col_ecf  = _find_col_by_keyword(
            self.ws, self.header_row, ["ecf", "resultado ecf", "json ecf"]
        )
        self.col_nfce = _find_col_by_keyword(
            self.ws, self.header_row, ["nfc", "nfce", "resultado nfc"]
        )
        self.col_just = _find_col_by_keyword(
            self.ws, self.header_row,
            ["just", "motivo", "observa", "resultado obs", "obs result"]
        )

        # Fallback: colunas fixas R(18) S(19) T(20) U(21)
        if not self.col_sat:  self.col_sat  = 18
        if not self.col_ecf:  self.col_ecf  = 19
        if not self.col_nfce: self.col_nfce = 20
        if not self.col_just: self.col_just = 21

        logger.info(
            "ResultWriter: colunas detectadas SAT=%s ECF=%s NFCE=%s JUST=%s",
            self.col_sat, self.col_ecf, self.col_nfce, self.col_just
        )

        # ── FIX v4: desfaz TODOS os merges que tocam nas colunas de resultado ──
        result_cols = {c for c in (self.col_sat, self.col_ecf, self.col_nfce, self.col_just) if c}
        _preemptive_unmerge(self.ws, result_cols)

    def write_result(self, result: TestResult, data_row: int) -> None:
        """Preenche as colunas de resultado para uma linha de dado."""
        status = "Ok"    if result.passed else "Erro"
        fill   = FILL_OK if result.passed else FILL_ERRO

        for col in (self.col_sat, self.col_ecf, self.col_nfce):
            if col:
                _safe_write(self.ws, data_row, col, status, fill)

        if self.col_just:
            motivo = result.motivo_erro if not result.passed else ""
            _safe_write(self.ws, data_row, self.col_just, motivo, FILL_NONE)

    def save(self) -> None:
        """Salva o workbook no caminho de saída."""
        self.wb.save(self.output_path)
        logger.info("Resultado salvo em: %s", self.output_path)
