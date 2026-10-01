"""
services/grok_parser.py
-----------------------
Usa a API do Grok (xAI) para extrair estruturalmente os dados do bilhete aéreo
e da mensagem de texto do Telegram, retornando um dicionário pronto para o IDDAS.

O Grok recebe:
  - Texto da mensagem Telegram (dados do cliente/fornecedor/valores)
  - Texto extraído do PDF do bilhete (voos, localizador)

E retorna um JSON estruturado com todos os campos necessários.
"""

import json
import logging
import re
from typing import Dict, Any, Optional

import httpx

import config

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Prompt do sistema enviado ao Grok
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Você é um assistente especialista em agências de viagem brasileiras.
Sua tarefa é extrair dados de bilhetes aéreos e mensagens de texto e retornar um JSON estruturado.

RETORNE APENAS O JSON, SEM TEXTO ADICIONAL, SEM MARKDOWN, SEM EXPLICAÇÕES.

O JSON deve ter EXATAMENTE esta estrutura:
{
  "cliente": {
    "nome": "Nome completo do passageiro",
    "cpf": "apenas dígitos, sem pontos ou traços",
    "data_nascimento": "YYYY-MM-DD ou vazio",
    "email": "email ou vazio",
    "telefone": "apenas dígitos ou vazio"
  },
  "fornecedor": {
    "nome": "Nome da companhia aérea ou consolidador (ex: Gol, Azul, Latam, TAP, VoePass)",
    "cpf_cnpj": "apenas dígitos ou vazio"
  },
  "valor_venda": 0.00,
  "valor_custo": 0.00,
  "forma_pagamento": "PIX, Cartão de Crédito, Boleto, Transferência, etc. ou vazio",
  "localizador": "código PNR/localizador de 5-6 caracteres alfanuméricos ou vazio",
  "voos": [
    {
      "voo": "código do voo ex: G3 1234 ou AD 4567 ou LA 3020",
      "aeroporto_origem": "código IATA 3 letras ex: GRU",
      "aeroporto_destino": "código IATA 3 letras ex: CGH",
      "data_embarque": "YYYY-MM-DD",
      "hora_embarque": "HH:MM:00",
      "data_chegada": "YYYY-MM-DD",
      "hora_chegada": "HH:MM:00",
      "tipo_trecho": "I para ida, V para volta, T para conexão/trecho interno"
    }
  ]
}

REGRAS IMPORTANTES:
- Para "tipo_trecho": o PRIMEIRO voo é sempre "I" (Ida). Se houver voos de volta (retornando ao aeroporto de origem), use "V". Conexões intermediárias (trecho entre dois pontos que não são origem/destino final) use "T".
- Para "localizador": é o código de reserva/PNR, geralmente 6 caracteres alfanuméricos como "ABC123" ou "XY89Z2". NÃO confunda com número do voo.
- Para CPF: extraia APENAS os dígitos (11 dígitos para CPF, 14 para CNPJ).
- Para datas: converta SEMPRE para formato YYYY-MM-DD.
- Para valores monetários: use ponto como separador decimal (ex: 1500.00).
- Se não encontrar um campo, deixe como string vazia "" ou 0.00 para valores numéricos.
- Para "forma_pagamento": extraia o método de pagamento conforme descrito (PIX, Cartão, Boleto, etc.)
"""

# ─────────────────────────────────────────────────────────────────────────────
# Função principal de extração via Grok
# ─────────────────────────────────────────────────────────────────────────────

async def extrair_dados_com_grok(
    texto_mensagem: str,
    texto_pdf: str = "",
    timeout: float = 30.0
) -> Dict[str, Any]:
    """
    Envia o texto da mensagem Telegram + texto do PDF para o Grok e retorna
    um dicionário estruturado com todos os campos necessários para o IDDAS.

    Parâmetros:
        texto_mensagem: Texto digitado pelo usuário no Telegram (dados cliente/fornecedor/valores)
        texto_pdf: Texto extraído do PDF do bilhete aéreo (voos, localizador)
        timeout: Timeout em segundos para a chamada à API

    Retorna:
        Dicionário estruturado com os campos do bilhete
    """
    if not config.GROK_API_KEY:
        raise Exception(
            "GROK_API_KEY não configurada! Adicione sua chave da xAI no arquivo .env:\n"
            "GROK_API_KEY=xai-SuaChaveAqui"
        )

    # Monta o prompt do usuário com as duas fontes de dados
    partes = []
    if texto_mensagem and texto_mensagem.strip():
        partes.append(f"=== DADOS DA MENSAGEM TELEGRAM ===\n{texto_mensagem.strip()}")
    if texto_pdf and texto_pdf.strip():
        # Limita o PDF a 6000 chars para não explodir o contexto
        pdf_truncado = texto_pdf.strip()[:6000]
        partes.append(f"=== TEXTO EXTRAÍDO DO PDF DO BILHETE ===\n{pdf_truncado}")

    if not partes:
        raise Exception("Nenhum dado foi fornecido (nem mensagem nem PDF).")

    user_prompt = "\n\n".join(partes) + "\n\nExtrai os dados e retorne o JSON estruturado."

    # Chamada à API xAI (compatível com OpenAI)
    headers = {
        "Authorization": f"Bearer {config.GROK_API_KEY}",
        "Content-Type": "application/json"
    }

    body = {
        "model": config.GROK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"}
    }

    logger.info(f"[Grok] Enviando requisição ao modelo {config.GROK_MODEL}...")

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{config.GROK_BASE_URL}/chat/completions",
            headers=headers,
            json=body
        )

    if resp.status_code != 200:
        raise Exception(
            f"Erro na API do Grok ({resp.status_code}): {resp.text[:500]}"
        )

    resp_json = resp.json()
    content = resp_json["choices"][0]["message"]["content"]
    logger.info(f"[Grok] Resposta recebida ({len(content)} chars)")
    logger.debug(f"[Grok] Conteúdo bruto: {content[:500]}")

    # Parse do JSON retornado pelo Grok
    parsed = _parse_grok_json(content)
    return parsed


def _parse_grok_json(content: str) -> Dict[str, Any]:
    """Faz o parse seguro do JSON retornado pelo Grok, com fallback robusto."""

    # Template de resultado vazio
    empty = {
        "cliente": {"nome": "", "cpf": "", "data_nascimento": "", "email": "", "telefone": ""},
        "fornecedor": {"nome": "", "cpf_cnpj": ""},
        "valor_venda": 0.0,
        "valor_custo": 0.0,
        "forma_pagamento": "",
        "localizador": "",
        "voos": []
    }

    try:
        # Tenta extrair JSON mesmo que venha com texto extra
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
        else:
            data = json.loads(content)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"[Grok] Falha ao parsear JSON: {e}\nConteúdo: {content[:300]}")
        return empty

    # Merge seguro com template (garante que todos os campos existam)
    result = empty.copy()

    # Cliente
    if isinstance(data.get("cliente"), dict):
        c = data["cliente"]
        result["cliente"] = {
            "nome":             str(c.get("nome", "") or ""),
            "cpf":              re.sub(r'\D', '', str(c.get("cpf", "") or "")),
            "data_nascimento":  str(c.get("data_nascimento", "") or ""),
            "email":            str(c.get("email", "") or ""),
            "telefone":         re.sub(r'\D', '', str(c.get("telefone", "") or ""))
        }

    # Fornecedor
    if isinstance(data.get("fornecedor"), dict):
        f = data["fornecedor"]
        result["fornecedor"] = {
            "nome":     str(f.get("nome", "") or ""),
            "cpf_cnpj": re.sub(r'\D', '', str(f.get("cpf_cnpj", "") or ""))
        }

    # Valores
    result["valor_venda"]     = _to_float(data.get("valor_venda", 0))
    result["valor_custo"]     = _to_float(data.get("valor_custo", 0))
    result["forma_pagamento"] = str(data.get("forma_pagamento", "") or "")
    result["localizador"]     = str(data.get("localizador", "") or "").upper().strip()

    # Voos
    voos_raw = data.get("voos", [])
    if isinstance(voos_raw, list):
        voos_ok = []
        for v in voos_raw:
            if not isinstance(v, dict):
                continue
            voo_entry = {
                "voo":               str(v.get("voo", "") or ""),
                "aeroporto_origem":  str(v.get("aeroporto_origem", "GRU") or "GRU").upper()[:3],
                "aeroporto_destino": str(v.get("aeroporto_destino", "GIG") or "GIG").upper()[:3],
                "data_embarque":     str(v.get("data_embarque", "") or ""),
                "hora_embarque":     str(v.get("hora_embarque", "08:00:00") or "08:00:00"),
                "data_chegada":      str(v.get("data_chegada", "") or ""),
                "hora_chegada":      str(v.get("hora_chegada", "10:00:00") or "10:00:00"),
                "tipo_trecho":       str(v.get("tipo_trecho", "I") or "I").upper(),
                "localizador":       result["localizador"]
            }
            # Valida tipo_trecho
            if voo_entry["tipo_trecho"] not in ("I", "V", "T"):
                voo_entry["tipo_trecho"] = "I"
            voos_ok.append(voo_entry)
        result["voos"] = voos_ok

    logger.info(
        f"[Grok] Dados extraídos: cliente={result['cliente']['nome']!r}, "
        f"fornecedor={result['fornecedor']['nome']!r}, "
        f"localizador={result['localizador']!r}, "
        f"voos={len(result['voos'])}, "
        f"venda=R${result['valor_venda']:.2f}, "
        f"custo=R${result['valor_custo']:.2f}"
    )
    return result


def _to_float(value) -> float:
    """Converte valor para float de forma segura."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # Remove R$, pontos de milhar e troca vírgula por ponto
        v = re.sub(r'[R$\s]', '', value)
        v = re.sub(r'\.(?=\d{3})', '', v)  # remove ponto de milhar
        v = v.replace(',', '.')
        try:
            return float(v)
        except ValueError:
            pass
    return 0.0
