"""
src/ — Módulos do validador QA Scanntech.

Arquitetura:
  1. FileLoader      — Valida existência e carrega todos os artefatos
  2. AuditParser     — Indexa movimentos do export Audit pelo nº cupom
  3. CouponPDFParser — Extrai cupons fiscais (DANFE/NFC-e/SAT) do PDF
  4. PromoEngine     — Motor de validação por tipo de promoção
  5. TestRunner      — Orquestra a validação linha a linha do roteiro
  6. ResultWriter    — Preenche colunas de resultado + salva xlsx
  7. AuditLogger     — Gera log JSON estruturado de cada check
"""
from .file_loader import FileLoader
from .audit_parser import AuditParser
from .coupon_pdf_parser import CouponPDFParser
from .promo_engine import PromoEngine
from .test_runner import TestRunner
from .result_writer import ResultWriter
from .audit_logger import AuditLogger

__all__ = [
    "FileLoader",
    "AuditParser",
    "CouponPDFParser",
    "PromoEngine",
    "TestRunner",
    "ResultWriter",
    "AuditLogger",
]
