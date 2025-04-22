import fitz  # PyMuPDF
import os
import re
from datetime import datetime
import pytz

# 🎯 Путь к шаблонам PDF (если лежат в корне, ничего менять не нужно)
TEMPLATES = {
    "UR Recruitment LTD": "clean_template_no_text.pdf",
    "SMALL WORLD RECRUITMENT LTD": "template_small_world.pdf"
}

# 🎨 Цвет текста (серый)
TEXT_COLOR = (69 / 255, 69 / 255, 69 / 255)

# 📍 Получить текущую дату по Лондону
def get_london_date() -> str:
    return datetime.now(pytz.timezone("Europe/London")).strftime("%d.%m.%Y")

# 🧽 Заменить текст на странице PDF
def replace_text(page, old_text, new_text):
    areas = page.search_for(old_text)
    for area in areas:
        page.add_redact_annot(area, fill=(1, 1, 1))  # белая заливка
    page.apply_redactions()
    for area in areas:
        y_offset = 8 if "Date" in old_text else 0
        page.insert_text(
            (area.x0, area.y0 + y_offset),
            new_text,
            fontname="helv",
            fontsize=11,
            color=TEXT_COLOR,
        )

# 📄 Генерация PDF по шаблону и тексту пользователя
def generate_pdf(template_path: str, user_text: str) -> str:
    safe_name = re.sub(r"[^\w\s-]", "", user_text, flags=re.UNICODE).strip()
    output_path = f"{safe_name}.pdf"
    doc = fitz.open(template_path)
    for page in doc:
        replace_text(page, "Client:", f"Client: {user_text}")
        replace_text(page, "Date:", f"Date: {get_london_date()}")
    doc.save(output_path, garbage=4, deflate=True, clean=True)
    doc.close()
    return output_path
