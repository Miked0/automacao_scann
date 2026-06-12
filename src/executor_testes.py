"""
Módulo 5 — ExecutorTestes  (v3 — L4: renomeado de test_runner.py)
Responsabilidade: Orquestra a validação linha a linha do roteiro.

Fix BUG-01: lê numero_cupom das colunas SAT(C6), ECF(C7) e NFCE(C8) individualmente,
            mapeadas pelo cabeçalho real do TEMPLATE.
Fix BUG-03: guard contra leitura de coluna já preenchida com 'Ok'/'Erro'.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from .processador_auditoria import ProcessadorAuditoria
from .extrator_cupom_pdf import CouponPDFParser, Coupon
from .motor_promocoes import MotorPromocoes

logger = logging.getLogger(__name__)

TOLERANCIA = 0.05

# Valores que indicam coluna de resultado já preenchida — NÃO usar como número
_SENTINELA_RESULTADO = {"ok", "erro", "error", "(status)", "n/a", ""}


def _limpar_numero(val) -> Optional[str]:
    """
    Sanitiza o valor lido da célula de número do cupom.
    Retorna None se for valor de resultado anterior (BUG-03 guard).
    """
    if val is None:
        return None
    s = str(val).strip()
    if s.lower() in _SENTINELA_RESULTADO:
        return None
    # Remove decimais de números lidos como float (ex: 79.0 → '79')
    try:
        return str(int(float(s)))
    except (ValueError, TypeError):
        return s if s else None


@dataclass
class ResultadoCheck:
    check: str
    ok: bool
    detalhe: str = ""


@dataclass
class ResultadoTeste:
    etapa: str
    linha: int
    cupom_numero: Optional[str]
    checks: list[ResultadoCheck] = field(default_factory=list)

    @property
    def passou(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def motivo_erro(self) -> str:
        for c in self.checks:
            if not c.ok:
                return c.detalhe[:100]
        return ""

    # Aliases de compatibilidade
    @property
    def passed(self) -> bool:
        return self.passou


class ExecutorTestes:
    """
    Executa os 10 checks em sequência para cada linha do roteiro.

    Espera que 'row' contenha as seguintes chaves (extraídas do TEMPLATE):
      numero_sat, numero_ecf, numero_nfce — número do cupom por tipo (BUG-01 fix)
      eans        — lista de EANs para fallback
      total, desconto, meio_pagamento, observacao, tipo_promo
      etapa, bin, qtd, trigger, paga, preco_unit, pct_promo, etc.
    """

    def __init__(
        self,
        auditoria: ProcessadorAuditoria,
        pdf: CouponPDFParser,
        motor: MotorPromocoes,
    ):
        self.auditoria = auditoria
        self.pdf       = pdf
        self.motor     = motor

    # ------------------------------------------------------------------
    # Execução principal
    # ------------------------------------------------------------------

    def executar(self, row: dict, linha: int) -> ResultadoTeste:
        etapa  = str(row.get("etapa", ""))
        result = ResultadoTeste(etapa=etapa, linha=linha, cupom_numero=None)

        # ── Check 1: Cupom localizado ──────────────────────────────────
        num_sat  = _limpar_numero(row.get("numero_sat"))
        num_ecf  = _limpar_numero(row.get("numero_ecf"))
        num_nfce = _limpar_numero(row.get("numero_nfce"))
        eans     = [str(e).strip() for e in row.get("eans", []) if e]

        cupom: Optional[Coupon] = None
        movimentos: list[dict]  = []

        for num in filter(None, [num_sat, num_ecf, num_nfce]):
            c = self.pdf.get_by_numero(num)
            m = self.auditoria.get_by_numero(num)
            if c or m:
                cupom      = c or cupom
                movimentos = m or movimentos
                result.cupom_numero = num
                break

        if not cupom and eans:
            cupom = self.pdf.get_by_eans(eans)
        if not movimentos and eans:
            movimentos = self.auditoria.get_by_eans(eans)
            if movimentos and not result.cupom_numero:
                result.cupom_numero = movimentos[0].get("numero")

        encontrado = cupom is not None or len(movimentos) > 0
        result.checks.append(ResultadoCheck(
            "cupom_localizado", encontrado,
            "" if encontrado else
            f"Cupom não localizado: SAT={num_sat} ECF={num_ecf} NFCE={num_nfce} EANs={eans}"
        ))
        if not encontrado:
            return result

        mov = movimentos[0] if movimentos else {}

        # ── Check 2: HTTP 200 ─────────────────────────────────────────
        status  = int(mov.get("status", mov.get("httpStatus", 200)))
        ok_http = status == 200
        result.checks.append(ResultadoCheck(
            "http_200", ok_http,
            "" if ok_http else f"Status HTTP: {status}"
        ))

        # ── Check 3: Cancelamento ─────────────────────────────────────
        obs                = str(row.get("observacao", "")).lower()
        cancelado_esperado = any(kw in obs for kw in ("cancelado", "cancelacion", "cancelamento"))
        cancelado_real     = bool(mov.get("cancelacion", False))
        ok_cancel          = cancelado_esperado == cancelado_real
        result.checks.append(ResultadoCheck(
            "cancelamento", ok_cancel,
            "" if ok_cancel else
            f"Cancelamento esperado={cancelado_esperado} real={cancelado_real}"
        ))

        # ── Check 4: Total ────────────────────────────────────────────
        total_rot = self._para_float(row, "total")
        total_mov = float(mov.get("total", 0))
        ok_total  = abs(total_rot - total_mov) <= TOLERANCIA
        result.checks.append(ResultadoCheck(
            "total", ok_total,
            "" if ok_total else
            f"Total roteiro={total_rot:.2f} movimento={total_mov:.2f}"
        ))

        # ── Check 5: Desconto ─────────────────────────────────────────
        desc_rot = self._para_float(row, "desconto")
        desc_mov = float(mov.get("descuentoTotal", 0))
        ok_desc  = abs(desc_rot - desc_mov) <= TOLERANCIA
        result.checks.append(ResultadoCheck(
            "desconto", ok_desc,
            "" if ok_desc else
            f"Desconto roteiro={desc_rot:.2f} mov={desc_mov:.2f}"
        ))

        # ── Check 6: Meio de pagamento ────────────────────────────────
        tipo_pag_rot = str(row.get("meio_pagamento", row.get("pagamento", "")))
        tipo_pag_mov = str(mov.get("codigoTipoPago", ""))
        res_pag = self.motor.validar_pagamento(tipo_pag_mov, tipo_pag_rot)
        result.checks.append(ResultadoCheck("pagamento", res_pag.ok, res_pag.detalhe))

        # ── Check 7: BIN ──────────────────────────────────────────────
        bin_esp = str(row.get("bin", "")).strip()
        if bin_esp and bin_esp.lower() not in ("nan", "none", "", "n/a"):
            res_bin = self.motor.validar_bin(mov, bin_esp)
            result.checks.append(ResultadoCheck("bin", res_bin.ok, res_bin.detalhe))

        # ── Check 8: Promoção ─────────────────────────────────────────
        tipo_promo = str(row.get("tipo_promo", row.get("tipo promo", ""))).strip().upper()
        if tipo_promo and tipo_promo not in ("N/A", "NA", "NONE", ""):
            promo_ativa = bool(row.get("promo_ativa", True))
            res_promo   = self.motor.validar(tipo_promo, mov, row)
            result.checks.append(ResultadoCheck("promocao", res_promo.ok, res_promo.detalhe))

            # ── Check 9: Desconto manual indevido ─────────────────────
            res_dm = self.motor.validar_desconto_manual(mov, obs, promo_ativa)
            result.checks.append(ResultadoCheck("desconto_manual", res_dm.ok, res_dm.detalhe))

        # ── Check 10: Schema JSON ─────────────────────────────────────
        res_schema = self.motor.validar_schema(mov)
        result.checks.append(ResultadoCheck("schema_json", res_schema.ok, res_schema.detalhe))

        return result

    # Alias de compatibilidade — mantido enquanto integrações externas chamam run()
    def run(self, row: dict, linha: int) -> ResultadoTeste:
        return self.executar(row, linha)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _para_float(row: dict, chave: str, padrao: float = 0.0) -> float:
        try:
            return float(row.get(chave, padrao) or padrao)
        except (TypeError, ValueError):
            return padrao

    # Alias de compatibilidade
    _safe_float = _para_float


# Aliases de compatibilidade — mantidos para integrações externas
TestRunner  = ExecutorTestes
TestResult  = ResultadoTeste
CheckResult = ResultadoCheck
