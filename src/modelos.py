"""
Modelos de dados compartilhados entre módulos.

Sem dependências internas — apenas dataclasses puras.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class BlocoCupom:
    """Cupom fiscal extraído do PDF."""

    texto_bruto: str
    numero_sat: Optional[str] = None
    numero_ecf: Optional[str] = None
    numero_nfce: Optional[str] = None
    numero_coo: Optional[str] = None
    eans: List[str] = field(default_factory=list)
    subtotal: Optional[float] = None
    desconto: Optional[float] = None
    total: Optional[float] = None
    pagamentos: List[Dict] = field(default_factory=list)


@dataclass
class MovimentoAudit:
    """Linha da aba AUDIT_TICKETS do export."""

    numero_cupom: str
    json_bruto: Dict[str, Any] = field(default_factory=dict)
    codigo_status: Optional[int] = None
    total: Optional[float] = None
    desconto_total: Optional[float] = None
    cancelado: Optional[bool] = None
    detalhes: List[Dict] = field(default_factory=list)
    pagamentos: List[Dict] = field(default_factory=list)
    bin_cartao: Optional[str] = None


@dataclass
class ResultadoCheck:
    """Resultado de uma verificação individual."""

    nome_check: str
    aprovado: bool
    detalhe: str = ""


@dataclass
class ResultadoTeste:
    """Resultado completo de uma linha do roteiro."""

    etapa: str
    linha: int
    chave_cupom: str = ""
    cupons_utilizados: List[str] = field(default_factory=list)
    checks: List[ResultadoCheck] = field(default_factory=list)
    aprovado: bool = True
    motivo_reprovacao: str = ""
    status_sat: str = ""
    status_ecf: str = ""
    status_nfce: str = ""
    justificativa: str = ""
