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
from services.grok_parser import extrair_dados_com_grok
from services.iddas_api import IddasApiClient

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ─── Extração de texto do PDF ────────────────────────────────────────────────
def extrair_texto_pdf(pdf_path: str) -> str:
    """Extrai texto bruto do PDF usando pdfplumber com fallback pypdf."""
    texto = ""
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            for p in pdf.pages:
                t = p.extract_text()
                if t:
                    texto += t + "\n"
    except Exception as e:
        logger.warning(f"[PDF] pdfplumber falhou: {e}")
        try:
            from pypdf import PdfReader
            reader = PdfReader(pdf_path)
            for p in reader.pages:
                t = p.extract_text()
                if t:
                    texto += t + "\n"
        except Exception as e2:
            logger.error(f"[PDF] pypdf também falhou: {e2}")
    return texto


# ─── Comandos ────────────────────────────────────────────────────────────────
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🤖 *Bot de Emissão e Lançamento IDDAS*\n\n"
        "Envie os dados da emissão com o bilhete em PDF!\n\n"
        "📋 *Estrutura da mensagem (legenda do PDF):*\n"
        "```\n"
        "Dados do cliente\n"
        "Nome: João Silva\n"
        "CPF: 123.456.789-00\n"
        "Data de Nascimento: 15/08/1990\n"
        "E-mail: joao@email.com\n"
        "Tel: 11999887766\n\n"
        "Dados do fornecedor\n"
        "Nome: Gol Linhas Aéreas\n"
        "CPF/CNPJ: 07.575.651/0001-59\n\n"
        "Valor da venda: R$ 1.500,00\n"
        "Valor de custo: R$ 1.100,00\n"
        "Forma de pagamento: PIX\n"
        "```\n\n"
        "📎 Anexe o PDF do bilhete com a mensagem acima como legenda.\n"
        "🔍 Para ver o que o bot leu antes de enviar ao IDDAS, use /debug"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_command(update, context)


async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ativa modo debug — próxima mensagem mostra o que foi lido sem enviar ao IDDAS."""
    context.user_data["debug_mode"] = True
    await update.message.reply_text(
        "🔍 *Modo DEBUG ativado!*\n\n"
        "Envie agora o PDF com a legenda.\n"
        "Vou mostrar o que o Grok extraiu *sem enviar ao IDDAS*.",
        parse_mode="Markdown"
    )


# ─── Handler principal ───────────────────────────────────────────────────────
async def handle_emission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa mensagem com texto + PDF, usa Grok para extrair dados e lança no IDDAS."""
    msg: Message = update.message
    if not msg:
        return

    debug_mode = context.user_data.pop("debug_mode", False)

    status_msg = await msg.reply_text(
        "🔍 *Lendo dados com IA (Grok)...*" if debug_mode else "🔄 *Processando emissão com IA...*",
        parse_mode="Markdown"
    )

    pdf_path = None
    try:
        # 1. Texto da mensagem (ou legenda do documento)
        raw_text = msg.text or msg.caption or ""

        # 2. Download do PDF
        if msg.document and (
            msg.document.mime_type == "application/pdf"
            or (msg.document.file_name and msg.document.file_name.lower().endswith(".pdf"))
        ):
            file = await msg.document.get_file()
            temp_dir = os.path.join(os.getcwd(), "tmp_pdf")
            os.makedirs(temp_dir, exist_ok=True)
            pdf_path = os.path.join(
                temp_dir,
                f"{msg.document.file_unique_id}_{msg.document.file_name or 'reserva.pdf'}"
            )
            await file.download_to_drive(pdf_path)
            logger.info(f"[Bot] PDF baixado: {pdf_path}")

        # 3. Extrai texto do PDF
        texto_pdf = ""
        if pdf_path and os.path.exists(pdf_path):
            texto_pdf = extrair_texto_pdf(pdf_path)
            logger.info(f"[Bot] PDF: {len(texto_pdf)} chars extraídos")

        if not raw_text.strip() and not texto_pdf.strip():
            await status_msg.edit_text(
                "⚠️ Nenhum texto ou PDF detectado.\n\n"
                "Por favor, envie a mensagem com os dados do cliente e fornecedor "
                "e/ou o PDF do bilhete como anexo.",
                parse_mode="Markdown"
            )
            return

        # 4. Extrai dados com Grok IA
        await status_msg.edit_text("🧠 *Analisando com Grok IA...*", parse_mode="Markdown")
        dados = await extrair_dados_com_grok(raw_text, texto_pdf)

        cliente_info        = dados["cliente"]
        fornecedor_info     = dados["fornecedor"]
        valor_venda         = dados["valor_venda"]
        valor_custo         = dados["valor_custo"]
        forma_pagamento_txt = dados["forma_pagamento"]
        localizador         = dados["localizador"] or "PNR000"
        voos                = dados["voos"]

        # ── MODO DEBUG ────────────────────────────────────────────────────────
        if debug_mode:
            voos_txt = "\n".join(
                f"  {i+1}. {v.get('voo','')} "
                f"{v.get('aeroporto_origem','')}→{v.get('aeroporto_destino','')} "
                f"{v.get('data_embarque','')} {v.get('hora_embarque','')} [{v.get('tipo_trecho','')}]"
                for i, v in enumerate(voos)
            ) or "  (nenhum voo detectado)"

            pdf_preview = texto_pdf[:800].replace("`", "'") if texto_pdf else "(sem texto extraído do PDF)"

            debug_msg = (
                "🔍 *DEBUG — Dados Extraídos pelo Grok*\n\n"
                f"*📄 Texto bruto do PDF (800 chars):*\n```\n{pdf_preview}\n```\n\n"
                f"*🎫 Localizador:* `{localizador}`\n\n"
                f"*✈️ Voos:*\n```\n{voos_txt}\n```\n\n"
                f"*👤 Cliente:*\n"
                f"  Nome: {cliente_info.get('nome','')}\n"
                f"  CPF: {cliente_info.get('cpf','')}\n"
                f"  Nasc: {cliente_info.get('data_nascimento','')}\n"
                f"  Email: {cliente_info.get('email','')}\n"
                f"  Tel: {cliente_info.get('telefone','')}\n\n"
                f"*🏢 Fornecedor:*\n"
                f"  Nome: {fornecedor_info.get('nome','')}\n"
                f"  CNPJ: {fornecedor_info.get('cpf_cnpj','')}\n\n"
                f"*💵 Valor Venda:* R$ {valor_venda:.2f}\n"
                f"*💸 Valor Custo:* R$ {valor_custo:.2f}\n"
                f"*💳 Forma Pgto:* {forma_pagamento_txt}"
            )

            # Telegram tem limite de 4096 chars
            if len(debug_msg) > 4000:
                await status_msg.edit_text(debug_msg[:4000], parse_mode="Markdown")
                await msg.reply_text(debug_msg[4000:8000], parse_mode="Markdown")
            else:
                await status_msg.edit_text(debug_msg, parse_mode="Markdown")
            return

        # ── MODO NORMAL: envia ao IDDAS ───────────────────────────────────────
        api_client = IddasApiClient()

        await status_msg.edit_text("🔑 *Autenticando no IDDAS...*", parse_mode="Markdown")
        await api_client.authenticate()

        # Forma de pagamento (ID numérico do IDDAS)
        forma_pagamento_id = await api_client.buscar_forma_pagamento_id(forma_pagamento_txt)

        # A. Cliente
        await status_msg.edit_text("👤 *Cadastrando/Buscando Cliente...*", parse_mode="Markdown")
        cliente_id = await api_client.cadastrar_cliente(cliente_info)

        # B. Fornecedor
        await status_msg.edit_text("🏢 *Cadastrando/Buscando Fornecedor...*", parse_mode="Markdown")
        fornecedor_id = await api_client.cadastrar_fornecedor(fornecedor_info)

        # C. Orçamento/Venda (situação = Aprovado)
        await status_msg.edit_text("📄 *Criando Venda no IDDAS...*", parse_mode="Markdown")
        titulo = f"Voo {localizador} - {cliente_info.get('nome','Cliente')}".strip()
        orcamento_id = await api_client.criar_orcamento(
            cliente_id, titulo, forma_pagamento=forma_pagamento_txt
        )

        # D. Voos
        await status_msg.edit_text("✈️ *Lançando Voos...*", parse_mode="Markdown")
        voos_cadastrados = 0
        if voos:
            for v in voos:
                v["localizador"] = localizador
                res_v = await api_client.cadastrar_voo(orcamento_id, v)
                if res_v:
                    voos_cadastrados += 1
        else:
            # Voo genérico se IA não detectou voos no PDF
            await api_client.cadastrar_voo(orcamento_id, {
                "localizador": localizador,
                "voo": "VOO 0000",
                "tipo_trecho": "I",
                "aeroporto_origem": "GRU",
                "aeroporto_destino": "GIG",
                "data_embarque": "",
                "hora_embarque": "08:00:00",
                "data_chegada": "",
                "hora_chegada": "10:00:00"
            })
            voos_cadastrados = 1

        # E. Financeiro
        await status_msg.edit_text("💰 *Lançando Financeiro...*", parse_mode="Markdown")
        rec_id  = await api_client.lançar_receita(
            cliente_id, valor_venda, localizador, forma_pagamento_id=forma_pagamento_id
        )
        desp_id = await api_client.lançar_despesa(
            fornecedor_id, valor_custo, localizador, forma_pagamento_id=forma_pagamento_id
        )

        # 6. Resposta final
        voos_desc = ""
        for v in voos[:8]:
            voos_desc += (
                f"  ✈️ {v.get('voo','')} "
                f"{v.get('aeroporto_origem','')}→{v.get('aeroporto_destino','')} "
                f"{v.get('data_embarque','')} {v.get('hora_embarque','')}\n"
            )

        resumo = (
            "✅ *Lançamento Realizado com Sucesso!*\n\n"
            f"🆔 *ID Venda:* `{orcamento_id}`\n"
            f"🎫 *Localizador:* `{localizador}`\n\n"
            f"👤 *Cliente:* {cliente_info.get('nome','N/A')} (ID: `{cliente_id}`)\n"
            f"🏢 *Fornecedor:* {fornecedor_info.get('nome','N/A')} (ID: `{fornecedor_id}`)\n\n"
            f"✈️ *Voos:* `{voos_cadastrados}` trecho(s)\n"
            + (voos_desc if voos_desc else "")
            + f"💵 *Venda:* R$ {valor_venda:,.2f}" + (f" (ID: `{rec_id}`)" if rec_id else "") + "\n"
            + f"💸 *Custo:* R$ {valor_custo:,.2f}" + (f" (ID: `{desp_id}`)" if desp_id else "") + "\n"
            + (f"💳 *Pgto:* {forma_pagamento_txt}\n" if forma_pagamento_txt else "")
            + "\n_Lançamento feito via Grok IA_ 🤖"
        )
        await status_msg.edit_text(resumo, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"[Bot Error] {e}", exc_info=True)
        await status_msg.edit_text(
            f"❌ *Erro ao processar:*\n`{str(e)[:500]}`",
            parse_mode="Markdown"
        )
    finally:
        # Em debug, mantém o PDF para inspeção; em modo normal, deleta
        if pdf_path and os.path.exists(pdf_path) and not debug_mode:
            try:
                os.remove(pdf_path)
            except Exception:
                pass


# ─── Entry point ─────────────────────────────────────────────────────────────
def main():
    token = config.TELEGRAM_BOT_TOKEN
    if not token or token == "SEU_TELEGRAM_BOT_TOKEN_HERE":
        print("⚠️  TELEGRAM_BOT_TOKEN não configurado no .env!")
        sys.exit(1)

    if not config.GROK_API_KEY:
        print("⚠️  GROK_API_KEY não configurada no .env! Adicione sua chave xAI.")
        sys.exit(1)

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start",  start_command))
    app.add_handler(CommandHandler("help",   help_command))
    app.add_handler(CommandHandler("debug",  debug_command))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, handle_emission))

    print("🚀 Bot Telegram IDDAS com Grok IA rodando...")
    print(f"   Modelo: {config.GROK_MODEL}")
    app.run_polling()


if __name__ == "__main__":
    main()
