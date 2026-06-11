"""
Módulo 1 — FileLoader
Responsabilidade: Valida existência e carrega todos os artefatos.
"""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd
import openpyxl
import pdfplumber

logger = logging.getLogger(__name__)


class FileLoader:
    """Valida e carrega os artefatos de entrada do validador QA."""

    def __init__(
        self,
        roteiro_path: str,
        audit_path: str,
        pdf_path: str,
        json_dir: Optional[str] = None,
    ):
        self.roteiro_path = Path(roteiro_path)
        self.audit_path   = Path(audit_path)
        self.pdf_path     = Path(pdf_path)
        self.json_dir     = Path(json_dir) if json_dir else None

    # ------------------------------------------------------------------
    # Validação
    # ------------------------------------------------------------------

    def validate_paths(self) -> None:
        """Lança FileNotFoundError se qualquer artefato obrigatório não existir."""
        required = [
            (self.roteiro_path, "Roteiro (TEMPLATE xlsx)"),
            (self.audit_path,   "Export Audit xlsx"),
            (self.pdf_path,     "PDF de cupons"),
        ]
        for path, label in required:
            if not path.exists():
                raise FileNotFoundError(f"{label} não encontrado: {path}")
            logger.info("Artefato validado: %s → %s", label, path)

        if self.json_dir and not self.json_dir.exists():
            raise FileNotFoundError(f"Diretório JSON não encontrado: {self.json_dir}")

    # ------------------------------------------------------------------
    # Carregamento individual
    # ------------------------------------------------------------------

    def load_roteiro(self) -> openpyxl.Workbook:
        """Carrega o TEMPLATE xlsx em modo data_only=True (preserva valores calculados)."""
        logger.info("Carregando roteiro: %s", self.roteiro_path)
        return openpyxl.load_workbook(self.roteiro_path, data_only=True)

    def load_audit(self) -> pd.DataFrame:
        """Carrega o export Audit como DataFrame, priorizando a aba AUDIT_TICKETS."""
        logger.info("Carregando audit: %s", self.audit_path)
        try:
            df = pd.read_excel(self.audit_path, sheet_name="AUDIT_TICKETS")
        except Exception:
            logger.warning("Aba AUDIT_TICKETS não encontrada — lendo primeira aba.")
            df = pd.read_excel(self.audit_path, sheet_name=0)
        logger.info("Audit carregado: %d linhas", len(df))
        return df

    def load_pdf_text_blocks(self) -> list[str]:
        """Extrai texto bruto do PDF e retorna lista de páginas."""
        logger.info("Carregando PDF: %s", self.pdf_path)
        pages: list[str] = []
        with pdfplumber.open(self.pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                pages.append(text)
                logger.debug("Página %d: %d chars", i + 1, len(text))
        logger.info("PDF carregado: %d páginas", len(pages))
        return pages

    def list_json_files(self) -> list[Path]:
        """Lista arquivos JSON no diretório opcional."""
        if not self.json_dir:
            return []
        files = sorted(self.json_dir.glob("*.json"))
        logger.info("JSON dir: %d arquivos encontrados", len(files))
        return files

    # ------------------------------------------------------------------
    # Carregamento unificado
    # ------------------------------------------------------------------

    def load_all(self) -> dict:
        """Valida e carrega todos os artefatos de uma vez.

        Returns:
            dict com chaves: workbook, audit_df, pdf_pages, json_files
        """
        self.validate_paths()
        return {
            "workbook":   self.load_roteiro(),
            "audit_df":   self.load_audit(),
            "pdf_pages":  self.load_pdf_text_blocks(),
            "json_files": self.list_json_files(),
        }
