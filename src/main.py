from __future__ import annotations

from pathlib import Path

from exporters import export_results
from reader import load_roteiro_tests
from validators import validate_test_case


def run_mvp_v2(input_path: str, output_path: str) -> None:
    tests, blocks = load_roteiro_tests(Path(input_path))
    validated = [validate_test_case(t) for t in tests]
    export_results(validated, blocks, Path(output_path))


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Validação automática de roteiro de testes de PDV - v2')
    parser.add_argument('input', help='Caminho do arquivo roteiro_testes.xlsx')
    parser.add_argument('output', help='Caminho do arquivo de saída validacao_resultado.xlsx')

    args = parser.parse_args()
    run_mvp_v2(args.input, args.output)
