import os
import re
import logging
import pytz
import fitz
from datetime import datetime
from flask import Flask, request, abort
from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# === Конфигурация ===
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Пример: https://your-domain.com

TEMPLATES = {
    "UR Recruitment LTD": "clean_template_no_text.pdf",
    "SMALL WORLD RECRUITMENT LTD": "template_small_world.pdf"
}
COLOR = (69/255, 69/255, 69/255)

# === Telegram Application ===
telegram_app = Application.builder().token(TOKEN).build()

# === Flask App ===
web_app = Flask(__name__)

# === PDF utils ===
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

# === Обработчики Telegram ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client_name = update.message.text.strip()
    safe_name = re.sub(r'[^\w\s-]', '', client_name, flags=re.UNICODE).strip()
    template_path = context.user_data.get('template')
    if not template_path:
        await update.message.reply_text("Сначала выберите шаблон.")
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

async def choose_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton(text=label, callback_data=label)] for label in TEMPLATES
    ]
    await query.edit_message_text("Выберите шаблон:", reply_markup=InlineKeyboardMarkup(keyboard))

async def set_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['template'] = TEMPLATES[query.data]
    await query.edit_message_text(f"Шаблон выбран: {query.data}")

# === Роут для Telegram Webhook ===
@web_app.route('/telegram', methods=["POST"])
def telegram_webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), telegram_app.bot)
        telegram_app.update_queue.put_nowait(update)
        return "OK"
    abort(403)

# === Регистрация Telegram-хендлеров ===
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
telegram_app.add_handler(CallbackQueryHandler(choose_template, pattern="choose_template"))
telegram_app.add_handler(CallbackQueryHandler(set_template))

# === Запуск Flask и Telegram бота с Webhook ===
if __name__ == "__main__":
    import threading

    async def set_webhook():
        await telegram_app.bot.set_webhook(url=f"{WEBHOOK_URL}/telegram")

    def run_flask():
        web_app.run(host="0.0.0.0", port=8080)

    threading.Thread(target=run_flask).start()

    telegram_app.run_async(set_webhook())
    telegram_app.run_polling(stop_signals=None)
