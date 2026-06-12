"""
Módulo 2 — AuditParser  (v2 — corrigido BUG-05)
Responsabilidade: Indexa movimentos do export Audit pelo nº cupom.

Fix BUG-05: detecta automaticamente o tipo de export:
  - Se a planilha contiver coluna 'Request' (JSON aninhado) → parseia via json.loads
  - Se contiver coluna 'NUMERO_DE_CUPON' ou 'NUMERO_CUPON' (tabular) → lê diretamente
"""

import json
import logging
import re
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Tolerância monetária
TOLERANCE = 0.05


class AuditParser:
    """Parseia e indexa o export Audit pelo número do cupom."""

    # Nomes possíveis para coluna de número do cupom no export tabular
    _CUPON_COLS = [
        "NUMERO_DE_CUPON", "NUMERO_CUPON", "NUM_CUPON", "CUPON",
        "numero", "numeroCupon", "number", "NUMERO",
    ]
    # Nomes possíveis para colunas de valores no export tabular
    _TOTAL_COLS   = ["IMPORTE", "TOTAL", "total", "importe", "valorTotal"]
    _DESC_COLS    = ["DESCUENTO_TOTAL", "descuentoTotal", "DESCUENTO", "descuento"]
    _STATUS_COLS  = ["STATUS", "HTTP_STATUS", "status", "httpStatus", "CODIGO_RESPUESTA"]
    _CANCEL_COLS  = ["CANCELACION", "cancelacion", "CANCELADO", "cancelado"]

    def __init__(self, audit_df: pd.DataFrame):
        self.audit_df = audit_df
        self._index: dict[str, list[dict]] = {}
        self._mode: str = "unknown"
        self._build_index()

    # ------------------------------------------------------------------
    # Construção do índice
    # ------------------------------------------------------------------

    def _build_index(self) -> None:
        cols_upper = {str(c).upper(): c for c in self.audit_df.columns}

        # Detecta modo: JSON (coluna Request) ou tabular (colunas separadas)
        if "REQUEST" in cols_upper:
            self._mode = "json"
            logger.info("AuditParser: modo JSON (coluna Request detectada)")
            self._build_index_json(cols_upper["REQUEST"])
        else:
            self._mode = "tabular"
            logger.info("AuditParser: modo TABULAR (colunas separadas)")
            self._build_index_tabular(cols_upper)

        logger.info("AuditParser: %d cupons indexados (modo=%s)", len(self._index), self._mode)

    def _build_index_json(self, request_col: str) -> None:
        """Modo JSON: parseia campo Request de cada linha."""
        for _, row in self.audit_df.iterrows():
            raw = row.get(request_col, "")
            movement = self._parse_request(str(raw))
            if not movement:
                continue
            # Tenta enriquecer com colunas adicionais da linha
            movement.setdefault("status", row.get("STATUS", row.get("status", 0)))
            numero = str(movement.get("numero", "")).strip()
            if numero:
                self._index.setdefault(numero, []).append(movement)

    def _build_index_tabular(self, cols_upper: dict) -> None:
        """Modo Tabular: lê colunas separadas diretamente."""
        # Encontra coluna de número do cupom
        cupon_col = None
        for name in self._CUPON_COLS:
            if name.upper() in cols_upper:
                cupon_col = cols_upper[name.upper()]
                break

        if not cupon_col:
            logger.warning("AuditParser tabular: coluna de número de cupom não encontrada. "
                           "Colunas disponíveis: %s", list(self.audit_df.columns))
            return

        # Encontra colunas de valores opcionais
        total_col  = self._find_col(cols_upper, self._TOTAL_COLS)
        desc_col   = self._find_col(cols_upper, self._DESC_COLS)
        status_col = self._find_col(cols_upper, self._STATUS_COLS)
        cancel_col = self._find_col(cols_upper, self._CANCEL_COLS)

        logger.info("AuditParser tabular: cupon=%s total=%s desc=%s status=%s cancel=%s",
                    cupon_col, total_col, desc_col, status_col, cancel_col)

        for _, row in self.audit_df.iterrows():
            numero = str(row.get(cupon_col, "")).strip()
            if not numero or numero.lower() in ("nan", "", "none"):
                continue

            movement: dict = {
                "numero":        numero,
                "total":         self._safe_float(row, total_col),
                "descuentoTotal":self._safe_float(row, desc_col),
                "status":        self._safe_int(row, status_col, default=200),
                "cancelacion":   self._safe_bool(row, cancel_col),
                # Mantém linha original para acesso a campos extras
                "_raw_row":      row.to_dict(),
            }
            # Extrai detalles e pagos se existirem como colunas JSON embutidas
            for extra in ("detalles", "pagos", "DETALLES", "PAGOS"):
                if extra.upper() in {c.upper() for c in self.audit_df.columns}:
                    try:
                        movement[extra.lower()] = json.loads(str(row.get(extra, "[]"))
                                                              .replace('""', '"'))
                    except Exception:
                        movement[extra.lower()] = []

            self._index.setdefault(numero, []).append(movement)

    @staticmethod
    def _find_col(cols_upper: dict, candidates: list) -> Optional[str]:
        for name in candidates:
            if name.upper() in cols_upper:
                return cols_upper[name.upper()]
        return None

    @staticmethod
    def _safe_float(row, col: Optional[str], default: float = 0.0) -> float:
        if col is None:
            return default
        try:
            return float(row.get(col, default))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_int(row, col: Optional[str], default: int = 0) -> int:
        if col is None:
            return default
        try:
            return int(float(row.get(col, default)))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_bool(row, col: Optional[str]) -> bool:
        if col is None:
            return False
        val = str(row.get(col, "")).strip().lower()
        return val in ("true", "1", "sim", "yes", "s")

    # ------------------------------------------------------------------
    # Parsing JSON (modo json)
    # ------------------------------------------------------------------

    def _parse_request(self, raw: str) -> Optional[dict]:
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

    def get_by_numero(self, numero: str) -> list[dict]:
        """Retorna movimentos indexados pelo número do cupom."""
        return self._index.get(str(numero).strip(), [])

    def get_by_eans(self, eans: list[str]) -> list[dict]:
        """Fallback: busca movimentos que contenham ao menos um EAN da lista."""
        results = []
        ean_set = set(eans)
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
