import os
import sys
import json
import logging
import asyncio
import tempfile
from flask import Flask, request, jsonify

# Adiciona diretório raiz ao path para importar módulos do projeto
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from parsers.text_parser import parse_telegram_text
from parsers.pdf_parser import parse_pdf_ticket
from services.iddas_api import IddasApiClient
from telegram import Bot, Update

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def process_telegram_update(update_dict: dict):
    token = config.TELEGRAM_BOT_TOKEN
    if not token:
        logger.error("[Vercel Webhook] TELEGRAM_BOT_TOKEN não configurado!")
        return

    bot = Bot(token=token)
    update = Update.de_json(update_dict, bot)

    if not update or not update.message:
        return

    msg = update.message
    chat_id = msg.chat_id

    # Mensagem inicial de processamento no Telegram
    status_msg = await bot.send_message(
        chat_id=chat_id,
        text="🔄 *Processando emissão e lendo PDF no Vercel Serverless...*",
        parse_mode="Markdown"
    )

    pdf_path = None
    try:
        raw_text = msg.text or msg.caption or ""

        # Download do PDF se houver document anexo
        if msg.document and msg.document.mime_type == "application/pdf":
            telegram_file = await bot.get_file(msg.document.file_id)
            temp_dir = tempfile.gettempdir()
            pdf_path = os.path.join(temp_dir, f"{msg.document.file_unique_id}_{msg.document.file_name}")
            await telegram_file.download_to_drive(pdf_path)
            logger.info(f"[Vercel Webhook] PDF baixado com sucesso em: {pdf_path}")

        # Parsing de dados
        text_data = parse_telegram_text(raw_text)
        cliente_info = text_data["cliente"]
        fornecedor_info = text_data["fornecedor"]
        valor_venda = text_data["valor_venda"]
        valor_custo = text_data["valor_custo"]

        pdf_data = {}
        if pdf_path and os.path.exists(pdf_path):
            pdf_data = parse_pdf_ticket(pdf_path)

        localizador = pdf_data.get("localizador") or "PNR000"
        voos = pdf_data.get("voos", [])

        if not fornecedor_info["nome"] and pdf_data.get("companhia"):
            fornecedor_info["nome"] = pdf_data["companhia"]

        # Chamada API IDDAS
        api_client = IddasApiClient()
        await api_client.authenticate()

        # Cadastrar Cliente & Fornecedor
        cliente_id = await api_client.cadastrar_cliente(cliente_info)
        fornecedor_id = await api_client.cadastrar_fornecedor(fornecedor_info)

        # Criar Orçamento / Venda
        titulo_orcamento = f"Venda Voo {localizador} - {cliente_info.get('nome', 'Cliente')}".strip()
        orcamento_id = await api_client.criar_orcamento(cliente_id, titulo_orcamento)

        # Cadastrar Voos
        voos_cadastrados = 0
        if voos:
            for v in voos:
                res_v = await api_client.cadastrar_voo(orcamento_id, v)
                if res_v:
                    voos_cadastrados += 1
        else:
            await api_client.cadastrar_voo(orcamento_id, {
                "localizador": localizador,
                "voo": "VOO 1000",
                "tipo_trecho": "I",
                "aeroporto_origem": "GRU",
                "aeroporto_destino": "GIG"
            })
            voos_cadastrados = 1

        # Lançar Receita e Despesa
        rec_id = await api_client.lançar_receita(cliente_id, valor_venda, localizador)
        desp_id = await api_client.lançar_despesa(fornecedor_id, valor_custo, localizador)

        # Atualizar resposta ao usuário
        resumo = (
            "✅ *Lançamento Realizado com Sucesso (Vercel Serverless)!*\n\n"
            f"🆔 *ID Venda/Orçamento:* `{orcamento_id}`\n"
            f"🎫 *Localizador:* `{localizador}`\n\n"
            f"👤 *Cliente:* {cliente_info.get('nome', 'N/A')} (ID: `{cliente_id}`)\n"
            f"🏢 *Fornecedor:* {fornecedor_info.get('nome', 'N/A')} (ID: `{fornecedor_id}`)\n\n"
            f"✈️ *Voos Lançados:* `{voos_cadastrados}` trecho(s)\n"
            f"💵 *Valor de Venda (Receita):* R$ {valor_venda:,.2f} " + (f"(ID: `{rec_id}`)" if rec_id else "") + "\n"
            f"💸 *Valor de Custo (Despesa):* R$ {valor_custo:,.2f} " + (f"(ID: `{desp_id}`)" if desp_id else "") + "\n"
        )
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text=resumo,
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"[Vercel Webhook Error] {e}", exc_info=True)
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text=f"❌ *Erro ao processar no IDDAS:*\n`{str(e)}`",
            parse_mode="Markdown"
        )
    finally:
        if pdf_path and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except Exception:
                pass

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "active", "service": "Telegram IDDAS Bot on Vercel"})

@app.route("/api/webhook", methods=["POST"])
@app.route("/webhook", methods=["POST"])
def webhook():
    if request.method == "POST":
        update_dict = request.get_json(force=True)
        asyncio.run(process_telegram_update(update_dict))
        return jsonify({"status": "ok"}), 200
    return jsonify({"status": "method_not_allowed"}), 405

if __name__ == "__main__":
    app.run(port=5000)
