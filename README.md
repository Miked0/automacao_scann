# 🧾 Scanntech QA Validator

Validador automatizado de cupons fiscais e promoções Scanntech.

---

## Instalação

```bash
pip install -r requirements.txt
```

---

## Uso

```bash
python validador_qa_scanntech.py \
  --roteiro  "TEMPLATE_COM_BIN_NOVO.xlsx" \
  --audit    "export_tickets_audit_companyId-200056.xlsx" \
  --pdf      "ilovepdf_merged-1-2.pdf" \
  --output   "TEMPLATE_PREENCHIDO.xlsx" \
  --log      "qa_audit_log.json"
```

O parâmetro `--json-dir` é opcional e aponta para um diretório com JSONs de venda avulsos.

---

## Estrutura dos Módulos

```
automacao_scann/
├── validador_qa_scanntech.py      # Orquestrador principal
├── requirements.txt
├── README.md
├── automacao_scann_colab.ipynb    # Notebook Google Colab
└── src/
    ├── __init__.py
    ├── carregador_arquivos.py      # M1 — Valida e carrega artefatos (xlsx, pdf, json)
    ├── processador_auditoria.py    # M2 — Indexa movimentos do Audit por nº cupom
    ├── extrator_cupom_pdf.py       # M3 — Extrai cupons DANFE/NFC-e/SAT do PDF
    ├── motor_promocoes.py          # M4 — Motor de validação por tipo de promoção
    ├── executor_testes.py          # M5 — Orquestra 10 checks por linha do roteiro
    ├── gravador_resultados.py      # M6 — Preenche colunas xlsx com fill verde/vermelho
    ├── registrador_auditoria.py    # M7 — Gera log JSON estruturado
    ├── modelos.py                  # Dataclasses compartilhadas (ResultadoTeste, etc.)
    ├── validadores.py              # Funções auxiliares de validação
    ├── pagamentos.py               # Lógica de meios de pagamento e BIN
    └── processador_itens.py        # Extração e normalização de itens do cupom
```

---

## Fluxo de Execução

```
CarregadorArquivos
    ↓ workbook + audit_df + pdf_paginas
ProcessadorAuditoria + CouponPDFParser
    ↓ índices por número de cupom
ExecutorTestes (por linha do roteiro)
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
GravadorResultados → TEMPLATE_PREENCHIDO.xlsx (colunas R/S/T/U)
RegistradorAuditoria  → qa_audit_log.json
```

---

## Tipos de Promoção Suportados

| Tipo | Lógica |
|------|--------|
| `LLEVAPAGA` | `lotes × (trigger − paga) × preço_unit ≈ descuentoTotal` |
| `DESCUENTOVARIABLE` | `subtotal_promo × pct ≈ descuentoTotal`; sem qtd mínima → desconto zero |
| `PRECIOFIJO` | `lotes × preco_fixo ≈ valor cobrado nos itens participantes` |
| `ADICIONALREGALO` | `descuentoTotal > 0` quando presente esperado |
| `ADICIONALDESCUENTO` | `descuento_item / preco_item ≈ pct_promo ± 2%` |
| `DESCUENTOFIJO` | `descuentoTotal == valor_fixo` |

---

## Saídas

| Arquivo | Descrição |
|---------|-----------|
| `TEMPLATE_PREENCHIDO.xlsx` | Roteiro com colunas R/S/T/U preenchidas (🟢 Ok / 🔴 Erro) |
| `qa_validation.log` | Log textual com timestamps (INFO/WARNING/ERROR) |
| `qa_audit_log.json` | Log estruturado por teste com todos os checks e detalhes |

---

## Execução via Google Colab

Abra o notebook `automacao_scann_colab.ipynb` no Google Colab e execute as células em ordem:

| Etapa | O que faz |
|-------|-----------|
| 1️⃣ Dependências | Instala libs e clona o repositório |
| 2️⃣ Upload | Faz upload dos 3 arquivos de entrada |
| 3️⃣ Detecção | Detecta arquivos e valida nomes automaticamente |
| 4️⃣ Execução | Roda o validador completo |
| 5️⃣ Resumo | Exibe relatório de resultados por check |
| 6️⃣ Download | Baixa o TEMPLATE preenchido + logs |

---

## Requisitos

- Python 3.9+
- `openpyxl >= 3.1.2`
- `pandas >= 2.0.0`
- `pdfplumber >= 0.10.0`
