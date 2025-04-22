import os
import re
import pytz
import fitz  # PyMuPDF
import logging
import asyncio
from datetime import datetime
from aiohttp import web
from telegram import Update, InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters
)

# === Конфигурация ===
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.environ.get("PORT", 8080))

TEMPLATES = {
    "UR Recruitment LTD": "clean_template_no_text.pdf",
    "SMALL WORLD RECRUITMENT LTD": "template_small_world.pdf"
}

COLOR = (69 / 255, 69 / 255, 69 / 255)

# === Логирование ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log")
    ]
)
logger = logging.getLogger(__name__)

# === Telegram Application ===
telegram_app = ApplicationBuilder().token(TOKEN).build()

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
    keyboard = [[InlineKeyboardButton(text=label, callback_data=label)] for label in TEMPLATES.keys()]
    await update.message.reply_text("Выберите шаблон:", reply_markup=InlineKeyboardMarkup(keyboard))

async def template_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected = query.data
    context.user_data['template'] = TEMPLATES[selected]
    await query.edit_message_text(f"Шаблон выбран: {selected}")

async def handle_template_switch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"Ошибка при ответе на callback query: {e}")
    keyboard = [[InlineKeyboardButton(text=label, callback_data=label)] for label in TEMPLATES.keys()]
    await query.edit_message_text("Выберите шаблон:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client_name = update.message.text.strip()
    safe_name = re.sub(r"[^\w\s-]", "", client_name, flags=re.UNICODE).strip()
    template_path = context.user_data.get('template')
    if not template_path:
        await update.message.reply_text("Сначала выберите шаблон через /template")
        return
    output_path = f"{safe_name}.pdf"
    try:
        fill_pdf_template(template_path, output_path, safe_name, get_london_date())
        with open(output_path, "rb") as f:
            await update.message.reply_document(document=InputFile(f, filename=output_path))
        keyboard = [[InlineKeyboardButton("Выбрать другой шаблон", callback_data="choose_template")]]
        await update.message.reply_text(
            f'Договор на имя "{client_name}" сгенерирован.',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Ошибка при генерации PDF: {e}")
        await update.message.reply_text("Произошла ошибка при генерации документа. Попробуйте снова.")
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)

# === Webhook Handler ===
async def telegram_webhook(request):
    try:
        data = await request.json()
        update = Update.de_json(data, telegram_app.bot)
        if update:
            await telegram_app.process_update(update)
            return web.json_response({"status": "ok"})
        else:
            logger.warning("Получен пустой или некорректный update")
            return web.json_response({"status": "error", "message": "Invalid update"}, status=400)
    except Exception as e:
        logger.error(f"Ошибка в вебхуке: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)

async def home(request):
    return web.Response(text="Bot is alive!")

# === Запуск ===
async def main():
    try:
        # Настройка обработчиков
        telegram_app.add_handler(CommandHandler("template", set_template))
        telegram_app.add_handler(CallbackQueryHandler(handle_template_switch, pattern="choose_template"))
        telegram_app.add_handler(CallbackQueryHandler(template_callback))
        telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        # Инициализация приложения
        await telegram_app.initialize()
        logger.info(f"Установка вебхука: {WEBHOOK_URL}")

        # Установка вебхука
        webhook_info = await telegram_app.bot.set_webhook(url=WEBHOOK_URL)
        logger.info(f"Вебхук установлен: {webhook_info}")

        # Запуск Telegram приложения
        await telegram_app.start()

        # Настройка aiohttp сервера
        app = web.Application()
        app.router.add_post("/telegram", telegram_webhook)
        app.router.add_get("/", home)

        # Запуск сервера
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", PORT)
        await site.start()
        logger.info(f"Сервер запущен на порту {PORT}")

        # Держим приложение запущенным
        while True:
            await asyncio.sleep(3600)

    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        raise
    finally:
        await telegram_app.stop()
        await telegram_app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
