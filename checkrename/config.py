import json
import os
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional

def get_default_downloads_dir() -> str:
    """Определяет стандартный путь к папке Загрузок пользователя."""
    # Пытаемся получить путь из реестра Windows или стандартный путь
    try:
        import winreg
        sub_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub_key) as key:
            # {374DE290-123F-4565-9164-39C4925E467B} - GUID папки Загрузки
            guid = "{374DE290-123F-4565-9164-39C4925E467B}"
            try:
                val, _ = winreg.QueryValueEx(key, guid)
                expanded = os.path.expandvars(val)
                if os.path.isdir(expanded):
                    return str(Path(expanded).resolve())
            except OSError:
                pass
    except Exception:
        pass

    downloads = Path.home() / "Downloads"
    if downloads.exists():
        return str(downloads.resolve())
    return str(Path.home().resolve())


def get_default_tesseract_path() -> str:
    """Ищет установленный tesseract.exe в типовых путях Windows."""
    typical_paths = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR" / "tesseract.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Tesseract-OCR" / "tesseract.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tesseract.exe",
    ]
    for p in typical_paths:
        if p.is_file():
            return str(p)
    return ""


@dataclass
class AppConfig:
    watch_enabled: bool = True
    watch_folder: str = field(default_factory=get_default_downloads_dir)
    pattern: str = "Счет №{number} ({org} - {date})"
    move_enabled: bool = False
    destination_folder: str = ""
    ocr_enabled: bool = True
    tesseract_path: str = field(default_factory=get_default_tesseract_path)
    show_notifications: bool = True
    autostart: bool = True
    date_format: str = "%d.%m.%Y"

    @classmethod
    def get_config_path(cls) -> Path:
        """Путь к файлу конфигурации в AppData пользователя."""
        app_data = Path(os.environ.get("APPDATA", str(Path.home())))
        config_dir = app_data / "CheckRename"
        config_dir.mkdir(parents=True, exist_ok=True)

        new_path = config_dir / "config.json"
        # Миграция старого конфига, если существует
        old_path = app_data / "DocRename" / "config.json"
        if not new_path.exists() and old_path.exists():
            try:
                import shutil
                shutil.copy2(str(old_path), str(new_path))
            except Exception:
                pass
        return new_path

    @classmethod
    def load(cls) -> "AppConfig":
        config_path = cls.get_config_path()
        if not config_path.exists():
            config = cls()
            config.save()
            return config
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Фильтруем неизвестные поля для совместимости версий
            valid_fields = {f for f in cls.__dataclass_fields__}
            filtered = {k: v for k, v in data.items() if k in valid_fields}
            # Если в сохраненном конфиге остался старый шаблон по умолчанию, обновляем до нового
            if filtered.get("pattern") in ("счет {number}", "счет {number}", ""):
                filtered["pattern"] = "Счет №{number} ({org} - {date})"
            return cls(**filtered)
        except Exception:
            return cls()

    def save(self) -> None:
        config_path = self.get_config_path()
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения конфигурации: {e}")
