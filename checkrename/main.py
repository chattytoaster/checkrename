import sys
import os
import argparse
from pathlib import Path

# Обеспечиваем корректный импорт пакета при любом способе запуска файла
_pkg_root = Path(__file__).resolve().parent.parent
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon
from PyQt6.QtCore import QTimer, Qt

from checkrename.config import AppConfig
from checkrename.parser import parse_invoice_pdf
from checkrename.renamer import Renamer
from checkrename.ui.tray import TrayManager
from checkrename.ui.resources import create_app_icon
from checkrename.context_menu import (
    register_context_menu, unregister_context_menu, is_context_menu_registered,
    set_autostart, is_autostart_registered
)

def set_windows_app_id():
    """Устанавливает явный AppUserModelID для Windows, чтобы уведомления приходили от CheckRename, а не от python."""
    try:
        import ctypes
        myappid = "CheckRename.PDFRenamer.1.0"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

def handle_single_file_cli(file_path_str: str):
    """
    Обработка файла при вызове из контекстного меню Проводника (ПКМ «Найти номер счета»).
    """
    set_windows_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName("CheckRename")
    app.setApplicationDisplayName("CheckRename")
    app.setOrganizationName("CheckRename")
    app.setQuitOnLastWindowClosed(False)

    config = AppConfig.load()
    renamer = Renamer(config)
    path = Path(file_path_str).resolve()

    tray = QSystemTrayIcon()
    tray.setIcon(create_app_icon(active=True))
    tray.show()

    def finish():
        tray.hide()
        app.quit()

    if not path.is_file():
        tray.showMessage("Ошибка", f"Файл не найден: {path.name}", QSystemTrayIcon.MessageIcon.Warning, 4000)
        QTimer.singleShot(3500, finish)
        sys.exit(app.exec())

    info = parse_invoice_pdf(
        path,
        ocr_enabled=config.ocr_enabled,
        tesseract_cmd=config.tesseract_path
    )

    if not info.number:
        tray.showMessage(
            "Номер счета не найден",
            f"В файле «{path.name}» не удалось обнаружить номер счета на оплату.",
            QSystemTrayIcon.MessageIcon.Warning,
            4500
        )
    else:
        new_path = renamer.process_file(path, info, force=True)
        if new_path:
            if new_path.resolve() == path.resolve():
                tray.showMessage(
                    "Счет проверен",
                    f"Файл уже имеет требуемое имя:\n{new_path.name}\n№ счета: {info.number}",
                    QSystemTrayIcon.MessageIcon.Information,
                    4500
                )
            else:
                details = []
                if info.date:
                    details.append(f"Дата: {info.date}")
                if info.org:
                    details.append(f"Организация: {info.org}")
                det_str = f"\n({', '.join(details)})" if details else ""

                tray.showMessage(
                    "Счет успешно переименован",
                    f"Новое имя: {new_path.name}\n№ счета: {info.number}{det_str}",
                    QSystemTrayIcon.MessageIcon.Information,
                    5000
                )
        else:
            tray.showMessage(
                "Ошибка переименования",
                f"Не удалось переименовать файл «{path.name}». Возможно, файл открыт в другой программе.",
                QSystemTrayIcon.MessageIcon.Warning,
                4500
            )

    QTimer.singleShot(4500, finish)
    sys.exit(app.exec())


def main():
    parser = argparse.ArgumentParser(description="CheckRename - автоматическое переименование PDF-счетов.")
    parser.add_argument("--file", "-f", type=str, help="Путь к PDF файлу для переименования (из контекстного меню)")
    parser.add_argument("--install-menu", action="store_true", help="Зарегистрировать пункт контекстного меню")
    parser.add_argument("--uninstall-menu", action="store_true", help="Удалить пункт контекстного меню")
    parser.add_argument("--settings", "-s", action="store_true", help="Открыть окно настроек")

    args = parser.parse_args()

    if args.install_menu:
        if register_context_menu():
            print("Пункт контекстного меню успешно установлен.")
        else:
            print("Ошибка при установке пункта контекстного меню.")
        return

    if args.uninstall_menu:
        if unregister_context_menu():
            print("Пункт контекстного меню успешно удален.")
        else:
            print("Ошибка при удалении пункта контекстного меню.")
        return

    # Запуск обработки одиночного файла (ПКМ)
    if args.file:
        handle_single_file_cli(args.file)
        return

    # Стандартный запуск приложения в трее
    set_windows_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName("CheckRename")
    app.setApplicationDisplayName("CheckRename")
    app.setOrganizationName("CheckRename")
    app.setQuitOnLastWindowClosed(False)

    config = AppConfig.load()

    # Автоматически регистрируем пункт контекстного меню при первом запуске
    if not is_context_menu_registered():
        register_context_menu()

    # Автоматически регистрируем автозапуск при первом запуске, если включен в конфигурации
    if config.autostart and not is_autostart_registered():
        set_autostart(True)

    tray_manager = TrayManager(config)

    if args.settings:
        tray_manager.show_settings()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
