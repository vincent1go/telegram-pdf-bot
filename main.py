import os
import logging
import pytz
from datetime import datetime
from flask import Flask, request
from telegram import Update, InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters
)
import fitz  # PyMuPDF

# === Конфигурация ===
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-app-url.onrender.com/telegram")

TEMPLATES = {
    "UR Recruitment LTD": "clean_template_no_text.pdf",
    "SMALL WORLD RECRUITMENT LTD": "template_small_world.pdf"
}
COLOR = (69/255, 69/255, 69/255)

# === Telegram App ===
telegram_app = ApplicationBuilder().token(TOKEN).build()

# === Flask App ===
flask_app = Flask(__name__)

# === Логирование ===
logging.basicConfig(level=logging.INFO)

# === PDF функции ===
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
            fontname="helv", fontsize=11, color=COLOR
        )

def fill_pdf_template(template_path, output_path, client_name, date_str):
    doc = fitz.open(template_path)
    for page in doc:
        replace_text(page, "Client:", f"Client: {client_name}")
        replace_text(page, "Date:", f"Date: {date_str}")
    doc.save(output_path)
    doc.close()

# === Telegram Handlers ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client_name = update.message.text.strip()
    if not client_name:
        await update.message.reply_text("Пожалуйста, введите имя клиента.")
        return

    template = context.user_data.get("template")
    if not template:
        await update.message.reply_text("Сначала выберите шаблон.")
        return

    output_path = f"{client_name}.pdf"
    fill_pdf_template(template, output_path, client_name, get_london_date())

    with open(output_path, "rb") as f:
        await update.message.reply_document(InputFile(f, filename=output_path))

    keyboard = [[InlineKeyboardButton("Выбрать другой шаблон", callback_data="choose_template")]]
    await update.message.reply_text(f"Договор на имя \"{client_name}\" сгенерирован.", reply_markup=InlineKeyboardMarkup(keyboard))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_template_menu(update)

async def show_template_menu(update: Update):
    keyboard = [[InlineKeyboardButton(text=name, callback_data=name)] for name in TEMPLATES.keys()]
    await update.message.reply_text("Выберите шаблон:", reply_markup=InlineKeyboardMarkup(keyboard))

async def template_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    template = query.data
    context.user_data["template"] = TEMPLATES[template]
    await query.edit_message_text(f"Шаблон выбран: {template}")

async def switch_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_template_menu(update)

# === Telegram Routing ===
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
telegram_app.add_handler(CallbackQueryHandler(template_callback, pattern="^(UR Recruitment LTD|SMALL WORLD RECRUITMENT LTD)$"))
telegram_app.add_handler(CallbackQueryHandler(switch_template, pattern="choose_template"))
telegram_app.add_handler(CommandHandler("start", start))

# === Flask Webhook Route ===
@flask_app.route("/telegram", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    telegram_app.update_queue.put_nowait(update)
    return "ok", 200

@flask_app.route("/", methods=["GET"])
def home():
    return "Bot is running!", 200

# === Запуск ===
if __name__ == "__main__":
    import asyncio

    async def main():
        await telegram_app.initialize()
        await telegram_app.bot.set_webhook(url=WEBHOOK_URL)
        await telegram_app.start()

        flask_app.run(host="0.0.0.0", port=8080)

    asyncio.run(main())
