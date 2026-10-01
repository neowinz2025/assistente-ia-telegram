import re
from typing import Dict, Any
from utils.helpers import clean_digits, parse_currency, parse_date, format_phone

def parse_telegram_text(text: str) -> Dict[str, Any]:
    """
    Extrai dados do cliente, fornecedor e valores a partir da mensagem de texto recebida no Telegram.
    
    Estrutura esperada:
    Dados do cliente
    Nome: ...
    CPF: ...
    Data de Nascimento: ...
    E-mail: ...
    Tel: ...
    
    Dados do fornecedor
    Nome: ...
    CPF/CNPJ: ...
    Tel: ...
    
    Valor da venda: ...
    Valor de custo: ...
    """
    result = {
        "cliente": {
            "nome": "",
            "cpf": "",
            "data_nascimento": "",
            "email": "",
            "telefone": ""
        },
        "fornecedor": {
            "nome": "",
            "cpf_cnpj": "",
            "telefone": ""
        },
        "valor_venda": 0.0,
        "valor_custo": 0.0,
        "forma_pagamento": ""
    }

    if not text:
        return result

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    current_section = None

    for i, line in enumerate(lines):
        line_lower = line.lower()

        # Identificação de Seções
        if "dados do cliente" in line_lower:
            current_section = "cliente"
            continue
        elif "dados do fornecedor" in line_lower:
            current_section = "fornecedor"
            continue
        elif "valor da venda" in line_lower:
            current_section = "valor_venda"
            # Se a própria linha contém o valor (ex: "Valor da venda: R$ 1500,00" ou "Valor da venda 1500")
            val = re.sub(r'(?i)valor\s+da\s+venda\s*[:\-]*', '', line).strip()
            if val:
                result["valor_venda"] = parse_currency(val)
            continue
        elif "valor de custo" in line_lower:
            current_section = "valor_custo"
            val = re.sub(r'(?i)valor\s+de\s+custo\s*[:\-]*', '', line).strip()
            if val:
                result["valor_custo"] = parse_currency(val)
            continue
        elif "forma de pagamento" in line_lower or "pagamento" in line_lower:
            current_section = "forma_pagamento"
            val = re.sub(r'(?i)(forma\s+de\s+)?pagamento\s*[:\-]*', '', line).strip()
            if val:
                result["forma_pagamento"] = val
            continue

        # Processamento por chave-valor na linha
        if ":" in line or "-" in line:
            # Separa chave e valor
            parts = re.split(r'[:\-]', line, maxsplit=1)
            key = parts[0].strip().lower()
            val = parts[1].strip() if len(parts) > 1 else ""

            if "forma" in key or "pagamento" in key:
                result["forma_pagamento"] = val

            if current_section == "cliente":
                if "nome" in key:
                    result["cliente"]["nome"] = val
                elif "cpf" in key:
                    result["cliente"]["cpf"] = clean_digits(val)
                elif "nascimento" in key or "data" in key:
                    result["cliente"]["data_nascimento"] = parse_date(val) or val
                elif "mail" in key:
                    result["cliente"]["email"] = val
                elif "tel" in key or "celular" in key or "fone" in key:
                    result["cliente"]["telefone"] = format_phone(val)

            elif current_section == "fornecedor":
                if "nome" in key:
                    result["fornecedor"]["nome"] = val
                elif "cpf" in key or "cnpj" in key:
                    result["fornecedor"]["cpf_cnpj"] = clean_digits(val)
                elif "tel" in key or "celular" in key or "fone" in key:
                    result["fornecedor"]["telefone"] = format_phone(val)

            elif current_section == "valor_venda" and not result["valor_venda"]:
                result["valor_venda"] = parse_currency(val)

            elif current_section == "valor_custo" and not result["valor_custo"]:
                result["valor_custo"] = parse_currency(val)

        else:
            # Se a linha não tem chave-valor explícito com `:` ou `-`
            # Verifica se é um valor numérico para valores de venda/custo se estivermos na seção correspondente
            if current_section == "valor_venda" and result["valor_venda"] == 0.0:
                result["valor_venda"] = parse_currency(line)
            elif current_section == "valor_custo" and result["valor_custo"] == 0.0:
                result["valor_custo"] = parse_currency(line)
            else:
                # Tentar extrair por padrão de conteúdo (Regex)
                # CPF
                if not result["cliente"]["cpf"] and re.search(r'\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b', line):
                    cpf_match = re.search(r'\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b', line)
                    if cpf_match:
                        if current_section == "fornecedor":
                            result["fornecedor"]["cpf_cnpj"] = clean_digits(cpf_match.group(0))
                        else:
                            result["cliente"]["cpf"] = clean_digits(cpf_match.group(0))

                # CNPJ
                elif not result["fornecedor"]["cpf_cnpj"] and re.search(r'\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b', line):
                    cnpj_match = re.search(r'\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b', line)
                    if cnpj_match:
                        result["fornecedor"]["cpf_cnpj"] = clean_digits(cnpj_match.group(0))

                # E-mail
                elif not result["cliente"]["email"] and "@" in line:
                    email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', line)
                    if email_match:
                        result["cliente"]["email"] = email_match.group(0)

                # Data
                elif not result["cliente"]["data_nascimento"] and parse_date(line):
                    result["cliente"]["data_nascimento"] = parse_date(line)

    # Fallback de busca global via Regex se algum campo ainda estiver em branco
    if not result["cliente"]["email"]:
        email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
        if email_match:
            result["cliente"]["email"] = email_match.group(0)

    if not result["cliente"]["cpf"]:
        cpf_match = re.search(r'(?i)cpf\s*[:\-]?\s*(\d{3}\.?\d{3}\.?\d{3}-?\d{2})', text)
        if cpf_match:
            result["cliente"]["cpf"] = clean_digits(cpf_match.group(1))

    return result
