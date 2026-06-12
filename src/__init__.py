# automacao_scann — pacote src
# Expõe as classes principais para uso externo e compatibilidade com imports legados.

from .carregador_arquivos  import CarregadorArquivos
from .extrator_cupom_pdf   import CouponPDFParser, Coupon
from .processador_auditoria import ProcessadorAuditoria
from .promo_engine         import PromoEngine
from .test_runner          import TestRunner, TestResult, CheckResult
from .gravador_resultados  import GravadorResultados
from .registrador_auditoria import AuditLogger

# Aliases de compatibilidade (nomes legados usados por integrações externas)
FileLoader   = CarregadorArquivos
ResultWriter = GravadorResultados
AuditParser  = ProcessadorAuditoria

__all__ = [
    # Nomes canônicos (pt-BR)
    "CarregadorArquivos",
    "CouponPDFParser",
    "Coupon",
    "ProcessadorAuditoria",
    "PromoEngine",
    "TestRunner",
    "TestResult",
    "CheckResult",
    "GravadorResultados",
    "AuditLogger",
    # Aliases legados
    "FileLoader",
    "ResultWriter",
    "AuditParser",
]
