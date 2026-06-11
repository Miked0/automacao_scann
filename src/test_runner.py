# src/test_runner.py
"""
Módulo 5 — TestRunner
Responsabilidade: Orquestra os 10 checks de validação linha a linha do roteiro.

Fix v3 — localização de cupons:
- Ampliação dos aliases de coluna para extrair número do cupom do row
- Normalização do número antes de buscar (strip + lstrip zeros)
- Log diagnóstico quando cupom não é localizado (mostra chaves do row)
- Mantém todos os checks anteriores sem regressão
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from .audit_parser import AuditParser, _norm
from .coupon_pdf_parser import CouponPDFParser, Coupon
from .promo_engine import PromoEngine

logger = logging.getLogger(__name__)

TOLERANCE = 0.05

# Todos os aliases possíveis para a coluna de número do cupom no roteiro
_NUMERO_ALIASES = [
    "numero_cupom", "num. cupon", "num cupon", "num. cupom", "num cupom",
    "numero_cupon", "numerocupom", "numerocupon", "número cupom",
    "número do cupom", "numero do cupom", "cupon", "cupom",
    "número", "numero", "nro", "nro.", "no.", "n°",
    "coupon", "coupon_number", "coupon number",
    "sat", "ecf", "nfce", "nfc-e", "coo",
]


def _extract_numero(row: dict) -> str:
    """
    Extrai o número do cupom do row tentando todos os aliases conhecidos.
    Retorna string vazia se não encontrar.
    """
    # Tenta cada alias em ordem
    for alias in _NUMERO_ALIASES:
        val = row.get(alias)
        if val is not None:
            s = str(val).strip()
            if s and s.lower() not in ("none", "nan", "", "-", "0"):
                return s

    # Busca case-insensitive nas chaves do row
    for key, val in row.items():
        key_lower = str(key).lower()
        if any(alias in key_lower for alias in ["num", "cupon", "cupom", "sat", "ecf", "coo"]):
            if "status" in key_lower or "desc" in key_lower or "total" in key_lower:
                continue
            s = str(val).strip() if val is not None else ""
            if s and s.lower() not in ("none", "nan", "", "-", "0"):
                logger.debug("TestRunner: número do cupom encontrado via chave '%s': %s", key, s)
                return s

    return ""


@dataclass
class CheckResult:
    check: str
    ok: bool
    detalhe: str = ""


@dataclass
class TestResult:
    etapa: str
    linha: int
    cupom_numero: Optional[str]
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def motivo_erro(self) -> str:
        for c in self.checks:
            if not c.ok:
                return c.detalhe[:100]
        return ""


class TestRunner:
    """Executa os 10 checks em sequência para cada linha do roteiro."""

    def __init__(
        self,
        audit: AuditParser,
        pdf: CouponPDFParser,
        promo: PromoEngine,
    ):
        self.audit = audit
        self.pdf = pdf
        self.promo = promo

    def run(self, row: dict, linha: int) -> TestResult:
        etapa = str(row.get("etapa", ""))
        result = TestResult(etapa=etapa, linha=linha, cupom_numero=None)

        # ------------------------------------------------------------------
        # Check 1: Cupom localizado
        # ------------------------------------------------------------------
        numero_raw = _extract_numero(row)
        # Normaliza para busca (remove zeros à esquerda)
        numero_norm = _norm(numero_raw) if numero_raw else ""

        eans_raw = row.get("eans", [])
        if isinstance(eans_raw, str):
            eans = [e.strip() for e in eans_raw.split(",") if e.strip()]
        else:
            eans = [str(e).strip() for e in (eans_raw or []) if e]

        coupon: Optional[Coupon] = None
        movements: list[dict] = []

        # Tenta localizar pelo número (raw e normalizado)
        if numero_raw:
            coupon = self.pdf.get_by_numero(numero_raw)
            movements = self.audit.get_by_numero(numero_raw)

            # Se não achou com raw, tenta com normalizado
            if not coupon and numero_norm != numero_raw:
                coupon = self.pdf.get_by_numero(numero_norm)
            if not movements and numero_norm != numero_raw:
                movements = self.audit.get_by_numero(numero_norm)

        # Fallback por EANs
        if not coupon and eans:
            coupon = self.pdf.get_by_eans(eans)

        if not movements and eans:
            movements = self.audit.get_by_eans(eans)

        found = coupon is not None or len(movements) > 0
        result.cupom_numero = (
            coupon.get_numero() if coupon
            else (movements[0].get("numero") if movements else None)
        )

        if not found:
            # Log diagnóstico com as chaves disponíveis no row
            row_keys = {k: v for k, v in row.items() if v is not None and str(v).strip()}
            logger.warning(
                "Linha %d: cupom NÃO localizado — numero_raw='%s' norm='%s' EANs=%s | "
                "chaves_row=%s | chaves_audit_sample=%s",
                linha, numero_raw, numero_norm, eans,
                list(row_keys.keys())[:8],
                self.audit.all_numeros()[:10]
            )

        result.checks.append(CheckResult(
            "cupom_localizado", found,
            "" if found else (
                f"Cupom não localizado: numero='{numero_raw}' "
                f"(norm='{numero_norm}') EANs={eans}"
            )
        ))
        if not found:
            return result

        mov = movements[0] if movements else {}

        # ------------------------------------------------------------------
        # Check 2: HTTP 200
        # ------------------------------------------------------------------
        status = int(mov.get("_http_status", 0))
        ok_http = status == 200
        result.checks.append(CheckResult(
            "http_200", ok_http,
            "" if ok_http else f"Status HTTP: {status} (esperado 200)"
        ))

        # ------------------------------------------------------------------
        # Check 3: Cancelamento
        # ------------------------------------------------------------------
        obs = str(row.get("observacao", row.get("observação", row.get("obs", "")))).lower()
        cancelado_esperado = any(
            kw in obs for kw in ["cancelado", "cancelamento", "cancelacion", "cancel"]
        )
        cancelado_real = bool(mov.get("cancelacion", False))
        ok_cancel = cancelado_esperado == cancelado_real
        result.checks.append(CheckResult(
            "cancelamento", ok_cancel,
            "" if ok_cancel else (
                f"Cancelamento: esperado={cancelado_esperado} real={cancelado_real}"
            )
        ))

        # ------------------------------------------------------------------
        # Check 4: Total
        # ------------------------------------------------------------------
        total_rot = float(row.get("total", 0) or 0)
        total_mov = float(mov.get("total", 0) or 0)
        ok_total = abs(total_rot - total_mov) <= TOLERANCE
        result.checks.append(CheckResult(
            "total", ok_total,
            "" if ok_total else (
                f"Total: roteiro=R${total_rot:.2f} movimento=R${total_mov:.2f} "
                f"diff={abs(total_rot - total_mov):.2f}"
            )
        ))

        # ------------------------------------------------------------------
        # Check 5: Desconto
        # ------------------------------------------------------------------
        desc_rot = float(row.get("desconto", 0) or 0)
        desc_mov = float(mov.get("descuentoTotal", 0) or 0)
        ok_desc = abs(desc_rot - desc_mov) <= TOLERANCE
        result.checks.append(CheckResult(
            "desconto", ok_desc,
            "" if ok_desc else (
                f"Desconto: roteiro=R${desc_rot:.2f} mov=R${desc_mov:.2f}"
            )
        ))

        # ------------------------------------------------------------------
        # Check 6: Meio de pagamento — codigoTipoPago em pagos[0]
        # ------------------------------------------------------------------
        tipo_pag_rot = str(row.get(
            "meio_pagamento", row.get("pagamento", row.get("forma_pagamento", ""))
        )).strip()
        pagos = mov.get("pagos", [])
        tipo_pag_mov = pagos[0].get("codigoTipoPago", "") if pagos else ""

        if tipo_pag_rot and tipo_pag_rot.lower() not in ("none", "nan", ""):
            res_pag = self.promo.validate_pagamento(tipo_pag_mov, tipo_pag_rot)
            result.checks.append(CheckResult("pagamento", res_pag.ok, res_pag.detalhe))

        # ------------------------------------------------------------------
        # Check 7: BIN — lido de pagos[0].bin
        # ------------------------------------------------------------------
        bin_esp = str(row.get("bin", "") or "").strip()
        if bin_esp and bin_esp.lower() not in ("none", "nan", ""):
            res_bin = self.promo.validate_bin(mov, bin_esp)
            result.checks.append(CheckResult("bin", res_bin.ok, res_bin.detalhe))

        # ------------------------------------------------------------------
        # Check 8: Promoção (dispatcher por tipo)
        # ------------------------------------------------------------------
        tipo_promo = str(row.get(
            "tipo_promo", row.get("tipo promo", row.get("tipopromo", ""))
        ) or "").strip()
        if tipo_promo and tipo_promo.lower() not in ("none", "nan", "-", ""):
            promo_ativa = bool(row.get("promo_ativa", True))
            res_promo = self.promo.validate(tipo_promo, mov, row)
            result.checks.append(CheckResult("promocao", res_promo.ok, res_promo.detalhe))

            # ------------------------------------------------------------------
            # Check 9: Desconto manual indevido
            # ------------------------------------------------------------------
            res_dm = self.promo.validate_desconto_manual(mov, obs, promo_ativa)
            result.checks.append(CheckResult("desconto_manual", res_dm.ok, res_dm.detalhe))

        # ------------------------------------------------------------------
        # Check 10: Schema JSON mínimo
        # ------------------------------------------------------------------
        res_schema = self.promo.validate_schema(mov)
        result.checks.append(CheckResult("schema_json", res_schema.ok, res_schema.detalhe))

        return result
