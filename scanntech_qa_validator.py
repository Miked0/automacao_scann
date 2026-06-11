#!/usr/bin/env python3
"""
scanntech_qa_validator.py
Orquestrador principal do Scanntech QA Validator.

Uso:
    python scanntech_qa_validator.py \\
        --roteiro  "TEMPLATE_COM_BIN_NOVO.xlsx" \\
        --audit    "export_tickets_audit_companyId-200056.xlsx" \\
        --pdf      "ilovepdf_merged-1-2.pdf" \\
        --output   "TEMPLATE_PREENCHIDO.xlsx" \\
        --log      "qa_audit_log.json"
"""

import argparse
import logging
import sys
from pathlib import Path

from src.file_loader       import FileLoader
from src.audit_parser      import AuditParser
from src.coupon_pdf_parser import CouponPDFParser
from src.promo_engine      import PromoEngine
from src.test_runner       import TestRunner
from src.result_writer     import ResultWriter, KEYWORDS_HEADER
from src.audit_logger      import AuditLogger

# ---------------------------------------------------------------------------
# Logging: arquivo + console simultâneos
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("qa_validation.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("qa_validator")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scanntech QA Validator")
    p.add_argument("--roteiro",  required=True, help="Caminho do TEMPLATE xlsx")
    p.add_argument("--audit",    required=True, help="Caminho do Export Audit xlsx")
    p.add_argument("--pdf",      required=True, help="Caminho do PDF de cupons")
    p.add_argument("--output",   required=True, help="Caminho do xlsx de saída")
    p.add_argument("--log",      default="qa_audit_log.json",
                   help="Caminho do log JSON de auditoria")
    p.add_argument("--json-dir", default=None,
                   help="(Opcional) Diretório com JSONs de venda avulsos")
    return p.parse_args()


def _detect_header(wb) -> int:
    ws = wb.active
    for row in ws.iter_rows():
        for cell in row:
            if cell.value and any(
                kw in str(cell.value).lower() for kw in KEYWORDS_HEADER
            ):
                return cell.row
    return 1


def _extract_roteiro_rows(wb, header_row: int) -> list[dict]:
    """Lê linhas do roteiro a partir da linha de cabeçalho."""
    ws = wb.active
    headers = [
        str(cell.value).strip().lower() if cell.value else f"col_{cell.column}"
        for cell in ws[header_row]
    ]
    rows = []
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        if all(v is None for v in row):
            continue
        rows.append(dict(zip(headers, row)))
    return rows


def main() -> int:
    args = parse_args()
    logger.info("=== Scanntech QA Validator — início ===")

    # --- 1. Carregamento ---
    loader = FileLoader(
        roteiro_path=args.roteiro,
        audit_path=args.audit,
        pdf_path=args.pdf,
        json_dir=args.json_dir,
    )
    try:
        artefatos = loader.load_all()
    except FileNotFoundError as e:
        logger.error("Artefato não encontrado: %s", e)
        return 1

    wb        = artefatos["workbook"]
    audit_df  = artefatos["audit_df"]
    pdf_pages = artefatos["pdf_pages"]

    # --- 2. Parsing ---
    audit_parser = AuditParser(audit_df)
    pdf_parser   = CouponPDFParser(pdf_pages)
    promo_engine = PromoEngine()

    # --- 3. Runner + Writer + Logger ---
    runner  = TestRunner(audit_parser, pdf_parser, promo_engine)
    writer  = ResultWriter(wb, args.output)
    alogger = AuditLogger(args.log)

    header_row = _detect_header(wb)
    rows       = _extract_roteiro_rows(wb, header_row)

    total = len(rows)
    logger.info("Roteiro: %d linhas de teste encontradas", total)

    for idx, row in enumerate(rows, start=1):
        data_row = header_row + idx
        result   = runner.run(row, linha=data_row)
        writer.write_result(result, data_row)
        alogger.record(result)

        label = "✓" if result.passed else "✗"
        logger.info(
            "[%d/%d] Linha %-3d %s  %s",
            idx, total, data_row, label,
            f"({result.motivo_erro})" if not result.passed else "",
        )

    # --- 4. Persistência ---
    writer.save()
    alogger.flush()

    sumario = alogger.summary()
    logger.info(
        "=== Concluído: %d/%d passaram (%.1f%%) ===",
        sumario["passou"], sumario["total"], sumario["pct_ok"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
