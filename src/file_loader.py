"""
M1 — FileLoader
Valida existência e carrega todos os artefatos necessários:
  - Roteiro XLSX (openpyxl, data_only=True)
  - Export Audit XLSX (pandas)
  - PDF de cupons (pdfplumber — retorna lista de páginas)
  - JSONs avulsos opcionais (diretório)
"""

from __future__ import annotations
import glob
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import pdfplumber
from openpyxl import load_workbook
from openpyxl.workbook import Workbook

log = logging.getLogger(__name__)


class FileLoader:
    """Valida existência e carrega todos os artefatos de entrada."""

    def __init__(
        self,
        roteiro_path: str,
        audit_path: str,
        pdf_path: str,
        json_dir: Optional[str] = None,
    ) -> None:
        self.roteiro_path = roteiro_path
        self.audit_path   = audit_path
        self.pdf_path     = pdf_path
        self.json_dir     = json_dir

    # ── Validação ────────────────────────────────────────────────────────────
    def validate(self) -> None:
        """Levanta FileNotFoundError se algum arquivo obrigatório não existir."""
        for path in (self.roteiro_path, self.audit_path, self.pdf_path):
            if not os.path.isfile(path):
                raise FileNotFoundError(f"Arquivo não encontrado: {path}")
        if self.json_dir and not os.path.isdir(self.json_dir):
            raise FileNotFoundError(f"Diretório JSON não encontrado: {self.json_dir}")
        log.info("Todos os artefatos obrigatórios encontrados.")

    # ── Carga ────────────────────────────────────────────────────────────────
    def load(
        self,
    ) -> Tuple[Workbook, pd.DataFrame, List[Any], List[Dict]]:
        """
        Returns:
            wb_roteiro   — Workbook openpyxl (data_only=True)
            df_audit     — DataFrame com a aba AUDIT_TICKETS
            pdf_pages    — lista de objetos pdfplumber.Page
            extra_jsons  — lista de dicts dos JSONs avulsos (pode ser [])
        """
        wb        = self._load_roteiro()
        df_audit  = self._load_audit()
        pdf_pages = self._load_pdf()
        jsons     = self._load_jsons()
        return wb, df_audit, pdf_pages, jsons

    def _load_roteiro(self) -> Workbook:
        log.info("Carregando roteiro: %s", self.roteiro_path)
        wb = load_workbook(self.roteiro_path, data_only=True)
        return wb

    def _load_audit(self) -> pd.DataFrame:
        log.info("Carregando Audit: %s", self.audit_path)
        try:
            df = pd.read_excel(self.audit_path, sheet_name="AUDIT_TICKETS")
        except Exception:
            # Fallback: primeira aba
            log.warning("Aba AUDIT_TICKETS não encontrada; usando primeira aba.")
            df = pd.read_excel(self.audit_path)
        log.info("  %d linhas no Audit.", len(df))
        return df

    def _load_pdf(self) -> List[Any]:
        log.info("Abrindo PDF: %s", self.pdf_path)
        pdf = pdfplumber.open(self.pdf_path)
        pages = pdf.pages
        log.info("  %d páginas no PDF.", len(pages))
        return pages

    def _load_jsons(self) -> List[Dict]:
        if not self.json_dir:
            return []
        pattern = os.path.join(self.json_dir, "*.json")
        files   = sorted(glob.glob(pattern))
        result  = []
        for fp in files:
            try:
                with open(fp, encoding="utf-8") as fh:
                    result.append(json.load(fh))
            except Exception as exc:
                log.warning("Erro ao ler JSON %s: %s", fp, exc)
        log.info("  %d JSONs avulsos carregados de %s.", len(result), self.json_dir)
        return result
