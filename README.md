# Automação QA Roteiro PDV

Automação para validação de roteiros de teste de PDV integrado com Scanntech.

## Estrutura

```
automacao_scann/
├── input/                   ← coloque o roteiro_testes.xlsx aqui
├── output/                  ← resultado gerado aqui
├── src/
│   ├── main.py              ← entry point
│   ├── reader.py            ← leitura e detecção de blocos
│   ├── parser_items.py      ← parser de itens da venda
│   ├── payments.py          ← normalização de pagamentos
│   ├── validators.py        ← validações com Decimal
│   └── exporters.py         ← exportação para Excel
├── automacao_scann_colab.ipynb
├── requirements.txt
└── README.md
```

## Como rodar localmente

```bash
pip install -r requirements.txt
python src/main.py input/roteiro_testes.xlsx output/validacao_resultado.xlsx
```

## Como rodar no Google Colab

Abra o notebook `automacao_scann_colab.ipynb` diretamente pelo Colab:

[![Abrir no Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Miked0/automacao_scann/blob/main/automacao_scann_colab.ipynb)

## Status de validação

| Status | Significado |
|--------|-------------|
| `OK` | Caso validado sem divergências |
| `ALERTA` | Diferença ≤ 0,01 dentro da tolerância |
| `REVISAR` | Caso especial detectado (acréscimo, cancelamento, BIN) |
| `ERRO_PARSE` | Falha ao parsear itens |
| `ERRO_VALOR` | Subtotal/desconto/total com problema aritmético |
| `ERRO_PAGAMENTO` | Forma de pagamento não mapeada |

## Mapeamento de pagamentos

| Texto na planilha | codigoTipoPago |
|-------------------|----------------|
| Dinheiro / Efetivo | 9 |
| Cartão Crédito | 10 |
| Cheque | 11 |
| Vale | 12 |
| Cartão Débito | 13 |
| PIX / QR | 14 |
