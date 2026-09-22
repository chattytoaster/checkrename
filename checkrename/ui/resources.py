from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QBrush, QFont
from PyQt6.QtCore import Qt, QPoint, QRectF
from pathlib import Path

def create_app_icon(active: bool = True, size: int = 64) -> QIcon:
    """Генерирует аккуратную векторную иконку документа со статусом."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Размеры документа
    margin = size * 0.1
    doc_width = size * 0.65
    doc_height = size * 0.8
    doc_x = margin + (size - doc_width) * 0.2
    doc_y = margin

    # Цвет основного листа
    painter.setPen(QPen(QColor("#2563EB"), max(2, int(size * 0.04))))
    painter.setBrush(QBrush(QColor("#EFF6FF")))
    doc_rect = QRectF(doc_x, doc_y, doc_width, doc_height)
    painter.drawRoundedRect(doc_rect, size * 0.08, size * 0.08)

    # Линии текста в документе
    painter.setPen(QPen(QColor("#93C5FD"), max(2, int(size * 0.035))))
    line_y1 = doc_y + doc_height * 0.35
    line_y2 = doc_y + doc_height * 0.55
    line_y3 = doc_y + doc_height * 0.75
    painter.drawLine(int(doc_x + doc_width * 0.2), int(line_y1), int(doc_x + doc_width * 0.8), int(line_y1))
    painter.drawLine(int(doc_x + doc_width * 0.2), int(line_y2), int(doc_x + doc_width * 0.8), int(line_y2))
    painter.drawLine(int(doc_x + doc_width * 0.2), int(line_y3), int(doc_x + doc_width * 0.55), int(line_y3))

    # Бейдж статуса слежения (зеленый - активно, серый - пауза)
    badge_radius = size * 0.16
    badge_cx = size - badge_radius - size * 0.05
    badge_cy = size - badge_radius - size * 0.05

    painter.setPen(QPen(QColor("#FFFFFF"), max(2, int(size * 0.04))))
    if active:
        painter.setBrush(QBrush(QColor("#10B981"))) # Изумрудно-зеленый
    else:
        painter.setBrush(QBrush(QColor("#9CA3AF"))) # Серый

    painter.drawEllipse(QPoint(int(badge_cx), int(badge_cy)), int(badge_radius), int(badge_radius))
    painter.end()

    return QIcon(pixmap)


def export_ico_file(filepath: Path) -> Path:
    """Экспортирует сгенерированную иконку в формат .ico для PyInstaller."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    icon = create_app_icon(active=True, size=256)
    pix = icon.pixmap(256, 256)
    pix.save(str(filepath), "ICO")
    return filepath
