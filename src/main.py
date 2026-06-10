"""Entry point para a automação de validação do roteiro de testes de PDV.

Fluxo:
1. Lê a planilha do roteiro
2. Localiza blocos de teste automaticamente
3. Extrai e normaliza cada linha
4. Valida subtotal, desconto, total e itens
5. Exporta resultado consolidado para Excel
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from reader import load_roteiro_tests
from validators import validate_test_case
from exporters import export_results


def run_mvp(input_path: str, output_path: str) -> None:
    print(f"[INFO] Lendo planilha: {input_path}")
    tests = load_roteiro_tests(Path(input_path))
    print(f"[INFO] {len(tests)} casos de teste encontrados")

    results = []
    for t in tests:
        status = validate_test_case(t)
        results.append({**t, **status})

    ok = sum(1 for r in results if r["status_final"] == "OK")
    alerta = sum(1 for r in results if r["status_final"] == "ALERTA")
    erro = sum(1 for r in results if r["status_final"].startswith("ERRO"))
    print(f"[RESULTADO] OK={ok} | ALERTA={alerta} | ERRO={erro}")

    export_results(results, Path(output_path))
    print(f"[INFO] Resultado exportado para: {output_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Validação automática de roteiro de testes PDV"
    )
    parser.add_argument("input", help="Caminho do roteiro_testes.xlsx")
    parser.add_argument("output", help="Caminho do arquivo de saída .xlsx")
    args = parser.parse_args()
    run_mvp(args.input, args.output)
