"""
Módulo 3 — CouponPDFParser
Responsabilidade: Extrai cupons fiscais (DANFE/NFC-e/SAT) do PDF.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Padrões de cabeçalho de cupom e campos monetários
# ---------------------------------------------------------------------------

_COUPON_HEADERS = re.compile(
    r"(NFC-e|SAT\s+FISCAL|CUPOM\s+FISCAL|DANFE|COO\s*[:=]\s*\d+|NF-e)",
    re.IGNORECASE,
)

_RE_SUBTOTAL  = re.compile(r"(?:subtotal|sub[-\s]?total)\s*[:\-]?\s*([\d.,]+)", re.IGNORECASE)
_RE_DESCONTO  = re.compile(r"(?:desconto|desc\.?)\s*[:\-]?\s*([\d.,]+)", re.IGNORECASE)
_RE_TOTAL     = re.compile(r"(?:^|\s)total\s*[:\-]?\s*([\d.,]+)", re.IGNORECASE | re.MULTILINE)
_RE_EAN       = re.compile(r"\b(\d{13})\b")
_RE_COO       = re.compile(r"COO\s*[:\-=]?\s*(\d+)", re.IGNORECASE)
_RE_SAT       = re.compile(r"SAT\s*[:\-=]?\s*(\d{6,})", re.IGNORECASE)
_RE_NFCE      = re.compile(r"NFC-e\s*[:\-=]?\s*(\d+)", re.IGNORECASE)
_RE_PAGAMENTO = re.compile(
    r"(?:dinheiro|cart[aã]o\s+cr[eé]dito|cart[aã]o\s+d[eé]bito|pix|vale[-\s]?refei[çc][aã]o)",
    re.IGNORECASE,
)


def _to_float(val: str) -> float:
    """Converte string monetária BR (1.234,56) para float."""
    return float(val.replace(".", "").replace(",", "."))


# ---------------------------------------------------------------------------
# Dataclass Coupon
# ---------------------------------------------------------------------------

@dataclass
class Coupon:
    """Representa um cupom fiscal extraído do PDF."""
    raw_text:          str
    numero_sat:        Optional[str]   = None
    numero_coo:        Optional[str]   = None
    numero_nfce:       Optional[str]   = None
    subtotal:          Optional[float] = None
    desconto:          Optional[float] = None
    total:             Optional[float] = None
    eans:              list[str]       = field(default_factory=list)
    formas_pagamento:  list[str]       = field(default_factory=list)

    def get_numero(self) -> Optional[str]:
        """Retorna o melhor identificador disponível."""
        return self.numero_sat or self.numero_nfce or self.numero_coo


# ---------------------------------------------------------------------------
# Parser principal
# ---------------------------------------------------------------------------

class CouponPDFParser:
    """Extrai e parseia cupons fiscais de páginas PDF brutas."""

    def __init__(self, pdf_pages: list[str]):
        self.pdf_pages = pdf_pages
        self._coupons: list[Coupon] = []
        self._parse_all()

    # ------------------------------------------------------------------
    # Pipeline de parsing
    # ------------------------------------------------------------------

    def _parse_all(self) -> None:
        full_text = "\n".join(self.pdf_pages)
        blocks = self._split_into_blocks(full_text)
        for block in blocks:
            c = self._parse_block(block)
            if c:
                self._coupons.append(c)
        logger.info("CouponPDFParser: %d cupons extraídos", len(self._coupons))

    def _split_into_blocks(self, text: str) -> list[str]:
        """Divide o texto em blocos por padrão de cabeçalho de cupom."""
        positions = [m.start() for m in _COUPON_HEADERS.finditer(text)]
        if not positions:
            return [text]
        blocks = []
        for i, start in enumerate(positions):
            end = positions[i + 1] if i + 1 < len(positions) else len(text)
            blocks.append(text[start:end])
        logger.debug("Blocos de cupom encontrados: %d", len(blocks))
        return blocks

    def _parse_block(self, block: str) -> Optional[Coupon]:
        if not block.strip():
            return None
        c = Coupon(raw_text=block)

        m = _RE_SAT.search(block)
        if m:
            c.numero_sat = m.group(1).strip()

        m = _RE_COO.search(block)
        if m:
            c.numero_coo = m.group(1).strip()

        m = _RE_NFCE.search(block)
        if m:
            c.numero_nfce = m.group(1).strip()

        m = _RE_SUBTOTAL.search(block)
        if m:
            try:
                c.subtotal = _to_float(m.group(1))
            except ValueError:
                pass

        m = _RE_DESCONTO.search(block)
        if m:
            try:
                c.desconto = _to_float(m.group(1))
            except ValueError:
                pass

        # Pega o último match de total (evita falsos positivos de "subtotal")
        totals = _RE_TOTAL.findall(block)
        if totals:
            try:
                c.total = _to_float(totals[-1])
            except ValueError:
                pass

        # EANs únicos preservando ordem
        c.eans = list(dict.fromkeys(_RE_EAN.findall(block)))

        # Formas de pagamento únicas
        c.formas_pagamento = list({
            m.group(0).lower()
            for m in _RE_PAGAMENTO.finditer(block)
        })

        return c

    # ------------------------------------------------------------------
    # Consultas públicas
    # ------------------------------------------------------------------

    def get_by_numero(self, numero: str) -> Optional[Coupon]:
        """Busca cupom por SAT, NFC-e ou COO."""
        numero = str(numero).strip()
        for c in self._coupons:
            if numero in (c.numero_sat, c.numero_nfce, c.numero_coo):
                return c
        return None

    def get_by_eans(self, eans: list[str]) -> Optional[Coupon]:
        """Fallback: retorna o cupom com maior interseção de EANs."""
        best, best_score = None, 0
        ean_set = set(eans)
        for c in self._coupons:
            score = len(ean_set & set(c.eans))
            if score > best_score:
                best, best_score = c, score
        return best if best_score > 0 else None

    @property
    def coupons(self) -> list[Coupon]:
        return self._coupons
