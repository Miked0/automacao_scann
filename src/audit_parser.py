"""
Módulo 2 — AuditParser
Responsabilidade: Indexa movimentos do export Audit pelo nº cupom.

Estrutura de índice:
  _index_numero : { numero (str) → list[dict] }   ← campo "numero" do JSON da API
  _index_nfce   : { numeroNFCe (str) → list[dict] }
  _index_sat    : { numeroSAT  (str) → list[dict] }
  _index_ecf    : { numeroCOO  (str) → list[dict] }

Todos os campos são extraídos do JSON presente na coluna "Request"
do export Audit (AUDIT_TICKETS), normalizando as aspas duplas escapadas.
"""

import json
import logging
import re
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


class AuditParser:
    """Parseia e indexa o export Audit por múltiplas chaves de cupom."""

    def __init__(self, audit_df: pd.DataFrame):
        self.audit_df = audit_df
        self._index_numero: dict[str, list[dict]] = {}  # campo "numero" do JSON
        self._index_nfce:   dict[str, list[dict]] = {}
        self._index_sat:    dict[str, list[dict]] = {}
        self._index_ecf:    dict[str, list[dict]] = {}
        self._build_index()

    # ------------------------------------------------------------------
    # Construção do índice
    # ------------------------------------------------------------------

    def _build_index(self) -> None:
        for _, row in self.audit_df.iterrows():
            raw = row.get("Request", "")
            movement = self._parse_request(str(raw))
            if not movement:
                continue

            # Campo principal: "numero" — identificador único do cenário/venda
            numero = str(movement.get("numero", "")).strip()
            if numero and numero.lower() not in ("none", "nan", ""):
                self._index_numero.setdefault(numero, []).append(movement)

            # Campos alternativos presentes em alguns parceiros
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
            "numero":         r'"numero"\s*:\s*"([^"]+)"',
            "numeroNFCe":     r'"numero(?:NFCe|NFCE|nfce)"\s*:\s*"([^"]+)"',
            "numeroSAT":      r'"numero(?:SAT|sat)"\s*:\s*"([^"]+)"',
            "numeroCOO":      r'"numero(?:COO|coo|ECF|ecf)"\s*:\s*"([^"]+)"',
            "total":          r'"total"\s*:\s*([\d.]+)',
            "descuentoTotal": r'"descuentoTotal"\s*:\s*([\d.]+)',
            "cancelacion":    r'"cancelacion"\s*:\s*(true|false)',
            "status":         r'"status"\s*:\s*(\d+)',
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

        if result:
            logger.warning("Fallback regex usado — campos extraídos: %s", list(result.keys()))
            return result
        return None

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def get_by_numero(self, numero: str) -> list[dict]:
        """
        Busca principal: campo "numero" do JSON da API.
        Esse é o identificador canônico do cenário de venda.
        """
        return self._index_numero.get(str(numero).strip(), [])

    def get_by_nfce(self, numero_nfce: str) -> list[dict]:
        """Busca pelo número da NFC-e."""
        return self._index_nfce.get(str(numero_nfce).strip(), [])

    def get_by_sat(self, numero_sat: str) -> list[dict]:
        """Busca pelo número SAT."""
        return self._index_sat.get(str(numero_sat).strip(), [])

    def get_by_ecf(self, numero_ecf: str) -> list[dict]:
        """Busca pelo número ECF/COO."""
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
        Fallback final: busca movimentos cujos detalles contenham
        ao menos um EAN da lista fornecida.
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
