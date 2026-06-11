"""
M7 — AuditLogger
Gera o log JSON estruturado (qa_audit_log.json) com uma entrada por teste,
contendo: etapa, linha, cupons utilizados, lista de checks {check, ok, detalhe}
e motivo de erro.
"""

from __future__ import annotations
import json
import logging
import os
from typing import List

from .models import TestResult

log = logging.getLogger(__name__)


class AuditLogger:
    """Serializa TestResults em um arquivo JSON estruturado."""

    def __init__(self, output_path: str) -> None:
        self.output_path = output_path

    def write(self, results: List[TestResult]) -> None:
        entries = [self._serialize(r) for r in results]
        summary = {
            "total":    len(results),
            "ok":       sum(1 for r in results if r.overall_ok),
            "erro":     sum(1 for r in results if not r.overall_ok),
        }
        payload = {"summary": summary, "results": entries}

        os.makedirs(os.path.dirname(os.path.abspath(self.output_path)), exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)

        log.info(
            "AuditLogger: %d entradas salvas em %s. OK=%d ERRO=%d",
            len(results),
            self.output_path,
            summary["ok"],
            summary["erro"],
        )

    @staticmethod
    def _serialize(r: TestResult) -> dict:
        return {
            "etapa":         r.etapa,
            "linha":         r.linha,
            "cupom_key":     r.cupom_key,
            "coupons_used":  r.coupons_used,
            "overall_ok":    r.overall_ok,
            "error_reason":  r.error_reason,
            "checks": [
                {
                    "check":   c.check,
                    "ok":      c.ok,
                    "detalhe": c.detalhe,
                }
                for c in r.checks
            ],
        }
