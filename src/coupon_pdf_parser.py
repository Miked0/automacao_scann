"""
M3 — CouponPDFParser
Extrai cupons fiscais (DANFE/NFC-e/SAT) do PDF usando pdfplumber.

Estratégia:
  1. Extrai texto bruto de todas as páginas.
  2. Divide em blocos pelo padrão de cabeçalho (NFC-e, SAT, COO).
  3. Cada bloco é parseado via regex para: subtotal, desconto, total,
     EANs e formas de pagamento.
"""

from __future__ import annotations
import logging
import re
from typing import Any, Dict, List, Optional

from .models import CouponBlock

log = logging.getLogger(__name__)

# ── Padrões de cabeçalho de cupom ────────────────────────────────────────────
_BLOCK_HEADER = re.compile(
    r"(?:NFC-?E|SAT|COO|CUPOM\s+FISCAL|DOCUMENTO\s+AUXILIAR)",
    re.IGNORECASE,
)

# ── Padrões de campos ────────────────────────────────────────────────────────
_SAT_RE    = re.compile(r"(?:SAT|Nº\s*SAT)[\s:]+([\d]+)",       re.IGNORECASE)
_NFCE_RE   = re.compile(r"(?:NFC-?E|CHAVE)[\s:]+([\d]{44}|[\d]+)", re.IGNORECASE)
_COO_RE    = re.compile(r"COO[:\s]+([\d]+)",                     re.IGNORECASE)
_ECF_RE    = re.compile(r"ECF[:\s#]+([\d]+)",                    re.IGNORECASE)
_SUBTOTAL  = re.compile(r"SUB[\s-]?TOTAL[\s:R$]+([\d]+[,\.][\d]{2})", re.IGNORECASE)
_DESCONTO  = re.compile(r"DESCONTO[\s:R$-]+([\d]+[,\.][\d]{2})", re.IGNORECASE)
_TOTAL     = re.compile(r"(?:TOTAL\s+(?:GERAL|A\s+PAGAR)|TOTAL)[\s:R$]+([\d]+[,\.][\d]{2})", re.IGNORECASE)
_EAN       = re.compile(r"\b(\d{8}|\d{12,14})\b")
_PAGTO     = re.compile(
    r"(DINHEIRO|CART[ÃA]O\s+CR[ÉE]DITO|CART[ÃA]O\s+D[ÉE]BITO|PIX|CREDIT|DEBIT|CASH)"
    r"[\s:R$]+([\d]+[,\.][\d]{2})",
    re.IGNORECASE,
)


class CouponPDFParser:
    """Extrai todos os cupons do PDF carregado pelo FileLoader."""

    def __init__(self, pdf_pages: List[Any]) -> None:
        self.pdf_pages = pdf_pages

    def extract_all(self) -> List[CouponBlock]:
        full_text = self._extract_full_text()
        blocks    = self._split_into_blocks(full_text)
        coupons   = [self._parse_block(b) for b in blocks if b.strip()]
        log.info("CouponPDFParser: %d blocos → %d cupons parseados.", len(blocks), len(coupons))
        return coupons

    # ── Extração de texto ────────────────────────────────────────────────────
    def _extract_full_text(self) -> str:
        parts: List[str] = []
        for i, page in enumerate(self.pdf_pages):
            try:
                text = page.extract_text() or ""
                parts.append(text)
            except Exception as exc:
                log.warning("Erro ao extrair texto da página %d: %s", i + 1, exc)
        return "\n".join(parts)

    @staticmethod
    def _split_into_blocks(text: str) -> List[str]:
        """Divide o texto em blocos pelo padrão de cabeçalho de cupom."""
        positions = [m.start() for m in _BLOCK_HEADER.finditer(text)]
        if not positions:
            # Sem marcadores: trata o texto todo como um bloco
            return [text]
        blocks: List[str] = []
        for i, start in enumerate(positions):
            end = positions[i + 1] if i + 1 < len(positions) else len(text)
            blocks.append(text[start:end])
        return blocks

    # ── Parse de bloco individual ────────────────────────────────────────────
    def _parse_block(self, block: str) -> CouponBlock:
        cb = CouponBlock(raw_text=block)

        cb.sat_number  = self._first_group(_SAT_RE,   block)
        cb.nfce_number = self._first_group(_NFCE_RE,  block)
        cb.coo_number  = self._first_group(_COO_RE,   block)
        cb.ecf_number  = self._first_group(_ECF_RE,   block)

        cb.subtotal = self._parse_money(_first_group_or_none(_SUBTOTAL, block))
        cb.desconto = self._parse_money(_first_group_or_none(_DESCONTO, block))
        cb.total    = self._parse_money(_first_group_or_none(_TOTAL,    block))

        cb.eans     = _EAN.findall(block)
        cb.pagamentos = [
            {"tipo": m.group(1).upper(), "valor": self._parse_money(m.group(2))}
            for m in _PAGTO.finditer(block)
        ]

        return cb

    # ── Utilitários ──────────────────────────────────────────────────────────
    @staticmethod
    def _first_group(pattern: re.Pattern, text: str) -> Optional[str]:
        m = pattern.search(text)
        return m.group(1).strip() if m else None

    @staticmethod
    def _parse_money(val: Optional[str]) -> Optional[float]:
        if val is None:
            return None
        try:
            return float(val.replace(".", "").replace(",", "."))
        except ValueError:
            return None


def _first_group_or_none(pattern: re.Pattern, text: str) -> Optional[str]:
    m = pattern.search(text)
    return m.group(1) if m else None
