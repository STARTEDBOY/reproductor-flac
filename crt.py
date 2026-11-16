"""Efecto CRT superpuesto a la ventana del reproductor."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

CRT_MODES = ("off", "mono", "amber", "green")

_TINTS = {
    "off": None,
    "mono": None,
    "amber": QColor(255, 176, 0, 20),
    "green": QColor(70, 255, 130, 16),
}


class CrtOverlay(QWidget):
    """Scanlines, tinte de fósforo y viñeta sobre toda la interfaz."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.mode = "off"
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAutoFillBackground(False)
        self.hide()

    def set_mode(self, mode: str) -> None:
        self.mode = mode if mode in CRT_MODES else "off"
        if self.mode == "off":
            self.hide()
            return
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - API de Qt
        if self.mode == "off":
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        rect = self.rect()
        width = rect.width()
        height = rect.height()

        tint = _TINTS.get(self.mode)
        if tint is not None:
            painter.fillRect(rect, tint)

        # Scanlines: una línea oscura cada tres píxeles y un brillo tenue
        # justo debajo para simular el fósforo.
        dark = QPen(QColor(0, 0, 0, 52))
        dark.setWidth(1)
        painter.setPen(dark)
        for y in range(0, height, 3):
            painter.drawLine(0, y, width, y)
        glow = QPen(QColor(255, 255, 255, 12))
        glow.setWidth(1)
        painter.setPen(glow)
        for y in range(1, height, 3):
            painter.drawLine(0, y, width, y)

        # Viñeta: centro limpio y bordes ligeramente oscurecidos.
        radius = max(width, height) * 0.72
        vignette = QRadialGradient(rect.center(), radius)
        vignette.setColorAt(0.55, QColor(0, 0, 0, 0))
        vignette.setColorAt(0.82, QColor(0, 0, 0, 34))
        vignette.setColorAt(1.0, QColor(0, 0, 0, 130))
        painter.fillRect(rect, vignette)
        painter.end()
