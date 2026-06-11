"""
Módulo 6 — ResultWriter
Responsabilidade: Preenche colunas de resultado + salva xlsx.
"""

import logging
from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl.styles import PatternFill

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
    """Encontra índice da coluna pelo cabeçalho."""
    for cell in ws[header_row]:
        if cell.value and any(kw in str(cell.value).lower() for kw in keywords):
            return cell.column
    return None


class ResultWriter:
    """Escreve resultados nas colunas corretas do TEMPLATE e salva o xlsx."""

    def __init__(self, workbook: openpyxl.Workbook, output_path: str):
        self.wb          = workbook
        self.output_path = Path(output_path)
        self.ws          = workbook.active

        self.header_row = _detect_header_row(self.ws)

        # Detecta índices das colunas de resultado
        self.col_sat  = _find_col_by_keyword(self.ws, self.header_row, ["sat", "ecf"])
        self.col_ecf  = _find_col_by_keyword(self.ws, self.header_row, ["ecf"])
        self.col_nfce = _find_col_by_keyword(self.ws, self.header_row, ["nfc", "nfce"])
        self.col_just = _find_col_by_keyword(self.ws, self.header_row, ["just", "motivo", "obs"])

        # Fallback: colunas R, S, T, U
        if not self.col_sat:  self.col_sat  = 18
        if not self.col_ecf:  self.col_ecf  = 19
        if not self.col_nfce: self.col_nfce = 20
        if not self.col_just: self.col_just = 21

        logger.info(
            "ResultWriter: colunas detectadas SAT=%s ECF=%s NFCE=%s JUST=%s",
            self.col_sat, self.col_ecf, self.col_nfce, self.col_just
        )

    def write_result(self, result: TestResult, data_row: int) -> None:
        """Preenche as colunas de resultado para uma linha de dado."""
        status = "Ok"   if result.passed else "Erro"
        fill   = FILL_OK if result.passed else FILL_ERRO

        for col in (self.col_sat, self.col_ecf, self.col_nfce):
            if col:
                cell       = self.ws.cell(row=data_row, column=col)
                cell.value = status
                cell.fill  = fill

        if not result.passed and self.col_just:
            cell       = self.ws.cell(row=data_row, column=self.col_just)
            cell.value = result.motivo_erro

    def save(self) -> None:
        """Salva o workbook no caminho de saída."""
        self.wb.save(self.output_path)
        logger.info("Resultado salvo em: %s", self.output_path)
