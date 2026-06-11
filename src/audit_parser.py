# src/audit_parser.py
"""
Módulo 2 — AuditParser
Responsabilidade: Indexa movimentos do export Audit pelo nº cupom.

fix v4:
  - _build_index() normaliza a chave via _norm() antes de indexar
  - get_by_numero() normaliza o argumento antes de buscar
    → resolve divergência '006221' vs '6221'
"""

import json
import logging
import re
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


def _norm(value) -> str:
    """
    Normaliza número de cupom: remove .0, zeros à esquerda e sinal negativo.
    Centralizado aqui para ser importado também pelo TestRunner.
    """
    if value is None:
        return ""
    s = str(value).strip()
    if s.endswith(".0") and s[:-2].lstrip("-").isdigit():
        s = s[:-2]
    s = s.lstrip("-")
    s = s.lstrip("0") or "0"
    if s.lower() in ("0", "none", "nan", "", "-"):
        return ""
    return s


class AuditParser:
    """Parseia e indexa o export Audit pelo número do cupom."""

    def __init__(self, audit_df: pd.DataFrame):
        self.audit_df = audit_df
        # índice: numero_cupom normalizado (str) → lista de movimentos
        self._index: dict[str, list[dict]] = {}
        self._build_index()

    # ------------------------------------------------------------------
    # Construção do índice
    # ------------------------------------------------------------------

    def _build_index(self) -> None:
        """Itera o DataFrame e indexa pelo campo 'numero' normalizado."""
        for _, row in self.audit_df.iterrows():
            raw = row.get("Request", "")
            movement = self._parse_request(str(raw))
            if not movement:
                continue

            # Coleta status HTTP separado (pode vir em coluna própria)
            http_status = row.get("StatusCode", row.get("Status", row.get("HttpStatus", 0)))
            if http_status:
                movement["_http_status"] = int(str(http_status).split(".")[0])

            # Normaliza o número antes de indexar
            numero_raw  = str(movement.get("numero", "")).strip()
            numero_norm = _norm(numero_raw)

            if numero_norm:
                self._index.setdefault(numero_norm, []).append(movement)
                # Também indexa o raw caso haja diferença
                if numero_raw != numero_norm:
                    self._index.setdefault(numero_raw, []).append(movement)

        logger.info("AuditParser: %d cupons indexados", len(self._index))

    def _parse_request(self, raw: str) -> Optional[dict]:
        """
        Normaliza aspas duplas escapadas e tenta json.loads.
        Fallback: extrai campos via regex.
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

    def get_by_numero(self, numero) -> list[dict]:
        """Busca movimentos normalizando o argumento antes de consultar."""
        numero_norm = _norm(numero)
        # Tenta normalizado primeiro, depois raw
        result = self._index.get(numero_norm, [])
        if not result:
            result = self._index.get(str(numero).strip(), [])
        return result

    def get_by_eans(self, eans: list[str]) -> list[dict]:
        """Fallback: retorna movimentos que contenham ao menos um EAN da lista."""
        ean_set = set(eans)
        results = []
        for movements in self._index.values():
            for mov in movements:
                if any(e in self._extract_eans(mov) for e in ean_set):
                    results.append(mov)
        return results

    @staticmethod
    def _extract_eans(movement: dict) -> set[str]:
        eans: set[str] = set()
        for item in movement.get("detalles", []):
            ean = str(item.get("ean", "")).strip()
            if ean:
                eans.add(ean)
        return eans

    def all_numeros(self) -> list[str]:
        return list(self._index.keys())
