import sys
import os
import winreg
from pathlib import Path
from typing import List, Optional

REG_SYS_KEY = r"Software\Classes\SystemFileAssociations\.pdf\shell\CheckRename"
REG_ALL_KEY = r"Software\Classes\*\shell\CheckRename"
REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_WIN11_CLASSIC_KEY = r"Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32"
APP_NAME = "CheckRename"

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

    # Если доступен скомпилированный бинарник CheckRename.exe
    pkg_dir = Path(__file__).resolve().parent.parent
    dist_exe = pkg_dir / "dist" / "CheckRename.exe"
    if dist_exe.is_file():
        return f'"{dist_exe.resolve()}"{arg_suffix}'

    python_exe = sys.executable
    pythonw_exe = Path(python_exe).parent / "pythonw.exe"
    if not pythonw_exe.exists():
        pythonw_exe = Path(python_exe)

    main_py = Path(__file__).parent / "main.py"
    return f'"{pythonw_exe}" "{main_py.resolve()}"{arg_suffix}'


def get_current_pdf_progid() -> Optional[str]:
    """Возвращает текущую зарегистрированную программу для .pdf (например FirefoxPDF, ChromeHTML, Acrobat)."""
    try:
        user_choice_key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.pdf\UserChoice"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, user_choice_key) as k:
            val, _ = winreg.QueryValueEx(k, "ProgId")
            return val
    except OSError:
        return None


def get_target_shell_keys() -> List[str]:
    """Возвращает список всех ключей реестра, где должен быть зарегистрирован пункт меню."""
    keys = [
        REG_SYS_KEY,
        REG_ALL_KEY,
        r"Software\Classes\.pdf\shell\CheckRename",
    ]
    prog_id = get_current_pdf_progid()
    if prog_id:
        keys.append(f"Software\\Classes\\{prog_id}\\shell\\CheckRename")
    return keys


def is_context_menu_registered() -> bool:
    """Проверяет, зарегистрирован ли пункт хотя бы в одном из ключевых мест реестра."""
    for key_path in (REG_SYS_KEY, REG_ALL_KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path):
                return True
        except OSError:
            pass
    return False


def register_context_menu(menu_title: str = "Найти номер счета") -> bool:
    r"""
    Регистрирует пункт в контекстном меню во всех ключевых ветках реестра HKCU:
    - SystemFileAssociations\.pdf
    - *\shell\CheckRename с фильтром AppliesTo = System.FileExtension:=.pdf
    - ProgId пользователя (Firefox, Chrome, Acrobat и т.д.)
    """
    success = False
    cmd = get_launch_command(file_arg_placeholder=True)

    for base_key in get_target_shell_keys():
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base_key) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, menu_title)

                # Для ветки *\shell задаем фильтр только для файлов .pdf
                if base_key == REG_ALL_KEY:
                    winreg.SetValueEx(key, "AppliesTo", 0, winreg.REG_SZ, "System.FileExtension:=.pdf")

                # Иконка
                if getattr(sys, "frozen", False):
                    winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, sys.executable)

            cmd_key_path = f"{base_key}\\command"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, cmd_key_path) as k_cmd:
                winreg.SetValueEx(k_cmd, "", 0, winreg.REG_SZ, cmd)

            success = True
        except Exception as e:
            print(f"Ошибка регистрации ветки {base_key}: {e}")

    return success


def _delete_key_recursive(root, subkey: str):
    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                    _delete_key_recursive(root, f"{subkey}\\{sub}")
                except OSError:
                    break
        winreg.DeleteKey(root, subkey)
    except OSError:
        pass


def unregister_context_menu() -> bool:
    """Удаляет пункт контекстного меню из всех веток реестра."""
    for base_key in get_target_shell_keys():
        _delete_key_recursive(winreg.HKEY_CURRENT_USER, base_key)
    return True


def is_win11_classic_menu_enabled() -> bool:
    """Проверяет, включено ли классическое контекстное меню Windows 10 в Windows 11."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_WIN11_CLASSIC_KEY):
            return True
    except OSError:
        return False


def set_win11_classic_menu(enabled: bool) -> bool:
    """
    Включает или отключает классическое контекстное меню в Windows 11.
    Позволяет сразу видеть все пункты по правому клику без «Показать дополнительные параметры».
    """
    try:
        if enabled:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_WIN11_CLASSIC_KEY) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "")
        else:
            base_clsid = r"Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}"
            _delete_key_recursive(winreg.HKEY_CURRENT_USER, base_clsid)
        return True
    except Exception as e:
        print(f"Ошибка настройки классического меню Windows 11: {e}")
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
