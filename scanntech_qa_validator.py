#!/usr/bin/env python3
"""
scanntech_qa_validator.py
Orquestrador principal do Scanntech QA Validator.

Colunas do roteiro para identificação do cupom:
  F → "Numero de cupom"  (número genérico)
  G → "SAT"              (SAT fiscal)
  H → "ECF" ou "NFCE"   (ECF/COO ou NFC-e)

Uso:
    python scanntech_qa_validator.py \\
        --roteiro  "TEMPLATE_COM_BIN_NOVO.xlsx" \\
        --audit    "export_tickets_audit.xlsx" \\
        --pdf      "ilovepdf_merged.pdf" \\
        --output   "TEMPLATE_PREENCHIDO.xlsx" \\
        --log      "qa_audit_log.json"
"""

import argparse
import logging
import sys

from src.file_loader       import FileLoader
from src.audit_parser      import AuditParser
from src.coupon_pdf_parser import CouponPDFParser
from src.promo_engine      import PromoEngine
from src.test_runner       import TestRunner
from src.result_writer     import ResultWriter, build_row_dict, _detect_header_row
from src.audit_logger      import AuditLogger

# -------------------------------------------------------------------
# Logging: console + arquivo simultâneos
# -------------------------------------------------------------------
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


def main() -> int:
    args = parse_args()
    logger.info("=== Scanntech QA Validator — início ===")

    # 1. Carregamento e validação dos artefatos
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

    # 2. Parsing dos artefatos
    audit_parser = AuditParser(audit_df)
    pdf_parser   = CouponPDFParser(pdf_pages)
    promo_engine = PromoEngine()

    # 3. Runner + Writer + Logger
    runner  = TestRunner(audit_parser, pdf_parser, promo_engine)
    writer  = ResultWriter(wb, args.output)
    alogger = AuditLogger(args.log)

    ws         = wb.active
    header_row = _detect_header_row(ws)

    # Conta linhas de dados
    data_rows = [
        r for r in range(header_row + 1, ws.max_row + 1)
        if any(ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1))
    ]
    total = len(data_rows)
    logger.info("Roteiro: %d linhas de teste encontradas (cabeçalho na linha %d)",
                total, header_row)

    for idx, data_row in enumerate(data_rows, start=1):
        # Monta dict da linha com chaves canônicas (sat, ecf, nfce, numero_cupom, ...)
        row = build_row_dict(ws, header_row, data_row)

        result = runner.run(row, linha=data_row)
        writer.write_result(result, data_row)
        alogger.record(result)

        status_label = "✓" if result.passed else "✗"
        logger.info(
            "[%d/%d] Linha %-3d %s  %s",
            idx, total, data_row, status_label,
            f"({result.motivo_erro})" if not result.passed else "",
        )

    # 4. Persistência final
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
