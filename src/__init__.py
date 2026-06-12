"""
Pacote de automação de validação de roteiro de testes PDV.
"""
from .modelos               import BlocoCupom, MovimentoAudit, ResultadoCheck, ResultadoTeste
from .leitor                import carregar_casos_do_roteiro
from .processador_itens     import processar_itens
from .pagamentos            import normalizar_pagamento
from .motor_promocoes       import MotorPromocoes, ResultadoPromo
from .validadores           import validar_caso_de_teste
from .exportadores          import exportar_resultados
from .registrador_auditoria import RegistradorAuditoria

__all__ = [
    "BlocoCupom",
    "MovimentoAudit",
    "ResultadoCheck",
    "ResultadoTeste",
    "carregar_casos_do_roteiro",
    "processar_itens",
    "normalizar_pagamento",
    "MotorPromocoes",
    "ResultadoPromo",
    "validar_caso_de_teste",
    "exportar_resultados",
    "RegistradorAuditoria",
]
