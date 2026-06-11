"""
Módulo 1 — FileLoader
Responsabilidade: Valida existência e carrega todos os artefatos de entrada.
"""
import os
import logging
import pandas as pd
import openpyxl
import pdfplumber

logger = logging.getLogger(__name__)


class FileLoader:
    """Valida e carrega os três artefatos de entrada do validador QA."""

    REQUIRED_EXTENSIONS = {
        "roteiro": [".xlsx"],
        "audit": [".xlsx"],
        "pdf": [".pdf"],
    }

    def __init__(self, roteiro_path: str, audit_path: str, pdf_path: str, json_dir: str = None):
        self.roteiro_path = roteiro_path
        self.audit_path = audit_path
        self.pdf_path = pdf_path
        self.json_dir = json_dir
        self._validate_paths()

    def _validate_paths(self):
        paths = {
            "roteiro": self.roteiro_path,
            "audit": self.audit_path,
            "pdf": self.pdf_path,
        }
        for name, path in paths.items():
            if not os.path.exists(path):
                raise FileNotFoundError(f"Arquivo não encontrado [{name}]: {path}")
            ext = os.path.splitext(path)[1].lower()
            allowed = self.REQUIRED_EXTENSIONS[name]
            if ext not in allowed:
                raise ValueError(
                    f"Extensão inválida para [{name}]: {ext}. Esperado: {allowed}"
                )
        if self.json_dir and not os.path.isdir(self.json_dir):
            raise NotADirectoryError(f"Diretório json-dir não encontrado: {self.json_dir}")
        logger.info("Todos os arquivos de entrada validados com sucesso.")

    def load_roteiro(self) -> openpyxl.Workbook:
        """Carrega o roteiro TEMPLATE xlsx em modo data_only para preservar valores calculados."""
        logger.info(f"Carregando roteiro: {self.roteiro_path}")
        wb = openpyxl.load_workbook(self.roteiro_path, data_only=True)
        return wb

    def load_audit(self) -> pd.DataFrame:
        """Carrega o export Audit como DataFrame."""
        logger.info(f"Carregando audit: {self.audit_path}")
        try:
            df = pd.read_excel(self.audit_path, sheet_name="AUDIT_TICKETS")
        except Exception:
            df = pd.read_excel(self.audit_path, sheet_name=0)
        logger.info(f"Audit carregado: {len(df)} linhas.")
        return df

    def load_pdf(self) -> pdfplumber.PDF:
        """Abre o PDF de cupons fiscais via pdfplumber."""
        logger.info(f"Carregando PDF: {self.pdf_path}")
        return pdfplumber.open(self.pdf_path)

    def load_json_dir(self) -> list:
        """Carrega JSONs avulsos do diretório opcional."""
        import json
        jsons = []
        if not self.json_dir:
            return jsons
        for fname in os.listdir(self.json_dir):
            if fname.lower().endswith(".json"):
                fpath = os.path.join(self.json_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        jsons.append(json.load(f))
                except Exception as e:
                    logger.warning(f"Falha ao carregar JSON avulso {fname}: {e}")
        logger.info(f"{len(jsons)} JSONs avulsos carregados de {self.json_dir}.")
        return jsons
