# tests/test_localizacao_cupom.py
"""
Testes unitários — localização de cupons (20 casos)
Cobre os 3 gargalos identificados na causa raiz.

Executar: pytest tests/test_localizacao_cupom.py -v
"""

import pytest
from src.test_runner import _norm, _extract_numero


# ----------------------------------------------------------------
# Grupo 1: FLOAT → string (gargalo principal)
# ----------------------------------------------------------------

class TestNorm:
    def test_float_60(self):
        assert _norm(6221.0) == "6221"

    def test_float_ticket(self):
        assert _norm(6232.0) == "6232"

    def test_int(self):
        assert _norm(6240) == "6240"

    def test_zeros_esquerda(self):
        assert _norm("006221") == "6221"

    def test_espacos(self):
        assert _norm(" 6221 ") == "6221"

    def test_sinal_negativo(self):
        assert _norm("-6221") == "6221"

    def test_str_ponto_zero(self):
        assert _norm("6221.0") == "6221"

    def test_none(self):
        assert _norm(None) == ""

    def test_vazio(self):
        assert _norm("") == ""

    def test_nan(self):
        assert _norm("nan") == ""

    def test_zero(self):
        assert _norm(0) == ""


# ----------------------------------------------------------------
# Grupo 2: Aliases de coluna
# ----------------------------------------------------------------

class TestExtractNumero:
    def test_n_grau_cupom(self):
        assert _extract_numero({"n° cupom": "6221"}) == "6221"

    def test_n_ord_cupom(self):
        assert _extract_numero({"nº cupom": "6221"}) == "6221"

    def test_n_grau_ticket(self):
        assert _extract_numero({"n° ticket": "6250"}) == "6250"

    def test_n_ord_ticket(self):
        assert _extract_numero({"nº ticket": "6251"}) == "6251"

    def test_ticket_maiuscula(self):
        """Cai na varredura dinâmica case-insensitive."""
        assert _extract_numero({"Ticket": "6260"}) == "6260"

    def test_num_cupon(self):
        assert _extract_numero({"num. cupon": "6240"}) == "6240"

    def test_cupon(self):
        assert _extract_numero({"cupon": "6260"}) == "6260"

    def test_ticketid(self):
        assert _extract_numero({"ticketid": "6270"}) == "6270"

    def test_float_em_n_ticket(self):
        assert _extract_numero({"n° ticket": 6221.0}) == "6221"

    def test_sem_falso_positivo(self):
        """Row complexo não deve confundir desconto/total com número."""
        row = {
            "etapa": "1",
            "tipo promo": "LLEVAPAGA",
            "desconto": 10.0,
            "total": 89.90,
            "n° cupom": 6221.0,
            "observacao": "ok",
        }
        assert _extract_numero(row) == "6221"
