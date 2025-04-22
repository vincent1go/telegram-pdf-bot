import os
import re
import logging
import pytz
from datetime import datetime
from telegram import Update, InputFile, InlineKeyboardMarkup, InlineKeyboardButton, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, CallbackQueryHandler, filters
import fitz  # PyMuPDF
from flask import Flask, request
from threading import Thread
import asyncio

# === Конфигурация ===
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.environ.get("PORT", "8080"))

TEMPLATES = {
    "UR Recruitment LTD": "clean_template_no_text.pdf",
    "SMALL WORLD RECRUITMENT LTD": "template_small_world.pdf"
}

COLOR = (69/255, 69/255, 69/255)
bot = Bot(token=TOKEN)

# === Логирование ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

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
            fontname="helv", fontsize=11, color=COLOR
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

# === Telegram Handlers ===
async def set_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(t, callback_data=t)] for t in TEMPLATES.keys()]
    await update.message.reply_text("Выберите шаблон:", reply_markup=InlineKeyboardMarkup(keyboard))

async def template_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected = query.data
    context.user_data["template"] = TEMPLATES[selected]
    await query.edit_message_text(f"Шаблон выбран: {selected}")

async def handle_template_switch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton(t, callback_data=t)] for t in TEMPLATES.keys()]
    await query.edit_message_text("Выберите шаблон:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client_name = update.message.text.strip()
    try:
        safe_name = re.sub(r"[^\w\s\-\u0400-\u04FF]", "", client_name).strip()
        template_path = context.user_data.get("template")
        if not template_path:
            keyboard = [[InlineKeyboardButton(t, callback_data=t)] for t in TEMPLATES.keys()]
            await update.message.reply_text("Сначала выберите шаблон:", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        output_path = f"{safe_name}.pdf"
        fill_pdf_template(template_path, output_path, safe_name, get_london_date())
        with open(output_path, "rb") as f:
            await update.message.reply_document(document=InputFile(f, filename=output_path))
        await update.message.reply_text(
            f"Договор на имя \"{client_name}\" сгенерирован.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Выбрать другой шаблон", callback_data="choose_template")]])
        )
        os.remove(output_path)
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await notify_admin(context, f"Ошибка у {update.effective_user.id}: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")

# === Flask сервер ===
web_app = Flask(__name__)
telegram_app = None  # Здесь позже инициализируем Application

@web_app.route("/")
def index():
    return "Бот запущен!"

@web_app.route("/telegram", methods=["POST"])
def webhook():
    if telegram_app:
        update = Update.de_json(request.get_json(force=True), bot)
        telegram_app.create_task(telegram_app.process_update(update))
    return "ok"

# === Запуск Flask + Telegram ===
async def main():
    global telegram_app
    telegram_app = ApplicationBuilder().token(TOKEN).build()

    telegram_app.add_handler(CommandHandler("template", set_template))
    telegram_app.add_handler(CallbackQueryHandler(template_callback))
    telegram_app.add_handler(CallbackQueryHandler(handle_template_switch, pattern="choose_template"))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await bot.set_webhook(f"{WEBHOOK_URL}/telegram")
    logging.info("Webhook установлен.")

    flask_thread = Thread(target=lambda: web_app.run(host="0.0.0.0", port=PORT), daemon=True)
    flask_thread.start()

    logging.info("Бот работает через вебхуки. Ожидаем события...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Остановлено вручную")
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")
