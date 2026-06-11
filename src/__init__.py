"""
Scanntech QA Validator — pacote src
Exporta os 7 módulos da arquitetura.
"""

from .file_loader        import FileLoader
from .audit_parser       import AuditParser
from .coupon_pdf_parser  import CouponPDFParser, Coupon
from .promo_engine       import PromoEngine, PromoResult, TOLERANCE, PAGAMENTO_MAP
from .test_runner        import TestRunner, TestResult, CheckResult
from .result_writer      import ResultWriter, KEYWORDS_HEADER
from .audit_logger       import AuditLogger

__all__ = [
    "FileLoader",
    "AuditParser",
    "CouponPDFParser",
    "Coupon",
    "PromoEngine",
    "PromoResult",
    "TOLERANCE",
    "PAGAMENTO_MAP",
    "TestRunner",
    "TestResult",
    "CheckResult",
    "ResultWriter",
    "KEYWORDS_HEADER",
    "AuditLogger",
]
