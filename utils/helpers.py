import re
from datetime import datetime
from typing import Optional

def clean_digits(value: str) -> str:
    """Remove todos os caracteres não numéricos de uma string."""
    if not value:
        return ""
    return re.sub(r'\D', '', value)

def parse_currency(value_str: str) -> float:
    """
    Converte strings monetárias como 'R$ 1.500,50', '1500,50', '1.500', '1500.50'
    para o tipo float.
    """
    if not value_str:
        return 0.0
    
    # Remove R$, espaços e caracteres inválidos mantendo apenas números, vírgula e ponto
    cleaned = re.sub(r'[^\d,\.]', '', value_str).strip()
    if not cleaned:
        return 0.0

    # Caso brasileiro: 1.500,50 -> 1500.50
    if ',' in cleaned and '.' in cleaned:
        cleaned = cleaned.replace('.', '').replace(',', '.')
    elif ',' in cleaned:
        cleaned = cleaned.replace(',', '.')

    try:
        return float(cleaned)
    except ValueError:
        return 0.0

def parse_date(date_str: str) -> Optional[str]:
    """
    Converte datas em formatos comuns ('DD/MM/YYYY', 'DD-MM-YYYY', 'YYYY-MM-DD')
    para o formato padronizado da API IDDAS: 'YYYY-MM-DD'.
    """
    if not date_str:
        return None

    date_str = date_str.strip()
    
    formats = [
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
        "%d/%m/%y",
        "%d-%m-%y"
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None

def format_phone(phone_str: str) -> str:
    """
    Normaliza número de telefone. Adiciona prefixo +55 se for número brasileiro simples.
    """
    digits = clean_digits(phone_str)
    if not digits:
        return ""
    if digits.startswith("55"):
        return f"+{digits}"
    if len(digits) in [10, 11]:
        return f"+55{digits}"
    return f"+{digits}"
