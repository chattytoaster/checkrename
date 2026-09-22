from pathlib import Path
from typing import Optional
from PyQt6.QtWidgets import (
    QSystemTrayIcon, QMenu, QApplication, QMessageBox
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import QObject, pyqtSignal

from checkrename.config import AppConfig
from checkrename.parser import parse_invoice_pdf, InvoiceInfo
from checkrename.renamer import Renamer
from checkrename.watcher import DownloadsWatcher
from checkrename.ui.resources import create_app_icon
from checkrename.ui.settings_dialog import SettingsDialog

class TrayManager(QObject):
    file_renamed = pyqtSignal(str, str) # old_name, new_name

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.renamer = Renamer(config)
        self.settings_dialog: Optional[SettingsDialog] = None

        # Инициализация слушателя
        self.watcher = DownloadsWatcher(
            watch_folder=self.config.watch_folder,
            callback=self.handle_incoming_file,
            tracker=self.renamer.tracker
        )

        self._init_tray()

        if self.config.watch_enabled:
            self.watcher.start()

    def _init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self._update_icon()

        self.menu = QMenu()

        # Заголовок меню
        self.act_title = QAction("CheckRename — Мониторинг счетов", self.menu)
        self.act_title.setEnabled(False)
        self.menu.addAction(self.act_title)
        self.menu.addSeparator()

        # Тумблер мониторинга
        self.act_watch = QAction("Мониторинг папки Загрузки", self.menu)
        self.act_watch.setCheckable(True)
        self.act_watch.setChecked(self.config.watch_enabled)
        self.act_watch.toggled.connect(self._toggle_watching)
        self.menu.addAction(self.act_watch)

        # Отмена последнего переименования
        self.act_undo = QAction("Отменить последнее переименование (Undo)", self.menu)
        self.act_undo.triggered.connect(self._handle_undo)
        self.menu.addAction(self.act_undo)

        self.menu.addSeparator()

        # Настройки
        self.act_settings = QAction("Настройки...", self.menu)
        self.act_settings.triggered.connect(self.show_settings)
        self.menu.addAction(self.act_settings)

        self.menu.addSeparator()

        # Выход
        self.act_quit = QAction("Выход", self.menu)
        self.act_quit.triggered.connect(self._quit_app)
        self.menu.addAction(self.act_quit)

        self.tray_icon.setContextMenu(self.menu)
        self.tray_icon.setToolTip("CheckRename — Автопереименование PDF-счетов")
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _update_icon(self):
        icon = create_app_icon(active=self.config.watch_enabled)
        self.tray_icon.setIcon(icon)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_settings()

    def _toggle_watching(self, checked: bool):
        self.config.watch_enabled = checked
        self.config.save()
        if checked:
            self.watcher.restart(self.config.watch_folder)
        else:
            self.watcher.stop()
        self._update_icon()

    def show_settings(self):
        if self.settings_dialog is None:
            self.settings_dialog = SettingsDialog(self.config)
            self.settings_dialog.settings_saved.connect(self._on_settings_saved)
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def _on_settings_saved(self, new_config: AppConfig):
        self.config = new_config
        self.renamer.config = new_config
        self.act_watch.setChecked(self.config.watch_enabled)
        if self.config.watch_enabled:
            self.watcher.restart(self.config.watch_folder)
        else:
            self.watcher.stop()
        self._update_icon()

    def notify(self, title: str, message: str, is_error: bool = False):
        """Отображает всплывающее уведомление Windows."""
        if not self.config.show_notifications:
            return
        icon = QSystemTrayIcon.MessageIcon.Warning if is_error else QSystemTrayIcon.MessageIcon.Information
        self.tray_icon.showMessage(title, message, icon, 4000)

    def process_pdf_file(self, file_path: Path, silent_if_not_invoice: bool = True, force: bool = False) -> bool:
        """
        Обрабатывает PDF файл: парсит, извлекает данные и переименовывает.
        """
        if not file_path.is_file() or file_path.suffix.lower() != ".pdf":
            return False

        if not force and self.renamer.tracker.is_processed(file_path):
            return False

        orig_name = file_path.name
        info: InvoiceInfo = parse_invoice_pdf(
            file_path,
            ocr_enabled=self.config.ocr_enabled,
            tesseract_cmd=self.config.tesseract_path
        )

        if not info.number:
            if not silent_if_not_invoice:
                self.notify(
                    "Номер счета не найден",
                    f"В файле {orig_name} не удалось обнаружить номер счета на оплату.",
                    is_error=True
                )
            return False

        new_path = self.renamer.process_file(file_path, info, force=force)
        if new_path:
            if new_path.resolve() == file_path.resolve():
                if not force:
                    # Файл уже имел требуемое имя или пользовательское дополнение
                    return False
                else:
                    self.notify("Счет распознан", f"Файл уже имеет требуемое имя:\n{new_path.name}")
                    return True

            extra = []
            if info.date:
                extra.append(f"Дата: {info.date}")
            if info.org:
                extra.append(f"Организация: {info.org}")
            extra_str = f" ({', '.join(extra)})" if extra else ""

            msg = f"Файл переименован в:\n{new_path.name}\n№ счета: {info.number}{extra_str}"
            self.notify("Счет распознан и переименован", msg)
            self.file_renamed.emit(orig_name, new_path.name)
            return True
        else:
            if not silent_if_not_invoice:
                self.notify("Ошибка переименования", f"Не удалось переименовать файл {orig_name}.", is_error=True)
            return False

    def handle_incoming_file(self, file_path: Path):
        """Коллбэк от watcher при обнаружении нового файла в папке Загрузок."""
        if not self.config.watch_enabled:
            return
        self.process_pdf_file(file_path, silent_if_not_invoice=True)

    def _handle_undo(self):
        res = self.renamer.undo_last()
        if res:
            curr, restored = res
            self.notify("Отмена переименования", f"Файл возвращен:\n{restored.name}")
        else:
            self.notify("Отмена действия", "История операций пуста или файл уже перемещен/удален.", is_error=True)

    def _quit_app(self):
        self.watcher.stop()
        self.tray_icon.hide()
        QApplication.quit()
