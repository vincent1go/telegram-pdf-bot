import os
import re
import logging
import pytz
from datetime import datetime
from flask import Flask, request
from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, ContextTypes, MessageHandler,
    CallbackQueryHandler, filters
)
import fitz  # PyMuPDF
import asyncio

# === Конфигурация ===
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ADMIN_ID = os.getenv("ADMIN_ID")

TEMPLATES = {
    "UR Recruitment LTD": "clean_template_no_text.pdf",
    "SMALL WORLD RECRUITMENT LTD": "template_small_world.pdf"
}

COLOR = (69/255, 69/255, 69/255)
FONT_NAME = "helv"

# === Логирование ===
logging.basicConfig(level=logging.INFO)

# === Telegram-приложение ===
app = ApplicationBuilder().token(TOKEN).build()
bot = app.bot

# === Flask-приложение ===
web_app = Flask(__name__)

# === Маршрут для Webhook ===
@web_app.route("/telegram", methods=["POST"])
def telegram_webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    asyncio.run(app.process_update(update))
    return "ok"

# === Утилиты ===
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
            fontname=FONT_NAME,
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
    safe_name = re.sub(r'[^\w\s-]', '', client_name, flags=re.UNICODE).strip()
    if not safe_name:
        await update.message.reply_text("Неверное имя клиента.")
        return

    template_path = context.user_data.get("template")
    if not template_path:
        await ask_template_choice(update, context)
        return

    output_path = f"{safe_name}.pdf"
    try:
        fill_pdf_template(template_path, output_path, safe_name, get_london_date())

        with open(output_path, "rb") as f:
            await update.message.reply_document(InputFile(f, filename=output_path))

        keyboard = [
            [InlineKeyboardButton("Выбрать другой шаблон", callback_data="choose_template")]
        ]
        await update.message.reply_text(
            f"Договор на имя \"{client_name}\" сгенерирован.\n\n"
            f"Текущий шаблон: {get_template_name_by_path(template_path)}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logging.error(f"Ошибка PDF: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")
        if ADMIN_ID:
            await context.bot.send_message(chat_id=int(ADMIN_ID), text=f"Ошибка у {update.effective_user.id}: {e}")
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)

async def ask_template_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(name, callback_data=name)] for name in TEMPLATES]
    if update.message:
        await update.message.reply_text("Выберите шаблон:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif update.callback_query:
        await update.callback_query.edit_message_text("Выберите шаблон:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_template_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected = query.data
    if selected == "choose_template":
        await ask_template_choice(update, context)
        return
    context.user_data["template"] = TEMPLATES[selected]
    await query.edit_message_text(f"Выбран шаблон: {selected}")

# === Регистрация обработчиков ===
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CallbackQueryHandler(handle_template_selection))

# === Webhook установка при старте ===
async def start_webhook():
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(url=WEBHOOK_URL)
    logging.info("✅ Webhook установлен")

# === Запуск ===
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_webhook())
    web_app.run(host="0.0.0.0", port=8080)
