import sys
import subprocess
from pathlib import Path
from PyQt6.QtWidgets import QApplication

def build():
    print("=== Начало сборки DocRename в автономный .exe ===")
    project_dir = Path(__file__).parent.resolve()
    
    # 1. Генерация иконки .ico
    icon_path = project_dir / "app_icon.ico"
    try:
        app = QApplication(sys.argv)
        from docrename.ui.resources import export_ico_file
        export_ico_file(icon_path)
        print(f"[OK] Сгенерирована иконка: {icon_path}")
    except Exception as e:
        print(f"[!] Не удалось создать .ico иконку: {e}")
        icon_path = None

    # 2. Формирование команды PyInstaller
    main_script = project_dir / "docrename" / "main.py"
    
    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--name=DocRename",
        "--onefile",
        "--noconsole",
        "--clean",
    ]

    if icon_path and icon_path.exists():
        cmd.append(f"--icon={icon_path}")

    # Добавляем пути и скрытые импорты
    cmd.extend([
        "--hidden-import=PyQt6",
        "--hidden-import=fitz",
        "--hidden-import=watchdog",
        "--hidden-import=pypdf",
        "--hidden-import=PIL",
        f"--paths={project_dir}",
        str(main_script)
    ])

    print("Запуск PyInstaller...")
    res = subprocess.run(cmd, cwd=str(project_dir))
    if res.returncode == 0:
        exe_path = project_dir / "dist" / "DocRename.exe"
        print("\n" + "="*50)
        print(f"[УСПЕХ] Сборка завершена успешно!")
        print(f"Исполняемый файл находится по пути:\n{exe_path}")
        print("="*50)
    else:
        print(f"\n[ОШИБКА] Сборка завершилась с кодом ошибки {res.returncode}")

if __name__ == "__main__":
    build()
