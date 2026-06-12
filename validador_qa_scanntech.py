#!/usr/bin/env python3
"""
validador_qa_scanntech.py  (v4 — orquestrador definitivo)

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

# Imports usando nomes reais das classes dentro de cada módulo
from src.carregador_arquivos   import CarregadorArquivos
from src.processador_auditoria import AuditParser
from src.extrator_cupom_pdf    import CouponPDFParser
from src.motor_promocoes       import MotorPromocoes
from src.executor_testes       import ExecutorTestes
from src.gravador_resultados   import GravadorResultados
from src.registrador_auditoria import RegistradorAuditoria

# ── Logging ────────────────────────────────────────────────────────
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
    p = argparse.ArgumentParser(description="Scanntech QA Validator v4")
    p.add_argument("--roteiro",  required=True)
    p.add_argument("--audit",    required=True)
    p.add_argument("--pdf",      required=True)
    p.add_argument("--output",   required=True)
    p.add_argument("--log",      default="qa_audit_log.json")
    p.add_argument("--json-dir", default=None)
    return p.parse_args()


# ── Mapeamento de colunas ────────────────────────────────────────────────
_COL_MAP = {
    "teste":       ["teste"],
    "tipo_promo":  ["tipo promo", "tipopromo", "tipo_promo", "promo"],
    "itens":       ["itens", "item", "produto"],
    "pagamento":   ["pagamento", "payment", "pago"],
    "observacao":  ["observac", "obs"],
    "numero_sat":  ["sat"],
    "numero_ecf":  ["ecf"],
    "numero_nfce": ["nfce", "nfc-e", "nfc"],
    "subtotal":    ["sub-total", "subtotal", "sub total"],
    "desconto":    ["desconto", "descuento"],
    "total":       ["total"],
}


def _build_col_index(ws, header_row: int) -> dict:
    index = {}
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


def _extract_rows(ws, header_row: int, col_index: dict) -> list:
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
    logger.info("=== Scanntech QA Validator v4 — inicio ===")

    # 1. Carregamento — parametros corretos: caminho_roteiro / caminho_audit / caminho_pdf
    loader = CarregadorArquivos(
        caminho_roteiro=args.roteiro,
        caminho_audit=args.audit,
        caminho_pdf=args.pdf,
        diretorio_json=args.json_dir,
    )
    try:
        artefatos = loader.carregar_tudo()
    except FileNotFoundError as e:
        logger.error("Artefato nao encontrado: %s", e)
        return 1

    wb          = artefatos["workbook"]
    audit_df    = artefatos["audit_df"]
    pdf_paginas = artefatos["pdf_paginas"]   # chave correta do carregar_tudo()

    # 2. Parsing — AuditParser (nome real da classe em processador_auditoria.py)
    audit_parser = AuditParser(audit_df)
    pdf_parser   = CouponPDFParser(pdf_paginas)
    motor_promos = MotorPromocoes()

    # 3. Writer + Runner + Logger
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

        label = "OK" if getattr(resultado, "aprovado", getattr(resultado, "passed", False)) else "ERRO"
        motivo = getattr(resultado, "motivo_reprovacao", getattr(resultado, "motivo_erro", ""))
        logger.info(
            "[%d/%d] Linha %-3d %-4s %s",
            idx, total, data_row, label,
            f"({motivo})" if label == "ERRO" else ""
        )

    # 4. Persistência
    writer.save()
    try:
        alogger.finalizar()
        sumario = alogger.sumario()
    except AttributeError:
        # fallback caso metodos sejam flush()/summary()
        alogger.flush()
        sumario = alogger.summary()

    logger.info(
        "=== Concluido: %s/%d finalizados ===",
        sumario.get("aprovados", sumario.get("passou", "?")), sumario.get("total", total)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
