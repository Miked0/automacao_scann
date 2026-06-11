"""
Módulo 7 — AuditLogger
Responsabilidade: Gera log JSON estruturado de cada check.

Artefato gerado: qa_audit_log.json
Estrutura de cada entrada:
  {
    "timestamp": "ISO-8601",
    "etapa": str,
    "linha": int,
    "cupom_numero": str | null,
    "cupons_utilizados": [str],
    "passou": bool,
    "motivo_erro": str,
    "checks": [{"check": str, "ok": bool, "detalhe": str}]
  }
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .test_runner import TestResult

logger = logging.getLogger(__name__)


class AuditLogger:
    """Registra cada execução de teste em log JSON estruturado."""

    def __init__(self, log_path: str):
        self.log_path  = Path(log_path)
        self._entries: list[dict] = []

    def record(
        self,
        result: TestResult,
        cupons_utilizados: Optional[list[str]] = None,
    ) -> None:
        """Adiciona entrada de um teste ao log em memória."""
        entry = {
            "timestamp":         datetime.now().isoformat(),
            "etapa":             result.etapa,
            "linha":             result.linha,
            "cupom_numero":      result.cupom_numero,
            "cupons_utilizados": cupons_utilizados or [],
            "passou":            result.passed,
            "motivo_erro":       result.motivo_erro,
            "checks": [
                {
                    "check":   c.check,
                    "ok":      c.ok,
                    "detalhe": c.detalhe,
                }
                for c in result.checks
            ],
        }
        self._entries.append(entry)

    def flush(self) -> None:
        """Persiste todos os registros no arquivo JSON."""
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(self._entries, f, ensure_ascii=False, indent=2)
        logger.info(
            "AuditLogger: %d entradas salvas em %s",
            len(self._entries), self.log_path,
        )

    def summary(self) -> dict:
        """Retorna resumo estatístico da execução."""
        total  = len(self._entries)
        passou = sum(1 for e in self._entries if e["passou"])
        return {
            "total":  total,
            "passou": passou,
            "falhou": total - passou,
            "pct_ok": round((passou / total * 100) if total else 0, 1),
        }
