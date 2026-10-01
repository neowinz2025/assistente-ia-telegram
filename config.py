import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Config
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# IDDAS API Config
IDDAS_API_KEY = os.getenv("IDDAS_API_KEY", "")
IDDAS_BASE_URL = os.getenv("IDDAS_BASE_URL", "https://apiagencia.iddas.com.br/api/v1")

# Groq / xAI / OpenAI — API do LLM para extração de dados
GROK_API_KEY  = os.getenv("GROK_API_KEY", "")
GROK_MODEL    = os.getenv("GROK_MODEL", "llama-3.3-70b-versatile")
GROK_BASE_URL = os.getenv("GROK_BASE_URL", "https://api.groq.com/openai/v1")

# Default Account & Category IDs for Financial Entries (can be overridden by env)
DEFAULT_CONTA_ID              = int(os.getenv("IDDAS_DEFAULT_CONTA_ID", "1"))
DEFAULT_CATEGORIA_RECEITA_ID  = int(os.getenv("IDDAS_DEFAULT_CATEGORIA_RECEITA_ID", "1"))
DEFAULT_CATEGORIA_DESPESA_ID  = int(os.getenv("IDDAS_DEFAULT_CATEGORIA_DESPESA_ID", "1"))
DEFAULT_FORMA_PAGAMENTO_ID    = int(os.getenv("IDDAS_DEFAULT_FORMA_PAGAMENTO_ID", "1"))
DEFAULT_CANAL_VENDA_ID        = os.getenv("IDDAS_DEFAULT_CANAL_VENDA_ID", "1")
