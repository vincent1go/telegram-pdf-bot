import os

# 🔐 Токен Telegram-бота (установи в переменных окружения на Render)
BOT_TOKEN = os.getenv("7511704960:AAH-rIBOQkhzYvTVOp2tiodxzK3vp8GUiYM")

# 👤 ID администратора (может пригодиться для логов или отправки уведомлений)
ADMIN_ID = os.getenv("ADMIN_ID")

# 🌐 Вебхук URL (например: https://имя-проекта.onrender.com/telegram)
WEBHOOK_URL = os.getenv("https://telegram-pdf-bot-1f5c.onrender.com/telegram")

# 📄 Пути к PDF-шаблонам (названия => файл)
TEMPLATES = {
    "UR Recruitment LTD": "clean_template_no_text.pdf",
    "SMALL WORLD RECRUITMENT LTD": "template_small_world.pdf"
}
