import os
import logging
import pytz
from datetime import datetime
from flask import Flask, request, abort
from telegram import Update, InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import fitz  # PyMuPDF
import re
import json

# === Конфигурация ===
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

TEMPLATES = {
    "UR Recruitment LTD": "clean_template_no_text.pdf",
    "SMALL WORLD RECRUITMENT LTD": "template_small_world.pdf"
}

COLOR = (69 / 255, 69 / 255, 69 / 255)

# === Логирование ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# === Telegram Application ===
telegram_app = ApplicationBuilder().token(TOKEN).build()

# === Flask App ===
flask_app = Flask(__name__)

# === Вспомогательные функции ===
def get_london_date():
    return datetime.now(pytz.timezone("Europe/London")).strftime("%d.%m.%Y")

def get_template_name_by_path(path):
    for name, file in TEMPLATES.items():
        if file == path:
            return name
    return "Неизвестно"

def replace_text(page, old_text, new_text):
    areas = page.search_for(old_text)
    for area in areas:
        page.add_redact_annot(area, fill=(1, 1, 1))
    page.apply_redactions()
    for area in areas:
        y_offset = 8 if "Date" in old_text else 0
        page.insert_text(
            (area.x0, area.y0 + y_offset),
            new_text,
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
async def set_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(text=label, callback_data=label)] for label in TEMPLATES.keys()
    ]
    await update.message.reply_text(
        "Выберите шаблон:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def template_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected = query.data
    context.user_data['template'] = TEMPLATES[selected]
    await query.edit_message_text(f"Шаблон выбран: {selected}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client_name = update.message.text.strip()
    safe_name = re.sub(r'[^\w\s-]', '', client_name, flags=re.UNICODE).strip()
    template_path = context.user_data.get('template')
    if not template_path:
        await update.message.reply_text("Сначала выберите шаблон через /template")
        return
    output_path = f"{safe_name}.pdf"
    fill_pdf_template(template_path, output_path, safe_name, get_london_date())
    with open(output_path, "rb") as f:
        await update.message.reply_document(document=InputFile(f, filename=output_path))
    keyboard = [[InlineKeyboardButton("Выбрать другой шаблон", callback_data="choose_template")]]
    await update.message.reply_text(
        f"Договор на имя "{client_name}" сгенерирован.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    os.remove(output_path)

async def handle_template_switch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton(text=label, callback_data=label)] for label in TEMPLATES.keys()
    ]
    await query.edit_message_text("Выберите шаблон:", reply_markup=InlineKeyboardMarkup(keyboard))

# === Flask Webhook Endpoint ===
@flask_app.route("/telegram", methods=["POST"])
def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), telegram_app.bot)
        telegram_app.update_queue.put_nowait(update)
        return "OK", 200
    return "Method Not Allowed", 405

@flask_app.route("/")
def home():
    return "Bot is running", 200

# === Запуск ===
if __name__ == "__main__":
    telegram_app.add_handler(CommandHandler("template", set_template))
    telegram_app.add_handler(CallbackQueryHandler(handle_template_switch, pattern="choose_template"))
    telegram_app.add_handler(CallbackQueryHandler(template_callback))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    telegram_app.initialize()
    telegram_app.bot.set_webhook(url=WEBHOOK_URL)
    telegram_app.start()
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))