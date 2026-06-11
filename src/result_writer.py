"""
Módulo 6 — ResultWriter
Responsabilidade: Preenche colunas de resultado + salva xlsx.

Colunas de resultado (detectadas dinamicamente ou fallback R/S/T/U):
  - col_sat  → "Ok" / "Erro" + fill verde/vermelho
  - col_ecf  → "Ok" / "Erro" + fill verde/vermelho
  - col_nfce → "Ok" / "Erro" + fill verde/vermelho
  - col_just → justificativa ≤ 100 chars em caso de ERRO

Colunas de entrada do cupom (leitura):
  F → numero_cupom / numero de cupom
  G → SAT
  H → ECF ou NFCE
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

# Palavras-chave para detectar a linha de cabeçalho do roteiro
KEYWORDS_HEADER = {"teste", "tipo", "promo", "roteiro", "etapa", "descricao",
                   "sat", "ecf", "nfce", "cupom"}

# Mapeamento: chave normalizada → palavras-chave de detecção
# Colunas de ENTRADA (F, G, H) — usadas para leitura do número do cupom
COLUNA_CUPOM_KEYWORDS = {
    "sat":          ["sat"],
    "nfce":         ["nfce", "nfc-e", "nf-ce"],
    "ecf":          ["ecf", "coo"],
    "numero_cupom": ["numero de cupom", "numero_cupom", "n° cupom", "nº cupom", "num cupom"],
}


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


def build_row_dict(ws, header_row: int, data_row: int) -> dict:
    """
    Constrói o dicionário de uma linha de dados mapeando cada célula
    pela chave normalizada do cabeçalho.

    Normalização: lower().strip(), espaços → underline.
    Colunas F/G/H do cupom recebem chaves canônicas:
      G → 'sat', H → 'ecf' ou 'nfce', F → 'numero_cupom'
    """
    headers_raw = [
        str(cell.value).strip() if cell.value else f"_col{cell.column}"
        for cell in ws[header_row]
    ]
    headers_norm = [h.lower().replace(" ", "_") for h in headers_raw]

    # Substitui cabeçalhos de cupom pelos nomes canônicos
    canonical_map = {}
    for canon, kws in COLUNA_CUPOM_KEYWORDS.items():
        for i, h_raw in enumerate(headers_raw):
            h_low = h_raw.lower()
            if any(kw in h_low for kw in kws):
                canonical_map[i] = canon
                break

    values = [cell.value for cell in ws[data_row]]
    row_dict = {}
    for i, val in enumerate(values):
        key = canonical_map.get(i, headers_norm[i] if i < len(headers_norm) else f"_col{i}")
        row_dict[key] = val

    return row_dict


class ResultWriter:
    """Escreve resultados nas colunas corretas do TEMPLATE e salva o xlsx."""

    def __init__(self, workbook: openpyxl.Workbook, output_path: str):
        self.wb          = workbook
        self.output_path = Path(output_path)
        self.ws          = workbook.active

        self.header_row = _detect_header_row(self.ws)

        # Detecta colunas de resultado dinamicamente
        self.col_sat  = _find_col_by_keyword(self.ws, self.header_row, ["sat"])
        self.col_ecf  = _find_col_by_keyword(self.ws, self.header_row, ["ecf", "coo"])
        self.col_nfce = _find_col_by_keyword(self.ws, self.header_row, ["nfce", "nfc-e"])
        self.col_just = _find_col_by_keyword(
            self.ws, self.header_row, ["just", "motivo", "observ"]
        )

        # Fallback: R=18, S=19, T=20, U=21
        if not self.col_sat:  self.col_sat  = 18
        if not self.col_ecf:  self.col_ecf  = 19
        if not self.col_nfce: self.col_nfce = 20
        if not self.col_just: self.col_just = 21

        logger.info(
            "ResultWriter colunas de resultado: SAT=%s ECF=%s NFCE=%s JUST=%s",
            self.col_sat, self.col_ecf, self.col_nfce, self.col_just,
        )

        # Log das colunas de entrada do cupom
        for canon, kws in COLUNA_CUPOM_KEYWORDS.items():
            col = _find_col_by_keyword(self.ws, self.header_row, kws)
            logger.info("Coluna de entrada '%s': %s", canon, col or "não encontrada")

    def write_result(self, result: TestResult, data_row: int) -> None:
        """Preenche as colunas de resultado para uma linha de dado.

        Garante que APENAS as colunas de resultado sejam modificadas.
        """
        status = "Ok"   if result.passed else "Erro"
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
