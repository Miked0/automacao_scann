#!/usr/bin/env python3
"""
scanntech_qa_validator.py
Orquestrador principal do Scanntech QA Validator.

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
from typing import Optional

from src.file_loader       import FileLoader
from src.audit_parser      import AuditParser
from src.coupon_pdf_parser import CouponPDFParser
from src.promo_engine      import PromoEngine
from src.test_runner       import TestRunner
from src.result_writer     import ResultWriter, KEYWORDS_HEADER
from src.audit_logger      import AuditLogger

# -------------------------------------------------------------------
# Logging: arquivo + console simultâneos
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


def _resolve_merged_headers(ws, header_row: int) -> dict:
    """
    Constrói um mapa coluna_index -> nome_header resolvendo células mescladas.

    Problema: quando o cabeçalho tem merges, as células secundárias retornam
    None em ws[header_row]. Esta função propaga o valor da célula âncora para
    todos os índices cobertos pelo merge, garantindo que nenhum header fique
    como col_N.
    """
    # Passo 1: mapa base usando os valores diretos da linha
    col_map: dict[int, str] = {}
    for cell in ws[header_row]:
        if cell.value is not None:
            col_map[cell.column] = str(cell.value).strip().lower()

    # Passo 2: propaga valores das âncoras para colunas cobertas por merges
    for mr in ws.merged_cells.ranges:
        if mr.min_row <= header_row <= mr.max_row:
            anchor_val = ws.cell(row=mr.min_row, column=mr.min_col).value
            if anchor_val is None:
                continue
            anchor_str = str(anchor_val).strip().lower()
            for col_idx in range(mr.min_col, mr.max_col + 1):
                if col_idx not in col_map:
                    col_map[col_idx] = anchor_str

    # Passo 3: preenche colunas ainda sem nome como col_N
    max_col = ws.max_column or 0
    for col_idx in range(1, max_col + 1):
        if col_idx not in col_map:
            col_map[col_idx] = f"col_{col_idx}"

    logger.debug("Headers detectados: %s", col_map)
    return col_map


def _detect_header(wb) -> int:
    """
    Detecta linha de cabeçalho por palavras-chave.
    Também verifica células mescladas para não perder o cabeçalho quando
    a primeira célula está num bloco mesclado.
    """
    ws = wb.active

    # Varre células normais
    for row in ws.iter_rows():
        for cell in row:
            if cell.value and any(
                kw in str(cell.value).lower() for kw in KEYWORDS_HEADER
            ):
                return cell.row

    # Fallback: varre âncoras de merges
    for mr in ws.merged_cells.ranges:
        anchor = ws.cell(row=mr.min_row, column=mr.min_col)
        if anchor.value and any(
            kw in str(anchor.value).lower() for kw in KEYWORDS_HEADER
        ):
            return mr.min_row

    return 1


def _extract_roteiro_rows(wb, header_row: int) -> list:
    """
    Lê linhas do roteiro a partir da linha de cabeçalho.
    Usa _resolve_merged_headers para garantir que células mescladas no
    cabeçalho sejam corretamente mapeadas.
    """
    ws = wb.active
    col_map = _resolve_merged_headers(ws, header_row)

    # Ordena por índice de coluna para montar lista de headers na ordem certa
    max_col = ws.max_column or 0
    headers = [col_map.get(i, f"col_{i}") for i in range(1, max_col + 1)]

    rows = []
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        if all(v is None for v in row):
            continue
        rows.append(dict(zip(headers, row)))

    # Log de diagnóstico: mostra os headers reais encontrados
    if rows:
        logger.info("Headers do roteiro: %s", list(rows[0].keys())[:10])

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
    total      = len(rows)
    logger.info("Roteiro: %d linhas de teste encontradas", total)

    for idx, row in enumerate(rows, start=1):
        data_row = header_row + idx
        result   = runner.run(row, linha=data_row)
        writer.write_result(result, data_row)
        alogger.record(result)

        status_label = "\u2713" if result.passed else "\u2717"
        logger.info(
            "[%d/%d] Linha %-3d %s  %s",
            idx, total, data_row, status_label,
            f"({result.motivo_erro})" if not result.passed else ""
        )

    # --- 4. Persistência ---
    writer.save()
    alogger.flush()

    sumario = alogger.summary()
    logger.info(
        "=== Concluído: %d/%d passaram (%.1f%%) ===",
        sumario["passou"], sumario["total"], sumario["pct_ok"]
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
