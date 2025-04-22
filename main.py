import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
import config
from pdf_generator import generate_pdf

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния
SELECTING_TEMPLATE = 1
ENTERING_TEXT = 2

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = (
        "👋 *Добро пожаловать в PDF Генератор Бот!* 🚀\n\n"
        "Я помогу тебе создать PDF-документ по готовому шаблону.\n\n"
        "*Как это работает:*\n"
        "- Выбери шаблон из списка.\n"
        "- Отправь текст, который нужно вставить.\n"
        "- Получи PDF-документ! 📄\n\n"
        "Начнём?"
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
        "ℹ️ *О боте PDF Генератор*\n\n"
        "Этот бот создаёт PDF-документы по шаблону на основе твоего текста. 📄\n"
        "Создан с ❤️ автором [Your Name].\n"
        "Исходный код: [GitHub](https://github.com/vincent1go/telegram-pdf-bot)\n\n"
        "Готов продолжить? Вернёмся в меню! 🔄"
    )
    keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="main_menu")]]
    await query.message.edit_text(message, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    message = (
        "👋 *С возвращением в PDF Генератор Бот!* 🚀\n\n"
        "Выбери, что хочешь сделать:"
    )
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
    message = "*📄 Выбери шаблон*\n\nВыбери один из доступных шаблонов:"
    keyboard = []
    names = list(config.TEMPLATES.keys())
    for i in range(0, len(names), 2):
        row = [InlineKeyboardButton(f"📄 {names[i]}", callback_data=f"template_{names[i]}")]
        if i + 1 < len(names):
            row.append(InlineKeyboardButton(f"📄 {names[i+1]}", callback_data=f"template_{names[i+1]}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    await query.message.edit_text(message, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data["state"] = SELECTING_TEMPLATE

async def template_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    template_name = query.data.replace("template_", "")
    if template_name not in config.TEMPLATES:
        await query.message.edit_text("⚠️ *Ошибка*: Недопустимый шаблон.", parse_mode="Markdown")
        return
    context.user_data["template"] = template_name
    context.user_data["state"] = ENTERING_TEXT
    message = (
        f"✅ *Выбран шаблон*: {template_name}\n\n"
        "📝 Отправь текст, который нужно вставить в шаблон."
    )
    keyboard = [
        [
            InlineKeyboardButton("🔄 Начать заново", callback_data="select_template"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel"),
        ]
    ]
    await query.message.edit_text(message, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    message = "❌ *Операция отменена*\n\nВыбери, что хочешь сделать:"
    keyboard = [
        [
            InlineKeyboardButton("📄 Выбрать шаблон", callback_data="select_template"),
            InlineKeyboardButton("ℹ️ О боте", callback_data="about"),
        ]
    ]
    await query.message.edit_text(message, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("state") != ENTERING_TEXT:
        await update.message.reply_text("⚠️ Сначала выбери шаблон через меню.", parse_mode="Markdown")
        return
    text = update.message.text
    template_name = context.user_data.get("template")
    template_path = config.TEMPLATES.get(template_name)
    try:
        pdf_path = generate_pdf(template_path, text)
        with open(pdf_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                caption=f"✅ *PDF-документ готов!* 🎉\nШаблон: {template_name}",
                parse_mode="Markdown"
            )
        context.user_data.clear()
        await update.message.reply_text(
            "📎 Хочешь создать ещё один документ?",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📄 Новый шаблон", callback_data="select_template"),
                    InlineKeyboardButton("ℹ️ О боте", callback_data="about")
                ]
            ]),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Ошибка при генерации PDF: {e}")
        await update.message.reply_text(
            f"❌ Ошибка при создании PDF:\n\n{str(e)}",
            parse_mode="Markdown"
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Update {update} вызвал ошибку {context.error}")
    if update.message:
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуй снова.")

def main():
    application = Application.builder().token(config.BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(select_template, pattern="select_template"))
    application.add_handler(CallbackQueryHandler(main_menu, pattern="main_menu"))
    application.add_handler(CallbackQueryHandler(about, pattern="about"))
    application.add_handler(CallbackQueryHandler(cancel, pattern="cancel"))
    application.add_handler(CallbackQueryHandler(template_selected, pattern="template_.*"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text))
    application.add_error_handler(error_handler)
    application.run_polling()

if __name__ == "__main__":
    main()
