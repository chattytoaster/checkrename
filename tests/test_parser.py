import pytest
from pathlib import Path
import pymupdf as fitz  # PyMuPDF
from checkrename.parser import (
    extract_invoice_data_from_text,
    normalize_date,
    sanitize_filename_part,
    extract_supplier_org,
    normalize_org_name,
    parse_invoice_pdf
)

def test_normalize_org_name():
    assert normalize_org_name("Общество с ограниченной ответственностью «Ромашка»") == "ООО Ромашка"
    assert normalize_org_name("общество с огр отв Вектор") == "ООО Вектор"
    assert normalize_org_name("Общество с огр. отв. Лидер") == "ООО Лидер"
    assert normalize_org_name("Индивидуальный предприниматель Иванов И.И.") == "ИП Иванов И.И."
    assert normalize_org_name("Публичное акционерное общество Сбербанк") == "ПАО Сбербанк"
    assert normalize_org_name("Акционерное общество «Тинькофф Банк»") == "АО Тинькофф Банк"


def test_normalize_date():
    assert normalize_date("15 мая 2024 г.") == "15.05.2024"
    assert normalize_date("1 января 2025") == "01.01.2025"
    assert normalize_date("15.05.2024") == "15.05.2024"
    assert normalize_date("2024-08-20") == "20.08.2024"
    assert normalize_date("не дата") is None


def test_sanitize_filename_part():
    assert sanitize_filename_part('Счет "Ромашка" № 12/3:тест') == 'Счет _Ромашка_ № 12_3_тест'
    assert sanitize_filename_part("  тест   пробелов  ") == "тест пробелов"


def test_extract_invoice_data_joint_1c():
    text = """
    Индивидуальный предприниматель Иванов И.И.
    Поставщик: ООО "Рога и Копыта", ИНН 7701234567, КПП 770101001
    Покупатель: ООО "Клиент"

    Счет на оплату № 1054 от 25 мая 2024 г.

    Всего к оплате: 150 000,00 руб.
    """
    info = extract_invoice_data_from_text(text)
    assert info.number == "1054"
    assert info.date == "25.05.2024"
    assert "Рога и Копыта" in (info.org or "")


def test_extract_invoice_data_short():
    text = "Счет № 42-АБ от 10.02.2024"
    info = extract_invoice_data_from_text(text)
    assert info.number == "42-АБ"
    assert info.date == "10.02.2024"


def test_extract_invoice_english():
    text = "Commercial Invoice No. INV-9982 from 12.11.2024"
    info = extract_invoice_data_from_text(text)
    assert info.number == "INV-9982"
    assert info.date == "12.11.2024"


def test_parse_real_pdf(tmp_path: Path):
    pdf_path = tmp_path / "test_invoice.pdf"
    doc = fitz.open()
    page = doc.new_page()
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    if font_path.exists():
        page.insert_font(fontname="arial", fontfile=str(font_path))
        page.insert_text(
            (50, 72),
            "Поставщик: ООО Ромашка, ИНН 1234567890\nСчет на оплату № 789 от 14 апреля 2024 г.",
            fontname="arial",
            fontsize=12
        )
    else:
        page.insert_text(
            (50, 72),
            "Invoice No. 789 dated 14.04.2024",
            fontsize=12
        )
    doc.save(str(pdf_path))
    doc.close()

    info = parse_invoice_pdf(pdf_path, ocr_enabled=False)
    assert info.number == "789"
    assert info.date == "14.04.2024"

