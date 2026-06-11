"""
Módulo 6 — ResultWriter
Responsabilidade: Preenche colunas de resultado + salva xlsx.

Fix v3:
  - _safe_write com captura de AttributeError como fallback duplo:
    1) tenta _unmerge_cell + escrita normal
    2) se ainda AttributeError, força ws.unmerge_cells no intervalo inteiro
       e repete a escrita na célula âncora do merge
  - _find_col_by_keyword: resolve MergedCell no cabeçalho lendo valor da
    âncora quando cell.value é None
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
    """
    Encontra índice da coluna pelo cabeçalho.
    Resolve MergedCell: quando cell.value é None mas a célula faz parte de
    um merge, busca o valor na âncora do merge.
    """
    # Monta mapa col_index -> valor_real resolvendo merges
    col_val: dict[int, str] = {}
    for cell in ws[header_row]:
        if cell.value is not None:
            col_val[cell.column] = str(cell.value).lower()

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


def _find_merged_range(ws, row: int, col: int):
    """Retorna o MergedCellRange que contém (row, col), ou None."""
    col_letter = get_column_letter(col)
    cell_coord = f"{col_letter}{row}"
    for mr in ws.merged_cells.ranges:
        if cell_coord in mr:
            return mr
    return None


def _unmerge_cell(ws, row: int, col: int) -> None:
    """
    Se a célula (row, col) faz parte de um intervalo mesclado,
    desfaz o merge preservando o valor da âncora.
    """
    mr = _find_merged_range(ws, row, col)
    if mr is None:
        return
    anchor = ws.cell(row=mr.min_row, column=mr.min_col)
    saved_val  = anchor.value
    saved_fill = anchor.fill
    ws.unmerge_cells(str(mr))
    anchor.value = saved_val
    anchor.fill  = saved_fill
    logger.debug("Unmerge aplicado: %s (linha %d col %d)", mr, row, col)


def _safe_write(ws, row: int, col: int, value, fill) -> None:
    """
    Escreve value/fill na célula (row, col).

    Estratégia em 3 camadas:
    1) Desfaz merge se necessário e escreve normalmente.
    2) Se AttributeError (MergedCell proxy remanescente), força unmerge
       do range inteiro e escreve na âncora.
    3) Loga warning se ainda falhar.
    """
    _unmerge_cell(ws, row, col)
    try:
        cell = ws.cell(row=row, column=col)
        cell.value = value
        cell.fill  = fill
        return
    except AttributeError:
        logger.debug("AttributeError na escrita (%d,%d) — tentando fallback", row, col)

    # Fallback: localiza e desfaz qualquer merge residual
    mr = _find_merged_range(ws, row, col)
    if mr:
        ws.unmerge_cells(str(mr))
        logger.debug("Fallback unmerge: %s", mr)

    try:
        cell = ws.cell(row=row, column=col)
        cell.value = value
        cell.fill  = fill
    except AttributeError as e:
        logger.warning("Não foi possível escrever em (%d,%d): %s", row, col, e)


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
