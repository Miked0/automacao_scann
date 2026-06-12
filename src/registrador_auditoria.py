"""
Registrador de auditoria — gera log JSON estruturado de cada check.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .modelos import ResultadoTeste

logger = logging.getLogger(__name__)


class RegistradorAuditoria:
    """Registra cada execução de teste em log JSON estruturado."""

    def __init__(self, caminho_log: str):
        self.caminho_log = Path(caminho_log)
        self._entradas: list = []

    def registrar(self, resultado: ResultadoTeste, cupons_utilizados: Optional[list] = None) -> None:
        entrada = {
            "timestamp":         datetime.now().isoformat(),
            "etapa":             resultado.etapa,
            "linha":             resultado.linha,
            "chave_cupom":       resultado.chave_cupom,
            "cupons_utilizados": cupons_utilizados or [],
            "aprovado":          resultado.aprovado,
            "motivo_reprovacao": resultado.motivo_reprovacao,
            "checks": [
                {
                    "nome_check": c.nome_check,
                    "aprovado":   c.aprovado,
                    "detalhe":    c.detalhe,
                }
                for c in resultado.checks
            ],
        }
        self._entradas.append(entrada)

    def persistir(self) -> None:
        """Persiste todos os registros no arquivo JSON."""
        with open(self.caminho_log, "w", encoding="utf-8") as f:
            json.dump(self._entradas, f, ensure_ascii=False, indent=2)
        logger.info(
            "RegistradorAuditoria: %d entradas salvas em %s",
            len(self._entradas), self.caminho_log,
        )

    def resumo(self) -> dict:
        total  = len(self._entradas)
        passou = sum(1 for e in self._entradas if e["aprovado"])
        return {
            "total":  total,
            "passou": passou,
            "falhou": total - passou,
            "pct_ok": round((passou / total * 100) if total else 0, 1),
        }

    # Aliases de compatibilidade
    def record(self, resultado, cupons_utilizados=None):
        return self.registrar(resultado, cupons_utilizados)

    def flush(self):
        return self.persistir()

    def summary(self):
        return self.resumo()


# Alias de compatibilidade
AuditLogger = RegistradorAuditoria
