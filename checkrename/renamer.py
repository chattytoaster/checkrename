import os
import shutil
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Tuple
from checkrename.parser import InvoiceInfo, sanitize_filename_part
from checkrename.config import AppConfig

@dataclass
class RenameRecord:
    original_path: Path
    new_path: Path
    timestamp: float

class Renamer:
    def __init__(self, config: AppConfig):
        self.config = config
        self.history: List[RenameRecord] = []

    def format_new_name(self, original_path: Path, info: InvoiceInfo) -> str:
        """
        Форматирует базовое имя файла на основе шаблона и извлеченных данных.
        """
        pattern = self.config.pattern or "Счет №{number} ({org} - {date})"
        orig_stem = original_path.stem

        number_val = info.number or "БН"
        date_val = info.date or ""
        org_val = info.org or ""

        # Подставляем переменные
        result = pattern
        result = result.replace("{number}", number_val)
        result = result.replace("{date}", date_val)
        result = result.replace("{org}", org_val)
        result = result.replace("{original}", orig_stem)

        # Очищаем дефисы и пустые скобки, если {org} или {date} отсутствуют
        result = re.sub(r'\(\s*-\s*\)', '', result)  # ( - ) -> пусто
        result = re.sub(r'\(\s*-\s*', '(', result)   # ( - дата) -> (дата)
        result = re.sub(r'\s*-\s*\)', ')', result)   # (орг - ) -> (орг)
        result = re.sub(r'\(\s*\)', '', result)      # () -> пусто
        result = re.sub(r'\[\s*\]', '', result)
        result = re.sub(r'-\s*-', '-', result)
        result = sanitize_filename_part(result)

        if not result:
            result = f"Счет №{number_val}"

        return result

    def resolve_destination_path(self, original_path: Path, base_new_name: str) -> Path:
        """
        Определяет целевую папку и разрешает коллизии имен с добавлением (1), (2)...
        """
        if self.config.move_enabled and self.config.destination_folder:
            dest_dir = Path(self.config.destination_folder)
            dest_dir.mkdir(parents=True, exist_ok=True)
        else:
            dest_dir = original_path.parent

        candidate_name = f"{base_new_name}.pdf"
        candidate_path = dest_dir / candidate_name

        # Если файл с таким именем уже существует (и это не тот же самый файл)
        counter = 1
        while candidate_path.exists() and candidate_path.resolve() != original_path.resolve():
            candidate_name = f"{base_new_name} ({counter}).pdf"
            candidate_path = dest_dir / candidate_name
            counter += 1

        return candidate_path

    def process_file(self, file_path: Path | str, info: InvoiceInfo) -> Optional[Path]:
        """
        Выполняет переименование (и возможно перемещение) файла.
        Возвращает новый путь к файлу или None при ошибке/отсутствии номера.
        """
        original_path = Path(file_path).resolve()
        if not original_path.is_file():
            return None

        if not info.number:
            return None

        base_name = self.format_new_name(original_path, info)
        target_path = self.resolve_destination_path(original_path, base_name)

        if target_path.resolve() == original_path.resolve():
            # Имя файла уже соответствует целевому
            return original_path

        import time
        # Попытка перемещения с повторами (если файл временно заблокирован)
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                shutil.move(str(original_path), str(target_path))
                self.history.append(RenameRecord(
                    original_path=original_path,
                    new_path=target_path,
                    timestamp=time.time()
                ))
                return target_path
            except PermissionError:
                time.sleep(0.5)
            except Exception as e:
                print(f"Ошибка при перемещении файла {original_path} -> {target_path}: {e}")
                return None

        return None

    def undo_last(self) -> Optional[Tuple[Path, Path]]:
        """
        Отменяет последнее переименование/перемещение.
        Возвращает кортеж (текущий_путь, восстановленный_путь) или None.
        """
        if not self.history:
            return None

        record = self.history.pop()
        current_path = record.new_path
        restore_path = record.original_path

        if not current_path.exists():
            return None

        # Разрешаем возможную коллизию в исходной папке
        dest_dir = restore_path.parent
        dest_stem = restore_path.stem
        target_restore = restore_path
        counter = 1
        while target_restore.exists() and target_restore.resolve() != current_path.resolve():
            target_restore = dest_dir / f"{dest_stem} ({counter}).pdf"
            counter += 1

        try:
            shutil.move(str(current_path), str(target_restore))
            return (current_path, target_restore)
        except Exception as e:
            print(f"Ошибка отмены переименования: {e}")
            return None
