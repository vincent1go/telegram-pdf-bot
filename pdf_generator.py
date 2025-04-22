import os
import re
import fitz  # PyMuPDF
import pytz
from datetime import datetime

# Цвет текста (тёмно-серый)
COLOR = (69 / 255, 69 / 255, 69 / 255)

def текущая_дата_лондон():
    """Возвращает текущую дату в формате дд.мм.гггг (часовой пояс Лондона)"""
    return datetime.now(pytz.timezone("Europe/London")).strftime("%d.%m.%Y")

def очистить_имя_файла(text):
    """Удаляет опасные символы из текста для имени файла"""
    return re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip()

def заменить_текст_на_странице(page, старый_текст, новый_текст):
    """Находит текст на странице и заменяет его на новый"""
    области = page.search_for(старый_текст)
    for область in области:
        page.add_redact_annot(область, fill=(1, 1, 1))  # закрасить белым
    page.apply_redactions()
    for область in области:
        смещение_y = 8 if "Date" in старый_текст else 0
        page.insert_text(
            (область.x0, область.y0 + смещение_y),
            новый_текст,
            fontname="helv",
            fontsize=11,
            color=COLOR
        )

def generate_pdf(путь_к_шаблону: str, текст: str) -> str:
    """
    Заполняет PDF шаблон пользовательским текстом и сохраняет в файл.
    :param путь_к_шаблону: Путь к PDF шаблону
    :param текст: Текст пользователя (имя клиента, данные и т.д.)
    :return: Путь к сгенерированному PDF
    """
    дата = текущая_дата_лондон()
    имя_файла = очистить_имя_файла(текст) or "результат"
    путь_к_выходному_файлу = f"{имя_файла}.pdf"

    doc = fitz.open(путь_к_шаблону)
    for page in doc:
        заменить_текст_на_странице(page, "Client:", f"Client: {текст}")
        заменить_текст_на_странице(page, "Date:", f"Date: {дата}")
    doc.save(путь_к_выходному_файлу, garbage=4, deflate=True, clean=True)
    doc.close()

    return путь_к_выходному_файлу
