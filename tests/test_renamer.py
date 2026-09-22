import pytest
from pathlib import Path
from docrename.config import AppConfig
from docrename.renamer import Renamer
from docrename.parser import InvoiceInfo

def test_format_new_name_default(tmp_path: Path):
    config = AppConfig()
    renamer = Renamer(config)

    file_path = tmp_path / "original_download.pdf"
    info = InvoiceInfo(number="123", date="01.05.2024", org="ООО Тест")

    name = renamer.format_new_name(file_path, info)
    assert name == "Счет №123 (ООО Тест - 01.05.2024)"


def test_format_new_name_partial_fields(tmp_path: Path):
    config = AppConfig()
    renamer = Renamer(config)
    file_path = tmp_path / "doc.pdf"

    # Только номер и дата
    info_no_org = InvoiceInfo(number="45", date="12.08.2024")
    assert renamer.format_new_name(file_path, info_no_org) == "Счет №45 (12.08.2024)"

    # Только номер и организация
    info_no_date = InvoiceInfo(number="45", org="ООО Вектор")
    assert renamer.format_new_name(file_path, info_no_date) == "Счет №45 (ООО Вектор)"

    # Только номер
    info_only_num = InvoiceInfo(number="45")
    assert renamer.format_new_name(file_path, info_only_num) == "Счет №45"


def test_format_new_name_custom_template(tmp_path: Path):
    config = AppConfig(pattern="Счет_{number}_от_{date}_{org}")
    renamer = Renamer(config)

    file_path = tmp_path / "invoice.pdf"
    info = InvoiceInfo(number="99", date="10.10.2024", org="Альфа")

    name = renamer.format_new_name(file_path, info)
    assert name == "Счет_99_от_10.10.2024_Альфа"


def test_rename_in_place_and_collision(tmp_path: Path):
    config = AppConfig(pattern="счет {number}", move_enabled=False)
    renamer = Renamer(config)

    file1 = tmp_path / "download1.pdf"
    file1.write_text("dummy")

    info = InvoiceInfo(number="500")

    # Первое переименование
    res1 = renamer.process_file(file1, info)
    assert res1 is not None
    assert res1.name == "счет 500.pdf"
    assert res1.exists()
    assert not file1.exists()

    # Создаем второй файл с тем же номером
    file2 = tmp_path / "download2.pdf"
    file2.write_text("dummy 2")

    # Должен добавиться суффикс (1)
    res2 = renamer.process_file(file2, info)
    assert res2 is not None
    assert res2.name == "счет 500 (1).pdf"
    assert res2.exists()


def test_rename_with_move(tmp_path: Path):
    dest_dir = tmp_path / "invoices_folder"
    config = AppConfig(pattern="счет {number}", move_enabled=True, destination_folder=str(dest_dir))
    renamer = Renamer(config)

    file1 = tmp_path / "incoming.pdf"
    file1.write_text("pdf content")

    info = InvoiceInfo(number="777")
    res = renamer.process_file(file1, info)

    assert res is not None
    assert res.parent == dest_dir
    assert res.name == "счет 777.pdf"
    assert res.exists()
    assert not file1.exists()


def test_undo_operation(tmp_path: Path):
    config = AppConfig(pattern="счет {number}", move_enabled=False)
    renamer = Renamer(config)

    file1 = tmp_path / "my_bill.pdf"
    file1.write_text("data")

    info = InvoiceInfo(number="100")
    new_path = renamer.process_file(file1, info)
    assert new_path.name == "счет 100.pdf"
    assert not file1.exists()

    # Выполняем отмену (Undo)
    undo_res = renamer.undo_last()
    assert undo_res is not None
    curr, restored = undo_res
    assert restored.name == "my_bill.pdf"
    assert restored.exists()
    assert not new_path.exists()
