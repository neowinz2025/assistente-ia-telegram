import os
import unittest
from parsers.text_parser import parse_telegram_text
from parsers.pdf_parser import parse_pdf_ticket
from utils.helpers import parse_currency, parse_date, clean_digits, format_phone

class TestParsers(unittest.TestCase):

    def test_helpers(self):
        self.assertEqual(clean_digits("123.456.789-00"), "12345678900")
        self.assertEqual(parse_currency("R$ 1.500,50"), 1500.50)
        self.assertEqual(parse_currency("1100,00"), 1100.00)
        self.assertEqual(parse_date("15/08/1990"), "1990-08-15")
        self.assertEqual(format_phone("11999887766"), "+5511999887766")

    def test_text_parser(self):
        raw_text = """
        Anexo - PDF da reserva

        Dados do cliente 
        Nome: Carlos Eduardo
        CPF: 123.456.789-00
        Data de Nascimento: 10/05/1985
        E-mail: carlos@exemplo.com
        Tel: 11988776655

        Dados do fornecedor 
        Nome: Latam Airlines
        CPF/CNPJ: 02.012.862/0001-60
        Tel: 1130001111

        Valor da venda: R$ 2.450,00
        Valor de custo: R$ 1.900,00
        """
        parsed = parse_telegram_text(raw_text)

        self.assertEqual(parsed["cliente"]["nome"], "Carlos Eduardo")
        self.assertEqual(parsed["cliente"]["cpf"], "12345678900")
        self.assertEqual(parsed["cliente"]["data_nascimento"], "1985-05-10")
        self.assertEqual(parsed["cliente"]["email"], "carlos@exemplo.com")
        self.assertEqual(parsed["cliente"]["telefone"], "+5511988776655")

        self.assertEqual(parsed["fornecedor"]["nome"], "Latam Airlines")
        self.assertEqual(parsed["fornecedor"]["cpf_cnpj"], "02012862000160")

        self.assertEqual(parsed["valor_venda"], 2450.0)
        self.assertEqual(parsed["valor_custo"], 1900.0)

if __name__ == "__main__":
    unittest.main()
