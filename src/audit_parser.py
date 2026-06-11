# src/audit_parser.py
"""
Módulo 2 — AuditParser
Responsabilidade: Indexa movimentos do export Audit pelo nº cupom.

Fix v3 — localização de cupons:
- Tripla indexação: campo 'numero' do JSON + coluna 'Número cupom' do DataFrame
  + campo 'numeroCupom' do JSON (todos os três como chaves do índice)
- Normalização de chave: strip + lstrip('0') para evitar mismatch por zeros à esquerda
- Busca tolerante: tenta exato, sem zeros, e partial-suffix (últimos 4 dígitos)
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

# Possíveis nomes da coluna de número de cupom no DataFrame
_NUMERO_COL_CANDIDATES = [
    "Número cupom", "Numero cupom", "numero_cupom", "NumeroCupom",
    "Num. Cupon", "Num Cupon", "num_cupon", "numero_cupon",
    "Número do Cupom", "Numero do Cupom", "CouponNumber", "coupon_number",
    "Número", "Numero", "numero",
]


def _norm(value) -> str:
    """Normaliza um número de cupom: strip de espaços e zeros à esquerda."""
    s = str(value).strip()
    # Remove prefixo '-' para indexar também a versão sem cancelamento
    clean = s.lstrip("-").lstrip("0") or "0"
    return clean


class AuditParser:
    """Parseia e indexa o export Audit pelo número do cupom."""

    def __init__(self, audit_df: pd.DataFrame):
        self.audit_df = audit_df
        self._status_col: Optional[str] = self._detect_status_col()
        self._numero_col: Optional[str] = self._detect_numero_col()
        # índice: numero_cupom normalizado (str) → lista de dicts com dados do movimento
        self._index: dict[str, list[dict]] = {}
        self._build_index()

    # ------------------------------------------------------------------
    # Detecção de colunas
    # ------------------------------------------------------------------

    def _detect_status_col(self) -> Optional[str]:
        for candidate in _STATUS_COL_CANDIDATES:
            if candidate in self.audit_df.columns:
                logger.info("AuditParser: coluna status HTTP → '%s'", candidate)
                return candidate
        for col in self.audit_df.columns:
            if "status" in str(col).lower():
                logger.info("AuditParser: coluna status HTTP (parcial) → '%s'", col)
                return col
        logger.warning("AuditParser: coluna de status HTTP não encontrada")
        return None

    def _detect_numero_col(self) -> Optional[str]:
        """Detecta a coluna de número do cupom diretamente no DataFrame."""
        for candidate in _NUMERO_COL_CANDIDATES:
            if candidate in self.audit_df.columns:
                logger.info("AuditParser: coluna número cupom → '%s'", candidate)
                return candidate
        for col in self.audit_df.columns:
            col_lower = str(col).lower()
            if ("num" in col_lower or "cupon" in col_lower or "cupom" in col_lower) and \
               "status" not in col_lower:
                logger.info("AuditParser: coluna número cupom (parcial) → '%s'", col)
                return col
        logger.warning("AuditParser: coluna de número de cupom não encontrada no DataFrame")
        return None

    # ------------------------------------------------------------------
    # Construção do índice
    # ------------------------------------------------------------------

    def _build_index(self) -> None:
        """
        Indexa cada linha do DataFrame por TRÊS chaves:
          1. campo 'numero' do JSON do Request
          2. campo 'numeroCupom' do JSON do Request (alias da API)
          3. valor da coluna 'Número cupom' (ou equivalente) do DataFrame
        Todas as chaves são normalizadas (strip + lstrip zeros).
        """
        for _, row in self.audit_df.iterrows():
            raw = row.get("Request", "")
            movement = self._parse_request(str(raw))
            if not movement:
                continue

            # Injeta status HTTP do DataFrame
            if self._status_col:
                try:
                    movement["_http_status"] = int(row[self._status_col])
                except (ValueError, TypeError):
                    movement["_http_status"] = 0
            else:
                movement["_http_status"] = 0

            # Coleta todas as chaves candidatas para este movimento
            keys_to_index: set[str] = set()

            # Chave 1: campo 'numero' do JSON
            numero_json = str(movement.get("numero", "")).strip()
            if numero_json:
                keys_to_index.add(numero_json)
                keys_to_index.add(_norm(numero_json))

            # Chave 2: campo 'numeroCupom' do JSON (alias)
            numero_cupom_json = str(movement.get("numeroCupom", "")).strip()
            if numero_cupom_json:
                keys_to_index.add(numero_cupom_json)
                keys_to_index.add(_norm(numero_cupom_json))

            # Chave 3: coluna do DataFrame
            if self._numero_col:
                df_val = str(row.get(self._numero_col, "")).strip()
                if df_val and df_val not in ("", "nan", "None"):
                    # Guarda o valor bruto no movimento para inspeção
                    movement["_numero_df"] = df_val
                    keys_to_index.add(df_val)
                    keys_to_index.add(_norm(df_val))

            # Indexa em todas as chaves coletadas
            for key in keys_to_index:
                if key:
                    self._index.setdefault(key, []).append(movement)

        logger.info(
            "AuditParser: %d chaves indexadas a partir de %d linhas do DataFrame",
            len(self._index), len(self.audit_df)
        )
        # Log das primeiras 10 chaves para diagnóstico
        sample = list(self._index.keys())[:10]
        logger.debug("AuditParser: amostra de chaves indexadas: %s", sample)

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
            "numeroCupom":    r'"numeroCupom"\s*:\s*"([^"]+)"',
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

        if "numero" in result or "numeroCupom" in result:
            n = result.get("numero", result.get("numeroCupom", "?"))
            logger.warning("Fallback regex usado para cupom %s", n)
            return result
        return None

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def get_by_numero(self, numero: str) -> list[dict]:
        """
        Busca movimentos pelo número do cupom.
        Tenta em ordem: exato → normalizado (sem zeros) → sufixo (últimos 4 dígitos).
        """
        numero = str(numero).strip()

        # 1. Exato
        if numero in self._index:
            return self._index[numero]

        # 2. Normalizado
        norm = _norm(numero)
        if norm in self._index:
            return self._index[norm]

        # 3. Sufixo (últimos 4 dígitos) — útil quando roteiro tem número parcial
        if len(norm) >= 4:
            suffix = norm[-4:]
            for key, movs in self._index.items():
                if key.endswith(suffix):
                    logger.debug(
                        "AuditParser: match por sufixo '%s' para busca '%s'",
                        key, numero
                    )
                    return movs

        logger.debug("AuditParser: nenhum movimento para número '%s' (norm='%s')", numero, norm)
        return []

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
            ean = str(item.get("codigoBarras", item.get("ean", ""))).strip()
            if ean:
                eans.add(ean)
        return eans

    def all_numeros(self) -> list[str]:
        """Retorna todos os números de cupom indexados."""
        return list(self._index.keys())

    def log_index_sample(self, n: int = 20) -> None:
        """Loga os primeiros N números indexados (útil para diagnóstico)."""
        sample = list(self._index.keys())[:n]
        logger.info("AuditParser: primeiros %d números indexados: %s", len(sample), sample)
