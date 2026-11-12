#!/usr/bin/env python3
"""Reproductor FLAC de STARTED — punto de entrada."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from theme import app_icon
from ui import MainWindow, load_fonts


def main() -> int:
    base = Path(__file__).resolve().parent
    app = QApplication([sys.argv[0]])
    app.setApplicationName("Reproductor FLAC")
    app.setOrganizationName("STARTED")
    app.setDesktopFileName("reproductor-flac")
    app.setStyle("Fusion")

    load_fonts(base)
    app.setWindowIcon(app_icon(base))

    initial = None
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_dir():
        initial = sys.argv[1]

    window = MainWindow(base, initial_library=initial)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
