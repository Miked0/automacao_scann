# Scanntech QA Validator

Automação de validação de roteiros QA para promoções Scanntech.
Processa TEMPLATE xlsx + Export Audit + PDF de cupons e preenche automaticamente as colunas de resultado.

## Arquitetura — 7 Módulos

| # | Módulo | Responsabilidade |
|---|--------|------------------|
| 1 | `FileLoader` | Valida existência e carrega todos os artefatos |
| 2 | `AuditParser` | Indexa movimentos do Audit pelo nº cupom |
| 3 | `CouponPDFParser` | Extrai cupons fiscais (DANFE/NFC-e/SAT) do PDF |
| 4 | `PromoEngine` | Motor de validação por tipo de promoção |
| 5 | `TestRunner` | Orquestra a validação linha a linha do roteiro |
| 6 | `ResultWriter` | Preenche colunas de resultado + salva xlsx |
| 7 | `AuditLogger` | Gera log JSON estruturado de cada check |

## Instalação

```bash
pip install openpyxl pandas pdfplumber
```

## Uso

```bash
python scanntech_qa_validator.py \
  --roteiro  "TEMPLATE_COM_BIN_NOVO.xlsx" \
  --audit    "export_tickets_audit_companyId-200056.xlsx" \
  --pdf      "ilovepdf_merged-1-2.pdf" \
  --output   "TEMPLATE_PREENCHIDO.xlsx" \
  --log      "qa_audit_log.json"
```

O parâmetro `--json-dir` é opcional e aponta para um diretório com JSONs de venda avulsos.

## Fluxo de Execução

```
FileLoader → AuditParser → CouponPDFParser → PromoEngine
                                              ↓
                                          TestRunner  ← (10 checks por linha)
                                              ↓
                              ResultWriter + AuditLogger
```

## Checks por Linha do Roteiro

1. **Cupom localizado** — por nº SAT/ECF/NFCE ou fallback por EANs
2. **HTTP 200** — Status code = 200 no Audit
3. **Cancelamento** — `cancelacion` true/false conforme observação
4. **Total** — `|mov.total − roteiro.total| ≤ R$0,05`
5. **Desconto** — `|mov.descuentoTotal − roteiro.desconto| ≤ R$0,05`
6. **Meio de pagamento** — `codigoTipoPago` mapeado
7. **BIN** — valida presença quando exigido
8. **Promoção** — dispatcher por tipo (LLEVAPAGA, DESCUENTOVARIABLE, etc.)
9. **Desconto manual indevido** — rejeita desconto adicional quando proibido
10. **Schema JSON mínimo** — campos `total`, `numero`, `detalles`, `pagos`

## Tipos de Promoção Suportados

| Tipo | Lógica |
|------|--------|
| `LLEVAPAGA` | `lotes × (trigger − paga) × preço_unit` vs `descuentoTotal` |
| `DESCUENTOVARIABLE` | `subtotal_promo × pct` vs `descuentoTotal` |
| `PRECIOFIJO` | `lotes × preco_fixo` vs valor cobrado nos itens |
| `ADICIONALREGALO` | `descuentoTotal > 0` quando presente esperado |
| `ADICIONALDESCUENTO` | `descuento_item / preco_item ≈ pct_promo ± 2%` |
| `DESCUENTOFIJO` | `descuentoTotal == valor_fixo ± R$0,05` |

## Saídas

- **TEMPLATE_PREENCHIDO.xlsx** — Roteiro com colunas R/S/T preenchidas (Ok/Erro) e coluna U com justificativas
- **qa_validation.log** — Log textual com timestamps
- **qa_audit_log.json** — Log estruturado por teste

## Estrutura do Projeto

```
.
├── scanntech_qa_validator.py   ← Ponto de entrada CLI
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── models.py               ← Dataclasses compartilhadas
│   ├── file_loader.py          ← M1
│   ├── audit_parser.py         ← M2
│   ├── coupon_pdf_parser.py    ← M3
│   ├── promo_engine.py         ← M4
│   ├── test_runner.py          ← M5
│   ├── result_writer.py        ← M6
│   └── audit_logger.py         ← M7
```
