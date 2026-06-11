"""
Módulo 6 — ResultWriter
Responsabilidade: Preenche colunas de resultado + salva xlsx.

Mapeamento de colunas de resultado (fixo, conforme TEMPLATE real):
  R (18) → resultado SAT
  S (19) → resultado ECF
  T (20) → resultado NFCE
  U (21) → justificativa do erro

O script detecta as colunas pelo cabeçalho dinamicamente.
Se não encontrar, usa os indicadores fixos acima como fallback.

Regra de escrita:
  - Escreve Ok/Erro + fill verde/vermelho nas 3 colunas de status.
  - Escreve a justificativa (até 100 chars) apenas quando Erro.
  - NÃO altera nenhuma outra célula fora dessas 4 colunas.
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
FILL_NONE = PatternFill()

# ---------------------------------------------------------------------------
# KEYWORDS_HEADER: palavras que identificam a linha de cabeçalho do roteiro.
# IMPORTANTE: devem ser exclusivas da linha de cabeçalho — evitar palavras
# genéricas como "tipo", "total", "obs" que podem aparecer em linhas de
# título ou apresentação do template (linhas 1-6).
# ---------------------------------------------------------------------------
KEYWORDS_HEADER = {
    "nº do teste",
    "n. do teste",
    "no. do teste",
    "numero do teste",
    "número do teste",
    "num. sat",
    "num. ecf",
    "num. nfce",
    "nº sat",
    "nº ecf",
    "nº nfce",
    "nfce",
    "itens da venda",
    "articulos movimiento",
    "tipo promo",
    "tipo de promo",
    "tipo promoción",
}

# Palavras-chave para detectar as colunas de resultado no cabeçalho
_RESULT_COL_KEYWORDS = {
    "col_sat":  ["resultado sat",  "res sat",  "result sat",  "ok sat",  "erro sat"],
    "col_ecf":  ["resultado ecf",  "res ecf",  "result ecf",  "ok ecf",  "erro ecf"],
    "col_nfce": ["resultado nfce", "res nfce", "result nfce", "ok nfce", "erro nfce",
                 "resultado nfc",  "res nfc"],
    "col_just": ["justificativa", "just", "motivo", "observ result", "resultado obs"],
}

# Fallback: colunas fixas do TEMPLATE (1-based)
_DEFAULT_COLS = {
    "col_sat":  18,  # R
    "col_ecf":  19,  # S
    "col_nfce": 20,  # T
    "col_just": 21,  # U
}

# Linha de cabeçalho esperada no TEMPLATE (1-based).
# O template Scanntech tem cabeçalho fixo na linha 7.
_EXPECTED_HEADER_ROW = 7


# ---------------------------------------------------------------------------
# Helpers de detecção
# ---------------------------------------------------------------------------

def _detect_header_row(ws) -> int:
    """
    Detecta a linha de cabeçalho com estratégia em três passos:

    1. Verifica se a linha _EXPECTED_HEADER_ROW (7) possui ao menos uma
       célula com palavra-chave exclusiva do cabeçalho → usa ela.
    2. Varre todas as linhas buscando palavras-chave exclusivas.
    3. Fallback: retorna _EXPECTED_HEADER_ROW (7) incondicionalmente.

    Evita falsos positivos de palavras genéricas (ex: "total", "tipo")
    que podem existir nas linhas de título/apresentação (1-6).
    """
    # Passo 1: verifica linha esperada
    for cell in ws[_EXPECTED_HEADER_ROW]:
        if cell.value and any(
            kw in str(cell.value).strip().lower() for kw in KEYWORDS_HEADER
        ):
            logger.debug("Cabeçalho confirmado na linha esperada %d", _EXPECTED_HEADER_ROW)
            return _EXPECTED_HEADER_ROW

    # Passo 2: varredura completa
    for row in ws.iter_rows():
        for cell in row:
            if cell.value and any(
                kw in str(cell.value).strip().lower() for kw in KEYWORDS_HEADER
            ):
                logger.info("Cabeçalho encontrado por varredura na linha %d", cell.row)
                return cell.row

    # Passo 3: fallback fixo
    logger.warning(
        "Cabeçalho não detectado por palavras-chave. Usando linha fixa %d.",
        _EXPECTED_HEADER_ROW
    )
    return _EXPECTED_HEADER_ROW


def _find_result_cols(ws, header_row: int) -> dict:
    """
    Localiza as colunas de resultado pelo cabeçalho.
    Retorna dict col_sat/col_ecf/col_nfce/col_just com indicadores 1-based.
    Usa _DEFAULT_COLS como fallback.
    """
    found = {}
    for cell in ws[header_row]:
        if not cell.value:
            continue
        val = str(cell.value).strip().lower()
        for key, keywords in _RESULT_COL_KEYWORDS.items():
            if key not in found and any(kw in val for kw in keywords):
                found[key] = cell.column

    for key, default_col in _DEFAULT_COLS.items():
        if key not in found:
            found[key] = default_col

    return found


# ---------------------------------------------------------------------------
# Unmerge preventivo nas colunas de resultado
# ---------------------------------------------------------------------------

def _preemptive_unmerge(ws, result_cols: set) -> None:
    for mr in list(ws.merged_cells.ranges):
        if any(mr.min_col <= c <= mr.max_col for c in result_cols):
            coord = str(mr)
            try:
                anchor = ws[coord.split(":")[0]]
                saved  = anchor.value if not isinstance(
                    anchor, openpyxl.cell.cell.MergedCell) else None
                ws.unmerge_cells(coord)
                try:
                    ws[coord.split(":")[0]].value = saved
                except Exception:
                    pass
            except Exception as e:
                logger.warning("Falha ao desfazer merge %s: %s", coord, e)


# ---------------------------------------------------------------------------
# Escrita segura
# ---------------------------------------------------------------------------

def _safe_write(ws, row: int, col: int, value, fill) -> None:
    try:
        cell = ws.cell(row=row, column=col)
        cell.value = value
        cell.fill  = fill
    except AttributeError:
        for mr in list(ws.merged_cells.ranges):
            if mr.min_col <= col <= mr.max_col and mr.min_row <= row <= mr.max_row:
                ws.unmerge_cells(str(mr))
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
        cols            = _find_result_cols(self.ws, self.header_row)

        self.col_sat  = cols["col_sat"]
        self.col_ecf  = cols["col_ecf"]
        self.col_nfce = cols["col_nfce"]
        self.col_just = cols["col_just"]

        logger.info(
            "ResultWriter: SAT=col%d ECF=col%d NFCE=col%d JUST=col%d (header linha %d)",
            self.col_sat, self.col_ecf, self.col_nfce, self.col_just, self.header_row
        )

        result_cols = {self.col_sat, self.col_ecf, self.col_nfce, self.col_just}
        _preemptive_unmerge(self.ws, result_cols)

    def write_result(self, result: TestResult, data_row: int) -> None:
        """Preenche as 4 colunas de resultado para a linha real do Excel."""
        status = "Ok"    if result.passed else "Erro"
        fill   = FILL_OK if result.passed else FILL_ERRO

        _safe_write(self.ws, data_row, self.col_sat,  status, fill)
        _safe_write(self.ws, data_row, self.col_ecf,  status, fill)
        _safe_write(self.ws, data_row, self.col_nfce, status, fill)

        motivo = result.motivo_erro[:100] if not result.passed else ""
        _safe_write(self.ws, data_row, self.col_just, motivo, FILL_NONE)

    def save(self) -> None:
        self.wb.save(self.output_path)
        logger.info("Resultado salvo em: %s", self.output_path)
