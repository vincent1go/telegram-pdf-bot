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

def заменить_текст_на_странице(page, старый_текст, новый_текст, is_date=False, only_first=False):
    """Находит текст на странице и заменяет его на новый"""
    области = page.search_for(старый_текст)
    if not области:
        logger.warning(f"Текст '{старый_текст}' не найден на странице {page.number + 1}")
        return False
    logger.info(f"Найдено {len(области)} вхождений '{старый_текст}' на странице {page.number + 1}")
    
    # Если only_first=True, берем только первое вхождение
    области_для_замены = [области[0]] if only_first and области else области
    
    # Закрашиваем области
    for область in области_для_замены:
        # Расширяем область закрашивания, чтобы гарантированно удалить старый текст
        расширенная_область = fitz.Rect(
            область.x0 - 5, область.y0 - 5,
            область.x1 + 50, область.y1 + 5
        )
        page.add_redact_annot(расширенная_область, fill=(1, 1, 1))  # закрасить белым
    page.apply_redactions()
    
    # Вставляем новый текст
    for область in области_для_замены:
        смещение_y = 15 if is_date else 0  # Увеличиваем смещение для дат
        page.insert_text(
            (область.x0, область.y0 + смещение_y),
            новый_текст,
            fontname="helv",
            fontsize=11,
            color=COLOR
        )
        logger.info(f"Заменено '{старый_текст}' на '{новый_текст}' в координатах {(область.x0, область.y0 + смещение_y)} на странице {page.number + 1}")
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
                # Для template_small_world.pdf заменяем только первое вхождение Date:
                only_first = "template_small_world.pdf" in путь_к_шаблону
                заменить_текст_на_странице(page, "Date: ", f"Date: {дата}", is_date=True, only_first=only_first)

    try:
        doc.save(путь_к_выходному_файлу, garbage=4, deflate=True, clean=True)
        logger.info(f"PDF сохранен как '{путь_к_выходному_файлу}'")
    except Exception as e:
        logger.error(f"Ошибка сохранения PDF: {str(e)}")
        raise
    finally:
        doc.close()

    return путь_к_выходному_файлу
