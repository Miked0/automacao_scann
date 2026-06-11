"""
Módulo 3 — CouponPDFParser
Responsabilidade: Extrai cupons fiscais (DANFE/NFC-e/SAT) do PDF.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

# Padrões que delimitam início de novo cupom
_COUPON_HEADERS = re.compile(
    r"(NFC-e|SAT\s+FISCAL|CUPOM\s+FISCAL|DANFE|COO\s*[:=]\s*\d+|NF-e)",
    re.IGNORECASE,
)

_RE_SUBTOTAL  = re.compile(r"(?:subtotal|sub[-\s]?total)\s*[:\-]?\s*([\d.,]+)",   re.IGNORECASE)
_RE_DESCONTO  = re.compile(r"(?:desconto|desc\.?)\s*[:\-]?\s*([\d.,]+)",           re.IGNORECASE)
_RE_TOTAL     = re.compile(r"(?:^|\s)total\s*[:\-]?\s*([\d.,]+)",                  re.IGNORECASE | re.MULTILINE)
_RE_EAN       = re.compile(r"\b(\d{13})\b")
_RE_COO       = re.compile(r"COO\s*[:\-=]?\s*(\d+)",    re.IGNORECASE)
_RE_SAT       = re.compile(r"SAT\s*[:\-=]?\s*(\d{6,})", re.IGNORECASE)
_RE_NFCE      = re.compile(r"NFC-e\s*[:\-=]?\s*(\d+)",  re.IGNORECASE)
_RE_PAGAMENTO = re.compile(
    r"(?:dinheiro|cart[aã]o\s+cr[eé]dito|cart[aã]o\s+d[eé]bito|pix|vale[-\s]?refeição)",
    re.IGNORECASE,
)


def _to_float(val: str) -> float:
    return float(val.replace(".", "").replace(",", "."))


@dataclass
class CouponBlock:
    """Representa um cupom fiscal extraído do PDF."""
    raw_text:         str
    sat_number:       Optional[str] = None
    coo_number:       Optional[str] = None
    nfce_number:      Optional[str] = None
    subtotal:         Optional[float] = None
    desconto:         Optional[float] = None
    total:            Optional[float] = None
    eans:             List[str] = field(default_factory=list)
    formas_pagamento: List[str] = field(default_factory=list)

    def get_numero(self) -> Optional[str]:
        return self.sat_number or self.nfce_number or self.coo_number


class CouponPDFParser:
    """Extrai e parseia cupons fiscais de páginas PDF brutas."""

    def __init__(self, pdf_pages: List[str]):
        self.pdf_pages = pdf_pages
        self._coupons: List[CouponBlock] = []
        self._parse_all()

    # ------------------------------------------------------------------
    # Interface pública chamada pelo orquestrador
    # ------------------------------------------------------------------

    def extract_all(self) -> List[CouponBlock]:
        """
        Alias público compatível com o orquestrador:
            coupons = pdf_parser.extract_all()
        Retorna lista de CouponBlock já extraídos.
        """
        return self._coupons

    # ------------------------------------------------------------------
    # Pipeline de parsing
    # ------------------------------------------------------------------

    def _parse_all(self) -> None:
        full_text = "\n".join(self.pdf_pages)
        blocks    = self._split_into_blocks(full_text)
        for block in blocks:
            c = self._parse_block(block)
            if c:
                self._coupons.append(c)
        logger.info("CouponPDFParser: %d cupons extraídos", len(self._coupons))

    def _split_into_blocks(self, text: str) -> List[str]:
        """Divide o texto em blocos por padrão de cabeçalho de cupom."""
        positions = [m.start() for m in _COUPON_HEADERS.finditer(text)]
        if not positions:
            return [text]
        blocks = []
        for i, start in enumerate(positions):
            end = positions[i + 1] if i + 1 < len(positions) else len(text)
            blocks.append(text[start:end])
        return blocks

    def _parse_block(self, block: str) -> Optional[CouponBlock]:
        if not block.strip():
            return None
        c = CouponBlock(raw_text=block)

        m = _RE_SAT.search(block)
        if m: c.sat_number = m.group(1).strip()

        m = _RE_COO.search(block)
        if m: c.coo_number = m.group(1).strip()

        m = _RE_NFCE.search(block)
        if m: c.nfce_number = m.group(1).strip()

        m = _RE_SUBTOTAL.search(block)
        if m:
            try: c.subtotal = _to_float(m.group(1))
            except ValueError: pass

        m = _RE_DESCONTO.search(block)
        if m:
            try: c.desconto = _to_float(m.group(1))
            except ValueError: pass

        totals = _RE_TOTAL.findall(block)
        if totals:
            try: c.total = _to_float(totals[-1])
            except ValueError: pass

        c.eans             = list(dict.fromkeys(_RE_EAN.findall(block)))
        c.formas_pagamento = list({m.group(0).lower() for m in _RE_PAGAMENTO.finditer(block)})
        return c

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def get_by_numero(self, numero: str) -> Optional[CouponBlock]:
        """Busca cupom por SAT, NFC-e ou COO."""
        numero = str(numero).strip()
        for c in self._coupons:
            if numero in (c.sat_number, c.nfce_number, c.coo_number):
                return c
        return None

    def get_by_eans(self, eans: List[str]) -> Optional[CouponBlock]:
        """Fallback: retorna o cupom que contém mais EANs coincidentes."""
        best, best_score = None, 0
        ean_set = set(eans)
        for c in self._coupons:
            score = len(ean_set & set(c.eans))
            if score > best_score:
                best, best_score = c, score
        return best if best_score > 0 else None

    @property
    def coupons(self) -> List[CouponBlock]:
        return self._coupons
