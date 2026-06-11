#!/usr/bin/env python3
"""
Scanntech QA Validator — Ponto de entrada CLI
Uso:
    python scanntech_qa_validator.py \
        --roteiro  TEMPLATE_COM_BIN_NOVO.xlsx \
        --audit    export_tickets_audit.xlsx \
        --pdf      ilovepdf_merged.pdf \
        --output   TEMPLATE_PREENCHIDO.xlsx \
        --log      qa_audit_log.json \
        [--json-dir ./jsons]
"""

import argparse
import sys
import logging

from src.file_loader import FileLoader
from src.audit_parser import AuditParser
from src.coupon_pdf_parser import CouponPDFParser
from src.promo_engine import PromoEngine
from src.test_runner import TestRunner
from src.result_writer import ResultWriter
from src.audit_logger import AuditLogger


def setup_logging(log_file: str = "qa_validation.log") -> None:
    fmt = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Validador automatizado de roteiros QA Scanntech"
    )
    p.add_argument("--roteiro",  required=True, help="TEMPLATE xlsx de roteiro")
    p.add_argument("--audit",    required=True, help="Export Audit XLSX")
    p.add_argument("--pdf",      required=True, help="PDF com cupons fiscais")
    p.add_argument("--output",   required=True, help="Arquivo XLSX de saída preenchido")
    p.add_argument("--log",      default="qa_audit_log.json", help="Arquivo JSON de log estruturado")
    p.add_argument("--json-dir", default=None,  help="Diretório com JSONs de venda avulsos (opcional)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging()
    log = logging.getLogger("main")

    # ── Etapa 1: FileLoader ──────────────────────────────────────────────────
    log.info("[1/7] Carregando artefatos...")
    loader = FileLoader(
        roteiro_path=args.roteiro,
        audit_path=args.audit,
        pdf_path=args.pdf,
        json_dir=args.json_dir,
    )
    loader.validate()
    wb_roteiro, df_audit, pdf_pages, extra_jsons = loader.load()

    # ── Etapa 2: AuditParser ────────────────────────────────────────────────
    log.info("[2/7] Indexando movimentos do Audit...")
    audit_parser = AuditParser(df_audit)
    movements = audit_parser.build_index()

    # ── Etapa 3: CouponPDFParser ────────────────────────────────────────────
    log.info("[3/7] Extraindo cupons do PDF...")
    pdf_parser = CouponPDFParser(pdf_pages)
    coupons = pdf_parser.extract_all()
    log.info("  %d cupons extraídos do PDF.", len(coupons))

    # ── Etapa 4: PromoEngine ────────────────────────────────────────────────
    log.info("[4/7] Inicializando motor de promoções...")
    promo_engine = PromoEngine()

    # ── Etapa 5: TestRunner ─────────────────────────────────────────────────
    log.info("[5/7] Executando validações linha a linha...")
    runner = TestRunner(
        wb_roteiro=wb_roteiro,
        movements=movements,
        coupons=coupons,
        promo_engine=promo_engine,
        extra_jsons=extra_jsons,
    )
    results = runner.run()
    log.info("  %d testes processados.", len(results))

    # ── Etapa 6: ResultWriter ───────────────────────────────────────────────
    log.info("[6/7] Preenchendo colunas de resultado no XLSX...")
    writer = ResultWriter(wb_roteiro)
    writer.write(results)
    writer.save(args.output)
    log.info("  Saída salva em: %s", args.output)

    # ── Etapa 7: AuditLogger ────────────────────────────────────────────────
    log.info("[7/7] Gerando log de auditoria JSON...")
    audit_logger = AuditLogger(args.log)
    audit_logger.write(results)
    log.info("  Log de auditoria salvo em: %s", args.log)

    ok   = sum(1 for r in results if r.overall_ok)
    fail = len(results) - ok
    log.info("Concluído. ✅ %d OK  ❌ %d ERRO", ok, fail)


if __name__ == "__main__":
    main()
