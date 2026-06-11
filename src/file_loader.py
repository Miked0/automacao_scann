"""
Módulo 1 — FileLoader
Responsabilidade: Valida existência e carrega todos os artefatos.

Planilhas suportadas:
  - TEMPLATE_COM_BIN_NOVO.xlsx  (3 etapas, com validação BIN ELO)
  - TEMPLATE_SEM_BIN_NOVO.xlsx  (3 etapas, sem BIN)

Estrutura da aba de testes (cabeçalho detectado dinamicamente):
  Teste | Tipo Promo | Items | Pagamento | Observacoes | SAT | ECF | NFCE |
  Sub-Total | Desconto | Total | Json | Minoristas | Cupom | Observacoes

Colunas de resultado (preenchidas pelo script):
  Json        → Ok/Erro (verde/vermelho)
  Minoristas  → Ok/Erro
  Cupom       → Ok/Erro
  Observacoes → justificativa ≤100 chars
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
    # Carregamento
    # ------------------------------------------------------------------

    def load_roteiro(self) -> openpyxl.Workbook:
        """
        Carrega o TEMPLATE xlsx em modo data_only=True.
        Preserva valores calculados sem reavaliar fórmulas.
        Compatível com TEMPLATE_COM_BIN_NOVO e TEMPLATE_SEM_BIN_NOVO.
        """
        logger.info("Carregando roteiro: %s", self.roteiro_path)
        wb = openpyxl.load_workbook(self.roteiro_path, data_only=True)
        logger.info("Abas encontradas: %s", wb.sheetnames)
        return wb

    def load_audit(self) -> pd.DataFrame:
        """
        Carrega o export Audit como DataFrame.
        Tenta a aba AUDIT_TICKETS; fallback para a primeira aba.
        O campo 'Request' contém o JSON da venda com aspas escapadas como "".
        """
        logger.info("Carregando audit: %s", self.audit_path)
        try:
            df = pd.read_excel(self.audit_path, sheet_name="AUDIT_TICKETS")
        except Exception:
            logger.warning("Aba AUDIT_TICKETS não encontrada — lendo primeira aba.")
            df = pd.read_excel(self.audit_path, sheet_name=0)
        logger.info("Audit carregado: %d linhas", len(df))
        return df

    def load_pdf_text_blocks(self) -> list:
        """
        Extrai texto bruto do PDF página a página.
        O CouponPDFParser faz o split em blocos de cupom.
        """
        logger.info("Carregando PDF: %s", self.pdf_path)
        pages = []
        with pdfplumber.open(self.pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                pages.append(text)
                logger.debug("Página %d: %d chars", i + 1, len(text))
        logger.info("PDF carregado: %d páginas", len(pages))
        return pages

    def list_json_files(self) -> list:
        """Lista arquivos JSON no diretório opcional."""
        if not self.json_dir:
            return []
        files = sorted(self.json_dir.glob("*.json"))
        logger.info("JSON dir: %d arquivos encontrados", len(files))
        return files

    def load_all(self) -> dict:
        """Valida e carrega todos os artefatos de uma vez."""
        self.validate_paths()
        return {
            "workbook":   self.load_roteiro(),
            "audit_df":   self.load_audit(),
            "pdf_pages":  self.load_pdf_text_blocks(),
            "json_files": self.list_json_files(),
        }
