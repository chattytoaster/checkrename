import os
import json
import ctypes
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List, Set, Tuple

from checkrename.config import AppConfig


def _get_ads_path(path: Path) -> str:
    """Возвращает путь к альтернативному потоку данных (ADS) NTFS."""
    return f"{path.resolve()}:checkrename"


def has_ads_marker(path: Path) -> bool:
    """Проверяет наличие маркера CheckRename в потоке данных NTFS."""
    if os.name != "nt":
        return False
    try:
        ads = _get_ads_path(path)
        return os.path.exists(ads)
    except Exception:
        return False


def set_ads_marker(path: Path, data: str = "processed=1") -> bool:
    """Записывает маркер в альтернативный поток данных NTFS файла."""
    if os.name != "nt":
        return False
    try:
        ads = _get_ads_path(path)
        with open(ads, "w", encoding="utf-8") as f:
            f.write(data)
        return True
    except Exception:
        return False


def remove_ads_marker(path: Path) -> bool:
    """Удаляет маркер потока данных NTFS."""
    if os.name != "nt":
        return False
    try:
        ads = _get_ads_path(path)
        if os.path.exists(ads):
            return bool(ctypes.windll.kernel32.DeleteFileW(ads))
    except Exception:
        pass
    return False


def get_file_identity(path: Path) -> Optional[Tuple[int, int]]:
    """Возвращает уникальный идентификатор файла на диске (dev, ino)."""
    try:
        st = path.stat()
        if st.st_ino != 0:
            return (int(st.st_dev), int(st.st_ino))
    except Exception:
        pass
    return None


class ProcessedTracker:
    """
    Отслеживает файлы, которые уже были переименованы утилитой CheckRename,
    чтобы исключить повторные или циклические переименования, а также сохранять
    пользовательские правки (в названии или содержимом файла).
    """

    def __init__(self, storage_path: Optional[Path] = None):
        if storage_path is None:
            config_dir = AppConfig.get_config_path().parent
            storage_path = config_dir / "processed_files.json"

        self.storage_path = storage_path
        self._lock = threading.Lock()

        # Кэш в оперативной памяти для быстрого поиска
        self._records: List[Dict[str, Any]] = []
        self._known_identities: Set[Tuple[int, int]] = set()
        self._known_paths: Set[str] = set()
        self._known_names: Set[str] = set()

        self._load()

    def _normalize_path_str(self, path: Path | str) -> str:
        try:
            return str(Path(path).resolve()).lower()
        except Exception:
            return str(path).lower()

    def _load(self):
        with self._lock:
            self._records.clear()
            self._known_identities.clear()
            self._known_paths.clear()
            self._known_names.clear()

            if not self.storage_path.exists():
                return

            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                records = data.get("records", [])
                for r in records:
                    self._records.append(r)
                    dev = r.get("dev")
                    ino = r.get("ino")
                    if dev is not None and ino is not None:
                        self._known_identities.add((int(dev), int(ino)))

                    for p in r.get("paths", []):
                        self._known_paths.add(p.lower())

                    for name in r.get("names", []):
                        self._known_names.add(name.lower())
            except Exception as e:
                print(f"Ошибка чтения базы обработанных файлов {self.storage_path}: {e}")

    def _save(self):
        """Сохраняет базу на диск (вызывать под self._lock)."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            temp_file = self.storage_path.with_suffix(".tmp")
            payload = {
                "version": 1,
                "records": self._records
            }
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            temp_file.replace(self.storage_path)
        except Exception as e:
            print(f"Ошибка сохранения базы обработанных файлов {self.storage_path}: {e}")

    def is_processed(self, path: Path | str) -> bool:
        """
        Проверяет, был ли данный файл уже обработан и переименован CheckRename.
        Использует многоуровневую проверку:
        1. NTFS ADS маркер (:checkrename).
        2. Идентификатор файла на уровне файловой системы (dev, ino).
        3. Полный путь к файлу.
        4. Имя файла в списке ранее переименованных.
        """
        p = Path(path)

        # 1. Проверка NTFS ADS маркера
        if has_ads_marker(p):
            return True

        # 2. Проверка dev, ino
        ident = get_file_identity(p)
        with self._lock:
            if ident and ident in self._known_identities:
                return True

            # 3. Проверка нормализованного пути
            norm_path = self._normalize_path_str(p)
            if norm_path in self._known_paths:
                return True

        return False

    def mark_processed(
        self,
        original_path: Path,
        new_path: Path,
        invoice_number: Optional[str] = None,
        invoice_date: Optional[str] = None,
        invoice_org: Optional[str] = None
    ) -> None:
        """
        Помечает файл как обработанный после успешного переименования.
        """
        orig_resolved = original_path.resolve()
        new_resolved = new_path.resolve()

        ident = get_file_identity(new_resolved) or get_file_identity(orig_resolved)
        dev = ident[0] if ident else None
        ino = ident[1] if ident else None

        # Записываем ADS маркер
        set_ads_marker(new_resolved, f"number={invoice_number or ''}")

        norm_orig = str(orig_resolved).lower()
        norm_new = str(new_resolved).lower()

        import time
        record = {
            "dev": dev,
            "ino": ino,
            "original_name": original_path.name,
            "current_name": new_path.name,
            "names": list({original_path.name, new_path.name}),
            "paths": list({norm_orig, norm_new}),
            "invoice_number": invoice_number,
            "invoice_date": invoice_date,
            "invoice_org": invoice_org,
            "timestamp": time.time()
        }

        with self._lock:
            # Если запись с таким ino или path уже была, объединяем
            matched_record = None
            if ident:
                for r in self._records:
                    if r.get("dev") == dev and r.get("ino") == ino:
                        matched_record = r
                        break

            if matched_record:
                matched_record["current_name"] = new_path.name
                for n in record["names"]:
                    if n not in matched_record["names"]:
                        matched_record["names"].append(n)
                for p_str in record["paths"]:
                    if p_str not in matched_record["paths"]:
                        matched_record["paths"].append(p_str)
                if invoice_number:
                    matched_record["invoice_number"] = invoice_number
                if invoice_date:
                    matched_record["invoice_date"] = invoice_date
                if invoice_org:
                    matched_record["invoice_org"] = invoice_org
            else:
                self._records.append(record)

            if ident:
                self._known_identities.add(ident)
            self._known_paths.add(norm_new)

            self._save()

    def update_path(self, old_path: Path | str, new_path: Path | str) -> None:
        """
        Обновляет запись, когда файл переименовывается пользователем или другой программой.
        Это сохраняет статус 'обработан' даже после ручного переименования.
        """
        old_p = Path(old_path)
        new_p = Path(new_path)

        norm_old = self._normalize_path_str(old_p)
        norm_new = self._normalize_path_str(new_p)

        ident = get_file_identity(new_p) or get_file_identity(old_p)
        dev = ident[0] if ident else None
        ino = ident[1] if ident else None

        # Переносим или обновляем ADS маркер
        if new_p.exists():
            set_ads_marker(new_p)

        with self._lock:
            found = False
            for r in self._records:
                matches_ident = (ident and r.get("dev") == dev and r.get("ino") == ino)
                matches_path = (norm_old in [p.lower() for p in r.get("paths", [])])
                matches_name = (old_p.name.lower() in [n.lower() for n in r.get("names", [])])

                if matches_ident or matches_path or matches_name:
                    r["current_name"] = new_p.name
                    if dev is not None and ino is not None:
                        r["dev"] = dev
                        r["ino"] = ino
                    if new_p.name not in r.get("names", []):
                        r.setdefault("names", []).append(new_p.name)
                    if norm_new not in r.get("paths", []):
                        r.setdefault("paths", []).append(norm_new)
                    found = True
                    break

            if not found and new_p.exists():
                # Создаем запись, чтобы этот переименованный файл не переименовывался обратно
                import time
                record = {
                    "dev": dev,
                    "ino": ino,
                    "original_name": old_p.name,
                    "current_name": new_p.name,
                    "names": [old_p.name, new_p.name],
                    "paths": [norm_old, norm_new],
                    "timestamp": time.time()
                }
                self._records.append(record)

            if ident:
                self._known_identities.add(ident)
            self._known_paths.add(norm_new)
            self._known_names.add(new_p.name.lower())

            self._save()

    def unmark_processed(self, path: Path | str) -> None:
        """
        Снимает отметку об обработке (например, при операции Undo).
        """
        p = Path(path)
        norm_path = self._normalize_path_str(p)
        ident = get_file_identity(p)
        remove_ads_marker(p)

        with self._lock:
            if ident:
                self._known_identities.discard(ident)
            self._known_paths.discard(norm_path)
            self._known_names.discard(p.name.lower())

            self._records = [
                r for r in self._records
                if not (
                    (ident and r.get("dev") == ident[0] and r.get("ino") == ident[1])
                    or norm_path in [x.lower() for x in r.get("paths", [])]
                )
            ]
            self._save()

    def clear(self) -> None:
        """Очищает всю базу (в основном для тестов)."""
        with self._lock:
            self._records.clear()
            self._known_identities.clear()
            self._known_paths.clear()
            self._known_names.clear()
            if self.storage_path.exists():
                try:
                    self.storage_path.unlink()
                except Exception:
                    pass


# Глобальный экземпляр трекера
default_tracker = ProcessedTracker()
