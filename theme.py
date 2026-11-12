"""Tema visual, fondo y controles reutilizables del reproductor."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QLinearGradient,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QStyle,
    QStyleOptionSlider,
    QSlider,
    QWidget,
)

DEFAULT_COVER_SIZE = 320
MIN_COVER_SIZE = 180
MAX_COVER_SIZE = 340
COVER_STEP = 20

STYLE_TEMPLATE = """
* { outline: none; }
QWidget {
    background-color: transparent;
    color: %(text)s;
    font-family: 'VT323';
    font-size: 18px;
}
QMainWindow { background-color: transparent; }
QDialog { background-color: %(dialog_bg)s; }
QFrame#panel {
    background-color: %(panel)s;
    border: 1px solid %(border)s;
}
QLabel#section {
    font-family: 'Press Start 2P';
    font-size: 10px;
    color: %(text)s;
}
QLabel#small {
    font-family: 'Press Start 2P';
    font-size: 8px;
    color: %(muted)s;
}
QLabel#muted { color: %(muted)s; }
QLabel#title { font-size: 30px; font-weight: bold; color: %(text)s; }
QLabel#artist { font-size: 21px; color: %(text)s; }
QLabel#meta { font-size: 16px; color: %(muted)s; }
QLabel#state {
    font-family: 'Press Start 2P';
    font-size: 8px;
    color: %(muted)s;
}
QLabel#cover {
    background-color: %(panel_alt)s;
    border: 1px solid %(border)s;
}
QLineEdit, QSpinBox {
    background-color: %(input_bg)s;
    border: 1px solid %(border)s;
    padding: 8px 10px;
    selection-background-color: %(selection)s;
    selection-color: %(selection_text)s;
}
QLineEdit:focus, QSpinBox:focus { border: 1px solid %(text)s; }
QComboBox {
    background-color: %(input_bg)s;
    border: 1px solid %(border)s;
    padding: 6px 8px;
}
QComboBox:hover { border-color: %(text)s; }
QComboBox QAbstractItemView {
    background-color: %(popup_bg)s;
    border: 1px solid %(border)s;
    selection-background-color: %(selection)s;
    selection-color: %(selection_text)s;
}
QTableWidget {
    background-color: %(table_bg)s;
    alternate-background-color: %(table_alt)s;
    border: 0;
    gridline-color: %(grid)s;
    selection-background-color: %(selection)s;
    selection-color: %(selection_text)s;
}
QTableWidget::item {
    padding: 2px 8px;
    border-bottom: 1px solid %(grid)s;
}
QTableWidget::item:selected {
    background-color: %(selection)s;
    color: %(selection_text)s;
}
QHeaderView::section {
    background-color: %(panel_alt)s;
    color: %(muted)s;
    border: 0;
    border-bottom: 1px solid %(border)s;
    padding: 7px 8px;
    font-family: 'Press Start 2P';
    font-size: 8px;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: %(scroll)s;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: %(scroll_hover)s; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QPushButton {
    background-color: %(input_bg)s;
    border: 1px solid %(border)s;
    padding: 6px 10px;
}
QPushButton:hover {
    background-color: %(selection)s;
    color: %(selection_text)s;
    border-color: %(selection)s;
}
QPushButton:pressed {
    background-color: %(selection)s;
    color: %(selection_text)s;
}
QPushButton:checked {
    background-color: %(selection)s;
    color: %(selection_text)s;
    border-color: %(selection)s;
}
QPushButton:disabled { color: %(muted)s; border-color: %(grid)s; }
QPushButton#small {
    font-family: 'Press Start 2P';
    font-size: 8px;
    padding: 7px 8px;
}
QPushButton#fav {
    font-family: 'Press Start 2P';
    font-size: 8px;
    padding: 4px 7px;
}
QPushButton#fav:hover {
    background-color: %(input_bg)s;
    color: %(text)s;
    border-color: %(text)s;
}
QPushButton#transport { font-size: 22px; padding: 4px 8px; }
QPushButton#play {
    background-color: %(accent)s;
    color: %(accent_text)s;
    border: 1px solid %(accent)s;
    font-family: 'Press Start 2P';
    font-size: 9px;
}
QPushButton#play:hover {
    background-color: transparent;
    color: %(text)s;
    border-color: %(text)s;
}
QSlider::groove:horizontal {
    height: 4px;
    background: %(soft)s;
}
QSlider::sub-page:horizontal { background: %(text)s; }
QSlider::handle:horizontal {
    background: %(text)s;
    width: 10px;
    height: 16px;
    margin: -6px 0;
}
QSlider::handle:horizontal:hover { background: %(muted)s; }
QToolTip {
    background-color: %(popup_bg)s;
    color: %(text)s;
    border: 1px solid %(border)s;
    padding: 4px;
}
QMenu {
    background-color: %(popup_bg)s;
    border: 1px solid %(border)s;
    padding: 4px;
}
QMenu::item { padding: 6px 22px 6px 14px; }
QMenu::item:selected {
    background-color: %(selection)s;
    color: %(selection_text)s;
}
QMenu::separator {
    height: 1px;
    background: %(border)s;
    margin: 4px 8px;
}
"""


def _palette(mode: str, color: str) -> dict[str, str]:
    if mode == "color":
        base = QColor(color)
        if not base.isValid():
            base = QColor("#101010")
        if base.lightnessF() > 0.55:
            values = {
                "text": "#000000",
                "muted": "#333333",
                "panel": "rgba(255,255,255,140)",
                "panel_alt": "rgba(255,255,255,115)",
                "input_bg": "rgba(255,255,255,150)",
                "border": "rgba(0,0,0,115)",
                "soft": "rgba(0,0,0,70)",
                "table_bg": "rgba(255,255,255,55)",
                "table_alt": "rgba(255,255,255,90)",
                "grid": "rgba(0,0,0,35)",
                "selection": "#000000",
                "selection_text": "#ffffff",
                "accent": "#000000",
                "accent_text": "#ffffff",
                "scroll": "rgba(0,0,0,90)",
                "scroll_hover": "rgba(0,0,0,140)",
                "dialog_bg": base.name(),
                "popup_bg": base.lighter(108).name(),
            }
        else:
            values = {
                "text": "#ffffff",
                "muted": "#c8c8c8",
                "panel": "rgba(0,0,0,95)",
                "panel_alt": "rgba(0,0,0,75)",
                "input_bg": "rgba(0,0,0,95)",
                "border": "rgba(255,255,255,90)",
                "soft": "rgba(255,255,255,50)",
                "table_bg": "rgba(0,0,0,80)",
                "table_alt": "rgba(255,255,255,15)",
                "grid": "rgba(255,255,255,20)",
                "selection": "#ffffff",
                "selection_text": "#000000",
                "accent": "#ffffff",
                "accent_text": "#000000",
                "scroll": "rgba(255,255,255,80)",
                "scroll_hover": "rgba(255,255,255,130)",
                "dialog_bg": base.name(),
                "popup_bg": base.darker(130).name(),
            }
        return values

    if mode == "cover":
        return {
            "text": "#ffffff",
            "muted": "#d0d0d0",
            "panel": "rgba(0,0,0,125)",
            "panel_alt": "rgba(0,0,0,100)",
            "input_bg": "rgba(0,0,0,120)",
            "border": "rgba(255,255,255,75)",
            "soft": "rgba(255,255,255,55)",
            "table_bg": "rgba(0,0,0,80)",
            "table_alt": "rgba(255,255,255,18)",
            "grid": "rgba(255,255,255,24)",
            "selection": "#ffffff",
            "selection_text": "#000000",
            "accent": "#ffffff",
            "accent_text": "#000000",
            "scroll": "rgba(255,255,255,90)",
            "scroll_hover": "rgba(255,255,255,140)",
            "dialog_bg": "#0b0b0b",
            "popup_bg": "#111111",
        }

    return {
        "text": "#ffffff",
        "muted": "#8a8a8a",
        "panel": "#050505",
        "panel_alt": "#0b0b0b",
        "input_bg": "#0b0b0b",
        "border": "#333333",
        "soft": "#262626",
        "table_bg": "#000000",
        "table_alt": "#0a0a0a",
        "grid": "#111111",
        "selection": "#ffffff",
        "selection_text": "#000000",
        "accent": "#ffffff",
        "accent_text": "#000000",
        "scroll": "#333333",
        "scroll_hover": "#666666",
        "dialog_bg": "#000000",
        "popup_bg": "#0b0b0b",
    }


def build_style(mode: str, color: str) -> str:
    """Devuelve la hoja de estilos según el fondo elegido."""
    return STYLE_TEMPLATE % _palette(mode, color)


def load_fonts(base_dir: Path) -> None:
    folder = Path(base_dir) / "assets" / "fonts"
    for filename in ("press-start-2p.ttf", "vt323.ttf"):
        path = folder / filename
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))


APP_ICON_NAME = "utilities-terminal-symbolic"


def app_icon(base_dir: Path) -> QIcon:
    """Icono del tema del escritorio, con el SVG local como respaldo."""
    icon = QIcon.fromTheme(APP_ICON_NAME)
    if not icon.isNull():
        return icon
    fallback = Path(base_dir) / "assets" / "icon.svg"
    return QIcon(str(fallback)) if fallback.exists() else QIcon()


def heart_icon(size: int, filled: bool) -> QIcon:
    """Corazón blanco que se vuelve negro sobre la fila seleccionada."""
    icon = QIcon()
    for factor in (1, 2, 3):
        scaled = size * factor
        for mode, color in (
            (QIcon.Mode.Normal, "#ffffff"),
            (QIcon.Mode.Selected, "#000000"),
            (QIcon.Mode.Disabled, "#6a6a6a"),
        ):
            icon.addPixmap(heart_pixmap(scaled, filled, color), mode)
    return icon


PIXEL_HEART = (
    "..##...##..",
    ".####.####.",
    "###########",
    "###########",
    ".#########.",
    "..#######..",
    "...#####...",
    "....###....",
    ".....#.....",
)


@lru_cache(maxsize=64)
def heart_pixmap(size: int, filled: bool, color: str = "#ffffff") -> QPixmap:
    """Corazón pixel art: relleno o solo el borde, escalado sin suavizar."""
    size = max(6, int(size))
    height = len(PIXEL_HEART)
    width = len(PIXEL_HEART[0])
    cells = [[char == "#" for char in row] for row in PIXEL_HEART]

    if not filled:
        border = [[False] * width for _ in range(height)]
        for y in range(height):
            for x in range(width):
                if not cells[y][x]:
                    continue
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if (
                        nx < 0
                        or ny < 0
                        or nx >= width
                        or ny >= height
                        or not cells[ny][nx]
                    ):
                        border[y][x] = True
                        break
        cells = border

    cell = max(1, round(size / max(width, height)))
    side = max(width, height) * cell
    pixmap = QPixmap(side, side)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    offset_x = (side - width * cell) // 2
    offset_y = (side - height * cell) // 2
    for y, row in enumerate(cells):
        for x, on in enumerate(row):
            if on:
                painter.drawRect(
                    offset_x + x * cell,
                    offset_y + y * cell,
                    cell,
                    cell,
                )
    painter.end()
    return pixmap


class Backdrop(QWidget):
    """Pinta el fondo de la ventana: negro, color sólido o portada."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.mode = "black"
        self.color = QColor("#000000")
        self.cover: QPixmap | None = None
        self._scaled: QPixmap | None = None
        self._scaled_size = None
        self.setAutoFillBackground(False)

    def set_background(self, mode: str, color: str) -> None:
        self.mode = mode
        self.color = QColor(color)
        if not self.color.isValid():
            self.color = QColor("#000000")
        self._scaled = None
        self.update()

    def set_cover(self, pixmap: QPixmap | None) -> None:
        self.cover = pixmap
        self._scaled = None
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802 - API de Qt
        self._scaled = None
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - API de Qt
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.color)
        if (
            self.mode == "cover"
            and self.cover is not None
            and not self.cover.isNull()
        ):
            if self._scaled is None or self._scaled_size != self.size():
                self._scaled = self.cover.scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._scaled_size = self.size()
            scaled = self._scaled
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            painter.fillRect(self.rect(), QColor(0, 0, 0, 90))
            gradient = QLinearGradient(0, 0, 0, self.height())
            gradient.setColorAt(0, QColor(0, 0, 0, 20))
            gradient.setColorAt(1, QColor(0, 0, 0, 135))
            painter.fillRect(self.rect(), gradient)


class ClickSlider(QSlider):
    """Slider que salta al punto donde se hace clic, además de arrastrar."""

    scrubbed = Signal(int)
    seekRequested = Signal(int)

    def __init__(self, orientation: Qt.Orientation, parent: QWidget | None = None):
        super().__init__(orientation, parent)
        self._dragging = False

    def _value_at(self, x: float) -> int:
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            option,
            QStyle.SubControl.SC_SliderGroove,
            self,
        )
        handle = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            option,
            QStyle.SubControl.SC_SliderHandle,
            self,
        )
        if groove.width() <= 0:
            return self.value()
        span = max(1, groove.right() - handle.width() + 1 - groove.x())
        position = int(x) - handle.width() // 2 - groove.x()
        return QStyle.sliderValueFromPosition(
            self.minimum(), self.maximum(), position, span, option.upsideDown
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802 - API de Qt
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._dragging = True
            value = self._value_at(event.position().x())
            self.setValue(value)
            self.scrubbed.emit(value)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - API de Qt
        if self._dragging:
            value = self._value_at(event.position().x())
            self.setValue(value)
            self.scrubbed.emit(value)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - API de Qt
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            value = self._value_at(event.position().x())
            self.setValue(value)
            self.seekRequested.emit(value)
            event.accept()
            return
        super().mouseReleaseEvent(event)
