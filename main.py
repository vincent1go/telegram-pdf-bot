import logging
import asyncio
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
import config
from pdf_generator import generate_pdf

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SELECTING_TEMPLATE = 1
ENTERING_TEXT = 2

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = (
        "👋 *Добро пожаловать в PDF-бот!*\n\n"
        "Выберите шаблон, введите имя клиента — и получите PDF-файл 📄"
    )
    keyboard = [
        [
            InlineKeyboardButton("📄 Выбрать шаблон", callback_data="select_template"),
            InlineKeyboardButton("ℹ️ О боте", callback_data="about"),
        ]
    ]
    await update.message.reply_text(message, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    message = (
        "ℹ️ *О боте*\n\n"
        "Бот генерирует PDF-документы на основе шаблонов.\n"
        "Автор: @vincent1go\n"
        "[GitHub](https://github.com/vincent1go/telegram-pdf-bot)"
    )
    keyboard = [[InlineKeyboardButton("🏠 Назад", callback_data="main_menu")]]
    await query.message.edit_text(message, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    message = "🏠 *Главное меню*\n\nВыберите действие:"
    keyboard = [
        [
            InlineKeyboardButton("📄 Выбрать шаблон", callback_data="select_template"),
            InlineKeyboardButton("ℹ️ О боте", callback_data="about"),
        ]
    ]
    await query.message.edit_text(message, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def select_template(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    message = "📄 *Выберите шаблон*:"
    keyboard = []
    for name in config.TEMPLATES.keys():
        keyboard.append([InlineKeyboardButton(name, callback_data=f"template_{name}")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    await query.message.edit_text(message, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data["state"] = SELECTING_TEMPLATE

async def template_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    name = query.data.replace("template_", "")
    if name not in config.TEMPLATES:
        await query.message.edit_text("⚠️ Ошибка: Шаблон не найден.")
        return
    context.user_data["template"] = name
    context.user_data["state"] = ENTERING_TEXT
    await query.message.edit_text(
        f"✅ Шаблон выбран: *{name}*\n\nВведите имя клиента:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Сменить шаблон", callback_data="select_template")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
        ])
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.message.edit_text("❌ Отменено. Выберите действие:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Выбрать шаблон", callback_data="select_template")],
        [InlineKeyboardButton("ℹ️ О боте", callback_data="about")]
    ]))

async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if "template" not in context.user_data:
        keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]]
        await update.message.reply_text(
            "⚠️ Сначала выберите шаблон через меню.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    client_name = update.message.text.strip()
    template_name = context.user_data["template"]
    try:
        template_path = config.TEMPLATES[template_name]
        pdf_path = generate_pdf(template_path, client_name)
        filename = f"{client_name}.pdf"
        with open(pdf_path, "rb") as f:
            await update.message.reply_document(document=f, filename=filename)

        keyboard = [
            [InlineKeyboardButton("📄 Сменить шаблон", callback_data="select_template")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        await update.message.reply_text(
            "✅ Документ успешно создан!\n\nМожете ввести другое имя клиента, и бот снова создаст PDF.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Ошибка генерации PDF: {e}")
        await update.message.reply_text("❌ Ошибка при создании PDF.")

# === Webhook ===

async def handle_webhook(request):
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return web.Response(text="ok")
    except Exception as e:
        logger.exception("Ошибка вебхука:")
        return web.Response(status=500, text="error")

async def home(request):
    return web.Response(text="Бот работает!")

# === Запуск ===

async def main():
    global application
    application = Application.builder().token(config.BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(select_template, pattern="select_template"))
    application.add_handler(CallbackQueryHandler(main_menu, pattern="main_menu"))
    application.add_handler(CallbackQueryHandler(about, pattern="about"))
    application.add_handler(CallbackQueryHandler(cancel, pattern="cancel"))
    application.add_handler(CallbackQueryHandler(template_selected, pattern="template_.*"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text))

    await application.initialize()
    await application.bot.set_webhook(url=config.WEBHOOK_URL)
    await application.start()

    app = web.Application()
    app.router.add_post("/telegram", handle_webhook)
    app.router.add_get("/", home)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port=8080)
    await site.start()

    logger.info("Бот успешно запущен на порту 8080")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
