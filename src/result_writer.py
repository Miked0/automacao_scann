"""
Módulo 6 — ResultWriter
Responsabilidade: Preenche colunas de resultado + salva xlsx.

Colunas de resultado (detectadas dinamicamente ou fallback R/S/T/U):
  - col_sat  → "Ok" / "Erro" + fill verde/vermelho
  - col_ecf  → "Ok" / "Erro" + fill verde/vermelho
  - col_nfce → "Ok" / "Erro" + fill verde/vermelho
  - col_just → justificativa ≤ 100 chars em caso de ERRO
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

# Palavras-chave usadas para detectar a linha de cabeçalho
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


def _find_col_by_keyword(ws, header_row: int, keywords: list[str]) -> Optional[int]:
    """Encontra índice (1-based) da coluna pelo conteúdo do cabeçalho."""
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

        # Detecta colunas de resultado dinamicamente
        self.col_sat  = _find_col_by_keyword(self.ws, self.header_row, ["sat", "ecf"])
        self.col_ecf  = _find_col_by_keyword(self.ws, self.header_row, ["ecf"])
        self.col_nfce = _find_col_by_keyword(self.ws, self.header_row, ["nfc", "nfce"])
        self.col_just = _find_col_by_keyword(
            self.ws, self.header_row, ["just", "motivo", "obs"]
        )

        # Fallback: R=18, S=19, T=20, U=21
        if not self.col_sat:  self.col_sat  = 18
        if not self.col_ecf:  self.col_ecf  = 19
        if not self.col_nfce: self.col_nfce = 20
        if not self.col_just: self.col_just = 21

        logger.info(
            "ResultWriter colunas: SAT=%s ECF=%s NFCE=%s JUST=%s",
            self.col_sat, self.col_ecf, self.col_nfce, self.col_just,
        )

    def write_result(self, result: TestResult, data_row: int) -> None:
        """Preenche as colunas de resultado para uma linha de dado.

        Garante que apenas as colunas de resultado sejam modificadas.
        """
        status = "Ok"  if result.passed else "Erro"
        fill   = FILL_OK if result.passed else FILL_ERRO

        for col in (self.col_sat, self.col_ecf, self.col_nfce):
            if col:
                cell       = self.ws.cell(row=data_row, column=col)
                cell.value = status
                cell.fill  = fill

        if not result.passed and self.col_just:
            cell       = self.ws.cell(row=data_row, column=self.col_just)
            cell.value = result.motivo_erro  # ≤ 100 chars (garantido por TestResult)

    def save(self) -> None:
        """Salva o workbook no caminho de saída."""
        self.wb.save(self.output_path)
        logger.info("Resultado salvo em: %s", self.output_path)
