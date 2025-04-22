import os
import re
import logging
import pytz
import json
from datetime import datetime
from telegram import Update, InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from flask import Flask, request
import fitz  # PyMuPDF
import asyncio

# === Конфигурация ===
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://yourdomain.com/telegram
PORT = int(os.environ.get("PORT", 8080))

TEMPLATES = {
    "UR Recruitment LTD": "clean_template_no_text.pdf",
    "SMALL WORLD RECRUITMENT LTD": "template_small_world.pdf"
}

COLOR = (69 / 255, 69 / 255, 69 / 255)
FONT_PATH = "fonts/times.ttf"

# === Логирование ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# === Telegram-приложение ===
telegram_app = Application.builder().token(TOKEN).build()

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

# === Telegram Handlers ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client_name = update.message.text.strip()
    safe_name = re.sub(r'[^\w\s-]', '', client_name, flags=re.UNICODE).strip()
    template_path = context.user_data.get('template', list(TEMPLATES.values())[0])
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

async def handle_choose_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(name, callback_data=name)] for name in TEMPLATES
    ]
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "Выберите шаблон:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_template_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected = update.callback_query.data
    context.user_data['template'] = TEMPLATES[selected]
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(f"Выбран шаблон: {selected}")

# === Flask сервер ===
flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    return 'Бот работает!'

@flask_app.route('/telegram', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    asyncio.get_event_loop().create_task(telegram_app.process_update(update))
    return 'ok'

# === Запуск ===
async def main():
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    telegram_app.add_handler(CallbackQueryHandler(handle_choose_template, pattern="choose_template"))
    telegram_app.add_handler(CallbackQueryHandler(handle_template_selected))

    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.bot.set_webhook(url=WEBHOOK_URL)
    flask_app.run(host="0.0.0.0", port=PORT)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        logging.error(f"Ошибка запуска: {e}")
