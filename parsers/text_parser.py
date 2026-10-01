import re
from typing import Dict, Any
from utils.helpers import clean_digits, parse_currency, parse_date, format_phone


def _extrair_valor_da_linha(linha: str, prefixo_regex: str) -> str:
    """Remove o prefixo de uma linha e retorna o valor restante."""
    return re.sub(prefixo_regex, '', linha, flags=re.IGNORECASE).strip()


def parse_telegram_text(text: str) -> Dict[str, Any]:
    """
    Extrai dados do cliente, fornecedor e valores a partir da mensagem de texto recebida no Telegram.

    Estrutura esperada (flexível, case-insensitive):
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
    Forma de pagamento: ...
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

    for line in lines:
        ll = line.lower()

        # ── Detecção de Seções ──────────────────────────────────────────────
        if re.search(r'dados\s+do\s+cliente', ll):
            current_section = "cliente"
            continue
        if re.search(r'dados\s+do\s+fornecedor', ll):
            current_section = "fornecedor"
            continue

        # Valor da venda (verifica primeiro para não cair no "pagamento" abaixo)
        if re.search(r'valor\s+da\s+venda', ll):
            val = _extrair_valor_da_linha(line, r'valor\s+da\s+venda\s*[:\-]?\s*')
            if val:
                result["valor_venda"] = parse_currency(val)
            current_section = "valor_venda"
            continue

        # Valor de custo
        if re.search(r'valor\s+de\s+custo', ll):
            val = _extrair_valor_da_linha(line, r'valor\s+de\s+custo\s*[:\-]?\s*')
            if val:
                result["valor_custo"] = parse_currency(val)
            current_section = "valor_custo"
            continue

        # Forma de pagamento (após checar valor_venda e valor_custo!)
        if re.search(r'forma\s+de\s+pagamento|forma\s+pgto', ll):
            val = _extrair_valor_da_linha(line, r'forma\s+(de\s+)?pagamento\s*[:\-]?\s*|forma\s+pgto\s*[:\-]?\s*')
            if val:
                result["forma_pagamento"] = val
            current_section = "forma_pagamento"
            continue

        # ── Processamento das Linhas por Seção ──────────────────────────────
        # Usa apenas ":" como separador para evitar quebrar nomes/valores com "-"
        if ":" in line:
            parts = line.split(":", 1)
            key = parts[0].strip().lower()
            val = parts[1].strip()

            # Qualquer seção pode ter forma de pagamento inline com ":"
            if re.search(r'forma.*(pag|pgto)', key):
                result["forma_pagamento"] = val
                continue

            if current_section == "cliente":
                if re.search(r'\bnome\b', key):
                    result["cliente"]["nome"] = val
                elif re.search(r'\bcpf\b', key):
                    result["cliente"]["cpf"] = clean_digits(val)
                elif re.search(r'nascimento|data.*nasc', key):
                    result["cliente"]["data_nascimento"] = parse_date(val) or val
                elif re.search(r'e.?mail|email', key):
                    result["cliente"]["email"] = val
                elif re.search(r'tel|fone|celular|whatsapp', key):
                    result["cliente"]["telefone"] = format_phone(val)

            elif current_section == "fornecedor":
                if re.search(r'\bnome\b', key):
                    result["fornecedor"]["nome"] = val
                elif re.search(r'cpf|cnpj', key):
                    result["fornecedor"]["cpf_cnpj"] = clean_digits(val)
                elif re.search(r'tel|fone|celular|whatsapp', key):
                    result["fornecedor"]["telefone"] = format_phone(val)

            elif current_section == "valor_venda" and not result["valor_venda"]:
                result["valor_venda"] = parse_currency(val)

            elif current_section == "valor_custo" and not result["valor_custo"]:
                result["valor_custo"] = parse_currency(val)

        else:
            # Linha sem ":" – tenta como valor puro se estiver dentro de seção financeira
            if current_section == "valor_venda" and not result["valor_venda"]:
                v = parse_currency(line)
                if v > 0:
                    result["valor_venda"] = v
            elif current_section == "valor_custo" and not result["valor_custo"]:
                v = parse_currency(line)
                if v > 0:
                    result["valor_custo"] = v

    # ── Fallbacks globais via Regex ─────────────────────────────────────────
    # CPF do cliente
    if not result["cliente"]["cpf"]:
        m = re.search(r'(?i)cpf\s*[:\-]?\s*(\d[\d.\-]+)', text)
        if m:
            result["cliente"]["cpf"] = clean_digits(m.group(1))

    # CPF/CNPJ do fornecedor
    if not result["fornecedor"]["cpf_cnpj"]:
        m = re.search(r'(?i)cnpj\s*[:\-]?\s*([\d.\-/]+)', text)
        if m:
            result["fornecedor"]["cpf_cnpj"] = clean_digits(m.group(1))

    # E-mail
    if not result["cliente"]["email"]:
        m = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', text)
        if m:
            result["cliente"]["email"] = m.group(0)

    return result
