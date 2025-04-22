
import os
import re
import logging
import pytz
import fitz  # PyMuPDF
from datetime import datetime
from flask import Flask, request, abort
from telegram import Update, InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
TEMPLATES = {
    "UR Recruitment LTD": "clean_template_no_text.pdf",
    "SMALL WORLD RECRUITMENT LTD": "template_small_world.pdf"
}

app = Flask(__name__)
telegram_app = ApplicationBuilder().token(TOKEN).build()
COLOR = (69/255, 69/255, 69/255)

logging.basicConfig(level=logging.INFO)

def get_london_date():
    return datetime.now(pytz.timezone("Europe/London")).strftime("%d.%m.%Y")

def replace_text(page, old_text, new_text):
    areas = page.search_for(old_text)
    for area in areas:
        page.add_redact_annot(area, fill=(1, 1, 1))
    page.apply_redactions()
    for area in areas:
        y_offset = 11 if "Date" in old_text else 0
        page.insert_text((area.x0, area.y0 + y_offset), new_text, fontname="helv", fontsize=11, color=COLOR)

def fill_pdf_template(template_path, output_path, client_name, date_str):
    doc = fitz.open(template_path)
    for page in doc:
        replace_text(page, "Client:", f"Client: {client_name}")
        replace_text(page, "Date:", f"Date: {date_str}")
    doc.save(output_path, garbage=4, deflate=True, clean=True)
    doc.close()

async def set_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(text=label, callback_data=label)] for label in TEMPLATES]
    await update.message.reply_text("Выберите шаблон:", reply_markup=InlineKeyboardMarkup(keyboard))

async def template_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected = query.data
    context.user_data['template'] = TEMPLATES[selected]
    await query.edit_message_text(f"Шаблон выбран: {selected}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client_name = update.message.text.strip()
    safe_name = re.sub(r'[^\w\s-]', '', client_name, flags=re.UNICODE).strip()
    template_path = context.user_data.get('template')
    if not template_path:
        await update.message.reply_text("Сначала выберите шаблон через /template")
        return
    output_path = f"{safe_name}.pdf"
    fill_pdf_template(template_path, output_path, safe_name, get_london_date())
    with open(output_path, "rb") as f:
        await update.message.reply_document(InputFile(f, filename=output_path))
    os.remove(output_path)
    keyboard = [[InlineKeyboardButton("Выбрать другой шаблон", callback_data="choose_template")]]
    await update.message.reply_text("Договор сгенерирован.", reply_markup=InlineKeyboardMarkup(keyboard))

@app.route("/telegram", methods=["POST"])
def webhook():
    if request.method == "POST":
        update = telegram_app.update_queue._application.bot._parse_update(request.json)
        telegram_app.create_task(telegram_app.process_update(update))
        return "ok"
    return abort(405)

@app.route('/')
def home():
    return "Bot is live"

@telegram_app.post_init
async def setup_webhook(application):
    await application.bot.set_webhook(WEBHOOK_URL)

telegram_app.add_handler(CommandHandler("template", set_template))
telegram_app.add_handler(CallbackQueryHandler(template_callback, pattern="^(UR Recruitment LTD|SMALL WORLD RECRUITMENT LTD)$"))
telegram_app.add_handler(CallbackQueryHandler(set_template, pattern="choose_template"))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
