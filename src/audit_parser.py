# src/audit_parser.py
"""
Módulo 2 — AuditParser
Responsabilidade: Indexa movimentos do export Audit pelo nº cupom.
Correções v2:
- Injeta _http_status da coluna separada do DataFrame (Coluna I)
- Usa codigoBarras (não 'ean') para extrair EANs dos detalles
- Trata número com prefixo '-' (cupons cancelados)
"""

import json
import logging
import re
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Possíveis nomes da coluna de status HTTP no export Audit
_STATUS_COL_CANDIDATES = [
    "Código status", "Codigo status", "codigo_status",
    "status_code", "StatusCode", "HTTP Status", "status",
]


class AuditParser:
    """Parseia e indexa o export Audit pelo número do cupom."""

    def __init__(self, audit_df: pd.DataFrame):
        self.audit_df = audit_df
        self._status_col: Optional[str] = self._detect_status_col()
        # índice: numero_cupom (str) → lista de dicts com dados do movimento
        self._index: dict[str, list[dict]] = {}
        self._build_index()

    # ------------------------------------------------------------------
    # Detecção da coluna de status HTTP
    # ------------------------------------------------------------------

    def _detect_status_col(self) -> Optional[str]:
        """Detecta qual coluna do DataFrame contém o status HTTP."""
        for candidate in _STATUS_COL_CANDIDATES:
            if candidate in self.audit_df.columns:
                logger.info("AuditParser: coluna status HTTP detectada → '%s'", candidate)
                return candidate
        # Busca parcial
        for col in self.audit_df.columns:
            if "status" in str(col).lower():
                logger.info("AuditParser: coluna status HTTP detectada (parcial) → '%s'", col)
                return col
        logger.warning("AuditParser: coluna de status HTTP não encontrada — usará 0")
        return None

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

            # Injeta status HTTP do DataFrame (fora do JSON)
            if self._status_col:
                try:
                    movement["_http_status"] = int(row[self._status_col])
                except (ValueError, TypeError):
                    movement["_http_status"] = 0
            else:
                movement["_http_status"] = 0

            numero = str(movement.get("numero", "")).strip()
            if numero:
                self._index.setdefault(numero, []).append(movement)
                # Cupons cancelados têm numero com '-', indexar sem o '-' também
                numero_sem_prefixo = numero.lstrip("-")
                if numero_sem_prefixo != numero:
                    self._index.setdefault(numero_sem_prefixo, []).append(movement)

        logger.info("AuditParser: %d chaves indexadas", len(self._index))

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
        }
        for key, pat in patterns.items():
            m = re.search(pat, text)
            if m:
                val = m.group(1)
                if key in ("total", "descuentoTotal"):
                    result[key] = float(val)
                elif key == "cancelacion":
                    result[key] = val == "true"
                else:
                    result[key] = val

        if "numero" in result:
            logger.warning("Fallback regex usado para cupom %s", result["numero"])
            return result
        return None

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def get_by_numero(self, numero: str) -> list[dict]:
        """Retorna todos os movimentos indexados pelo número do cupom.
        Aceita número com ou sem prefixo '-' (cancelamentos).
        """
        numero = str(numero).strip()
        # Tenta exato
        if numero in self._index:
            return self._index[numero]
        # Tenta sem prefixo '-'
        sem_prefixo = numero.lstrip("-")
        return self._index.get(sem_prefixo, [])

    def get_by_eans(self, eans: list[str]) -> list[dict]:
        """
        Fallback: busca movimentos cujos detalles contenham ao menos um EAN da lista.
        Usa codigoBarras conforme especificação da API Scanntech.
        """
        results = []
        ean_set = set(eans)
        for movements in self._index.values():
            for mov in movements:
                mov_eans = self._extract_eans(mov)
                if any(e in mov_eans for e in ean_set):
                    if mov not in results:
                        results.append(mov)
        return results

    @staticmethod
    def _extract_eans(movement: dict) -> set[str]:
        """Extrai EANs do campo detalles usando codigoBarras (API Scanntech oficial)."""
        eans: set[str] = set()
        for item in movement.get("detalles", []):
            # Campo oficial da API: codigoBarras
            ean = str(item.get("codigoBarras", item.get("ean", ""))).strip()
            if ean:
                eans.add(ean)
        return eans

    def all_numeros(self) -> list[str]:
        """Retorna todos os números de cupom indexados."""
        return list(self._index.keys())
