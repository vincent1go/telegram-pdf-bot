import os
import re
import logging
import pytz
from datetime import datetime
from telegram import Update, InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler,
                          ContextTypes, filters, CallbackQueryHandler)
import fitz  # PyMuPDF
from flask import Flask, request, abort
from threading import Thread
import time
import asyncio

# === Конфигурация ===
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
if not TOKEN:
    raise ValueError("BOT_TOKEN не установлен!")

TEMPLATES = {
    "UR Recruitment LTD": "clean_template_no_text.pdf",
    "SMALL WORLD RECRUITMENT LTD": "template_small_world.pdf"
}

COLOR = (69/255, 69/255, 69/255)
FONT_PATH = "fonts/times.ttf"

# === Логирование ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

error_logger = logging.FileHandler("errors.log")
error_logger.setLevel(logging.ERROR)
logging.getLogger().addHandler(error_logger)

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
    try:
        doc = fitz.open(template_path)
        for page in doc:
            replace_text(page, "Client:", f"Client: {client_name}")
            replace_text(page, "Date:", f"Date: {date_str}")
        doc.save(output_path, garbage=4, deflate=True, clean=True)
        doc.close()
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise ValueError("Файл PDF не создан или пуст.")
    except Exception as e:
        logging.error(f"Ошибка при замене текста в PDF: {e}")
        raise

async def notify_admin(context, message):
    if ADMIN_ID:
        try:
            await context.bot.send_message(chat_id=int(ADMIN_ID), text=message)
        except Exception as e:
            logging.error(f"Ошибка уведомления админа: {e}")

# === Обработчики Telegram ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name or "пользователь"
    welcome_text = (
        f"\U0001F44B Привет, {user}!\n\n"
        "Я помогу сгенерировать PDF-договор.\n"
        "Выберите шаблон для начала:"
    )
    keyboard = [[InlineKeyboardButton(text=label, callback_data=label)] for label in TEMPLATES.keys()]
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def set_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(text=label, callback_data=label)] for label in TEMPLATES.keys()]
    await update.message.reply_text("Выберите шаблон:", reply_markup=InlineKeyboardMarkup(keyboard))

async def template_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected = query.data
    context.user_data['template'] = TEMPLATES[selected]
    await query.edit_message_text(f"Шаблон выбран: {selected}")

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
            await update.message.reply_text("Сначала выберите шаблон через /template или /start")
            return
        output_path = f"{safe_name}.pdf"
        fill_pdf_template(template_path, output_path, safe_name, get_london_date())
        with open(output_path, "rb") as f:
            await update.message.reply_document(document=InputFile(f, filename=output_path))
        keyboard = [[InlineKeyboardButton("Выбрать другой шаблон", callback_data="choose_template")]]
        await update.message.reply_text(
            f"\u2705 Договор на имя \"{client_name}\" успешно создан.\n\n"
            f"\U0001F4C4 Шаблон: *{get_template_name_by_path(template_path)}*\n"
            f"\u27A1\uFE0F Введите новое имя или выберите другой шаблон ниже:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        os.remove(output_path)
        logging.info(f"Сгенерирован PDF для: {client_name} по шаблону: {get_template_name_by_path(template_path)}")
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await notify_admin(context, f"Ошибка у {update.effective_user.id}: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")

async def handle_template_switch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton(text=label, callback_data=label)] for label in TEMPLATES.keys()]
    await query.edit_message_text("Выберите шаблон:", reply_markup=InlineKeyboardMarkup(keyboard))

# === Flask сервер ===
web_app = Flask(__name__)

@web_app.before_request
def limit_remote_addr():
    if request.remote_addr not in ["127.0.0.1", "::1"]:
        abort(403)

@web_app.route('/')
def home():
    return "Bot is running"

@web_app.route('/status')
def status():
    return {"status": "ok", "bot": "running"}

def run_flask():
    while True:
        try:
            web_app.run(host='0.0.0.0', port=8080)
        except Exception as e:
            logging.error(f"Flask упал: {e}, перезапуск через 5 секунд")
            time.sleep(5)

# === Основная логика запуска ===
def run_bot():
    try:
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("template", set_template))
        app.add_handler(CallbackQueryHandler(handle_template_switch, pattern="choose_template"))
        app.add_handler(CallbackQueryHandler(template_callback))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        logging.info("Запуск Telegram бота...")
        asyncio.run(app.run_polling())
    except Exception as e:
        logging.error(f"Ошибка бота: {e}")

def main():
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    while True:
        try:
            run_bot()
        except Exception as e:
            logging.error(f"Бот вылетел с ошибкой: {e}. Перезапуск через 5 секунд...")
            time.sleep(5)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Бот остановлен")
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")