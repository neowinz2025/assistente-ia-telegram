import sys
import httpx
import config

def set_webhook(url: str):
    token = config.TELEGRAM_BOT_TOKEN
    if not token or token == "SEU_TELEGRAM_BOT_TOKEN_HERE":
        print("❌ Erro: TELEGRAM_BOT_TOKEN não foi configurado no .env!")
        return

    webhook_url = f"{url.rstrip('/')}/api/webhook"
    api_url = f"https://api.telegram.org/bot{token}/setWebhook"
    
    print(f"🔗 Configurando Webhook do Telegram para: {webhook_url}")
    resp = httpx.post(api_url, json={"url": webhook_url})
    
    if resp.status_code == 200:
        print("✅ Webhook configurado com sucesso!")
        print("Resposta do Telegram:", resp.json())
    else:
        print(f"❌ Erro ao configurar Webhook ({resp.status_code}): {resp.text}")

def delete_webhook():
    token = config.TELEGRAM_BOT_TOKEN
    if not token:
        print("❌ Erro: TELEGRAM_BOT_TOKEN não configurado no .env!")
        return

    api_url = f"https://api.telegram.org/bot{token}/deleteWebhook"
    resp = httpx.post(api_url)
    print("🗑️ Webhook removido! Resposta:", resp.json())

if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--delete":
            delete_webhook()
        else:
            set_webhook(arg)
    else:
        print("Uso:")
        print("  python set_webhook.py https://seu-app.vercel.app")
        print("  python set_webhook.py --delete")
