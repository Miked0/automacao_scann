# Automação QA Roteiro PDV

Automação para validação de roteiros de teste de PDV integrado com Scanntech.

[![Abrir no Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Miked0/automacao_scann/blob/main/automacao_scann_colab.ipynb)

## Etapas de validação

| Etapa | Arquivos necessários | O que valida |
|-------|----------------------|--------------|
| **1** | Planilha `.xlsx` | Parse de itens, pagamento, subtotal/desconto/total |
| **2** | Planilha + JSON de venda | Cruza EANs, quantidades, total e descontos com o movimento |
| **3** | Planilha + JSON de venda + JSON de cupons | Adiciona validação de tipo de promo, limite, BIN e forma de pagamento |

## Como usar no Google Colab

1. Clique no badge acima para abrir o notebook
2. Execute as células em ordem
3. Na **Célula 3**, edite `ETAPA = 1`, `2` ou `3`
4. Na **Célula 4**, faça upload dos arquivos conforme a etapa:
   - Etapa 1: só a planilha
   - Etapa 2: planilha + JSON de venda
   - Etapa 3: planilha + JSON de venda + JSON de cupons
5. Execute a **Célula 5** para rodar a validação
6. Veja o resumo na **Célula 6** e baixe o resultado na **Célula 7**

## Estrutura do projeto

```
automacao_scann/
├── input/                   ← arquivos de entrada (planilha, JSONs)
├── output/                  ← resultado gerado
├── src/
│   ├── main.py              ← entry point
│   ├── reader.py            ← leitura e detecção de blocos
│   ├── parser_items.py      ← parser de itens da venda
│   ├── payments.py          ← normalização de pagamentos
│   ├── validators.py        ← validações com Decimal
│   └── exporters.py         ← exportação para Excel (3 abas)
├── automacao_scann_colab.ipynb
├── requirements.txt
└── README.md
```

## Status de validação

| Status | Significado |
|--------|-------------|
| `OK` | Caso validado sem divergências |
| `ALERTA` | Diferença ≤ 0,01 dentro da tolerância |
| `REVISAR` | Caso especial detectado (acréscimo, cancelamento, BIN) |
| `ERRO_PARSE` | Falha ao parsear itens |
| `ERRO_VALOR` | Subtotal/desconto/total com problema aritmético |
| `ERRO_PAGAMENTO` | Forma de pagamento não mapeada |
| `DIVERGENCIA_JSON` | Diferença encontrada ao cruzar com o JSON de venda |
| `DIVERGENCIA_CUPON` | Tipo de promoção diverge do cupão consultado |
| `SEM_MATCH` | Número do teste não encontrado no JSON |

## Mapeamento de pagamentos

| Texto na planilha | codigoTipoPago |
|-------------------|----------------|
| Dinheiro / Efetivo | 9 |
| Cartão Crédito | 10 |
| Cheque | 11 |
| Vale | 12 |
| Cartão Débito | 13 |
| PIX / QR | 14 |
