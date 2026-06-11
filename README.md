# 🧪 Scanntech QA — Automação de Validação de Roteiro PDV

Automação em Python para validar roteiros de teste de integração entre PDVs parceiros e a API de sellout da Scanntech.

## 📌 Escopo atual

| Etapa | Status | O que valida |
|-------|--------|--------------|
| **Etapa 1** | ✅ Implementada | Vendas simples, cancelamentos, desconto/acréscimo por operador, multi-pagamento, item pesável, fechamento POS |
| **Etapa 2** | 🟡 Em desenvolvimento | Promoções (LLEVAPAGA, DESCUENTO_VARIABLE, PRECIO_FIJO) + limite por promoção + item cancelado |
| **Etapa 3** | 🟡 Em desenvolvimento | DESCUENTO_FIJO, ADICIONAL_DESCUENTO, ADICIONAL_REGALO + validação por BIN e tipo de pagamento |

## 📂 Estrutura do projeto

```
automacao_scann/
├── src/
│   ├── main.py            # Entry point (CLI)
│   ├── reader.py          # Leitura e parse da planilha do roteiro
│   ├── audit_parser.py    # Indexação do export Audit da API
│   ├── coupon_pdf_parser.py # Extração de cupons fiscais (DANFE/NFC-e/SAT)
│   ├── validators.py      # Checks: total, desconto, pagamento, EAN
│   ├── promo_engine.py    # Motor de validação por tipo de promoção
│   ├── payments.py        # Normalização de meios de pagamento e BIN
│   ├── parser_items.py    # Parse de EANs e quantidades da planilha
│   ├── models.py          # Dataclasses de TestCase e ValidationResult
│   ├── result_writer.py   # Preenchimento das colunas R, S, T, U
│   ├── exporters.py       # Exportação do resultado para Excel
│   ├── audit_logger.py    # Log estruturado JSON + log textual
│   └── __init__.py
├── automacao_scann_colab.ipynb  # ⭐ Notebook Google Colab (Etapa 1)
├── requirements.txt
└── .gitignore
```

## ▶️ Executar no Google Colab

Abra o notebook e execute as células na ordem:

[![Abrir no Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/drive/1zOaSFWIugNP9Tz6GREaJQCMA6bSGIpB8)

### Arquivos necessários para a Etapa 1

| Arquivo | Formato | Obrigatório |
|---------|---------|-------------|
| Planilha do roteiro | `.xlsx` (TEMPLATE_COM_BIN_NOVO) | ✅ |
| Export Audit da API | `.xlsx` (`export_tickets_audit_companyId-*`) | ✅ |
| PDF de cupons fiscais | `.pdf` | Opcional na E1 |

## 💻 Executar localmente

```bash
# Instalar dependências
pip install -r requirements.txt

# Rodar validação
python src/main.py caminho/TEMPLATE.xlsx caminho/resultado_saida.xlsx
```

## 📦 Dependências

```
pandas
openpyxl
pdfplumber
```

## 🎯 Saída

O script gera um arquivo Excel com as colunas de resultado preenchidas:
- **status_final** — `OK`, `ALERTA` ou `ERRO`
- **motivo_status** — justificativa objetiva em caso de ERRO
- **alertas** — observações adicionais
- Cruzamento com Audit: `audit_total`, `audit_diff_total`, `audit_total_ok`
