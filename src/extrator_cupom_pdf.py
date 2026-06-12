"""
Módulo 3 — CouponPDFParser (extrator_cupom_pdf)
Responsabilidade: Extrai cupons fiscais (DANFE/NFC-e/SAT/ECF) do PDF.

Estrutura de índice:
  _index_numero : { numero (str) → Coupon }  ← número extraído do próprio bloco
  _index_sat    : { sat_num → Coupon }
  _index_nfce   : { nfce_num → Coupon }
  _index_ecf    : { coo_num  → Coupon }

Além dos blocos do PDF, aceita nomes de arquivo no formato
  <numero>_<resto>.pdf  ou  cupom_<numero>.pdf
para enriquecer o índice quando o número constar apenas no nome do arquivo.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Padrões de cabeçalho que sinalizam início de novo cupom no texto bruto
_COUPON_HEADERS = re.compile(
    r"(NFC-e|SAT\s+FISCAL|CUPOM\s+FISCAL|DANFE|COO\s*[:=]\s*\d+|NF-e|ECF\s*[:=])",
    re.IGNORECASE,
)

_RE_SUBTOTAL  = re.compile(r"(?:subtotal|sub[-\s]?total)\s*[:\-]?\s*([\d.,]+)", re.IGNORECASE)
_RE_DESCONTO  = re.compile(r"(?:desconto|desc\.?)\s*[:\-]?\s*([\d.,]+)", re.IGNORECASE)
_RE_TOTAL     = re.compile(r"(?:^|\s)total\s*[:\-]?\s*([\d.,]+)", re.IGNORECASE | re.MULTILINE)
_RE_EAN       = re.compile(r"\b(\d{13})\b")
_RE_PAGAMENTO = re.compile(
    r"(?:dinheiro|cart[aã]o\s+cr[eé]dito|cart[aã]o\s+d[eé]bito|pix|vale[-\s]?refei[çc][aã]o)",
    re.IGNORECASE,
)

# Número do cupom impresso — padrões comuns em NFC-e, SAT, ECF
_RE_NUMERO_CUPOM = re.compile(
    r"(?:"
    r"N[úu]mero\s+(?:do\s+)?(?:Cupom|Extrato|SAT|NFC-e|NF-e)\s*[:\-]?\s*(\d+)"
    r"|COO\s*[:\-=]?\s*(\d+)"
    r"|SAT\s*[:\-=]?\s*(\d{6,})"
    r"|NFC-e\s*[:\-=]?\s*(\d+)"
    r"|Nº\s*(\d+)"
    r")",
    re.IGNORECASE,
)

# Padrão para extrair número do nome do arquivo: ex. "000042_venda.pdf", "cupom_42.pdf"
_RE_FILENAME_NUMERO = re.compile(r"(?:^|[_\-])0*(\d{3,})(?:[_\-]|$|\.)")


def _to_float(val: str) -> float:
    return float(val.replace(".", "").replace(",", "."))


@dataclass
class Coupon:
    raw_text: str
    numero: Optional[str] = None
    numero_sat: Optional[str] = None
    numero_coo: Optional[str] = None
    numero_nfce: Optional[str] = None
    source_filename: Optional[str] = None
    subtotal: Optional[float] = None
    desconto: Optional[float] = None
    total: Optional[float] = None
    eans: list[str] = field(default_factory=list)
    formas_pagamento: list[str] = field(default_factory=list)

    def get_numero(self) -> Optional[str]:
        """Retorna o identificador mais específico disponível."""
        return self.numero or self.numero_sat or self.numero_nfce or self.numero_coo

    def all_numeros(self) -> list[str]:
        """Todos os identificadores não-nulos deste cupom."""
        return [n for n in (
            self.numero, self.numero_sat, self.numero_nfce, self.numero_coo
        ) if n]


class CouponPDFParser:
    """
    Extrai e parseia cupons fiscais de páginas PDF brutas.

    Parâmetros
    ----------
    pdf_pages       : lista de strings (texto por página) vindo do pdfplumber
    pdf_filename    : (opcional) nome do arquivo PDF — usado para enriquecer
                      o índice quando o número do cupom está no nome do arquivo
    """

    def __init__(self, pdf_pages: list[str], pdf_filename: Optional[str] = None):
        self.pdf_pages = pdf_pages
        self.pdf_filename = pdf_filename

        self._index_numero: dict[str, Coupon] = {}
        self._index_sat:    dict[str, Coupon] = {}
        self._index_nfce:   dict[str, Coupon] = {}
        self._index_ecf:    dict[str, Coupon] = {}
        self._coupons: list[Coupon] = []

        self._parse_all()

    def _parse_all(self) -> None:
        full_text = "\n".join(self.pdf_pages)
        blocks = self._split_into_blocks(full_text)
        for block in blocks:
            c = self._parse_block(block)
            if c:
                self._register(c)
                self._coupons.append(c)
        logger.info(
            "CouponPDFParser: %d cupons extraídos (numero=%d sat=%d nfce=%d ecf=%d)",
            len(self._coupons),
            len(self._index_numero),
            len(self._index_sat),
            len(self._index_nfce),
            len(self._index_ecf),
        )

    def _split_into_blocks(self, text: str) -> list[str]:
        positions = [m.start() for m in _COUPON_HEADERS.finditer(text)]
        if not positions:
            return [text] if text.strip() else []
        blocks = []
        for i, start in enumerate(positions):
            end = positions[i + 1] if i + 1 < len(positions) else len(text)
            blocks.append(text[start:end])
        return blocks

    def _parse_block(self, block: str) -> Optional[Coupon]:
        if not block.strip():
            return None
        c = Coupon(raw_text=block)
        if self.pdf_filename:
            c.source_filename = self.pdf_filename

        for m in _RE_NUMERO_CUPOM.finditer(block):
            groups = [g for g in m.groups() if g]
            if not groups:
                continue
            val = groups[0].strip()
            txt = m.group(0).lower()
            if "sat" in txt:
                c.numero_sat = c.numero_sat or val
            elif "nfc" in txt or "nf-e" in txt:
                c.numero_nfce = c.numero_nfce or val
            elif "coo" in txt or "ecf" in txt:
                c.numero_coo = c.numero_coo or val
            else:
                if not c.numero:
                    c.numero = val

        if not c.numero:
            c.numero = c.numero_sat or c.numero_nfce or c.numero_coo

        if self.pdf_filename and not c.numero:
            m = _RE_FILENAME_NUMERO.search(Path(self.pdf_filename).stem)
            if m:
                c.numero = m.group(1)
                logger.debug("Número extraído do nome do arquivo: %s", c.numero)

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

        totals = _RE_TOTAL.findall(block)
        if totals:
            try:
                c.total = _to_float(totals[-1])
            except ValueError:
                pass

        c.eans = list(dict.fromkeys(_RE_EAN.findall(block)))
        c.formas_pagamento = list({
            m.group(0).lower() for m in _RE_PAGAMENTO.finditer(block)
        })

        return c

    def _register(self, c: Coupon) -> None:
        if c.numero:
            self._index_numero.setdefault(c.numero, c)
        if c.numero_sat:
            self._index_sat.setdefault(c.numero_sat, c)
        if c.numero_nfce:
            self._index_nfce.setdefault(c.numero_nfce, c)
        if c.numero_coo:
            self._index_ecf.setdefault(c.numero_coo, c)

    def get_by_numero(self, numero: str) -> Optional["Coupon"]:
        numero = str(numero).strip()
        return (
            self._index_numero.get(numero)
            or self._index_sat.get(numero)
            or self._index_nfce.get(numero)
            or self._index_ecf.get(numero)
        )

    def get_by_filename(self, filename: str) -> Optional["Coupon"]:
        stem = Path(filename).stem
        m = _RE_FILENAME_NUMERO.search(stem)
        if m:
            return self.get_by_numero(m.group(1))
        return self.get_by_numero(stem)

    def get_by_eans(self, eans: list[str]) -> Optional["Coupon"]:
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
