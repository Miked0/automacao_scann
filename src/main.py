"""Entry point para a automação de validação do roteiro de testes de PDV.

Fluxo:
1. Lê a planilha do roteiro (leitor)
2. Valida cada caso de teste (validadores)
3. Exporta resultado consolidado para Excel (exportadores)
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from leitor      import carregar_casos_do_roteiro
from validadores import validar_caso_de_teste
from exportadores import exportar_resultados


def executar_mvp(caminho_entrada: str, caminho_saida: str) -> None:
    print(f"[INFO] Lendo planilha: {caminho_entrada}")
    casos = carregar_casos_do_roteiro(Path(caminho_entrada))
    print(f"[INFO] {len(casos)} casos de teste encontrados")

    resultados = []
    for caso in casos:
        status = validar_caso_de_teste(caso)
        resultados.append({**caso, **status})

    total_ok     = sum(1 for r in resultados if r["status_final"] == "OK")
    total_alerta = sum(1 for r in resultados if r["status_final"] == "ALERTA")
    total_erro   = sum(1 for r in resultados if r["status_final"].startswith("ERRO"))
    print(f"[RESULTADO] OK={total_ok} | ALERTA={total_alerta} | ERRO={total_erro}")

    exportar_resultados(resultados, Path(caminho_saida))
    print(f"[INFO] Resultado exportado para: {caminho_saida}")


# Alias de compatibilidade — mantido enquanto scripts externos referenciam run_mvp
run_mvp = executar_mvp


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Validação automática de roteiro de testes PDV"
    )
    parser.add_argument("input",  help="Caminho do roteiro_testes.xlsx")
    parser.add_argument("output", help="Caminho do arquivo de saída .xlsx")
    args = parser.parse_args()
    executar_mvp(args.input, args.output)
