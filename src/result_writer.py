"""
Módulo 6 — ResultWriter
Responsabilidade: Preenche colunas de resultado + salva xlsx.

Fix v2:
  - Trata MergedCell: desfaz merge temporariamente na coluna de resultado
    antes de escrever, garantindo que a célula-âncora seja sempre gravável.
  - Busca de coluna mais robusta: aceita 'json', 'resultado', 'status' além
    dos keywords anteriores.
"""

import logging
from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl.styles import PatternFill
from openpyxl.utils import get_column_letter

from .test_runner import TestResult

logger = logging.getLogger(__name__)

FILL_OK   = PatternFill("solid", fgColor="C6EFCE")
FILL_ERRO = PatternFill("solid", fgColor="FFC7CE")

KEYWORDS_HEADER = {"teste", "tipo", "promo", "roteiro", "etapa", "descricao"}


def _detect_header_row(ws) -> int:
    """Detecta a linha de cabeçalho por palavras-chave."""
    for row in ws.iter_rows():
        for cell in row:
            if cell.value and any(
                kw in str(cell.value).lower() for kw in KEYWORDS_HEADER
            ):
                return cell.row
    return 1


def _find_col_by_keyword(ws, header_row: int, keywords: list) -> Optional[int]:
    """Encontra índice da coluna pelo cabeçalho (tolerante a MergedCell no header)."""
    for cell in ws[header_row]:
        val = cell.value
        # MergedCell no cabeçalho: pula (valor estará na célula âncora)
        if val is None:
            continue
        if any(kw in str(val).lower() for kw in keywords):
            return cell.column
    return None


def _unmerge_cell(ws, row: int, col: int) -> None:
    """
    Se a célula (row, col) faz parte de um intervalo mesclado,
    desfaz o merge desse intervalo para permitir a escrita.
    Preserva o valor da célula âncora.
    """
    col_letter = get_column_letter(col)
    cell_coord = f"{col_letter}{row}"
    ranges_to_remove = [
        mr for mr in ws.merged_cells.ranges
        if cell_coord in mr
    ]
    for mr in ranges_to_remove:
        # Guarda o valor e fill da âncora antes de desfazer
        anchor = ws.cell(row=mr.min_row, column=mr.min_col)
        saved_val  = anchor.value
        saved_fill = anchor.fill
        ws.unmerge_cells(str(mr))
        # Restaura âncora (unmerge limpa o valor)
        anchor.value = saved_val
        anchor.fill  = saved_fill
        logger.debug("Unmerge aplicado: %s (linha %d col %d)", mr, row, col)


def _safe_write(ws, row: int, col: int, value, fill) -> None:
    """
    Escreve value/fill na célula (row, col), desfazendo merge se necessário.
    Sempre garante que escrevemos na célula real (não num MergedCell proxy).
    """
    _unmerge_cell(ws, row, col)
    cell = ws.cell(row=row, column=col)
    cell.value = value
    cell.fill  = fill


class ResultWriter:
    """Escreve resultados nas colunas corretas do TEMPLATE e salva o xlsx."""

    def __init__(self, workbook: openpyxl.Workbook, output_path: str):
        self.wb          = workbook
        self.output_path = Path(output_path)
        self.ws          = workbook.active

        self.header_row = _detect_header_row(self.ws)

        # Detecta colunas de resultado por palavras-chave no cabeçalho
        self.col_sat  = _find_col_by_keyword(
            self.ws, self.header_row,
            ["sat", "resultado sat", "json sat"]
        )
        self.col_ecf  = _find_col_by_keyword(
            self.ws, self.header_row,
            ["ecf", "resultado ecf", "json ecf"]
        )
        self.col_nfce = _find_col_by_keyword(
            self.ws, self.header_row,
            ["nfc", "nfce", "resultado nfc"]
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

    def write_result(self, result: TestResult, data_row: int) -> None:
        """Preenche as colunas de resultado, desfazendo merges se necessário."""
        status = "Ok"    if result.passed else "Erro"
        fill   = FILL_OK if result.passed else FILL_ERRO

        for col in (self.col_sat, self.col_ecf, self.col_nfce):
            if col:
                _safe_write(self.ws, data_row, col, status, fill)

        if self.col_just:
            motivo = result.motivo_erro if not result.passed else ""
            _safe_write(self.ws, data_row, self.col_just, motivo, PatternFill())

    def save(self) -> None:
        """Salva o workbook no caminho de saída."""
        self.wb.save(self.output_path)
        logger.info("Resultado salvo em: %s", self.output_path)
