import time
from pathlib import Path
import pymupdf as fitz
from checkrename.watcher import DownloadsWatcher

def test_watcher_detects_pdf(tmp_path: Path):
    detected_files = []

    def callback(file_path: Path):
        detected_files.append(file_path)

    watcher = DownloadsWatcher(str(tmp_path), callback)
    watcher.start()

    try:
        # Создаем PDF в отслеживаемой папке
        test_pdf = tmp_path / "incoming_invoice.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 72), "Счет № 999", fontsize=12)
        doc.save(str(test_pdf))
        doc.close()

        # Ждем обработки
        timeout = 5.0
        start = time.time()
        while time.time() - start < timeout and not detected_files:
            time.sleep(0.2)

        assert len(detected_files) == 1
        assert detected_files[0].name == "incoming_invoice.pdf"
    finally:
        watcher.stop()
