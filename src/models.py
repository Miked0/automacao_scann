from __future__ import annotations

from dataclasses import dataclass, asdict, field
from decimal import Decimal
from typing import Any, Dict, List, Optional


@dataclass
class ParsedItem:
    codigo: str
    quantidade: Decimal
    tipo: str
    original: str


@dataclass
class PaymentInfo:
    pagamento_normalizado: Optional[str]
    codigo_tipo_pago: Optional[int]
    is_multiplo: bool = False
    requires_bin: bool = False
    original: Optional[str] = None


@dataclass
class NumericField:
    raw: Any
    norm: Optional[Decimal]
    error: bool = False


@dataclass
class ValidationResult:
    status_final: str
    motivo_status: Optional[str] = None
    alertas: List[str] = field(default_factory=list)


@dataclass
class TestCase:
    bloco: str
    row_index: int
    teste: Any = None
    tipo_promo: Optional[str] = None
    itens_raw: Optional[str] = None
    pagamento_raw: Optional[str] = None
    observacoes_raw: Optional[str] = None
    subtotal_raw: Any = None
    desconto_raw: Any = None
    total_raw: Any = None
    status_tecnico_raw: Optional[str] = None
    extra_fields: Dict[str, Any] = field(default_factory=dict)

    itens_parseados: List[ParsedItem] = field(default_factory=list)
    pagamento_info: Optional[PaymentInfo] = None
    subtotal: Optional[NumericField] = None
    desconto: Optional[NumericField] = None
    total: Optional[NumericField] = None
    validation: Optional[ValidationResult] = None

    def to_export_dict(self) -> Dict[str, Any]:
        return {
            'teste': self.teste,
            'bloco': self.bloco,
            'row_index': self.row_index,
            'tipo_promo': self.tipo_promo,
            'itens_raw': self.itens_raw,
            'itens_parseados': [asdict(i) for i in self.itens_parseados],
            'pagamento_raw': self.pagamento_raw,
            'pagamento_normalizado': self.pagamento_info.pagamento_normalizado if self.pagamento_info else None,
            'codigo_tipo_pago': self.pagamento_info.codigo_tipo_pago if self.pagamento_info else None,
            'is_multiplo': self.pagamento_info.is_multiplo if self.pagamento_info else None,
            'requires_bin': self.pagamento_info.requires_bin if self.pagamento_info else None,
            'observacoes_originais': self.observacoes_raw,
            'subtotal_raw': self.subtotal.raw if self.subtotal else self.subtotal_raw,
            'subtotal_norm': self.subtotal.norm if self.subtotal else None,
            'desconto_raw': self.desconto.raw if self.desconto else self.desconto_raw,
            'desconto_norm': self.desconto.norm if self.desconto else None,
            'total_raw': self.total.raw if self.total else self.total_raw,
            'total_norm': self.total.norm if self.total else None,
            'status_final': self.validation.status_final if self.validation else None,
            'motivo_status': self.validation.motivo_status if self.validation else None,
            'alertas': '; '.join(self.validation.alertas) if self.validation and self.validation.alertas else None,
            'status_tecnico_raw': self.status_tecnico_raw,
            **self.extra_fields,
        }
