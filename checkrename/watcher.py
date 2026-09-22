import os
import time
import threading
from pathlib import Path
from typing import Callable, Optional, Set
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent
from checkrename.tracker import ProcessedTracker, default_tracker

IGNORED_EXTENSIONS = {'.crdownload', '.tmp', '.part', '.download', '.swp'}

class DownloadsHandler(FileSystemEventHandler):
    def __init__(self, callback: Callable[[Path], None], tracker: Optional[ProcessedTracker] = None):
        super().__init__()
        self.callback = callback
        self.tracker = tracker or default_tracker
        self._processed_files: Set[str] = set()
        self._lock = threading.Lock()

    def _should_ignore(self, path_str: str) -> bool:
        path = Path(path_str)
        if path.suffix.lower() in IGNORED_EXTENSIONS:
            return True
        if path.name.startswith(('~$', '.')):
            return True
        if path.suffix.lower() != '.pdf':
            return True
        return False

    def _wait_until_ready(self, file_path: Path, timeout: float = 15.0) -> bool:
        """
        Ожидает, пока браузер или другая программа закончит запись в файл
        и снимет блокировку.
        """
        start_time = time.time()
        last_size = -1

        while time.time() - start_time < timeout:
            if not file_path.exists():
                return False
            try:
                current_size = file_path.stat().st_size
                # Пробуем открыть файл на чтение
                with open(file_path, "rb") as f:
                    # Читаем первые байты для проверки валидности
                    header = f.read(10)
                    if len(header) >= 4 and header.startswith(b'%PDF'):
                        if current_size == last_size and current_size > 0:
                            # Размер стабилен и файл доступен
                            return True
                        last_size = current_size
            except (PermissionError, OSError):
                # Файл еще заблокирован пишущим процессом
                pass

            time.sleep(0.5)

        # Финальная проверка
        try:
            with open(file_path, "rb") as f:
                return f.read(4) == b'%PDF'
        except Exception:
            return False

    def _handle_path(self, path_str: str):
        if self._should_ignore(path_str):
            return

        file_path = Path(path_str).resolve()

        # Если файл уже был обработан CheckRename, не трогаем его
        if self.tracker.is_processed(file_path):
            return

        norm_path = str(file_path)

        with self._lock:
            if norm_path in self._processed_files:
                return
            self._processed_files.add(norm_path)

        # Запускаем обработку в отдельном потоке, чтобы не блокировать события watchdog
        def worker():
            try:
                if self._wait_until_ready(file_path):
                    # Повторная проверка после ожидания доступности
                    if not self.tracker.is_processed(file_path):
                        self.callback(file_path)
            finally:
                # Через 10 секунд удаляем из множества недавних
                time.sleep(10)
                with self._lock:
                    self._processed_files.discard(norm_path)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def on_created(self, event: FileCreatedEvent):
        if not event.is_directory:
            self._handle_path(event.src_path)

    def on_moved(self, event: FileMovedEvent):
        if event.is_directory:
            return

        src = Path(event.src_path)
        dest = Path(event.dest_path)

        # Если существующий PDF переименовывается в другой PDF (пользователь добавил текст или CheckRename переместил)
        if src.suffix.lower() == '.pdf' and dest.suffix.lower() == '.pdf':
            # Обновляем трекер, но НЕ запускаем повторное автоматическое переименование
            self.tracker.update_path(src, dest)
            return

        # Завершение скачивания из браузера (.crdownload -> .pdf, .part -> .pdf, .tmp -> .pdf и т.п.)
        if dest.suffix.lower() == '.pdf':
            self._handle_path(event.dest_path)


class DownloadsWatcher:
    def __init__(
        self,
        watch_folder: str,
        callback: Callable[[Path], None],
        tracker: Optional[ProcessedTracker] = None
    ):
        self.watch_folder = watch_folder
        self.callback = callback
        self.tracker = tracker or default_tracker
        self.observer: Optional[Observer] = None
        self._is_running = False

    def start(self):
        if self._is_running:
            return

        watch_path = Path(self.watch_folder)
        if not watch_path.is_dir():
            try:
                watch_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                print(f"Не удалось создать папку для мониторинга {watch_path}: {e}")
                return

        handler = DownloadsHandler(self.callback, tracker=self.tracker)
        self.observer = Observer()
        self.observer.schedule(handler, str(watch_path), recursive=False)
        self.observer.daemon = True
        self.observer.start()
        self._is_running = True

    def stop(self):
        if not self._is_running or not self.observer:
            return
        try:
            self.observer.stop()
            self.observer.join(timeout=2)
        except Exception:
            pass
        self._is_running = False
        self.observer = None

    def restart(self, new_watch_folder: Optional[str] = None):
        self.stop()
        if new_watch_folder:
            self.watch_folder = new_watch_folder
        self.start()

    @property
    def is_running(self) -> bool:
        return self._is_running
