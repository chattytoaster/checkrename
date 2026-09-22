import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
    QPushButton, QCheckBox, QFileDialog, QMessageBox, QTabWidget, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from docrename.config import AppConfig
from docrename.context_menu import (
    is_context_menu_registered, register_context_menu, unregister_context_menu,
    is_autostart_registered, set_autostart
)
from docrename.ui.resources import create_app_icon

class SettingsDialog(QDialog):
    settings_saved = pyqtSignal(AppConfig)

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Настройки DocRename")
        self.setWindowIcon(create_app_icon(active=True))
        self.resize(540, 520)

        self._init_ui()
        self._load_values()
        self._update_preview()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)

        # Табы настроек
        tabs = QTabWidget(self)

        # Вкладка 1: Основные и мониторинг
        tab_general = QWidget()
        layout_general = QVBoxLayout(tab_general)

        # Группа: Мониторинг
        grp_monitor = QGroupBox("Мониторинг файлов")
        l_mon = QVBoxLayout(grp_monitor)

        self.chk_watch_enabled = QCheckBox("Автоматически отслеживать новые файлы")
        l_mon.addWidget(self.chk_watch_enabled)

        lbl_watch_path = QLabel("Отслеживаемая папка:")
        l_mon.addWidget(lbl_watch_path)

        h_watch = QHBoxLayout()
        self.txt_watch_folder = QLineEdit()
        btn_browse_watch = QPushButton("Обзор...")
        btn_browse_watch.clicked.connect(self._browse_watch_folder)
        h_watch.addWidget(self.txt_watch_folder)
        h_watch.addWidget(btn_browse_watch)
        l_mon.addLayout(h_watch)

        # Перемещение
        self.chk_move_enabled = QCheckBox("Перемещать переименованные файлы в отдельную папку")
        self.chk_move_enabled.toggled.connect(self._toggle_move_fields)
        l_mon.addWidget(self.chk_move_enabled)

        self.lbl_dest_path = QLabel("Целевая папка для счетов:")
        l_mon.addWidget(self.lbl_dest_path)

        h_dest = QHBoxLayout()
        self.txt_dest_folder = QLineEdit()
        self.btn_browse_dest = QPushButton("Обзор...")
        self.btn_browse_dest.clicked.connect(self._browse_dest_folder)
        h_dest.addWidget(self.txt_dest_folder)
        h_dest.addWidget(self.btn_browse_dest)
        l_mon.addLayout(h_dest)

        layout_general.addWidget(grp_monitor)

        # Группа: Шаблон имени
        grp_pattern = QGroupBox("Формат названия файла")
        l_pat = QVBoxLayout(grp_pattern)

        l_pat.addWidget(QLabel("Шаблон переименования:"))
        self.txt_pattern = QLineEdit()
        self.txt_pattern.textChanged.connect(self._update_preview)
        l_pat.addWidget(self.txt_pattern)

        # Кнопки тегов
        h_tags = QHBoxLayout()
        h_tags.addWidget(QLabel("Вставить тег:"))
        tags = [
            ("{number}", "Номер"),
            ("{date}", "Дата"),
            ("{org}", "Поставщик"),
            ("{original}", "Исходное"),
        ]
        for tag, name in tags:
            btn_tag = QPushButton(f"+ {tag}")
            btn_tag.setStyleSheet("padding: 2px 6px; font-size: 11px;")
            btn_tag.clicked.connect(lambda _, t=tag: self._insert_tag(t))
            h_tags.addWidget(btn_tag)
        h_tags.addStretch()
        l_pat.addLayout(h_tags)

        # Превью
        self.lbl_preview = QLabel("Превью: ")
        self.lbl_preview.setStyleSheet("color: #2563EB; font-weight: bold; padding: 4px 0;")
        l_pat.addWidget(self.lbl_preview)

        layout_general.addWidget(grp_pattern)
        layout_general.addStretch()
        tabs.addTab(tab_general, "Основные")

        # Вкладка 2: Интеграция с Windows и OCR
        tab_integration = QWidget()
        layout_int = QVBoxLayout(tab_integration)

        # Контекстное меню Проводника
        grp_ctx = QGroupBox("Интеграция с Проводником Windows")
        l_ctx = QVBoxLayout(grp_ctx)

        self.lbl_ctx_status = QLabel("Статус: не установлен")
        l_ctx.addWidget(self.lbl_ctx_status)

        h_ctx_btns = QHBoxLayout()
        self.btn_install_ctx = QPushButton("Добавить «Найти номер счета» в меню ПКМ")
        self.btn_install_ctx.clicked.connect(self._toggle_context_menu)
        h_ctx_btns.addWidget(self.btn_install_ctx)
        h_ctx_btns.addStretch()
        l_ctx.addLayout(h_ctx_btns)

        self.chk_autostart = QCheckBox("Запускать DocRename при старте Windows")
        l_ctx.addWidget(self.chk_autostart)

        self.chk_notifications = QCheckBox("Показывать всплывающие уведомления при переименовании")
        l_ctx.addWidget(self.chk_notifications)

        layout_int.addWidget(grp_ctx)

        # Распознавание OCR
        grp_ocr = QGroupBox("Распознавание сканов (OCR Tesseract)")
        l_ocr = QVBoxLayout(grp_ocr)

        self.chk_ocr_enabled = QCheckBox("Использовать OCR, если в файле нет текстового слоя")
        l_ocr.addWidget(self.chk_ocr_enabled)

        l_ocr.addWidget(QLabel("Путь к tesseract.exe (если не найден автоматически):"))
        h_tess = QHBoxLayout()
        self.txt_tesseract_path = QLineEdit()
        btn_browse_tess = QPushButton("Обзор...")
        btn_browse_tess.clicked.connect(self._browse_tesseract)
        h_tess.addWidget(self.txt_tesseract_path)
        h_tess.addWidget(btn_browse_tess)
        l_ocr.addLayout(h_tess)

        layout_int.addWidget(grp_ocr)
        layout_int.addStretch()
        tabs.addTab(tab_integration, "Система и OCR")

        main_layout.addWidget(tabs)

        # Нижние кнопки диалога
        h_bottom = QHBoxLayout()
        h_bottom.addStretch()

        btn_save = QPushButton("Сохранить")
        btn_save.setDefault(True)
        btn_save.setStyleSheet("background-color: #2563EB; color: white; padding: 6px 16px; border-radius: 4px;")
        btn_save.clicked.connect(self._save_and_close)

        btn_cancel = QPushButton("Отмена")
        btn_cancel.setStyleSheet("padding: 6px 16px;")
        btn_cancel.clicked.connect(self.reject)

        h_bottom.addWidget(btn_cancel)
        h_bottom.addWidget(btn_save)
        main_layout.addLayout(h_bottom)

    def _load_values(self):
        self.chk_watch_enabled.setChecked(self.config.watch_enabled)
        self.txt_watch_folder.setText(self.config.watch_folder)

        self.chk_move_enabled.setChecked(self.config.move_enabled)
        self.txt_dest_folder.setText(self.config.destination_folder)
        self._toggle_move_fields(self.config.move_enabled)

        self.txt_pattern.setText(self.config.pattern)

        self.chk_autostart.setChecked(is_autostart_registered())
        self.chk_notifications.setChecked(self.config.show_notifications)

        self.chk_ocr_enabled.setChecked(self.config.ocr_enabled)
        self.txt_tesseract_path.setText(self.config.tesseract_path)

        self._refresh_ctx_button()

    def _refresh_ctx_button(self):
        if is_context_menu_registered():
            self.lbl_ctx_status.setText("Статус: Пункт активен в меню ПКМ для файлов .pdf")
            self.lbl_ctx_status.setStyleSheet("color: #10B981; font-weight: bold;")
            self.btn_install_ctx.setText("Удалить из меню ПКМ")
        else:
            self.lbl_ctx_status.setText("Статус: Пункт не зарегистрирован в проводнике")
            self.lbl_ctx_status.setStyleSheet("color: #6B7280;")
            self.btn_install_ctx.setText("Добавить «Найти номер счета» в меню ПКМ")

    def _toggle_context_menu(self):
        if is_context_menu_registered():
            unregister_context_menu()
        else:
            register_context_menu()
        self._refresh_ctx_button()

    def _toggle_move_fields(self, enabled: bool):
        self.lbl_dest_path.setEnabled(enabled)
        self.txt_dest_folder.setEnabled(enabled)
        self.btn_browse_dest.setEnabled(enabled)

    def _browse_watch_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для отслеживания", self.txt_watch_folder.text())
        if folder:
            self.txt_watch_folder.setText(os.path.normpath(folder))

    def _browse_dest_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите целевую папку для счетов", self.txt_dest_folder.text())
        if folder:
            self.txt_dest_folder.setText(os.path.normpath(folder))

    def _browse_tesseract(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Укажите tesseract.exe", "", "Исполняемые файлы (*.exe)")
        if file_path:
            self.txt_tesseract_path.setText(os.path.normpath(file_path))

    def _insert_tag(self, tag: str):
        self.txt_pattern.insert(tag)
        self.txt_pattern.setFocus()

    def _update_preview(self):
        pattern = self.txt_pattern.text().strip() or "счет {number}"
        sample = pattern.replace("{number}", "124")
        sample = sample.replace("{date}", "15.05.2024")
        sample = sample.replace("{org}", "ООО Ромашка")
        sample = sample.replace("{original}", "download_invoice")
        self.lbl_preview.setText(f"Превью: {sample}.pdf")

    def _save_and_close(self):
        self.config.watch_enabled = self.chk_watch_enabled.isChecked()
        self.config.watch_folder = self.txt_watch_folder.text().strip()
        self.config.move_enabled = self.chk_move_enabled.isChecked()
        self.config.destination_folder = self.txt_dest_folder.text().strip()
        self.config.pattern = self.txt_pattern.text().strip() or "счет {number}"
        self.config.show_notifications = self.chk_notifications.isChecked()
        self.config.ocr_enabled = self.chk_ocr_enabled.isChecked()
        self.config.tesseract_path = self.txt_tesseract_path.text().strip()

        # Настройка автозапуска в реестре
        autostart_checked = self.chk_autostart.isChecked()
        self.config.autostart = autostart_checked
        set_autostart(autostart_checked)

        self.config.save()
        self.settings_saved.emit(self.config)
        self.accept()
