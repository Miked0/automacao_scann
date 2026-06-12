#!/usr/bin/env python3
"""
scanntech_qa_validator.py  (v2 — orquestrador corrigido)

Correcoes aplicadas:
  BUG-01/03: extrai numero_sat, numero_ecf, numero_nfce separadamente do header
  BUG-02/04: usa detect_header_row robusto e preenche 9 colunas de resultado
  BUG-05:    AuditParser detecta automaticamente modo JSON ou tabular

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
from pathlib import Path

from src.file_loader       import FileLoader
from src.audit_parser      import AuditParser
from src.coupon_pdf_parser import CouponPDFParser
from src.promo_engine      import PromoEngine
from src.test_runner       import TestRunner
from src.result_writer     import ResultWriter, detect_header_row
from src.audit_logger      import AuditLogger

# ── Logging: arquivo + console ──────────────────────────────────────
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
    p = argparse.ArgumentParser(description="Scanntech QA Validator v2")
    p.add_argument("--roteiro",  required=True, help="TEMPLATE xlsx (original, sem preenchimento)")
    p.add_argument("--audit",    required=True, help="Export Audit xlsx")
    p.add_argument("--pdf",      required=True, help="PDF de cupons fiscais")
    p.add_argument("--output",   required=True, help="Caminho do xlsx de saída preenchido")
    p.add_argument("--log",      default="qa_audit_log.json", help="Log JSON de auditoria")
    p.add_argument("--json-dir", default=None, help="(Opcional) dir com JSONs avulsos")
    return p.parse_args()


# ── Mapeamento de colunas do roteiro ─────────────────────────────────

# Chaves de busca para cada coluna do TEMPLATE (case-insensitive)
_COL_MAP = {
    "teste":          ["teste"],
    "tipo_promo":     ["tipo promo", "tipopromo", "tipo_promo", "promo"],
    "itens":          ["itens", "item", "produto"],
    "pagamento":      ["pagamento", "payment", "pago"],
    "observacao":     ["observac", "obs"],
    "numero_sat":     ["sat"],
    "numero_ecf":     ["ecf"],
    "numero_nfce":    ["nfce", "nfc-e", "nfc"],
    "subtotal":       ["sub-total", "subtotal", "sub total"],
    "desconto":       ["desconto", "descuento"],
    "total":          ["total"],
}


def _build_col_index(ws, header_row: int) -> dict[str, int]:
    """
    Mapeia nomes de campo → índice de coluna (1-based) usando _COL_MAP.
    BUG-01 fix: numero_sat, numero_ecf, numero_nfce mapeados separadamente.
    """
    index: dict[str, int] = {}
    for cell in ws[header_row]:
        if not cell.value:
            continue
        val = str(cell.value).lower().strip()
        for field_name, keywords in _COL_MAP.items():
            if field_name not in index and any(kw in val for kw in keywords):
                # Evita que 'total' sobrescreva 'subtotal'
                if field_name == "total" and "sub" in val:
                    continue
                # Evita que 'observacao' do input (C5) seja confundido com output (C21)
                # O input está antes das colunas de número; o output depois.
                index[field_name] = cell.column
    return index


def _extract_rows(ws, header_row: int, col_index: dict[str, int]) -> list[dict]:
    """Extrai linhas de dados do roteiro como lista de dicts."""
    rows = []
    for row_num in range(header_row + 1, ws.max_row + 1):
        row_vals = {}
        for field_name, col in col_index.items():
            row_vals[field_name] = ws.cell(row=row_num, column=col).value

        # Pula linhas completamente vazias
        if all(v is None for v in row_vals.values()):
            continue

        # Extrai EANs do campo itens (formato: "N x EAN + ...")
        import re
        itens_str = str(row_vals.get("itens", "") or "")
        row_vals["eans"] = re.findall(r"\b(\d{8,13})\b", itens_str)

        row_vals["_row_num"] = row_num
        rows.append(row_vals)
    return rows


def main() -> int:
    args = parse_args()
    logger.info("=== Scanntech QA Validator v2 — inicio ===")

    # ── 1. Carregamento ──────────────────────────────────────────────
    loader = FileLoader(
        roteiro_path=args.roteiro,
        audit_path=args.audit,
        pdf_path=args.pdf,
        json_dir=args.json_dir,
    )
    try:
        artefatos = loader.load_all()
    except FileNotFoundError as e:
        logger.error("Artefato nao encontrado: %s", e)
        return 1

    wb       = artefatos["workbook"]
    audit_df = artefatos["audit_df"]
    pdf_pages = artefatos["pdf_pages"]

    # ── 2. Parsing ───────────────────────────────────────────────────
    audit_parser = AuditParser(audit_df)      # BUG-05: auto-detecta modo
    pdf_parser   = CouponPDFParser(pdf_pages)
    promo_engine = PromoEngine()

    # ── 3. Writer + Runner + Logger ──────────────────────────────────
    writer  = ResultWriter(wb, args.output)   # BUG-02/04: header e 9 colunas
    runner  = TestRunner(audit_parser, pdf_parser, promo_engine)  # BUG-01/03
    alogger = AuditLogger(args.log)

    ws = wb.active
    header_row = writer.header_row  # reutiliza o detectado pelo ResultWriter
    col_index  = _build_col_index(ws, header_row)

    logger.info("Mapeamento de colunas: %s", col_index)

    rows = _extract_rows(ws, header_row, col_index)
    total = len(rows)
    logger.info("Roteiro: %d linhas de teste encontradas", total)

    for idx, row in enumerate(rows, start=1):
        data_row = row["_row_num"]

        # BUG-03: limpa resultados anteriores antes de reprocessar
        writer.clear_result_row(data_row)

        result = runner.run(row, linha=data_row)
        writer.write_result(result, data_row)
        alogger.record(result)

        label = "OK" if result.passed else "ERRO"
        logger.info(
            "[%d/%d] Linha %-3d %-4s %s",
            idx, total, data_row, label,
            f"({result.motivo_erro})" if not result.passed else ""
        )

    # ── 4. Persistencia ──────────────────────────────────────────────
    writer.save()
    alogger.flush()

    sumario = alogger.summary()
    logger.info(
        "=== Concluido: %d/%d passaram (%.1f%%) ===",
        sumario["passou"], sumario["total"], sumario["pct_ok"]
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
