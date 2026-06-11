"""
src — pacote principal do Scanntech QA Validator

Módulos:
    file_loader        — M1: valida e carrega artefatos
    audit_parser       — M2: indexa movimentos do Audit
    coupon_pdf_parser  — M3: extrai cupons do PDF
    promo_engine       — M4: motor de validação de promoções
    test_runner        — M5: orquestra validações linha a linha
    result_writer      — M6: preenche colunas e salva xlsx
    audit_logger       — M7: gera log JSON estruturado
"""

from .file_loader       import FileLoader
from .audit_parser      import AuditParser
from .coupon_pdf_parser import CouponPDFParser
from .promo_engine      import PromoEngine
from .test_runner       import TestRunner
from .result_writer     import ResultWriter
from .audit_logger      import AuditLogger

__all__ = [
    "FileLoader",
    "AuditParser",
    "CouponPDFParser",
    "PromoEngine",
    "TestRunner",
    "ResultWriter",
    "AuditLogger",
]
