import os
import logging
import pytz
from datetime import datetime
from flask import Flask, request, abort
from telegram import Update, InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, CallbackQueryHandler, filters
import fitz  # PyMuPDF
import asyncio

# === Конфигурация ===
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # например: https://your-app.onrender.com/telegram

TEMPLATES = {
    "UR Recruitment LTD": "clean_template_no_text.pdf",
    "SMALL WORLD RECRUITMENT LTD": "template_small_world.pdf"
}

COLOR = (69/255, 69/255, 69/255)
FONT_PATH = "fonts/times.ttf"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# === Telegram App ===
telegram_app = ApplicationBuilder().token(TOKEN).build()

# === Вспомогательные функции ===
def get_template_name_by_path(path):
    for name, file in TEMPLATES.items():
        if file == path:
            return name
    return "Неизвестно"

def get_london_date():
    return datetime.now(pytz.timezone("Europe/London")).strftime("%d.%m.%Y")

def replace_text(page, old_text, new_text):
    areas = page.search_for(old_text)
    for area in areas:
        page.add_redact_annot(area, fill=(1, 1, 1))
    page.apply_redactions()
    for area in areas:
        y_offset = 8 if "Date" in old_text else 0
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

# === Обработчики ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client_name = update.message.text.strip()
    if not client_name:
        await update.message.reply_text("Пожалуйста, введите имя клиента.")
        return
    template_path = context.user_data.get("template")
    if not template_path:
        await show_template_choice(update, context)
        return
    safe_name = client_name.replace('/', '-').strip()
    output_path = f"{safe_name}.pdf"
    fill_pdf_template(template_path, output_path, client_name, get_london_date())
    with open(output_path, "rb") as f:
        await update.message.reply_document(InputFile(f, filename=output_path))
    await update.message.reply_text(
        f"Договор на имя \"{client_name}\" сгенерирован.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Выбрать другой шаблон", callback_data="choose_template")]]
        )
    )
    os.remove(output_path)

async def show_template_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(name, callback_data=name)] for name in TEMPLATES]
    if update.message:
        await update.message.reply_text("Выберите шаблон:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif update.callback_query:
        await update.callback_query.edit_message_text("Выберите шаблон:", reply_markup=InlineKeyboardMarkup(keyboard))

async def template_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data
    if choice in TEMPLATES:
        context.user_data["template"] = TEMPLATES[choice]
        await query.edit_message_text(f"Шаблон выбран: {choice}")

# === Telegram Router ===
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
telegram_app.add_handler(CallbackQueryHandler(template_selected, pattern="^(UR Recruitment LTD|SMALL WORLD RECRUITMENT LTD)$"))
telegram_app.add_handler(CallbackQueryHandler(show_template_choice, pattern="choose_template"))

# === Flask сервер ===
flask_app = Flask(__name__)

@flask_app.route("/telegram", methods=["POST"])
def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), telegram_app.bot)
        telegram_app.create_task(telegram_app.process_update(update))
        return "", 200
    else:
        abort(405)

@flask_app.route("/")
def index():
    return "OK", 200

# === Запуск ===
if __name__ == "__main__":
    async def main():
        await telegram_app.initialize()
        await telegram_app.bot.set_webhook(url=WEBHOOK_URL)
        await telegram_app.start()
        flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
    asyncio.run(main())

