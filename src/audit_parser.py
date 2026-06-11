"""
Módulo 2 — AuditParser
Responsabilidade: Indexa movimentos do export Audit pelo nº cupom.
"""
import json
import re
import logging
from typing import Dict, List, Optional
import pandas as pd

logger = logging.getLogger(__name__)


class AuditParser:
    """
    Parseia o export Audit (xlsx) e indexa cada movimento de venda
    pelo número do cupom (campo 'numero' no JSON da requisição).
    """

    def __init__(self, df_audit: pd.DataFrame):
        self.df = df_audit
        self._index: Dict[str, List[dict]] = {}
        self._raw_movements: List[dict] = []
        self._parse()

    def _normalize_json_str(self, raw: str) -> str:
        """Normaliza aspas duplas escapadas típicas do export Audit."""
        if not isinstance(raw, str):
            return ""
        s = raw.strip()
        if s.startswith('"') and s.endswith('"'):
            s = s[1:-1]
        s = s.replace('""', '"')
        return s

    def _extract_fallback(self, raw: str) -> Optional[dict]:
        """Extração regex de campos críticos quando json.loads falha."""
        result = {}
        patterns = {
            "numero": r'"numero"\s*:\s*"([^"]+)"',
            "total": r'"total"\s*:\s*([\d.]+)',
            "descuentoTotal": r'"descuentoTotal"\s*:\s*([\d.]+)',
            "cancelacion": r'"cancelacion"\s*:\s*(true|false)',
        }
        for field, pat in patterns.items():
            m = re.search(pat, raw, re.IGNORECASE)
            if m:
                val = m.group(1)
                if field in ("total", "descuentoTotal"):
                    try:
                        val = float(val)
                    except ValueError:
                        pass
                elif field == "cancelacion":
                    val = val.lower() == "true"
                result[field] = val
        return result if result else None

    def _parse(self):
        """Parseia todas as linhas do DataFrame e indexa por numero."""
        request_col = None
        status_col = None

        for col in self.df.columns:
            col_lower = str(col).lower()
            if "request" in col_lower and request_col is None:
                request_col = col
            if "status" in col_lower and status_col is None:
                status_col = col

        if request_col is None:
            logger.warning("Coluna 'Request' não encontrada no Audit. Tentando primeira coluna com JSON.")
            for col in self.df.columns:
                sample = str(self.df[col].dropna().iloc[0]) if not self.df[col].dropna().empty else ""
                if "numero" in sample or "total" in sample:
                    request_col = col
                    break

        if request_col is None:
            logger.error("Não foi possível identificar coluna de Request no Audit.")
            return

        for idx, row in self.df.iterrows():
            raw = row.get(request_col, "")
            http_status = row.get(status_col, None) if status_col else None
            normalized = self._normalize_json_str(str(raw))
            mov = None
            try:
                mov = json.loads(normalized)
            except (json.JSONDecodeError, ValueError):
                mov = self._extract_fallback(normalized)
                if mov:
                    logger.debug(f"Linha {idx}: JSON malformado — fallback regex aplicado.")
                else:
                    logger.warning(f"Linha {idx}: falha total no parse do JSON.")
                    continue

            if mov is None:
                continue

            mov["_http_status"] = int(http_status) if http_status else None
            mov["_row_index"] = idx
            self._raw_movements.append(mov)

            numero = str(mov.get("numero", "")).strip()
            if numero:
                self._index.setdefault(numero, []).append(mov)
                num_clean = numero.lstrip("-")
                if num_clean != numero:
                    self._index.setdefault(num_clean, []).append(mov)

        logger.info(f"AuditParser: {len(self._raw_movements)} movimentos parseados, "
                    f"{len(self._index)} cupons únicos indexados.")

    def get_by_numero(self, numero: str) -> List[dict]:
        """Retorna lista de movimentos pelo número do cupom."""
        return self._index.get(str(numero).strip(), [])

    def get_all(self) -> List[dict]:
        return self._raw_movements

    @property
    def index(self) -> Dict[str, List[dict]]:
        return self._index
