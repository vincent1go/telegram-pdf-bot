import logging
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

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# User states
SELECTING_TEMPLATE = 1
ENTERING_TEXT = 2

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command with a welcoming message and navigation buttons."""
    welcome_message = (
        "👋 *Welcome to the PDF Generator Bot!* 🚀\n\n"
        "I help you create PDFs from predefined templates by filling them with your text.\n\n"
        "*How it works:*\n"
        "- Select a template from the list.\n"
        "- Provide the text to fill the template.\n"
        "- Receive a customized PDF file! 📄\n\n"
        "Let's get started!"
    )
    keyboard = [
        [
            InlineKeyboardButton("📄 Select Template", callback_data="select_template"),
            InlineKeyboardButton("ℹ️ About Bot", callback_data="about"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(welcome_message, parse_mode="Markdown", reply_markup=reply_markup)

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle 'About Bot' button with bot info and a back button."""
    query = update.callback_query
    await query.answer()
    about_message = (
        "ℹ️ *About PDF Generator Bot*\n\n"
        "This bot creates PDFs from templates using your input text. 📄\n"
        "Built with ❤️ by [Your Name].\n"
        "Source: [GitHub](https://github.com/vincent1go/telegram-pdf-bot)\n\n"
        "Ready to create a PDF? Let's go back to the menu! 🔄"
    )
    keyboard = [[InlineKeyboardButton("🏠 Back to Menu", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(about_message, parse_mode="Markdown", reply_markup=reply_markup, disable_web_page_preview=True)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return to the main menu with the welcome message."""
    query = update.callback_query
    await query.answer()
    welcome_message = (
        "👋 *Welcome back to the PDF Generator Bot!* 🚀\n\n"
        "Choose an option to continue:"
    )
    keyboard = [
        [
            InlineKeyboardButton("📄 Select Template", callback_data="select_template"),
            InlineKeyboardButton("ℹ️ About Bot", callback_data="about"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(welcome_message, parse_mode="Markdown", reply_markup=reply_markup)

async def select_template(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display template selection with a compact inline keyboard."""
    query = update.callback_query
    await query.answer()
    message = "*📄 Choose a Template*\n\nSelect a template to start creating your PDF:"
    keyboard = []
    template_names = list(config.TEMPLATES.keys())
    # Create two buttons per row
    for i in range(0, len(template_names), 2):
        row = [
            InlineKeyboardButton(f"📄 {template_names[i]}", callback_data=f"template_{template_names[i]}")
        ]
        if i + 1 < len(template_names):
            row.append(InlineKeyboardButton(f"📄 {template_names[i+1]}", callback_data=f"template_{template_names[i+1]}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(message, parse_mode="Markdown", reply_markup=reply_markup)
    context.user_data["state"] = SELECTING_TEMPLATE

async def template_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle template selection and prompt for text input."""
    query = update.callback_query
    await query.answer()
    template_name = query.data.replace("template_", "")
    if template_name not in config.TEMPLATES:
        await query.message.edit_text(
            "⚠️ *Error*: Invalid template selected.\n\nPlease choose a valid template.",
            parse_mode="Markdown"
        )
        return
    context.user_data["template"] = template_name
    message = (
        f"✅ *Template Selected*: {template_name}\n\n"
        "📝 Please send the text to fill the template.\n"
        "Make sure your text matches the template's requirements.\n\n"
        "You can also start over if needed."
    )
    keyboard = [
        [
            InlineKeyboardButton("🔄 Start Over", callback_data="select_template"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(message, parse_mode="Markdown", reply_markup=reply_markup)
    context.user_data["state"] = ENTERING_TEXT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle cancellation and return to main menu."""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    message = "❌ *Operation Cancelled*\n\nChoose an option to continue:"
    keyboard = [
        [
            InlineKeyboardButton("📄 Select Template", callback_data="select_template"),
            InlineKeyboardButton("ℹ️ About Bot", callback_data="about"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(message, parse_mode="Markdown", reply_markup=reply_markup)

async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text input and generate PDF."""
    if context.user_data.get("state") != ENTERING_TEXT:
        await update.message.reply_text(
            "⚠️ *Error*: Please select a template first using the menu.",
            parse_mode="Markdown"
        )
        return
    text = update.message.text
    template_name = context.user_data.get("template")
    template_path = config.TEMPLATES.get(template_name)
    try:
        pdf_path = generate_pdf(template_path, text)
        with open(pdf_path, "rb") as file:
            await update.message.reply_document(
                document=file,
                caption=f"✅ *Your PDF is ready!* 🎉\n\nTemplate: {template_name}",
                parse_mode="Markdown"
            )
        message = (
            "🚀 *PDF Generated Successfully!*\n\n"
            "Would you like to create another PDF or learn more about the bot?"
        )
        keyboard = [
            [
                InlineKeyboardButton("📄 Select Template", callback_data="select_template"),
                InlineKeyboardButton("ℹ️ About Bot", callback_data="about"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message, parse_mode="Markdown", reply_markup=reply_markup)
        context.user_data.clear()
    except Exception as e:
        logger.error(f"Error generating PDF: {e}")
        message = (
            "❌ *Error*: Failed to generate PDF.\n\n"
            f"Details: {str(e)}\n\n"
            "Please try again or select a different template."
        )
        keyboard = [
            [
                InlineKeyboardButton("🔄 Start Over", callback_data="select_template"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message, parse_mode="Markdown", reply_markup=reply_markup)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and notify user."""
    logger.error(f"Update {update} caused error {context.error}")
    if update.message:
        await update.message.reply_text(
            "⚠️ *Error*: Something went wrong.\n\nPlease try again or contact support.",
            parse_mode="Markdown"
        )

def main() -> None:
    """Run the bot."""
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
