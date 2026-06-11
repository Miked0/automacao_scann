# Scanntech QA Validator

Validador automatizado de cupons fiscais e promoções Scanntech.

## Instalação

```bash
pip install -r requirements.txt
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

## Estrutura dos Módulos

```
automacao_scann/
├── scanntech_qa_validator.py   # Orquestrador principal
├── requirements.txt
├── README.md
└── src/
    ├── __init__.py
    ├── file_loader.py          # M1 — Valida e carrega artefatos
    ├── audit_parser.py         # M2 — Indexa movimentos do Audit por nº cupom
    ├── coupon_pdf_parser.py    # M3 — Extrai cupons DANFE/NFC-e/SAT do PDF
    ├── promo_engine.py         # M4 — Motor de validação por tipo de promoção
    ├── test_runner.py          # M5 — Orquestra 10 checks por linha
    ├── result_writer.py        # M6 — Preenche colunas xlsx com fill verde/vermelho
    └── audit_logger.py         # M7 — Gera log JSON estruturado
```

## Fluxo de Execução

```
FileLoader
    ↓ workbook + audit_df + pdf_pages
AuditParser + CouponPDFParser
    ↓ índices por número de cupom
TestRunner (por linha do roteiro)
    ├── Check 1: Cupom localizado (SAT/ECF/NFCE ou fallback EAN)
    ├── Check 2: HTTP 200
    ├── Check 3: Cancelamento
    ├── Check 4: Total (tolerância ±R$0,05)
    ├── Check 5: Desconto (tolerância ±R$0,05)
    ├── Check 6: Meio de pagamento
    ├── Check 7: BIN (quando exigido)
    ├── Check 8: Promoção (dispatcher por tipo)
    ├── Check 9: Desconto manual indevido
    └── Check 10: Schema JSON mínimo
        ↓
ResultWriter → TEMPLATE_PREENCHIDO.xlsx (colunas R/S/T/U)
AuditLogger  → qa_audit_log.json
```

## Tipos de Promoção Suportados

| Tipo | Lógica |
|------|--------|
| `LLEVAPAGA` | `lotes × (trigger − paga) × preço_unit ≈ descuentoTotal` |
| `DESCUENTOVARIABLE` | `subtotal_promo × pct ≈ descuentoTotal`; sem qtd mínima → desconto zero |
| `PRECIOFIJO` | `lotes × preco_fixo ≈ valor cobrado nos itens participantes` |
| `ADICIONALREGALO` | `descuentoTotal > 0` quando presente esperado |
| `ADICIONALDESCUENTO` | `descuento_item / preco_item ≈ pct_promo ± 2%` |
| `DESCUENTOFIJO` | `descuentoTotal == valor_fixo` |

## Saídas

| Arquivo | Descrição |
|---------|----------|
| `TEMPLATE_PREENCHIDO.xlsx` | Roteiro com colunas R/S/T/U preenchidas (🟢 Ok / 🔴 Erro) |
| `qa_validation.log` | Log textual com timestamps (INFO/WARNING/ERROR) |
| `qa_audit_log.json` | Log estruturado por teste com todos os checks e detalhes |
