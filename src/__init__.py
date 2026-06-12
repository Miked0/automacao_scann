# automacao_scann — pacote src
# Expõe as classes principais para uso externo e compatibilidade com imports legados.

from .carregador_arquivos    import CarregadorArquivos
from .extrator_cupom_pdf     import CouponPDFParser, Coupon
from .processador_auditoria  import ProcessadorAuditoria
from .motor_promocoes        import MotorPromocoes
from .executor_testes        import ExecutorTestes, ResultadoTeste, ResultadoCheck
from .gravador_resultados    import GravadorResultados
from .registrador_auditoria  import AuditLogger

# Aliases de compatibilidade (nomes legados usados por integrações externas)
FileLoader   = CarregadorArquivos
ResultWriter = GravadorResultados
AuditParser  = ProcessadorAuditoria
PromoEngine  = MotorPromocoes
TestRunner   = ExecutorTestes
TestResult   = ResultadoTeste
CheckResult  = ResultadoCheck

__all__ = [
    # Nomes canônicos (pt-BR)
    "CarregadorArquivos",
    "CouponPDFParser",
    "Coupon",
    "ProcessadorAuditoria",
    "MotorPromocoes",
    "ExecutorTestes",
    "ResultadoTeste",
    "ResultadoCheck",
    "GravadorResultados",
    "AuditLogger",
    # Aliases legados
    "FileLoader",
    "ResultWriter",
    "AuditParser",
    "PromoEngine",
    "TestRunner",
    "TestResult",
    "CheckResult",
]
