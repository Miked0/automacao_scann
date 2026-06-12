#!/usr/bin/env python3
"""
validador_qa_scanntech.py  (v3 — orquestrador corrigido)

Correcoes aplicadas:
  BUG-01/03: extrai numero_sat, numero_ecf, numero_nfce separadamente do header
  BUG-02/04: usa detect_header_row robusto e preenche 9 colunas de resultado
  BUG-05:    ProcessadorAuditoria detecta automaticamente modo JSON ou tabular
  BUG-06:    Imports corrigidos para nomes reais dos modulos em src/
  BUG-07:    Chaves de artefatos e campos de resultado alinhados com modelos.py

Uso:
    python validador_qa_scanntech.py \\
        --roteiro  "TEMPLATE_COM_BIN_NOVO.xlsx" \\
        --audit    "export_tickets_audit.xlsx" \\
        --pdf      "ilovepdf_merged.pdf" \\
        --output   "TEMPLATE_PREENCHIDO.xlsx" \\
        --log      "qa_audit_log.json"
"""

import argparse
import logging
import re
import sys
from pathlib import Path

from src.carregador_arquivos   import CarregadorArquivos
from src.processador_auditoria import ProcessadorAuditoria
from src.extrator_cupom_pdf    import CouponPDFParser
from src.motor_promocoes       import MotorPromocoes
from src.executor_testes       import ExecutorTestes
from src.gravador_resultados   import GravadorResultados
from src.registrador_auditoria import RegistradorAuditoria

# ── Logging: arquivo + console ───────────────────────────────────────
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
    p = argparse.ArgumentParser(description="Scanntech QA Validator v3")
    p.add_argument("--roteiro",  required=True, help="TEMPLATE xlsx (original, sem preenchimento)")
    p.add_argument("--audit",    required=True, help="Export Audit xlsx")
    p.add_argument("--pdf",      required=True, help="PDF de cupons fiscais")
    p.add_argument("--output",   required=True, help="Caminho do xlsx de saída preenchido")
    p.add_argument("--log",      default="qa_audit_log.json", help="Log JSON de auditoria")
    p.add_argument("--json-dir", default=None, help="(Opcional) dir com JSONs avulsos")
    return p.parse_args()


# ── Mapeamento de colunas do roteiro ───────────────────────────────────
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
                if field_name == "total" and "sub" in val:
                    continue
                index[field_name] = cell.column
    return index


def _extract_rows(ws, header_row: int, col_index: dict[str, int]) -> list[dict]:
    """Extrai linhas de dados do roteiro como lista de dicts."""
    # BUG-08 fix: re importado no topo do arquivo, nao dentro do loop
    rows = []
    for row_num in range(header_row + 1, ws.max_row + 1):
        row_vals = {}
        for field_name, col in col_index.items():
            row_vals[field_name] = ws.cell(row=row_num, column=col).value

        if all(v is None for v in row_vals.values()):
            continue

        itens_str = str(row_vals.get("itens", "") or "")
        row_vals["eans"] = re.findall(r"\b(\d{8,13})\b", itens_str)
        row_vals["_row_num"] = row_num
        rows.append(row_vals)
    return rows


def main() -> int:
    args = parse_args()
    logger.info("=== Scanntech QA Validator v3 — inicio ===")

    # ── 1. Carregamento ────────────────────────────────────────────────
    loader = CarregadorArquivos(
        roteiro_path=args.roteiro,
        audit_path=args.audit,
        pdf_path=args.pdf,
        json_dir=args.json_dir,
    )
    try:
        artefatos = loader.carregar_tudo()
    except FileNotFoundError as e:
        logger.error("Artefato nao encontrado: %s", e)
        return 1

    # BUG-07 fix: chave correta 'pdf_paginas' (nao 'pdf_pages')
    wb          = artefatos["workbook"]
    audit_df    = artefatos["audit_df"]
    pdf_paginas = artefatos["pdf_paginas"]

    # ── 2. Parsing ──────────────────────────────────────────────────────
    audit_parser = ProcessadorAuditoria(audit_df)
    pdf_parser   = CouponPDFParser(pdf_paginas)
    motor_promos = MotorPromocoes()

    # ── 3. Writer + Runner + Logger ───────────────────────────────────────
    writer   = GravadorResultados(wb, args.output)
    executor = ExecutorTestes(audit_parser, pdf_parser, motor_promos)
    alogger  = RegistradorAuditoria(args.log)

    ws         = wb.active
    header_row = writer.header_row
    col_index  = _build_col_index(ws, header_row)

    logger.info("Mapeamento de colunas: %s", col_index)

    rows  = _extract_rows(ws, header_row, col_index)
    total = len(rows)
    logger.info("Roteiro: %d linhas de teste encontradas", total)

    for idx, row in enumerate(rows, start=1):
        data_row = row["_row_num"]

        writer.clear_result_row(data_row)

        resultado = executor.executar(row, linha=data_row)
        writer.write_result(resultado, data_row)
        alogger.registrar(resultado)

        # BUG-07 fix: campo 'aprovado' e 'motivo_reprovacao' (nao 'passed'/'motivo_erro')
        label = "OK" if resultado.aprovado else "ERRO"
        logger.info(
            "[%d/%d] Linha %-3d %-4s %s",
            idx, total, data_row, label,
            f"({resultado.motivo_reprovacao})" if not resultado.aprovado else ""
        )

    # ── 4. Persistência ──────────────────────────────────────────────────
    writer.save()
    alogger.finalizar()

    sumario = alogger.sumario()
    logger.info(
        "=== Concluido: %d/%d aprovados (%.1f%%) ===",
        sumario["aprovados"], sumario["total"], sumario["pct_ok"]
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
