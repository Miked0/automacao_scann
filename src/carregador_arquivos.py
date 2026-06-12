"""
Carregamento e validação dos artefatos de entrada.

Responsabilidade única: garantir que todos os arquivos existem
e entregá-los já carregados para os módulos seguintes.
"""
import logging
from pathlib import Path
from typing import Dict, List, Optional

import openpyxl
import pandas as pd
import pdfplumber

logger = logging.getLogger(__name__)

NOME_ABA_AUDIT      = "AUDIT_TICKETS"
INDICE_PRIMEIRA_ABA = 0


class CarregadorArquivos:
    """Valida e carrega os artefatos de entrada do validador QA."""

    def __init__(
        self,
        caminho_roteiro: str,
        caminho_audit: str,
        caminho_pdf: str,
        diretorio_json: Optional[str] = None,
    ):
        self.caminho_roteiro = Path(caminho_roteiro)
        self.caminho_audit   = Path(caminho_audit)
        self.caminho_pdf     = Path(caminho_pdf)
        self.diretorio_json  = Path(diretorio_json) if diretorio_json else None

    def validar_caminhos(self) -> None:
        """Lança FileNotFoundError se qualquer artefato obrigatório estiver ausente."""
        artefatos_obrigatorios = [
            (self.caminho_roteiro, "Roteiro (TEMPLATE xlsx)"),
            (self.caminho_audit,   "Export Audit xlsx"),
            (self.caminho_pdf,     "PDF de cupons"),
        ]
        for caminho, descricao in artefatos_obrigatorios:
            if not caminho.exists():
                raise FileNotFoundError(f"{descricao} não encontrado: {caminho}")
            logger.info("Artefato validado: %s → %s", descricao, caminho)

        if self.diretorio_json and not self.diretorio_json.exists():
            raise FileNotFoundError(
                f"Diretório JSON não encontrado: {self.diretorio_json}"
            )

    def carregar_roteiro(self) -> openpyxl.Workbook:
        logger.info("Carregando roteiro: %s", self.caminho_roteiro)
        return openpyxl.load_workbook(self.caminho_roteiro, data_only=True)

    def carregar_audit(self) -> pd.DataFrame:
        logger.info("Carregando audit: %s", self.caminho_audit)
        try:
            dataframe = pd.read_excel(self.caminho_audit, sheet_name=NOME_ABA_AUDIT)
        except Exception:
            # Aba padrão ausente — lemos a primeira disponível como fallback
            logger.warning("Aba '%s' não encontrada — lendo primeira aba.", NOME_ABA_AUDIT)
            dataframe = pd.read_excel(self.caminho_audit, sheet_name=INDICE_PRIMEIRA_ABA)
        logger.info("Audit carregado: %d linhas", len(dataframe))
        return dataframe

    def carregar_paginas_pdf(self) -> List[str]:
        """Extrai texto bruto do PDF página a página."""
        logger.info("Carregando PDF: %s", self.caminho_pdf)
        paginas: List[str] = []
        with pdfplumber.open(self.caminho_pdf) as pdf:
            for numero, pagina in enumerate(pdf.pages, start=1):
                texto = pagina.extract_text() or ""
                paginas.append(texto)
                logger.debug("Página %d: %d caracteres", numero, len(texto))
        logger.info("PDF carregado: %d página(s)", len(paginas))
        return paginas

    def listar_arquivos_json(self) -> List[Path]:
        if not self.diretorio_json:
            return []
        arquivos = sorted(self.diretorio_json.glob("*.json"))
        logger.info("Diretório JSON: %d arquivo(s) encontrado(s)", len(arquivos))
        return arquivos

    def carregar_tudo(self) -> Dict:
        """Valida e carrega todos os artefatos de uma vez."""
        self.validar_caminhos()
        return {
            "workbook":      self.carregar_roteiro(),
            "audit_df":      self.carregar_audit(),
            "pdf_paginas":   self.carregar_paginas_pdf(),
            "json_arquivos": self.listar_arquivos_json(),
        }


# Alias de compatibilidade — mantido enquanto __init__.py referencia FileLoader
FileLoader = CarregadorArquivos
