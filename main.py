import os
import re
import logging
import pytz
import asyncio
from datetime import datetime
from telegram import Update, InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (ApplicationBuilder, ContextTypes, CommandHandler,
                          MessageHandler, CallbackQueryHandler, filters)
from flask import Flask, request
import fitz  # PyMuPDF

# === Конфигурация ===
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

TEMPLATES = {
    "UR Recruitment LTD": "clean_template_no_text.pdf",
    "SMALL WORLD RECRUITMENT LTD": "template_small_world.pdf"
}

COLOR = (69/255, 69/255, 69/255)
FONT_PATH = "fonts/times.ttf"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

# === Telegram bot setup ===
telegram_app = ApplicationBuilder().token(TOKEN).build()

# === Вспомогательные функции ===
def get_london_date():
    return datetime.now(pytz.timezone("Europe/London")).strftime("%d.%m.%Y")

def replace_text(page, old_text, new_text):
    areas = page.search_for(old_text)
    for area in areas:
        page.add_redact_annot(area, fill=(1, 1, 1))
    page.apply_redactions()
    for area in areas:
        y_offset = 11 if "Date" in old_text else 0
        page.insert_text(
            (area.x0, area.y0 + y_offset), new_text,
            fontname="helv",
            fontsize=11,
            color=COLOR
        )

def fill_pdf_template(template_path, output_path, client_name, date_str):
    doc = fitz.open(template_path)
    for page in doc:
        replace_text(page, "Client:", f"Client: {client_name}")
        replace_text(page, "Date:", f"Date: {date_str}")
    doc.save(output_path, garbage=4, deflate=True, clean=True)
    doc.close()

async def notify_admin(context, message):
    if ADMIN_ID:
        try:
            await context.bot.send_message(chat_id=int(ADMIN_ID), text=message)
        except Exception as e:
            logging.error(f"Ошибка уведомления админа: {e}")

# === Обработчики Telegram ===
async def choose_template_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(t, callback_data=t)] for t in TEMPLATES.keys()]
    await update.message.reply_text("Выберите шаблон:", reply_markup=InlineKeyboardMarkup(keyboard))

async def template_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected = query.data
    context.user_data['template'] = TEMPLATES[selected]
    await query.edit_message_text(f"Шаблон выбран: {selected}")

async def handle_template_switch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await choose_template_prompt(query, context)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client_name = update.message.text.strip()
    if not client_name:
        await update.message.reply_text("Пожалуйста, введите имя клиента.")
        return
    try:
        safe_name = re.sub(r'[^\w\s-]', '', client_name, flags=re.UNICODE).strip()
        if not safe_name:
            await update.message.reply_text("Имя клиента содержит недопустимые символы.")
            return

        template_path = context.user_data.get('template')
        if not template_path:
            await choose_template_prompt(update, context)
            return

        output_path = f"{safe_name}.pdf"
        fill_pdf_template(template_path, output_path, safe_name, get_london_date())

        with open(output_path, "rb") as f:
            await update.message.reply_document(document=InputFile(f, filename=output_path))

        keyboard = [[InlineKeyboardButton("Выбрать другой шаблон", callback_data="choose_template")]]
        await update.message.reply_text(
            f"Договор на имя \"{client_name}\" сгенерирован.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        os.remove(output_path)
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await notify_admin(context, f"Ошибка у {update.effective_user.id}: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")

telegram_app.add_handler(CommandHandler("template", choose_template_prompt))
telegram_app.add_handler(CallbackQueryHandler(handle_template_switch, pattern="choose_template"))
telegram_app.add_handler(CallbackQueryHandler(template_callback))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# === Flask сервер ===
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is running"

@web_app.route('/telegram', methods=['POST'])
def webhook():
    from telegram import Update as TGUpdate
    update = TGUpdate.de_json(request.get_json(force=True), telegram_app.bot)
    telegram_app.create_task(telegram_app.process_update(update))
    return 'ok'

async def set_webhook():
    await telegram_app.bot.set_webhook(f"{WEBHOOK_URL}/telegram")

# === Запуск ===
if __name__ == '__main__':
    async def run():
        await telegram_app.initialize()
        await set_webhook()
        await telegram_app.start()
        web_app.run(host='0.0.0.0', port=8080)
    asyncio.run(run())
