"""
Módulo 7 — AuditLogger
Responsabilidade: Gera log JSON estruturado de cada check.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class AuditLogger:
    """Registra cada execução de teste em log JSON estruturado."""

    def __init__(self, log_path: str):
        self.log_path  = Path(log_path)
        self._entries: list[dict] = []

    # ------------------------------------------------------------------
    # Interface pública chamada pelo orquestrador
    # ------------------------------------------------------------------

    def write(self, results: list) -> None:
        """
        Alias público compatível com o orquestrador:
            audit_logger.write(results)
        Registra todos os TestResult e persiste o JSON.
        """
        for result in results:
            self.record(result)
        self.flush()

    # ------------------------------------------------------------------
    # API granular (para uso direto ou testes)
    # ------------------------------------------------------------------

    def record(self, result, cupons_utilizados: Optional[list] = None) -> None:
        """Adiciona entrada de um teste ao log em memória."""
        # Suporte a TestResult com atributo overall_ok (novo) ou passed (legado)
        passou = getattr(result, "overall_ok", None)
        if passou is None:
            passou = getattr(result, "passed", False)

        motivo = getattr(result, "error_reason", None) or getattr(result, "motivo_erro", "")

        entry = {
            "timestamp":         datetime.now().isoformat(),
            "etapa":             getattr(result, "etapa", ""),
            "linha":             getattr(result, "linha", 0),
            "cupom_numero":      getattr(result, "cupom_numero",  None)
                                  or getattr(result, "cupom_key", None),
            "cupons_utilizados": cupons_utilizados
                                  or getattr(result, "coupons_used", []),
            "passou":            passou,
            "motivo_erro":       motivo,
            "checks": [
                {
                    "check":   c.check,
                    "ok":      c.ok,
                    "detalhe": c.detalhe,
                }
                for c in getattr(result, "checks", [])
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
        """Retorna um resumo estatístico da execução."""
        total  = len(self._entries)
        passou = sum(1 for e in self._entries if e["passou"])
        return {
            "total":  total,
            "passou": passou,
            "falhou": total - passou,
            "pct_ok": round((passou / total * 100) if total else 0, 1),
        }
