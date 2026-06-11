"""
Módulo 2 — AuditParser
Responsabilidade: Indexa movimentos do export Audit pelo nº cupom.
"""

import json
import logging
import re
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


class AuditParser:
    """Parseia e indexa o export Audit pelo número do cupom."""

    def __init__(self, audit_df: pd.DataFrame):
        self.audit_df = audit_df
        # índice: numero_cupom (str) → lista de dicts com dados do movimento
        self._index: dict = {}
        self._build_index()

    # ------------------------------------------------------------------
    # Construção do índice
    # ------------------------------------------------------------------

    def _build_index(self) -> None:
        """Itera o DataFrame e indexa cada linha pelo campo 'numero' do JSON."""
        for _, row in self.audit_df.iterrows():
            raw = row.get("Request", "")
            movement = self._parse_request(str(raw))
            if not movement:
                continue
            numero = str(movement.get("numero", "")).strip()
            if numero:
                self._index.setdefault(numero, []).append(movement)
        logger.info("AuditParser: %d cupons indexados", len(self._index))

    def _parse_request(self, raw: str) -> Optional[dict]:
        """
        Normaliza aspas duplas escapadas e tenta json.loads.
        Fallback: extrai campos via regex se o JSON estiver malformado.
        """
        normalized = raw.replace('""', '"').strip()
        if normalized.startswith('"') and normalized.endswith('"'):
            normalized = normalized[1:-1]

        try:
            data = json.loads(normalized)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

        return self._regex_fallback(normalized)

    def _regex_fallback(self, text: str) -> Optional[dict]:
        """Extrai campos mínimos via regex quando o JSON está malformado."""
        result: dict = {}
        patterns = {
            "numero":        r'"numero"\s*:\s*"([^"]+)"',
            "total":         r'"total"\s*:\s*([\d.]+)',
            "descuentoTotal":r'"descuentoTotal"\s*:\s*([\d.]+)',
            "cancelacion":   r'"cancelacion"\s*:\s*(true|false)',
            "status":        r'"status"\s*:\s*(\d+)',
        }
        for key, pat in patterns.items():
            m = re.search(pat, text)
            if m:
                val = m.group(1)
                if key in ("total", "descuentoTotal"):
                    result[key] = float(val)
                elif key == "cancelacion":
                    result[key] = val == "true"
                elif key == "status":
                    result[key] = int(val)
                else:
                    result[key] = val

        if "numero" in result:
            logger.warning("Fallback regex usado para cupom %s", result["numero"])
            return result
        return None

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def get_by_numero(self, numero: str) -> list:
        """Retorna todos os movimentos indexados pelo número do cupom."""
        return self._index.get(str(numero).strip(), [])

    def get_by_eans(self, eans: list) -> list:
        """
        Fallback: busca movimentos cujos detalles contenham ao menos um EAN da lista.
        """
        results = []
        for movements in self._index.values():
            for mov in movements:
                mov_eans = self._extract_eans(mov)
                if any(e in mov_eans for e in eans):
                    results.append(mov)
        return results

    @staticmethod
    def _extract_eans(movement: dict) -> set:
        """Extrai EANs do campo detalles do movimento."""
        eans: set = set()
        for item in movement.get("detalles", []):
            ean = str(item.get("ean", "")).strip()
            if ean:
                eans.add(ean)
        return eans

    def all_numeros(self) -> list:
        """Retorna todos os números de cupom indexados."""
        return list(self._index.keys())
