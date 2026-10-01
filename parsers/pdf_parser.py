import re
from typing import Dict, Any, List
import pdfplumber
from pypdf import PdfReader
from utils.helpers import parse_date

# Tabela simplificada de mapeamento IATA de aeroportos brasileiros mais comuns
IATA_AIRPORTS = [
    "GRU", "CGH", "VCP", "GIG", "SDU", "BSB", "CNF", "POA", "CWB", "FLN", 
    "SSA", "REC", "FOR", "BEL", "MAO", "CGB", "GYN", "VIX", "MCZ", "NAT",
    "BVB", "RBR", "PVH", "SLZ", "THE", "AJU", "JPA", "MGF", "LDB", "UDI"
]

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extrai todo o texto do PDF usando pdfplumber com fallback para pypdf."""
    full_text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
    except Exception as e:
        print(f"[PDF Parser] Aviso: pdfplumber falhou ({e}), tentando pypdf...")
        try:
            reader = PdfReader(pdf_path)
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
        except Exception as e2:
            print(f"[PDF Parser] Erro ao extrair texto via pypdf: {e2}")

    return full_text

def parse_pdf_ticket(pdf_path: str) -> Dict[str, Any]:
    """
    Lê o arquivo PDF do bilhete aéreo e retorna os dados estruturados do voo.
    """
    text = extract_text_from_pdf(pdf_path)
    
    result = {
        "localizador": "",
        "numero_compra": "",
        "companhia": "",
        "voos": [],
        "raw_text": text
    }

    if not text:
        return result

    # 1. Localizador / PNR (6 caracteres alfanuméricos)
    pnr_match = re.search(r'(?i)(?:localizador|código\s+de\s+reserva|pnr|reserva)\s*[:\-]?\s*([A-Z0-9]{6})\b', text)
    if pnr_match:
        result["localizador"] = pnr_match.group(1).upper()
    else:
        # Padrão secundário: isolado após palavra "Código"
        pnr_match2 = re.search(r'\b([A-Z0-9]{6})\b', text)
        # Filtra se for uma palavra comum de 6 letras
        if pnr_match2 and not pnr_match2.group(1).isalpha():
            result["localizador"] = pnr_match2.group(1).upper()

    # 2. Identificação da Companhia Aérea
    text_upper = text.upper()
    if "GOL" in text_upper:
        result["companhia"] = "Gol"
    elif "AZUL" in text_upper:
        result["companhia"] = "Azul"
    elif "LATAM" in text_upper:
        result["companhia"] = "Latam"
    elif "TAP" in text_upper:
        result["companhia"] = "TAP"
    elif "VOEPASS" in text_upper or "PASSAREDO" in text_upper:
        result["companhia"] = "VoePass"

    # 3. Busca de Voos (ex: G3 1234, AD 4567, LA 3020, G3-1234, LA3020)
    flight_pattern = re.compile(r'\b(G3|AD|LA|JJ|2Z|TP|AR|AA|DL|UA|AF|LH)\s*[-]?\s*(\d{3,4})\b', re.IGNORECASE)
    flight_matches = flight_pattern.findall(text)

    # 4. Busca por códigos IATA de Origem e Destino
    iata_pattern = re.compile(r'\b([A-Z]{3})\b')
    raw_iatas = [m for m in iata_pattern.findall(text_upper) if m in IATA_AIRPORTS]

    # 5. Busca por Datas (DD/MM/YYYY ou YYYY-MM-DD ou DD/MM)
    dates_found = []
    date_matches = re.findall(r'\b(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2}|\d{2}/\d{2})\b', text)
    for d in date_matches:
        parsed = parse_date(d)
        if parsed and parsed not in dates_found:
            dates_found.append(parsed)

    # 6. Busca por Horários (HH:MM)
    time_matches = re.findall(r'\b([0-2]\d:[0-5]\d)\b', text)

    # Construção de Trechos de Voo
    if flight_matches:
        for idx, fm in enumerate(flight_matches):
            flight_num = f"{fm[0].upper()} {fm[1]}"
            origem = raw_iatas[idx * 2] if len(raw_iatas) > idx * 2 else (raw_iatas[0] if raw_iatas else "GRU")
            destino = raw_iatas[idx * 2 + 1] if len(raw_iatas) > idx * 2 + 1 else (raw_iatas[1] if len(raw_iatas) > 1 else "GIG")
            data_emb = dates_found[idx] if len(dates_found) > idx else (dates_found[0] if dates_found else "")
            hora_emb = time_matches[idx * 2] if len(time_matches) > idx * 2 else "08:00"
            hora_cheg = time_matches[idx * 2 + 1] if len(time_matches) > idx * 2 + 1 else "10:00"

            result["voos"].append({
                "voo": flight_num,
                "tipo_trecho": "I" if idx == 0 else "V",
                "aeroporto_origem": origem,
                "aeroporto_destino": destino,
                "data_embarque": data_emb,
                "hora_embarque": f"{hora_emb}:00" if len(hora_emb) == 5 else hora_emb,
                "data_chegada": data_emb,
                "hora_chegada": f"{hora_cheg}:00" if len(hora_cheg) == 5 else hora_cheg,
                "localizador": result["localizador"]
            })
    else:
        # Se não encontrou código de voo específico por regex, cria um trecho genérico baseado nas IATAs e datas encontradas
        if raw_iatas and len(raw_iatas) >= 2:
            origem = raw_iatas[0]
            destino = raw_iatas[1]
            data_emb = dates_found[0] if dates_found else ""
            hora_emb = time_matches[0] if time_matches else "08:00"
            hora_cheg = time_matches[1] if len(time_matches) > 1 else "10:00"

            result["voos"].append({
                "voo": "VOO 1000",
                "tipo_trecho": "I",
                "aeroporto_origem": origem,
                "aeroporto_destino": destino,
                "data_embarque": data_emb,
                "hora_embarque": f"{hora_emb}:00" if len(hora_emb) == 5 else hora_emb,
                "data_chegada": data_emb,
                "hora_chegada": f"{hora_cheg}:00" if len(hora_cheg) == 5 else hora_cheg,
                "localizador": result["localizador"]
            })

    return result
