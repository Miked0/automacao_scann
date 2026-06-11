"""
M2 — AuditParser
Lê o DataFrame do Export Audit e indexa cada movimento pelo número de cupom.

O campo `Request` de cada linha contém o JSON enviado à API com aspas
escapadas como """. Normaliza via str.replace('""', '"') antes do
json.loads, com fallback regex caso o JSON esteja malformado.
"""

from __future__ import annotations
import json
import logging
import re
from typing import Dict, List, Optional

import pandas as pd

from .models import AuditMovement

log = logging.getLogger(__name__)

# Campos obrigatórios extraídos do JSON da requisição
_COUPON_FIELDS = (
    "numero", "numero_sat", "numero_nfce", "numeroCupom",
    "sat", "nfce", "ecf",
)


class AuditParser:
    """Indexa movimentos do Audit pelo número de cupom."""

    def __init__(self, df: pd.DataFrame) -> None:
        self.df = df

    # ── Público ──────────────────────────────────────────────────────────────
    def build_index(self) -> Dict[str, AuditMovement]:
        """
        Processa todas as linhas e devolve dict  {cupom_key: AuditMovement}.
        cupom_key é o número do cupom em lowercase sem espaços.
        """
        index: Dict[str, AuditMovement] = {}
        for _, row in self.df.iterrows():
            mv = self._parse_row(row)
            if mv is None:
                continue
            key = mv.cupom_number.strip().lower()
            if key in index:
                log.debug("Cupom duplicado no Audit: %s — mantendo primeira ocorrência.", key)
            else:
                index[key] = mv
        log.info("Audit indexado: %d movimentos únicos.", len(index))
        return index

    # ── Privado ──────────────────────────────────────────────────────────────
    def _parse_row(self, row: pd.Series) -> Optional[AuditMovement]:
        request_raw = self._get_request_column(row)
        if not request_raw:
            return None

        data = self._safe_json_loads(str(request_raw))
        if data is None:
            return None

        cupom_number = self._extract_cupom_number(data)
        if not cupom_number:
            log.debug("Linha sem número de cupom identificável; pulando.")
            return None

        status_code = self._try_int(row.get("StatusCode") or row.get("status_code"))

        # Extrai campos do JSON principal
        total            = self._try_float(data.get("total"))
        descuento_total  = self._try_float(data.get("descuentoTotal") or data.get("descuento"))
        cancelacion      = data.get("cancelacion")
        if isinstance(cancelacion, str):
            cancelacion = cancelacion.lower() in ("true", "1", "yes")

        detalles = data.get("detalles") or []
        pagos    = data.get("pagos")    or []
        bin_val  = str(data.get("bin", "") or "").strip() or None

        return AuditMovement(
            cupom_number    = cupom_number,
            raw_json        = data,
            status_code     = status_code,
            total           = total,
            descuento_total = descuento_total,
            cancelacion     = cancelacion,
            detalles        = detalles if isinstance(detalles, list) else [],
            pagos           = pagos    if isinstance(pagos,    list) else [],
            bin_value       = bin_val,
        )

    # ── Utilitários ──────────────────────────────────────────────────────────
    @staticmethod
    def _get_request_column(row: pd.Series) -> Optional[str]:
        """Procura a coluna Request independentemente de maiúsculas/minúsculas."""
        for col in row.index:
            if str(col).strip().lower() == "request":
                val = row[col]
                if pd.notna(val) and str(val).strip():
                    return str(val)
        return None

    @staticmethod
    def _safe_json_loads(raw: str) -> Optional[Dict]:
        """Normaliza aspas duplas escapadas e tenta json.loads; fallback regex."""
        # Normaliza ""campo"" → "campo"
        normalized = raw.replace('""', '"')
        # Remove wrapper extra se vier como string JSON dentro de string
        if normalized.startswith('"') and normalized.endswith('"'):
            normalized = normalized[1:-1].replace('\\"', '"')
        try:
            return json.loads(normalized)
        except json.JSONDecodeError:
            pass

        # Fallback: extrai o primeiro objeto JSON via regex
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0).replace('""', '"'))
            except json.JSONDecodeError:
                pass

        log.warning("Não foi possível parsear JSON da linha; raw[:120]=%s", raw[:120])
        return None

    @staticmethod
    def _extract_cupom_number(data: Dict) -> Optional[str]:
        """Tenta vários campos para encontrar o número do cupom."""
        for field in _COUPON_FIELDS:
            val = data.get(field)
            if val and str(val).strip():
                return str(val).strip()
        return None

    @staticmethod
    def _try_float(val) -> Optional[float]:
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _try_int(val) -> Optional[int]:
        try:
            return int(val)
        except (TypeError, ValueError):
            return None
