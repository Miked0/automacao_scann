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
from pathlib import Path

from src.file_loader       import FileLoader
from src.audit_parser      import AuditParser
from src.coupon_pdf_parser import CouponPDFParser
from src.promo_engine      import PromoEngine
from src.test_runner       import TestRunner
from src.result_writer     import ResultWriter, KEYWORDS_HEADER, _EXPECTED_HEADER_ROW
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
    p.add_argument("--header-row", type=int, default=None,
                   help="(Opcional) Força o número da linha de cabeçalho (1-based)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Detecção de cabeçalho (mesma lógica do ResultWriter)
# ---------------------------------------------------------------------------

def _detect_header(wb, forced: int = None) -> int:
    """
    Detecta a linha de cabeçalho com estratégia em três passos:

      0. Se --header-row foi passado na CLI, usa diretamente (sem busca).
      1. Verifica se a linha _EXPECTED_HEADER_ROW (7) tem keyword exclusiva.
      2. Varredura completa por KEYWORDS_HEADER estritas.
      3. Fallback: retorna _EXPECTED_HEADER_ROW (7).

    As KEYWORDS_HEADER são exclusivas da linha real de cabeçalho, evitando
    falsos positivos em títulos ou rodapés das linhas 1-6.
    """
    if forced is not None:
        logger.info("Cabeçalho forçado via --header-row: linha %d", forced)
        return forced

    ws = wb.active

    # Passo 1: verifica linha esperada
    for cell in ws[_EXPECTED_HEADER_ROW]:
        if cell.value and any(
            kw in str(cell.value).strip().lower() for kw in KEYWORDS_HEADER
        ):
            logger.info(
                "Cabeçalho confirmado na linha esperada %d", _EXPECTED_HEADER_ROW
            )
            return _EXPECTED_HEADER_ROW

    # Passo 2: varredura completa
    for row in ws.iter_rows():
        for cell in row:
            if cell.value and any(
                kw in str(cell.value).strip().lower() for kw in KEYWORDS_HEADER
            ):
                logger.info(
                    "Cabeçalho encontrado por varredura na linha %d", cell.row
                )
                return cell.row

    # Passo 3: fallback
    logger.warning(
        "Cabeçalho não detectado. Usando fallback linha %d.", _EXPECTED_HEADER_ROW
    )
    return _EXPECTED_HEADER_ROW


# ---------------------------------------------------------------------------
# Leitura de linhas do roteiro
# ---------------------------------------------------------------------------

def _resolve_merged_headers(ws, header_row: int) -> dict:
    """
    Constrói mapa col_index -> nome_header resolvendo células mescladas.
    """
    col_map: dict[int, str] = {}
    for cell in ws[header_row]:
        if cell.value is not None:
            col_map[cell.column] = str(cell.value).strip().lower()

    for mr in ws.merged_cells.ranges:
        if mr.min_row <= header_row <= mr.max_row:
            anchor_val = ws.cell(row=mr.min_row, column=mr.min_col).value
            if anchor_val is None:
                continue
            anchor_str = str(anchor_val).strip().lower()
            for col_idx in range(mr.min_col, mr.max_col + 1):
                if col_idx not in col_map:
                    col_map[col_idx] = anchor_str

    max_col = ws.max_column or 0
    for col_idx in range(1, max_col + 1):
        if col_idx not in col_map:
            col_map[col_idx] = f"col_{col_idx}"

    logger.debug("Headers detectados: %s", col_map)
    return col_map


def _is_test_row(row_values: tuple) -> bool:
    """
    Linha de teste válida: Coluna A (index 0) deve ter conteúdo não vazio.
    Linhas de agrupamento/espaçamento têm Coluna A vazia.
    """
    if all(v is None for v in row_values):
        return False
    val_a = row_values[0] if row_values else None
    return val_a is not None and str(val_a).strip() != ""


def _extract_roteiro_rows(wb, header_row: int) -> list:
    """
    Retorna lista de (numero_real_linha_xlsx, dict_row).

    Preserva o número real da linha no xlsx para que o ResultWriter
    escreva nas células corretas mesmo com linhas não contíguas
    (ex: testes em linhas 8,9,19,21,22... com gaps de agrupamento).
    """
    ws = wb.active
    col_map = _resolve_merged_headers(ws, header_row)
    max_col = ws.max_column or 0
    headers = [col_map.get(i, f"col_{i}") for i in range(1, max_col + 1)]

    rows: list[tuple[int, dict]] = []

    for row_cells in ws.iter_rows(min_row=header_row + 1):
        values       = tuple(cell.value for cell in row_cells)
        real_row_num = row_cells[0].row

        if not _is_test_row(values):
            logger.debug("Linha %d ignorada (vazia ou agrupamento)", real_row_num)
            continue

        row_dict = dict(zip(headers, values))
        rows.append((real_row_num, row_dict))

    if rows:
        logger.info(
            "Linhas de teste: %d | Primeira=linha %d | Última=linha %d",
            len(rows), rows[0][0], rows[-1][0]
        )
        logger.info("Amostra de headers: %s", list(rows[0][1].keys())[:10])

    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

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

    # --- 2. Detecção do cabeçalho ---
    header_row = _detect_header(wb, forced=args.header_row)
    logger.info("Cabeçalho na linha %d", header_row)

    # --- 3. Parsing ---
    audit_parser = AuditParser(audit_df)
    pdf_parser   = CouponPDFParser(pdf_pages)
    promo_engine = PromoEngine()

    # --- 4. Runner + Writer + Logger ---
    runner  = TestRunner(audit_parser, pdf_parser, promo_engine)
    writer  = ResultWriter(wb, args.output)
    alogger = AuditLogger(args.log)

    rows  = _extract_roteiro_rows(wb, header_row)
    total = len(rows)
    logger.info("Roteiro: %d testes encontrados", total)

    for idx, (real_row_num, row_dict) in enumerate(rows, start=1):
        result = runner.run(row_dict, linha=real_row_num)
        writer.write_result(result, real_row_num)
        alogger.record(result)

        status_label = "✓" if result.passed else "✗"
        logger.info(
            "[%d/%d] Linha xlsx=%-3d %s  %s",
            idx, total, real_row_num, status_label,
            f"({result.motivo_erro})" if not result.passed else ""
        )

    # --- 5. Persistência ---
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
