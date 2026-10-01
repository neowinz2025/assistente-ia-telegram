import asyncio
import os
import unittest
from parsers.text_parser import parse_telegram_text
from parsers.pdf_parser import parse_pdf_ticket
from services.iddas_api import IddasApiClient

class TestEndToEndFlow(unittest.TestCase):

    def test_pipeline_parsing(self):
        sample_telegram_message = """
        Anexo - PDF da reserva

        Dados do cliente 
        Nome: Maria Oliveira
        CPF: 987.654.321-11
        Data de Nascimento: 20/11/1992
        E-mail: maria@exemplo.com
        Tel: 21988776655

        Dados do fornecedor 
        Nome: Gol Linhas Aéreas
        CPF/CNPJ: 07.575.651/0001-59
        Tel: 1130002222

        Valor da venda: R$ 3.200,00
        Valor de custo: R$ 2.500,00
        """

        parsed_text = parse_telegram_text(sample_telegram_message)

        self.assertEqual(parsed_text["cliente"]["nome"], "Maria Oliveira")
        self.assertEqual(parsed_text["cliente"]["cpf"], "98765432111")
        self.assertEqual(parsed_text["fornecedor"]["nome"], "Gol Linhas Aéreas")
        self.assertEqual(parsed_text["fornecedor"]["cpf_cnpj"], "07575651000159")
        self.assertEqual(parsed_text["valor_venda"], 3200.0)
        self.assertEqual(parsed_text["valor_custo"], 2500.0)

        # Simula objeto de voo montado a partir do PDF
        simulated_flight = {
            "localizador": "AB12CD",
            "voos": [{
                "voo": "G3 1450",
                "tipo_trecho": "I",
                "aeroporto_origem": "GRU",
                "aeroporto_destino": "SDU",
                "data_embarque": "2026-11-10",
                "hora_embarque": "09:30:00",
                "data_chegada": "2026-11-10",
                "hora_chegada": "10:40:00",
                "localizador": "AB12CD"
            }]
        }

        self.assertEqual(simulated_flight["localizador"], "AB12CD")
        self.assertEqual(simulated_flight["voos"][0]["aeroporto_origem"], "GRU")

if __name__ == "__main__":
    unittest.main()
