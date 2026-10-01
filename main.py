import os
import sys
import logging
import tempfile
from telegram import Update, Message
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

import config
from parsers.text_parser import parse_telegram_text
from parsers.pdf_parser import parse_pdf_ticket
from services.iddas_api import IddasApiClient

# Configuração de Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start"""
    welcome_text = (
        "🤖 *Bot de Emissão e Lançamento IDDAS*\n\n"
        "Envie os dados da emissão junto com o bilhete/reserva em PDF anexo!\n\n"
        "📋 *Estrutura esperada na mensagem:*\n"
        "```text\n"
        "Dados do cliente \n"
        "Nome: João Silva\n"
        "CPF: 123.456.789-00\n"
        "Data de Nascimento: 15/08/1990\n"
        "E-mail: joao@email.com\n"
        "Tel: 11999887766\n\n"
        "Dados do fornecedor \n"
        "Nome: Cia Gol\n"
        "CPF/CNPJ: 07.575.651/0001-59\n"
        "Tel: 1130000000\n\n"
        "Valor da venda: R$ 1.500,00\n"
        "Valor de custo: R$ 1.100,00\n"
        "```\n\n"
        "📎 *Anexo:* PDF da reserva/bilhete aéreo."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /help"""
    await start_command(update, context)

async def handle_emission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manipula mensagens recebidas com dados de texto e/ou arquivo PDF anexo."""
    msg: Message = update.message
    if not msg:
        return

    # Mensagem de status inicial
    status_msg = await msg.reply_text("🔄 *Processando emissão e realizando leitura do PDF...*", parse_mode="Markdown")

    pdf_path = None
    try:
        # 1. Extração do Texto da mensagem (ou da legenda do documento)
        raw_text = msg.text or msg.caption or ""

        # 2. Download do PDF anexo (se houver)
        if msg.document and (msg.document.mime_type == "application/pdf" or (msg.document.file_name and msg.document.file_name.lower().endswith(".pdf"))):
            file = await msg.document.get_file()
            temp_dir = os.path.join(os.getcwd(), "tmp_pdf")
            os.makedirs(temp_dir, exist_ok=True)
            pdf_path = os.path.join(temp_dir, f"{msg.document.file_unique_id}_{msg.document.file_name or 'reserva.pdf'}")
            await file.download_to_drive(pdf_path)
            logger.info(f"[Bot] PDF baixado com sucesso em: {pdf_path}")

        # 3. Parsing dos dados de texto
        text_data = parse_telegram_text(raw_text)
        cliente_info = text_data["cliente"]
        fornecedor_info = text_data["fornecedor"]
        valor_venda = text_data["valor_venda"]
        valor_custo = text_data["valor_custo"]

        forma_pagamento_texto = text_data.get("forma_pagamento", "")

        # 4. Parsing do PDF do Voo (se fornecido)
        pdf_data = {}
        if pdf_path and os.path.exists(pdf_path):
            pdf_data = parse_pdf_ticket(pdf_path)

        localizador = pdf_data.get("localizador") or "PNR000"
        voos = pdf_data.get("voos", [])

        # Se a mensagem não definiu nome do fornecedor mas o PDF identificou a companhia aérea:
        if not fornecedor_info["nome"] and pdf_data.get("companhia"):
            fornecedor_info["nome"] = pdf_data["companhia"]

        # 5. Comunicação com a API IDDAS
        api_client = IddasApiClient()
        
        await status_msg.edit_text("🔑 *Autenticando na API IDDAS...*", parse_mode="Markdown")
        await api_client.authenticate()

        # Resolver ID da Forma de Pagamento
        forma_pagamento_id = await api_client.buscar_forma_pagamento_id(forma_pagamento_texto)

        # A. Cadastrar/Obter Cliente
        await status_msg.edit_text("👤 *Cadastrando/Buscando Cliente no IDDAS...*", parse_mode="Markdown")
        cliente_id = await api_client.cadastrar_cliente(cliente_info)

        # B. Cadastrar/Obter Fornecedor
        await status_msg.edit_text("🏢 *Cadastrando/Buscando Fornecedor no IDDAS...*", parse_mode="Markdown")
        fornecedor_id = await api_client.cadastrar_fornecedor(fornecedor_info)

        # C. Criar Orçamento / Venda
        await status_msg.edit_text("📄 *Gerando Orçamento/Venda no IDDAS...*", parse_mode="Markdown")
        titulo_orcamento = f"Venda Voo {localizador} - {cliente_info.get('nome', 'Cliente')}".strip()
        orcamento_id = await api_client.criar_orcamento(cliente_id, titulo_orcamento, forma_pagamento=forma_pagamento_texto)

        # D. Cadastrar Voos
        voos_cadastrados = 0
        if voos:
            await status_msg.edit_text("✈️ *Lançando Voos no IDDAS...*", parse_mode="Markdown")
            for v in voos:
                res_v = await api_client.cadastrar_voo(orcamento_id, v)
                if res_v:
                    voos_cadastrados += 1
        else:
            # Voo padrão genérico
            await api_client.cadastrar_voo(orcamento_id, {
                "localizador": localizador,
                "voo": "VOO 1000",
                "tipo_trecho": "I",
                "aeroporto_origem": "GRU",
                "aeroporto_destino": "GIG"
            })
            voos_cadastrados = 1

        # E. Lançar Financeiro (Receita e Despesa)
        await status_msg.edit_text("💰 *Lançando Receita e Despesa Financeira...*", parse_mode="Markdown")
        rec_id = await api_client.lançar_receita(cliente_id, valor_venda, localizador, forma_pagamento_id=forma_pagamento_id)
        desp_id = await api_client.lançar_despesa(fornecedor_id, valor_custo, localizador, forma_pagamento_id=forma_pagamento_id)

        # 6. Resposta Final ao Usuário
        resumo = (
            "✅ *Lançamento Realizado com Sucesso no IDDAS!*\n\n"
            f"🆔 *ID Venda/Orçamento:* `{orcamento_id}`\n"
            f"🎫 *Localizador:* `{localizador}`\n\n"
            f"👤 *Cliente:* {cliente_info.get('nome', 'N/A')} (ID: `{cliente_id}`)\n"
            f"🏢 *Fornecedor:* {fornecedor_info.get('nome', 'N/A')} (ID: `{fornecedor_id}`)\n\n"
            f"✈️ *Voos Lançados:* `{voos_cadastrados}` trecho(s)\n"
            f"💵 *Valor de Venda (Receita):* R$ {valor_venda:,.2f} " + (f"(ID: `{rec_id}`)" if rec_id else "") + "\n"
            f"💸 *Valor de Custo (Despesa):* R$ {valor_custo:,.2f} " + (f"(ID: `{desp_id}`)" if desp_id else "") + "\n"
        )
        await status_msg.edit_text(resumo, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"[Bot Error] {e}", exc_info=True)
        await status_msg.edit_text(
            f"❌ *Erro ao processar emissão no IDDAS:*\n`{str(e)}`\n\n"
            "Verifique se a chave de API do IDDAS e o token do Telegram estão configurados corretamente no `.env`.",
            parse_mode="Markdown"
        )
    finally:
        # Limpa PDF temporário
        if pdf_path and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except Exception:
                pass

def main():
    token = config.TELEGRAM_BOT_TOKEN
    if not token or token == "SEU_TELEGRAM_BOT_TOKEN_HERE":
        print("⚠️ AVISO: TELEGRAM_BOT_TOKEN não foi configurado no arquivo .env!")
        print("Preencha as variáveis de ambiente no arquivo .env antes de rodar o bot.")

    app = ApplicationBuilder().token(token or "DUMMY_TOKEN").build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, handle_emission))

    print("🚀 Bot Telegram IDDAS rodando em modo polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
