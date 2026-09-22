import re
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Tuple
from datetime import datetime

# Соответствие русских названий месяцев их номерам
RUSSIAN_MONTHS = {
    "января": "01", "январь": "01",
    "февраля": "02", "февраль": "02",
    "марта": "03", "март": "03",
    "апреля": "04", "апрель": "04",
    "мая": "05", "май": "05",
    "июня": "06", "июнь": "06",
    "июля": "07", "июль": "07",
    "августа": "08", "август": "08",
    "сентября": "09", "сентябрь": "09",
    "октября": "10", "октябрь": "10",
    "ноября": "11", "ноябрь": "11",
    "декабря": "12", "декабрь": "12",
}

@dataclass
class InvoiceInfo:
    number: Optional[str] = None
    date: Optional[str] = None
    org: Optional[str] = None
    method: str = "text"  # "text" или "ocr"
    raw_text: str = ""


def sanitize_filename_part(text: str) -> str:
    """Удаляет недопустимые для имен файлов в Windows символы."""
    if not text:
        return ""
    # Заменяем запрещенные символы Windows \ / : * ? " < > |
    cleaned = re.sub(r'[\\/*?:"<>|]', '_', text)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def normalize_date(raw_date_str: str) -> Optional[str]:
    """Преобразует найденную дату в стандартный формат DD.MM.YYYY."""
    if not raw_date_str:
        return None
    raw = raw_date_str.strip().lower()
    raw = re.sub(r'[\sг\.]+$', '', raw).strip()

    # 1. Формат YYYY-MM-DD (ISO)
    iso_match = re.search(r'\b(\d{4})[\.\/\-](\d{1,2})[\.\/\-](\d{1,2})\b', raw)
    if iso_match:
        year, month, day = iso_match.groups()
        return f"{day.zfill(2)}.{month.zfill(2)}.{year}"

    # 2. Формат 15 мая 2024
    month_match = re.search(r'\b(\d{1,2})\s+([а-я]+)\s+(\d{2,4})\b', raw)
    if month_match:
        day, month_str, year = month_match.groups()
        month = RUSSIAN_MONTHS.get(month_str)
        if month:
            day = day.zfill(2)
            if len(year) == 2:
                year = "20" + year
            return f"{day}.{month}.{year}"

    # 3. Формат 15.05.2024 или 15/05/2024 или 15-05-2024
    num_match = re.search(r'\b(\d{1,2})[\.\/\-](\d{1,2})[\.\/\-](\d{2,4})\b', raw)
    if num_match:
        day, month, year = num_match.groups()
        day = day.zfill(2)
        month = month.zfill(2)
        if len(year) == 2:
            year = "20" + year
        return f"{day}.{month}.{year}"

    return None


def normalize_org_name(raw_org: str) -> str:
    """
    Сокращает длинные формы юридических лиц до общепринятых аббревиатур (ООО, АО, ИП и др.)
    и форматирует название организации для использования в имени файла.
    """
    if not raw_org:
        return ""

    text = raw_org.strip()

    # Словарь замен для организационно-правовых форм
    replacements = [
        # Общество с ограниченной ответственностью и варианты (огр. отв., огр отв и т.д.)
        (r'\bобществ[оа]\s+с\s+огр(?:аниченн[оы][йи]|\.)?\s*отв(?:етственност(?:ью|и)?|\.)?', 'ООО'),
        (r'\bо\.?\s*о\.?\s*о\.?', 'ООО'),

        # Акционерные общества (ПАО, НАО, ЗАО, ОАО, АО)
        (r'\bпубличн(?:ое|ого)\s+акционерн(?:ое|ого)\s+обществ[оа]\b', 'ПАО'),
        (r'\bнепубличн(?:ое|ого)\s+акционерн(?:ое|ого)\s+обществ[оа]\b', 'НАО'),
        (r'\bзакрыт(?:ое|ого)\s+акционерн(?:ое|ого)\s+обществ[оа]\b', 'ЗАО'),
        (r'\bоткрыт(?:ое|ого)\s+акционерн(?:ое|ого)\s+обществ[оа]\b', 'ОАО'),
        (r'\bакционерн(?:ое|ого)\s+обществ[оа]\b', 'АО'),

        # Индивидуальный предприниматель
        (r'\bиндивидуальн(?:ый|ого)\s+предпринимател(?:ь|я)\b', 'ИП'),
        (r'\bи\.?\s*п\.?', 'ИП'),

        # Автономная некоммерческая организация
        (r'\bавтономн(?:ая|ой)\s+некоммерческ(?:ая|ой)\s+организаци(?:я|и)\b', 'АНО'),

        # Товарищество с ограниченной ответственностью
        (r'\bтоварищество\s+с\s+ограниченной\s+ответственностью\b', 'ТОО'),
    ]

    for pattern, abbr in replacements:
        text = re.sub(pattern, abbr, text, flags=re.IGNORECASE)

    # Убираем случайную точку сразу после аббревиатуры (например "ООО." -> "ООО")
    text = re.sub(r'\b(ООО|ИП|АО|ПАО|НАО|ЗАО|ОАО|АНО|ТОО)\.+(?=\s|$)', r'\1', text)

    # Очищаем кавычки (двойные кавычки недопустимы в именах файлов Windows)
    text = re.sub(r'["«»„“\']', '', text)
    # Убираем множественные пробелы
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def extract_supplier_org(text: str) -> Optional[str]:
    """Извлекает наименование поставщика/исполнителя из текста счета."""
    patterns = [
        # Поставщик (Исполнитель): ООО "Ромашка", ИНН...
        r'(?:Поставщик|Исполнитель|Продавец|Организация)(?:\s*\([^\)]*\))?\s*[:\-]\s*([^\n\r]+)',
        # Получатель: ООО "Ромашка"
        r'(?:Получатель)\s*[:\-]\s*([^\n\r]+)',
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            raw_org = m.group(1).strip()
            # Обрезаем по ИНН / КПП / адресу если они идут следом через запятую
            raw_org = re.split(r'[,;]\s*(?:ИНН|КПП|ОГРН|тел|адрес|р\/с|р\.с|БИК)', raw_org, flags=re.IGNORECASE)[0]
            # Сокращаем организационно-правовую форму (например, общество с огр. отв. -> ООО)
            normalized = normalize_org_name(raw_org)
            # Очищаем спецсимволы для безопасного имени файла
            cleaned = sanitize_filename_part(normalized.strip(' .,;'))
            if cleaned and len(cleaned) <= 60:
                return cleaned
    return None


def extract_invoice_data_from_text(text: str) -> InvoiceInfo:
    """Ищет номер, дату и организацию в тексте счета с помощью регулярок."""
    info = InvoiceInfo(raw_text=text)

    # Префикс счета: Счет, Счёт, Заказ-счет и любые их составные формы (оферта, договор, фактура, заказ, на оплату и др.)
    invoice_prefix = (
        r'(?:(?:Счет|Счёт|Заказ-счет)'
        r'(?:[-—–\s]+(?:оферта|договор|фактура|заказ|проформа|акт|уведомление|квитанция))?'
        r'(?:[-—–\s]+(?:на\s+оплату|к\s+оплате|на\s+предоплату|на\s+аванс|за\s+услуги|на\s+услуги|на\s+поставку))?'
        r'|(?:Счет|Счёт)[\-—–\s]+[а-яА-Я]+(?:\s+на\s+оплату)?)'
    )

    # 1. Поиск номера и даты вместе (типично для 1С, счетов-оферт и стандартов)
    joint_patterns = [
        invoice_prefix + r'\s*(?:№|N|#|No\.?)?\s*([A-Za-zА-Яа-я0-9\-_/]+)\s+от\s+([0-9]{1,2}[\s\.\/][А-Яа-я0-9]+[\s\.\/][0-9]{2,4}(?:\s*г\.?)?)',
        r'СЧЕТ\s*(?:[-—–\s]+[А-Яа-я]+)*\s*(?:НА\s+ОПЛАТУ)?\s*(?:№|N|#)?\s*([A-Za-zА-Яа-я0-9\-_/]+)\s+ОТ\s+([0-9]{1,2}[\s\.\/][А-Яа-я0-9]+[\s\.\/][0-9]{2,4})',
        r'(?:Commercial\s+)?Invoice\s*(?:No\.?|#|number)?\s*[:№]?\s*([A-Za-z0-9\-_/]+)\s+(?:dated|date|of|from)\s+([0-9]{1,2}[\.\/\-][0-9]{1,2}[\.\/\-][0-9]{2,4})',
    ]

    for pat in joint_patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            raw_num = match.group(1).strip()
            raw_dt = match.group(2).strip()
            info.number = sanitize_filename_part(raw_num)
            info.date = normalize_date(raw_dt)
            break

    # 2. Если номер не найден по совместному шаблону, ищем только номер
    if not info.number:
        num_patterns = [
            invoice_prefix + r'\s*(?:№|N|#|No\.?)\s*([A-Za-zА-Яа-я0-9\-_/]+)',
            invoice_prefix + r'\s+([0-9]+[A-Za-zА-Яа-я0-9\-_/]*)',
            r'СЧЕТ\s*(?:[-—–\s]+[А-Яа-я]+)*\s*(?:НА\s+ОПЛАТУ)?\s*№?\s*([A-Za-zА-Яа-я0-9\-_/]+)',
            r'(?:Commercial\s+)?Invoice\s*(?:No\.?|#|number)?\s*[:№]?\s*([A-Za-z0-9\-_/]+)',
        ]
        for pat in num_patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                raw_num = match.group(1).strip()
                # Исключаем ложные срабатывания (например, если захватило "от" или слишком длинный текст)
                if len(raw_num) <= 30 and not re.match(r'^(?:от|на|для|к)$', raw_num, re.IGNORECASE):
                    info.number = sanitize_filename_part(raw_num)
                    break

    # 3. Если дата еще не найдена, ищем дату отдельно
    if not info.date:
        date_patterns = [
            r'от\s+([0-9]{1,2}\s+[а-яА-Я]+\s+[0-9]{4}(?:\s*г\.?)?)',
            r'от\s+([0-9]{1,2}[\.\/\-][0-9]{1,2}[\.\/\-][0-9]{2,4})',
            r'Дата(?:\s*счета)?\s*[:\-]\s*([0-9]{1,2}[\.\/\-][0-9]{1,2}[\.\/\-][0-9]{2,4})',
        ]
        for pat in date_patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                info.date = normalize_date(match.group(1))
                if info.date:
                    break

    # 4. Поиск организации
    info.org = extract_supplier_org(text)

    return info


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Извлекает цифровой текстовый слой из PDF файла."""
    full_text = []

    # Способ 1: PyMuPDF (fitz)
    try:
        import pymupdf as fitz
        doc = fitz.open(str(pdf_path))
        # Проверяем первые 3 страницы (обычно счет на 1-2 страницах)
        for i in range(min(3, len(doc))):
            page_text = doc[i].get_text()
            if page_text:
                full_text.append(page_text)
        doc.close()
        if full_text:
            return "\n".join(full_text)
    except Exception:
        pass

    # Способ 2: pypdf как запасной вариант
    try:
        import pypdf
        reader = pypdf.PdfReader(str(pdf_path))
        for i in range(min(3, len(reader.pages))):
            page_text = reader.pages[i].extract_text()
            if page_text:
                full_text.append(page_text)
        if full_text:
            return "\n".join(full_text)
    except Exception:
        pass

    return ""


def extract_ocr_from_pdf(pdf_path: Path, tesseract_cmd: str = "") -> str:
    """Распознает текст со страниц PDF с помощью OCR (Tesseract)."""
    try:
        import pymupdf as fitz
        import pytesseract
        from PIL import Image
        import io

        if tesseract_cmd and os.path.isfile(tesseract_cmd):
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        doc = fitz.open(str(pdf_path))
        ocr_texts = []
        for i in range(min(2, len(doc))):
            page = doc[i]
            # Рендерим страницу в изображение высокого разрешения (200 dpi)
            pix = page.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            try:
                # Пробуем распознать на русском и английском
                text = pytesseract.image_to_string(img, lang="rus+eng")
            except Exception:
                # Если языковой пакет rus отсутствует, пробуем стандартный
                text = pytesseract.image_to_string(img)
            if text:
                ocr_texts.append(text)
        doc.close()
        return "\n".join(ocr_texts)
    except Exception as e:
        print(f"Ошибка OCR распознавания: {e}")
        return ""


def parse_invoice_pdf(pdf_path: str | Path, ocr_enabled: bool = True, tesseract_cmd: str = "") -> InvoiceInfo:
    """
    Главная функция парсинга:
    1. Пробует извлечь цифровой текст.
    2. Если номер не найден и включен OCR - запускает распознавание.
    """
    path = Path(pdf_path)
    if not path.is_file():
        return InvoiceInfo()

    # 1. Цифровой слой
    digital_text = extract_text_from_pdf(path)
    info = extract_invoice_data_from_text(digital_text)
    info.method = "text"

    # Если номер найден, возвращаем результат
    if info.number:
        return info

    # 2. Если цифровой слой пуст или номер не найден, пробуем OCR
    if ocr_enabled:
        ocr_text = extract_ocr_from_pdf(path, tesseract_cmd=tesseract_cmd)
        if ocr_text:
            ocr_info = extract_invoice_data_from_text(ocr_text)
            if ocr_info.number:
                ocr_info.method = "ocr"
                return ocr_info

    return info
