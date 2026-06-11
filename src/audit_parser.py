"""
Módulo 2 — AuditParser
Responsabilidade: Indexa movimentos do export Audit pelo nº cupom.

Estrutura do export Audit (AUDIT_TICKETS):
  Coluna I → status HTTP da resposta (200, 400, etc.)
  Coluna S → JSON do Request (corpo enviado à API Scanntech)

Estrutura de índice:
  _index_numero : { numero (str) → list[dict] }   ← campo "numero" do JSON
  _index_nfce   : { numeroNFCe (str) → list[dict] }
  _index_sat    : { numeroSAT  (str) → list[dict] }
  _index_ecf    : { numeroCOO  (str) → list[dict] }

O dicionário de cada movimento contém:
  - Todos os campos do JSON do Request
  - "_http_status" (int): status HTTP lido da coluna I do DataFrame
"""

import json
import logging
import re
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Nomes conhecidos da coluna de status HTTP no export Audit.
# O script tenta cada um em ordem até encontrar; fallback = posição 8 (col I).
# ---------------------------------------------------------------------------
_STATUS_COL_ALIASES = [
    "status", "httpstatus", "http_status", "statuscode",
    "http status", "response code", "responsecode", "codigo", "código",
    "status code", "status_code",
]

# Nomes conhecidos da coluna de Request JSON no export Audit.
# Fallback = posição 18 (col S).
_REQUEST_COL_ALIASES = [
    "request", "json", "body", "payload", "request body",
    "request_body", "requestbody", "req",
]


def _find_col(df: pd.DataFrame, aliases: list[str], fallback_pos: int) -> str:
    """
    Retorna o nome da coluna do DataFrame que corresponde a um dos aliases.
    Se nenhum alias for encontrado, usa a coluna pela posição (0-based).
    """
    cols_lower = {str(c).strip().lower(): c for c in df.columns}
    for alias in aliases:
        if alias in cols_lower:
            found = cols_lower[alias]
            logger.info("Coluna detectada '%s' pelo alias '%s'", found, alias)
            return found

    # Fallback por posição
    if fallback_pos < len(df.columns):
        found = df.columns[fallback_pos]
        logger.warning(
            "Coluna não detectada por alias; usando posição %d → '%s'",
            fallback_pos, found
        )
        return found

    # Último recurso: primeira coluna
    logger.warning("Fallback de posição inválido; usando primeira coluna.")
    return df.columns[0]


class AuditParser:
    """Parseia e indexa o export Audit por múltiplas chaves de cupom."""

    def __init__(self, audit_df: pd.DataFrame):
        self.audit_df = audit_df
        self._index_numero: dict[str, list[dict]] = {}
        self._index_nfce:   dict[str, list[dict]] = {}
        self._index_sat:    dict[str, list[dict]] = {}
        self._index_ecf:    dict[str, list[dict]] = {}

        # Detecta as colunas corretas antes de indexar
        self._col_status  = _find_col(audit_df, _STATUS_COL_ALIASES,  fallback_pos=8)   # col I
        self._col_request = _find_col(audit_df, _REQUEST_COL_ALIASES, fallback_pos=18)  # col S

        logger.info(
            "AuditParser: coluna status='%s' (I), coluna request='%s' (S)",
            self._col_status, self._col_request
        )

        self._build_index()

    # ------------------------------------------------------------------
    # Construção do índice
    # ------------------------------------------------------------------

    def _build_index(self) -> None:
        for _, row in self.audit_df.iterrows():
            # --- Status HTTP da coluna I ---
            raw_status = row.get(self._col_status, 0)
            try:
                http_status = int(float(str(raw_status).strip()))
            except (ValueError, TypeError):
                http_status = 0

            # --- JSON do Request da coluna S ---
            raw_request = row.get(self._col_request, "")
            movement = self._parse_request(str(raw_request))
            if not movement:
                continue

            # Injeta o status HTTP no dicionário do movimento
            # usando chave privada "_http_status" para não colidir com campos do JSON
            movement["_http_status"] = http_status

            # Indexa pelo campo "numero" do JSON
            numero = str(movement.get("numero", "")).strip()
            if numero and numero.lower() not in ("none", "nan", ""):
                self._index_numero.setdefault(numero, []).append(movement)

            # Índices alternativos
            for key, idx in [
                ("numeroNFCe", self._index_nfce),
                ("nfce",       self._index_nfce),
                ("numeroSAT",  self._index_sat),
                ("sat",        self._index_sat),
                ("numeroCOO",  self._index_ecf),
                ("coo",        self._index_ecf),
                ("ecf",        self._index_ecf),
            ]:
                val = str(movement.get(key, "")).strip()
                if val and val.lower() not in ("none", "nan", ""):
                    idx.setdefault(val, []).append(movement)

        logger.info(
            "AuditParser: %d cupons indexados (numero=%d nfce=%d sat=%d ecf=%d)",
            len(self._index_numero),
            len(self._index_numero),
            len(self._index_nfce),
            len(self._index_sat),
            len(self._index_ecf),
        )

    def _parse_request(self, raw: str) -> Optional[dict]:
        """
        Normaliza aspas duplas escapadas ("") e tenta json.loads.
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
            "numero":         r'"numero"\s*:\s*"([^"]+)"',
            "numeroNFCe":     r'"numero(?:NFCe|NFCE|nfce)"\s*:\s*"([^"]+)"',
            "numeroSAT":      r'"numero(?:SAT|sat)"\s*:\s*"([^"]+)"',
            "numeroCOO":      r'"numero(?:COO|coo|ECF|ecf)"\s*:\s*"([^"]+)"',
            "total":          r'"total"\s*:\s*([\d.]+)',
            "descuentoTotal": r'"descuentoTotal"\s*:\s*([\d.]+)',
            "cancelacion":    r'"cancelacion"\s*:\s*(true|false)',
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

        if result:
            logger.warning("Fallback regex usado — campos extraídos: %s", list(result.keys()))
            return result
        return None

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def get_by_numero(self, numero: str) -> list[dict]:
        return self._index_numero.get(str(numero).strip(), [])

    def get_by_nfce(self, numero_nfce: str) -> list[dict]:
        return self._index_nfce.get(str(numero_nfce).strip(), [])

    def get_by_sat(self, numero_sat: str) -> list[dict]:
        return self._index_sat.get(str(numero_sat).strip(), [])

    def get_by_ecf(self, numero_ecf: str) -> list[dict]:
        return self._index_ecf.get(str(numero_ecf).strip(), [])

    def get_any(self, numero: str) -> list[dict]:
        """
        Tenta todos os índices em ordem: numero → nfce → sat → ecf.
        Retorna a primeira lista não-vazia encontrada.
        """
        for fn in (self.get_by_numero, self.get_by_nfce, self.get_by_sat, self.get_by_ecf):
            result = fn(numero)
            if result:
                return result
        return []

    def get_by_eans(self, eans: list[str]) -> list[dict]:
        """
        Fallback final: movimentos cujos detalles contenham ao menos 1 EAN da lista.
        """
        results = []
        ean_set = set(eans)
        for movements in self._index_numero.values():
            for mov in movements:
                if ean_set & self._extract_eans(mov):
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
        return list(self._index_numero.keys())
