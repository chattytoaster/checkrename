import pytest
from pathlib import Path
from checkrename.config import AppConfig
from checkrename.parser import InvoiceInfo
from checkrename.renamer import Renamer
from checkrename.tracker import ProcessedTracker, set_ads_marker, has_ads_marker, remove_ads_marker
from checkrename.watcher import DownloadsHandler
from watchdog.events import FileMovedEvent, FileCreatedEvent

def test_tracker_lifecycle(tmp_path: Path):
    db_file = tmp_path / "processed.json"
    tracker = ProcessedTracker(storage_path=db_file)

    f1 = tmp_path / "doc1.pdf"
    f1.write_text("dummy")

    assert not tracker.is_processed(f1)

    f1_renamed = tmp_path / "Счет №100.pdf"
    f1.rename(f1_renamed)

    tracker.mark_processed(f1, f1_renamed, invoice_number="100")
    assert tracker.is_processed(f1_renamed)

    # Перезагружаем трекер из файла на диске
    tracker2 = ProcessedTracker(storage_path=db_file)
    assert tracker2.is_processed(f1_renamed)


def test_renamer_only_renames_once(tmp_path: Path):
    db_file = tmp_path / "processed.json"
    tracker = ProcessedTracker(storage_path=db_file)
    config = AppConfig(pattern="Счет №{number}")
    renamer = Renamer(config, tracker=tracker)

    original_file = tmp_path / "документ.pdf"
    original_file.write_text("pdf dummy content")

    info = InvoiceInfo(number="3892", date="21.09.2026", org="ООО Центр")

    # 1. Первое появление файла: переименовываем
    result_path = renamer.process_file(original_file, info)
    assert result_path is not None
    assert result_path.name == "Счет №3892.pdf"
    assert result_path.exists()
    assert not original_file.exists()

    # 2. Пользователь модифицировал название файла, добавив статус
    user_custom_path = tmp_path / "Счет №3892 ОПЛАЧЕН.pdf"
    result_path.rename(user_custom_path)
    tracker.update_path(result_path, user_custom_path)

    # 3. Повторная попытка переименования (например, при сохранении правок или повторном сканировании):
    # НЕ должна возвращать файл к исходному "Счет №3892.pdf"!
    second_result = renamer.process_file(user_custom_path, info)
    assert second_result == user_custom_path
    assert user_custom_path.name == "Счет №3892 ОПЛАЧЕН.pdf"
    assert user_custom_path.exists()


def test_watcher_ignores_pdf_to_pdf_rename(tmp_path: Path):
    db_file = tmp_path / "processed.json"
    tracker = ProcessedTracker(storage_path=db_file)

    callback_calls = []
    def dummy_callback(path: Path):
        callback_calls.append(path)

    handler = DownloadsHandler(callback=dummy_callback, tracker=tracker)

    # Симулируем переименование пользователем .pdf -> .pdf
    event_user_rename = FileMovedEvent(
        src_path=str(tmp_path / "Счет №123.pdf"),
        dest_path=str(tmp_path / "Счет №123 ОПЛАЧЕН.pdf")
    )
    handler.on_moved(event_user_rename)

    # Коллбэк переименования НЕ должен вызываться
    assert len(callback_calls) == 0

    # Проверяем, что новое имя занесено в трекер
    assert tracker.is_processed(tmp_path / "Счет №123 ОПЛАЧЕН.pdf")


def test_watcher_handles_download_completion(tmp_path: Path):
    db_file = tmp_path / "processed.json"
    tracker = ProcessedTracker(storage_path=db_file)

    callback_calls = []
    def dummy_callback(path: Path):
        callback_calls.append(path)

    handler = DownloadsHandler(callback=dummy_callback, tracker=tracker)

    pdf_file = tmp_path / "incoming.pdf"
    # Создаем валидный заголовок PDF
    pdf_file.write_bytes(b"%PDF-1.4 dummy content")

    event_download_finished = FileMovedEvent(
        src_path=str(tmp_path / "incoming.pdf.crdownload"),
        dest_path=str(pdf_file)
    )
    handler.on_moved(event_download_finished)

    import time
    time.sleep(1.0)

    # Скачивание должно быть распознано и передано в коллбэк
    assert len(callback_calls) == 1
    assert callback_calls[0].name == "incoming.pdf"
