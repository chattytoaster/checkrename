import sys
import os
import winreg
from pathlib import Path

REG_SHELL_KEY = r"Software\Classes\SystemFileAssociations\.pdf\shell\DocRename"
REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "DocRename"

def get_launch_command(file_arg_placeholder: bool = True) -> str:
    """
    Возвращает строку запуска приложения:
    - если скомпилировано pyinstaller (sys.frozen), то путь к .exe
    - если запускается из python, то pythonw.exe + путь к main.py
    """
    arg_suffix = ' --file "%1"' if file_arg_placeholder else ""

    if getattr(sys, "frozen", False):
        exe_path = sys.executable
        return f'"{exe_path}"{arg_suffix}'
    else:
        # Для запуска из исходников используем pythonw.exe, чтобы не мигала консоль
        python_exe = sys.executable
        pythonw_exe = Path(python_exe).parent / "pythonw.exe"
        if not pythonw_exe.exists():
            pythonw_exe = Path(python_exe)

        main_py = Path(__file__).parent / "main.py"
        return f'"{pythonw_exe}" "{main_py.resolve()}"{arg_suffix}'


def is_context_menu_registered() -> bool:
    """Проверяет, зарегистрирован ли пункт в контекстном меню."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_SHELL_KEY) as key:
            return True
    except OSError:
        return False


def register_context_menu(menu_title: str = "Найти номер счета") -> bool:
    """
    Регистрирует пункт в контекстном меню для файлов .pdf (в HKCU, без прав админа).
    """
    try:
        # Создаем ключ меню
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_SHELL_KEY) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, menu_title)
            # Иконка (если это exe или есть иконка)
            if getattr(sys, "frozen", False):
                winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, sys.executable)

        # Создаем подключ command
        command_key_path = f"{REG_SHELL_KEY}\\command"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, command_key_path) as key:
            cmd = get_launch_command(file_arg_placeholder=True)
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, cmd)

        return True
    except Exception as e:
        print(f"Ошибка регистрации контекстного меню: {e}")
        return False


def unregister_context_menu() -> bool:
    """Удаляет пункт из контекстного меню."""
    try:
        command_key_path = f"{REG_SHELL_KEY}\\command"
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, command_key_path)
        except OSError:
            pass
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_SHELL_KEY)
        return True
    except OSError:
        return False
    except Exception as e:
        print(f"Ошибка удаления контекстного меню: {e}")
        return False


def is_autostart_registered() -> bool:
    """Проверяет, включен ли автозапуск в реестре Windows."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(enabled: bool) -> bool:
    """Включает или выключает автозапуск приложения при входе в Windows."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                cmd = get_launch_command(file_arg_placeholder=False)
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except OSError:
                    pass
        return True
    except Exception as e:
        print(f"Ошибка настройки автозапуска: {e}")
        return False
