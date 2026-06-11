# src/test_runner.py
"""
Módulo 5 — TestRunner
Responsabilidade: Orquestra os 10 checks de validação linha a linha do roteiro.

fix v4 — localização de cupons (3 gargalos corrigidos):
  1. float .0 → _norm() converte 6221.0 → '6221' antes de buscar
  2. aliases ticket: 'n° ticket', 'nº ticket', 'ticket', 'ticketid' adicionados
  3. AuditParser.get_by_numero() normaliza argumento antes da busca
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from .audit_parser import AuditParser
from .coupon_pdf_parser import CouponPDFParser, Coupon
from .promo_engine import PromoEngine

logger = logging.getLogger(__name__)

TOLERANCE = 0.05

# ---------------------------------------------------------------------------
# Normalização de valor numérico/string
# ---------------------------------------------------------------------------

def _norm(value) -> str:
    """
    Normaliza um valor de número de cupom:
      - float 6221.0  → '6221'
      - str  '006221' → '6221'   (remove zeros à esquerda)
      - str  ' 6221 ' → '6221'   (remove espaços)
      - str  '-6221'  → '6221'   (remove sinal negativo de cancelados)
    Retorna '' para None, 'nan', '0', etc.
    """
    if value is None:
        return ""
    s = str(value).strip()
    # Remove sufixo .0 de floats representados como string
    if s.endswith(".0") and s[:-2].lstrip("-").isdigit():
        s = s[:-2]
    # Remove sinal negativo
    s = s.lstrip("-")
    # Remove zeros à esquerda
    s = s.lstrip("0") or "0"
    # Rejeita valores inválidos
    if s.lower() in ("0", "none", "nan", "", "-"):
        return ""
    return s


# ---------------------------------------------------------------------------
# Aliases para a coluna de número do cupom no roteiro
# ---------------------------------------------------------------------------

_NUMERO_ALIASES = [
    # Variações com "cupom"
    "numero_cupom", "num. cupon", "num cupon", "num. cupom", "num cupom",
    "numero_cupon", "numerocupom", "numerocupon",
    "número cupom", "número do cupom", "numero do cupom",
    "n° cupom", "nº cupom",
    # Variações com "ticket" ← ADICIONADO
    "n° ticket", "nº ticket", "num. ticket", "num ticket",
    "numero ticket", "número ticket", "ticket",
    "ticketid", "ticket_id", "ticket id",
    # Termos simples
    "cupon", "cupom", "número", "numero",
    "nro", "nro.", "no.", "n°", "nº",
    # Fiscais
    "sat", "ecf", "nfce", "nfc-e", "coo",
    # EN
    "coupon", "coupon_number", "coupon number",
]

# Palavras-chave parciais para varredura dinâmica
_INCLUDE_KW = ["num", "cupon", "cupom", "ticket", "sat", "ecf", "coo", "nro", "n°", "nº"]
_EXCLUDE_KW = ["status", "desconto", "total", "tipo", "promo", "obs", "ean",
               "pagamento", "descuento", "cancelac", "bin", "etapa"]


def _extract_numero(row: dict) -> str:
    """
    Extrai o número do cupom do row:
      1. Tenta aliases exatos (lista _NUMERO_ALIASES)
      2. Varredura dinâmica case-insensitive nas chaves do row
    """
    # Tentativa 1: alias exato
    for alias in _NUMERO_ALIASES:
        val = row.get(alias)
        if val is not None:
            s = _norm(val)
            if s:
                return s

    # Tentativa 2: varredura dinâmica
    for key, val in row.items():
        key_lower = str(key).lower()
        if any(inc in key_lower for inc in _INCLUDE_KW) and \
           not any(exc in key_lower for exc in _EXCLUDE_KW):
            s = _norm(val) if val is not None else ""
            if s:
                logger.debug(
                    "TestRunner: número do cupom encontrado via chave dinâmica '%s': %s",
                    key, s
                )
                return s
    return ""


# ---------------------------------------------------------------------------
# Dataclasses de resultado
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# TestRunner
# ---------------------------------------------------------------------------

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
        numero_raw  = _extract_numero(row)          # string normalizada
        numero_norm = _norm(numero_raw)             # segunda normalização (idempotente)

        eans_raw = row.get("eans", [])
        if isinstance(eans_raw, str):
            eans = [e.strip() for e in eans_raw.split(",") if e.strip()]
        else:
            eans = [_norm(e) for e in (eans_raw or []) if _norm(e)]

        coupon: Optional[Coupon] = None
        movements: list[dict] = []

        # Tenta com o número extraído (já normalizado por _norm)
        if numero_raw:
            coupon    = self.pdf.get_by_numero(numero_raw)
            movements = self.audit.get_by_numero(numero_raw)

            # Segunda tentativa com _norm extra (por segurança)
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
            row_keys = {k: str(v)[:30] for k, v in row.items() if v is not None and str(v).strip()}
            logger.warning(
                "Linha %d: cupom NÃO localizado — raw='%s' norm='%s' EANs=%s\n"
                "  chaves_row=%s\n  sample_audit=%s",
                linha, numero_raw, numero_norm, eans,
                list(row_keys.keys())[:8],
                self.audit.all_numeros()[:5],
            )

        result.checks.append(CheckResult(
            "cupom_localizado", found,
            "" if found else (
                f"Cupom não localizado: numero='{numero_raw}' (norm='{numero_norm}') EANs={eans}"
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
        total_mov = float(mov.get("total",  0) or 0)
        ok_total  = abs(total_rot - total_mov) <= TOLERANCE
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
        desc_rot = float(row.get("desconto",       0) or 0)
        desc_mov = float(mov.get("descuentoTotal", 0) or 0)
        ok_desc  = abs(desc_rot - desc_mov) <= TOLERANCE
        result.checks.append(CheckResult(
            "desconto", ok_desc,
            "" if ok_desc else f"Desconto: roteiro=R${desc_rot:.2f} mov=R${desc_mov:.2f}"
        ))

        # ------------------------------------------------------------------
        # Check 6: Meio de pagamento — codigoTipoPago em pagos[0]
        # ------------------------------------------------------------------
        tipo_pag_rot = str(row.get(
            "meio_pagamento", row.get("pagamento", row.get("forma_pagamento", ""))
        ) or "").strip()
        pagos        = mov.get("pagos", [])
        tipo_pag_mov = pagos[0].get("codigoTipoPago", "") if pagos else ""

        if tipo_pag_rot and tipo_pag_rot.lower() not in ("none", "nan", ""):
            res_pag = self.promo.validate_pagamento(tipo_pag_mov, tipo_pag_rot)
            result.checks.append(CheckResult("pagamento", res_pag.ok, res_pag.detalhe))

        # ------------------------------------------------------------------
        # Check 7: BIN — campo bin em pagos[0] ou raiz
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
            res_promo   = self.promo.validate(tipo_promo, mov, row)
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
