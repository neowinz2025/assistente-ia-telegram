import re
from typing import Dict, Any, List
import pdfplumber
from pypdf import PdfReader
from utils.helpers import parse_date

# Tabela expandida de códigos IATA de aeroportos (Nacionais e Internacionais)
IATA_AIRPORTS = set([
    # Brasil
    "GRU", "CGH", "VCP", "GIG", "SDU", "BSB", "CNF", "POA", "CWB", "FLN", 
    "SSA", "REC", "FOR", "BEL", "MAO", "CGB", "GYN", "VIX", "MCZ", "NAT",
    "BVB", "RBR", "PVH", "SLZ", "THE", "AJU", "JPA", "MGF", "LDB", "UDI",
    "RAO", "SJP", "NVT", "IGU", "XAP", "IOS", "BPS", "PMW", "JDO", "PNZ",
    "STM", "MCP", "CXJ", "CPV", "IMP", "MOC", "VAL", "PET", "SFH", "CAC",
    # Internacional
    "MIA", "MCO", "JFK", "EWR", "LAX", "SFO", "ORD", "ATL", "IAD", "BOS",
    "LIS", "OPO", "MAD", "BCN", "CDG", "LHR", "AMS", "FRA", "MUC", "FCO",
    "EZE", "AEP", "MVD", "SCL", "LIM", "BOG", "ASU", "CUN", "PTY", "COR"
])

COMMON_EXCLUDED_WORDS = set([
    "AZUL", "LATAM", "STATUS", "CLASSE", "BAGAGEM", "PASSAGEM", "COMPRA",
    "BILHETE", "ORIGEM", "DESTINO", "ADULTO", "JANEIRO", "FEVEREIRO",
    "MARÇO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO", "SETEMBRO",
    "OUTUBRO", "NOVEMBRO", "DEZEMBRO", "TARIFA", "CABINE", "TICKET"
])

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
        try:
            reader = PdfReader(pdf_path)
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
        except Exception as e2:
            pass

    return full_text

def find_localizador(text: str) -> str:
    """
    Busca inteligente do Código Localizador / PNR (5 a 6 caracteres alfanuméricos).
    """
    if not text:
        return ""

    # Padrão 1: Rótulo explícito (ex: Localizador: ABCDEF, PNR: 123456, Código de reserva: XYZ123)
    pnr_patterns = [
        r'(?i)(?:localizador|código\s*(?:de)?\s*(?:reserva|confirmação)?|pnr|reserva|loc|booking\s*ref(?:erence)?|record\s*locator)\s*[:\-#\s]+([A-Z0-9]{5,6})\b',
        r'(?i)\b([A-Z0-9]{6})\b\s*(?:\(pnr\)|\(localizador\))'
    ]

    for pat in pnr_patterns:
        match = re.search(pat, text)
        if match:
            code = match.group(1).upper()
            if not code.isdigit() and code not in COMMON_EXCLUDED_WORDS:
                return code

    # Padrão 2: Busca por string isolada de 6 alfanuméricos perto de palavras chave
    lines = text.splitlines()
    for line in lines:
        line_upper = line.upper()
        if any(kw in line_upper for kw in ["RESERVA", "LOCALIZADOR", "PNR", "CÓDIGO", "CONFIRMAÇÃO"]):
            codes = re.findall(r'\b([A-Z0-9]{6})\b', line_upper)
            for c in codes:
                if not c.isdigit() and c not in COMMON_EXCLUDED_WORDS:
                    return c

    # Fallback: primeira sequência alfanumérica de 6 caracteres no texto que não seja palavra comum
    all_codes = re.findall(r'\b([A-Z0-9]{6})\b', text.upper())
    for c in all_codes:
        if not c.isdigit() and not c.isalpha() and c not in COMMON_EXCLUDED_WORDS:
            return c

    return ""

def parse_pdf_ticket(pdf_path: str) -> Dict[str, Any]:
    """
    Lê o arquivo PDF do bilhete aéreo e extrai todos os voos, trechos e conexões.
    """
    text = extract_text_from_pdf(pdf_path)

    result = {
        "localizador": find_localizador(text),
        "numero_compra": "",
        "companhia": "",
        "voos": [],
        "raw_text": text
    }

    if not text:
        return result

    # Identificação da Companhia Aérea
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

    # Regex de Códigos de Voos (ex: G3 1234, AD 4567, LA 3020, G31234, LA3020, 2Z 2234, TP 088)
    flight_pattern = re.compile(r'\b(G3|AD|LA|JJ|2Z|TP|AR|AA|DL|UA|AF|LH)\s*[-]?\s*(\d{3,4})\b', re.IGNORECASE)
    
    # Extração de datas do documento
    dates_found = []
    for d in re.findall(r'\b(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2}|\d{2}/\d{2})\b', text):
        parsed = parse_date(d)
        if parsed and parsed not in dates_found:
            dates_found.append(parsed)

    # Extração de horários (HH:MM)
    time_matches = [f"{t}:00" if len(t) == 5 else t for t in re.findall(r'\b([0-2]\d:[0-5]\d)\b', text)]

    # Análise de linhas/blocos do PDF para identificar conexões e trechos
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    segments = []
    current_flight = None

    for i, line in enumerate(lines):
        line_u = line.upper()
        flight_m = flight_pattern.search(line)

        if flight_m:
            code = f"{flight_m.group(1).upper()} {flight_m.group(2)}"
            
            # Procura por IATA na mesma linha ou no bloco de 3 linhas seguintes
            block_text = " ".join(lines[i:i+4]).upper()
            iatas_in_block = [m for m in re.findall(r'\b([A-Z]{3})\b', block_text) if m in IATA_AIRPORTS]

            origem = iatas_in_block[0] if len(iatas_in_block) >= 1 else "GRU"
            destino = iatas_in_block[1] if len(iatas_in_block) >= 2 else "GIG"

            # Se encontrou IATAs iguais (ex: GRU - GRU por engano), busca próxima IATA diferente
            if origem == destino and len(iatas_in_block) > 2:
                destino = iatas_in_block[2]

            # Datas e Horários no bloco
            dates_in_block = [parse_date(d) for d in re.findall(r'\b(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2}|\d{2}/\d{2})\b', block_text) if parse_date(d)]
            times_in_block = [f"{t}:00" if len(t) == 5 else t for t in re.findall(r'\b([0-2]\d:[0-5]\d)\b', block_text)]

            data_emb = dates_in_block[0] if dates_in_block else (dates_found[0] if dates_found else "")
            data_cheg = dates_in_block[1] if len(dates_in_block) > 1 else data_emb
            hora_emb = times_in_block[0] if times_in_block else "08:00:00"
            hora_cheg = times_in_block[1] if len(times_in_block) > 1 else "10:00:00"

            segments.append({
                "voo": code,
                "aeroporto_origem": origem,
                "aeroporto_destino": destino,
                "data_embarque": data_emb,
                "hora_embarque": hora_emb,
                "data_chegada": data_cheg,
                "hora_chegada": hora_cheg,
                "localizador": result["localizador"]
            })

    # Tratamento de Conexões e Tipo de Trecho (Ida, Volta, Conexão)
    if segments:
        first_orig = segments[0]["aeroporto_origem"]
        for idx, seg in enumerate(segments):
            if idx == 0:
                seg["tipo_trecho"] = "I"  # Ida
            elif seg["aeroporto_destino"] == first_orig or (idx > 0 and segments[idx-1]["aeroporto_destino"] == seg["aeroporto_origem"] and seg["data_embarque"] != segments[0]["data_embarque"]):
                seg["tipo_trecho"] = "V"  # Volta
            else:
                seg["tipo_trecho"] = "T"  # Trecho Interno / Conexão

        result["voos"] = segments

    else:
        # Fallback genérico se o PDF não tiver código de voo padrão visível
        all_iatas = [m for m in re.findall(r'\b([A-Z]{3})\b', text_upper) if m in IATA_AIRPORTS]
        if len(all_iatas) >= 2:
            origem = all_iatas[0]
            destino = all_iatas[1]
            data_emb = dates_found[0] if dates_found else ""
            hora_emb = time_matches[0] if time_matches else "08:00:00"
            hora_cheg = time_matches[1] if len(time_matches) > 1 else "10:00:00"

            result["voos"].append({
                "voo": "VOO 1000",
                "tipo_trecho": "I",
                "aeroporto_origem": origem,
                "aeroporto_destino": destino,
                "data_embarque": data_emb,
                "hora_embarque": hora_emb,
                "data_chegada": data_emb,
                "hora_chegada": hora_cheg,
                "localizador": result["localizador"]
            })

    return result
