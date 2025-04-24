import os
import re
import fitz  # PyMuPDF
import pytz
from datetime import datetime
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Цвет текста (тёмно-серый)
COLOR = (69 / 255, 69 / 255, 69 / 255)

def текущая_дата_лондон():
    """Возвращает текущую дату в формате дд.мм.гггг (часовой пояс Киева)"""
    return datetime.now(pytz.timezone("Europe/Kiev")).strftime("%d.%m.%Y")

def очистить_имя_файла(text):
    """Удаляет опасные символы из текста для имени файла"""
    return re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip()

def заменить_текст_на_странице(page, старый_текст, новый_текст, is_date=False):
    """Находит текст на странице и заменяет его на новый"""
    области = page.search_for(старый_текст)
    if not области:
        logger.warning(f"Текст '{старый_текст}' не найден на странице {page.number + 1}")
        return False
    logger.info(f"Найдено {len(области)} вхождений '{старый_текст}' на странице {page.number + 1}")
    for область in области:
        page.add_redact_annot(область, fill=(1, 1, 1))  # закрасить белым
    page.apply_redactions()
    for область in области:
        смещение_y = 8 if is_date else 0
        page.insert_text(
            (область.x0, область.y0 + смещение_y),
            новый_текст,
            fontname="helv",
            fontsize=11,
            color=COLOR
        )
        logger.info(f"Заменено '{старый_текст}' на '{новый_текст}' в координатах {область} на странице {page.number + 1}")
    return True

def generate_pdf(путь_к_шаблону: str, текст: str) -> str:
    """
    Заполняет PDF шаблон пользовательским текстом и сохраняет в файл.
    :param путь_к_шаблону: Путь к PDF шаблону
    :param текст: Текст пользователя (имя клиента, данные и т.д.)
    :return: Путь к сгенерированному PDF
    """
    logger.info(f"Генерация PDF с шаблоном '{путь_к_шаблону}' и текстом '{текст}'")
    дата = текущая_дата_лондон()
    имя_файла = очистить_имя_файла(текст) or "результат"
    путь_к_выходному_файлу = f"{имя_файла}.pdf"

    try:
        doc = fitz.open(путь_к_шаблону)
    except Exception as e:
        logger.error(f"Ошибка открытия файла '{путь_к_шаблону}': {str(e)}")
        raise

    for page in doc:
        logger.info(f"Обработка страницы {page.number + 1}")
        if "contract_template3.pdf" in путь_к_шаблону:
            # Для MILA CONSULTANTS LTD
            if page.number == 0:  # Первая страница
                заменить_текст_на_странице(page, "Client: ", f"Client: {текст}")
            if page.number == 12:  # Последняя страница (PAGE13)
                заменить_текст_на_странице(page, "DATE: ", f"DATE: {дата}", is_date=True)
        else:
            # Для старых шаблонов (UR Recruitment LTD, SMALL WORLD RECRUITMENT LTD)
            if page.number == 0:  # Первая страница
                заменить_текст_на_странице(page, "Client: ", f"Client: {текст}")
            if page.number == 4:  # Последняя страница (PAGE5)
                заменить_текст_на_странице(page, "Date: ", f"Date: {дата}", is_date=True)

    try:
        doc.save(путь_к_выходному_файлу, garbage=4, deflate=True, clean=True)
        logger.info(f"PDF сохранен как '{путь_к_выходному_файлу}'")
    except Exception as e:
        logger.error(f"Ошибка сохранения PDF: {str(e)}")
        raise
    finally:
        doc.close()

    return путь_к_выходному_файлу
