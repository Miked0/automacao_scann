"""
M0 — Modelos de dados compartilhados entre módulos.

Não possui dependências internas — apenas dataclasses/TypedDict puros.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CouponBlock:
    """Representa um cupom fiscal extraído do PDF."""
    raw_text: str
    sat_number: Optional[str]    = None
    ecf_number: Optional[str]    = None
    nfce_number: Optional[str]   = None
    coo_number: Optional[str]    = None
    eans: List[str]              = field(default_factory=list)
    subtotal: Optional[float]    = None
    desconto: Optional[float]    = None
    total: Optional[float]       = None
    pagamentos: List[Dict]       = field(default_factory=list)   # [{tipo, valor}]


@dataclass
class AuditMovement:
    """Representa um movimento do Audit (uma linha da aba AUDIT_TICKETS)."""
    cupom_number: str
    raw_json: Dict[str, Any]     = field(default_factory=dict)
    status_code: Optional[int]   = None
    total: Optional[float]       = None
    descuento_total: Optional[float] = None
    cancelacion: Optional[bool]  = None
    detalles: List[Dict]         = field(default_factory=list)
    pagos: List[Dict]            = field(default_factory=list)
    bin_value: Optional[str]     = None


@dataclass
class CheckResult:
    """Resultado de um check individual."""
    check: str
    ok: bool
    detalhe: str = ""


@dataclass
class TestResult:
    """Resultado completo de uma linha do roteiro."""
    etapa: str
    linha: int
    cupom_key: str                               = ""
    coupons_used: List[str]                      = field(default_factory=list)
    checks: List[CheckResult]                    = field(default_factory=list)
    overall_ok: bool                             = True
    error_reason: str                            = ""
    col_sat_status: str                          = ""
    col_ecf_status: str                          = ""
    col_nfce_status: str                         = ""
    col_justificativa: str                       = ""
