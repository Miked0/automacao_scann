"""
Módulo 3 — CouponPDFParser
Responsabilidade: Extrai cupons fiscais (DANFE/NFC-e/SAT) do PDF.
"""
import re
import logging
from typing import List, Dict, Optional
import pdfplumber

logger = logging.getLogger(__name__)

COUPON_HEADER_PATTERNS = [
    r"NFC-?e",
    r"\bSAT\b",
    r"COO\s*[:\-]?\s*\d+",
    r"DANFE",
    r"CUPOM\s+FISCAL",
    r"CF-?e",
]
COUPON_HEADER_RE = re.compile("|".join(COUPON_HEADER_PATTERNS), re.IGNORECASE)


class CouponPDFParser:
    """
    Extrai e parseia cupons fiscais de um PDF mesclado.
    Cada bloco de texto é mapeado para um dicionário com campos
    subtotal, desconto, total, eans, pagamentos, numero_sat, numero_ecf, numero_nfce.
    """

    def __init__(self, pdf: pdfplumber.PDF):
        self.pdf = pdf
        self.coupons: List[Dict] = []
        self._extract()

    def _get_full_text(self) -> str:
        pages = []
        for page in self.pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)
        return "\n".join(pages)

    def _split_into_blocks(self, full_text: str) -> List[str]:
        """Divide o texto em blocos por padrão de cabeçalho de cupom."""
        lines = full_text.split("\n")
        blocks = []
        current = []
        for line in lines:
            if COUPON_HEADER_RE.search(line) and current:
                blocks.append("\n".join(current))
                current = [line]
            else:
                current.append(line)
        if current:
            blocks.append("\n".join(current))
        return [b for b in blocks if len(b.strip()) > 50]

    def _parse_block(self, block: str) -> Optional[Dict]:
        """Parseia um bloco de texto de cupom para extrair campos relevantes."""
        coupon = {
            "raw": block,
            "subtotal": None,
            "desconto": None,
            "total": None,
            "eans": [],
            "pagamentos": [],
            "numero_sat": None,
            "numero_ecf": None,
            "numero_nfce": None,
        }

        m = re.search(r"SAT[\s\-:N°nº]*([\d]{6,})", block, re.IGNORECASE)
        if m:
            coupon["numero_sat"] = m.group(1).strip()

        m = re.search(r"COO\s*[:\-]?\s*(\d+)", block, re.IGNORECASE)
        if m:
            coupon["numero_ecf"] = m.group(1).strip()

        m = re.search(r"(?:nNF|N[uú]mero\s+NF|NFC-?e[\s\-:]*N[°oº]?)\s*[:\-]?\s*(\d+)", block, re.IGNORECASE)
        if m:
            coupon["numero_nfce"] = m.group(1).strip()

        m = re.search(r"(?:TOTAL|VALOR\s+TOTAL)[\s\$R]*[:\-]?\s*([\d]{1,6}[.,]\d{2})", block, re.IGNORECASE)
        if m:
            coupon["total"] = self._parse_float(m.group(1))

        m = re.search(r"(?:SUBTOTAL|SUB-?TOTAL)[\s\$R]*[:\-]?\s*([\d]{1,6}[.,]\d{2})", block, re.IGNORECASE)
        if m:
            coupon["subtotal"] = self._parse_float(m.group(1))

        m = re.search(r"(?:DESCONTO|DESCUENTO|DESC\.?)[\s\$R]*[:\-]?\s*([\d]{1,6}[.,]\d{2})", block, re.IGNORECASE)
        if m:
            coupon["desconto"] = self._parse_float(m.group(1))

        eans = re.findall(r"\b(\d{8,14})\b", block)
        coupon["eans"] = list(set(
            e for e in eans
            if not re.match(r"^\d{2}[/.-]\d{2}[/.-]", e) and len(e) >= 8
        ))

        pag_patterns = [
            (r"DINHEIRO|ESPECIE|ESPÉCIE", "dinheiro"),
            (r"CRÉDITO|CREDITO", "credito"),
            (r"DÉBITO|DEBITO", "debito"),
            (r"PIX", "pix"),
            (r"VALE|TICKET|VR|VA", "vale"),
        ]
        for pat, label in pag_patterns:
            if re.search(pat, block, re.IGNORECASE):
                coupon["pagamentos"].append(label)

        return coupon

    @staticmethod
    def _parse_float(s: str) -> float:
        s = s.strip().replace(".", "").replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return 0.0

    def _extract(self):
        full_text = self._get_full_text()
        blocks = self._split_into_blocks(full_text)
        logger.info(f"CouponPDFParser: {len(blocks)} blocos identificados no PDF.")
        for block in blocks:
            parsed = self._parse_block(block)
            if parsed:
                self.coupons.append(parsed)
        logger.info(f"CouponPDFParser: {len(self.coupons)} cupons parseados.")

    def find_by_numero(self, numero: str) -> Optional[Dict]:
        """Busca cupão pelo número SAT, ECF ou NFCE."""
        numero = str(numero).strip().lstrip("-")
        for c in self.coupons:
            if (c.get("numero_sat") == numero or
                    c.get("numero_ecf") == numero or
                    c.get("numero_nfce") == numero):
                return c
        return None

    def find_by_eans(self, eans: List[str]) -> Optional[Dict]:
        """Busca cupão por conjunto de EANs (fallback)."""
        ean_set = set(str(e) for e in eans)
        best = None
        best_score = 0
        for c in self.coupons:
            score = len(ean_set & set(c.get("eans", [])))
            if score > best_score:
                best_score = score
                best = c
        return best if best_score > 0 else None
