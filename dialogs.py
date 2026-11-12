"""Diálogos del reproductor: carpeta, fondo, temporizador y listas."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from library import Track, format_time


class NameDialog(QDialog):
    """Pide un nombre para una lista de reproducción."""

    def __init__(
        self,
        title: str,
        label: str,
        initial: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.value = ""
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(430)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(10)

        heading = QLabel(label)
        heading.setObjectName("section")
        heading.setWordWrap(True)
        layout.addWidget(heading)

        self.edit = QLineEdit(initial)
        self.edit.selectAll()
        layout.addWidget(self.edit)

        self.error = QLabel("")
        self.error.setObjectName("muted")
        layout.addWidget(self.error)

        row = QHBoxLayout()
        row.setSpacing(8)
        cancel = QPushButton("CANCELAR")
        cancel.setObjectName("small")
        cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        accept = QPushButton("GUARDAR")
        accept.setObjectName("small")
        accept.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(accept)
        layout.addLayout(row)

        cancel.clicked.connect(self.reject)
        accept.clicked.connect(self._accept)
        self.edit.returnPressed.connect(self._accept)

    def _accept(self) -> None:
        text = self.edit.text().strip()
        if not text:
            self.error.setText("ESCRIBE UN NOMBRE")
            return
        self.value = text
        self.accept()


class FolderDialog(QDialog):
    """Permite escribir, pegar o examinar la carpeta de la biblioteca."""

    def __init__(self, current: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.selected_path = ""
        self.setWindowTitle("Cambiar carpeta de música")
        self.setModal(True)
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(10)

        title = QLabel("RUTA DE LA BIBLIOTECA")
        title.setObjectName("section")
        layout.addWidget(title)

        self.path_edit = QLineEdit(current)
        self.path_edit.selectAll()
        layout.addWidget(self.path_edit)

        self.error = QLabel("")
        self.error.setObjectName("muted")
        layout.addWidget(self.error)

        row = QHBoxLayout()
        row.setSpacing(8)
        browse = QPushButton("EXAMINAR…")
        browse.setObjectName("small")
        browse.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        cancel = QPushButton("CANCELAR")
        cancel.setObjectName("small")
        cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        accept = QPushButton("CARGAR")
        accept.setObjectName("small")
        accept.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        row.addWidget(browse)
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(accept)
        layout.addLayout(row)

        browse.clicked.connect(self._browse)
        cancel.clicked.connect(self.reject)
        accept.clicked.connect(self._accept)
        self.path_edit.returnPressed.connect(self._accept)

    def _browse(self) -> None:
        start = self.path_edit.text().strip() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(
            self, "Elegir carpeta de música", start
        )
        if folder:
            self.path_edit.setText(folder)
            self.error.setText("")

    def _accept(self) -> None:
        text = self.path_edit.text().strip()
        if not text:
            self.error.setText("ESCRIBE UNA RUTA")
            return
        path = Path(text).expanduser()
        if not path.is_dir():
            self.error.setText("LA CARPETA NO EXISTE")
            return
        self.selected_path = str(path)
        self.accept()


class BackgroundDialog(QDialog):
    """Elige fondo negro, un color personalizado o la portada actual."""

    def __init__(
        self,
        mode: str,
        color: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.mode = mode
        self.color = color if QColor(color).isValid() else "#000000"
        self.setWindowTitle("Fondo de la ventana")
        self.setModal(True)
        self.setMinimumWidth(540)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        heading = QLabel("FONDO DE LA VENTANA")
        heading.setObjectName("section")
        layout.addWidget(heading)

        description = QLabel(
            "Elige negro, un color libre o la portada de la canción actual."
        )
        description.setObjectName("muted")
        description.setWordWrap(True)
        layout.addWidget(description)

        options = QHBoxLayout()
        options.setSpacing(8)
        self.black_btn = QPushButton("NEGRO")
        self.color_btn = QPushButton("COLOR")
        self.cover_btn = QPushButton("PORTADA")
        group = QButtonGroup(self)
        group.setExclusive(True)
        for button in (self.black_btn, self.color_btn, self.cover_btn):
            button.setObjectName("small")
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            group.addButton(button)
            options.addWidget(button)
        options.addStretch(1)
        layout.addLayout(options)

        color_row = QHBoxLayout()
        color_row.setSpacing(8)
        self.swatch = QLabel()
        self.swatch.setFixedSize(54, 30)
        self.hex_edit = QLineEdit(self.color)
        self.hex_edit.setMaxLength(9)
        self.hex_edit.setFixedWidth(130)
        self.hex_edit.setPlaceholderText("#RRGGBB")
        pick = QPushButton("ELEGIR COLOR…")
        pick.setObjectName("small")
        pick.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        color_row.addWidget(self.swatch)
        color_row.addWidget(self.hex_edit)
        color_row.addWidget(pick)
        color_row.addStretch(1)
        layout.addLayout(color_row)

        self.error = QLabel("")
        self.error.setObjectName("muted")
        layout.addWidget(self.error)

        row = QHBoxLayout()
        row.setSpacing(8)
        cancel = QPushButton("CANCELAR")
        cancel.setObjectName("small")
        cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        apply_btn = QPushButton("APLICAR")
        apply_btn.setObjectName("small")
        apply_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(apply_btn)
        layout.addLayout(row)

        self._select_mode(mode)
        self._update_swatch()
        self._sync_enabled()

        for button in (self.black_btn, self.color_btn, self.cover_btn):
            button.toggled.connect(self._sync_enabled)
        pick.clicked.connect(self._pick)
        self.hex_edit.textChanged.connect(self._hex_changed)
        cancel.clicked.connect(self.reject)
        apply_btn.clicked.connect(self._accept)

    def _select_mode(self, mode: str) -> None:
        self.black_btn.setChecked(mode == "black")
        self.color_btn.setChecked(mode == "color")
        self.cover_btn.setChecked(mode == "cover")

    def _current_mode(self) -> str:
        if self.color_btn.isChecked():
            return "color"
        if self.cover_btn.isChecked():
            return "cover"
        return "black"

    def _sync_enabled(self) -> None:
        enabled = self.color_btn.isChecked()
        self.hex_edit.setEnabled(enabled)
        self.swatch.setEnabled(enabled)

    def _pick(self) -> None:
        chosen = QColorDialog.getColor(
            QColor(self.color), self, "Elegir color de fondo"
        )
        if chosen.isValid():
            self.color = chosen.name()
            self.color_btn.setChecked(True)
            self.hex_edit.setText(self.color)
            self._update_swatch()

    def _hex_changed(self, text: str) -> None:
        chosen = QColor(text.strip())
        if chosen.isValid():
            self.color = chosen.name()
            self._update_swatch()

    def _update_swatch(self) -> None:
        self.swatch.setStyleSheet(
            f"background-color: {self.color}; border: 1px solid #777777;"
        )

    def _accept(self) -> None:
        mode = self._current_mode()
        if mode == "color":
            chosen = QColor(self.hex_edit.text().strip())
            if not chosen.isValid():
                self.error.setText("COLOR NO VÁLIDO · USA #RRGGBB")
                return
            self.color = chosen.name()
        self.mode = mode
        self.accept()


class SleepDialog(QDialog):
    """Configura el temporizador de apagado."""

    def __init__(
        self,
        remaining: int,
        action: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.minutes: int | None = None
        self.remove = False
        self.action = action
        self.setWindowTitle("Temporizador de apagado")
        self.setModal(True)
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        heading = QLabel("TEMPORIZADOR DE APAGADO")
        heading.setObjectName("section")
        layout.addWidget(heading)

        description = QLabel(
            "La música se detendrá cuando termine la cuenta atrás."
        )
        description.setObjectName("muted")
        description.setWordWrap(True)
        layout.addWidget(description)

        if remaining > 0:
            active = QLabel(f"ACTIVO · QUEDAN {format_time(remaining)}")
            active.setObjectName("section")
            layout.addWidget(active)

        presets = QHBoxLayout()
        presets.setSpacing(8)
        for minutes in (15, 30, 45, 60, 90):
            button = QPushButton(f"{minutes} MIN")
            button.setObjectName("small")
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(
                lambda _checked=False, value=minutes: self.spin.setValue(value)
            )
            presets.addWidget(button)
        presets.addStretch(1)
        layout.addLayout(presets)

        minutes_row = QHBoxLayout()
        minutes_row.setSpacing(8)
        minutes_label = QLabel("MINUTOS")
        minutes_label.setObjectName("small")
        self.spin = QSpinBox()
        self.spin.setRange(1, 600)
        self.spin.setSuffix(" min")
        initial = max(1, round(remaining / 60)) if remaining > 0 else 30
        self.spin.setValue(initial)
        minutes_row.addWidget(minutes_label)
        minutes_row.addWidget(self.spin)
        minutes_row.addStretch(1)
        layout.addLayout(minutes_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_label = QLabel("AL TERMINAR")
        action_label.setObjectName("small")
        self.action_combo = QComboBox()
        self.action_combo.addItem("PAUSAR LA MÚSICA", "pause")
        self.action_combo.addItem("CERRAR EL REPRODUCTOR", "close")
        self.action_combo.setCurrentIndex(1 if action == "close" else 0)
        action_row.addWidget(action_label)
        action_row.addWidget(self.action_combo, 1)
        layout.addLayout(action_row)

        self.error = QLabel("")
        self.error.setObjectName("muted")
        layout.addWidget(self.error)

        row = QHBoxLayout()
        row.setSpacing(8)
        if remaining > 0:
            remove = QPushButton("QUITAR TEMPORIZADOR")
            remove.setObjectName("small")
            remove.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            remove.clicked.connect(self._remove)
            row.addWidget(remove)
        row.addStretch(1)
        cancel = QPushButton("CANCELAR")
        cancel.setObjectName("small")
        cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        start = QPushButton("INICIAR")
        start.setObjectName("small")
        start.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        row.addWidget(cancel)
        row.addWidget(start)
        layout.addLayout(row)

        cancel.clicked.connect(self.reject)
        start.clicked.connect(self._start)

    def _start(self) -> None:
        self.minutes = self.spin.value()
        self.action = self.action_combo.currentData()
        self.accept()

    def _remove(self) -> None:
        self.remove = True
        self.accept()


class PlaylistPickerDialog(QDialog):
    """Selecciona varias canciones de la biblioteca para una lista."""

    def __init__(
        self,
        tracks: list[Track],
        playlist_name: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.tracks = list(tracks)
        self.visible = list(tracks)
        self.setWindowTitle("Añadir canciones")
        self.setModal(True)
        self.setMinimumSize(820, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(10)

        heading = QLabel(f"AÑADIR A «{playlist_name.upper()}»")
        heading.setObjectName("section")
        heading.setWordWrap(True)
        layout.addWidget(heading)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por título, artista o álbum…")
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["TÍTULO", "ARTISTA", "ÁLBUM", "DUR."]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.verticalHeader().setDefaultSectionSize(30)
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 180)
        self.table.setColumnWidth(2, 180)
        self.table.setColumnWidth(3, 70)
        layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.count_label = QLabel("")
        self.count_label.setObjectName("small")
        self.error = QLabel("")
        self.error.setObjectName("muted")
        cancel = QPushButton("CANCELAR")
        cancel.setObjectName("small")
        cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        add = QPushButton("AÑADIR SELECCIÓN")
        add.setObjectName("small")
        add.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        footer.addWidget(self.count_label)
        footer.addWidget(self.error, 1)
        footer.addWidget(cancel)
        footer.addWidget(add)
        layout.addLayout(footer)

        self.search.textChanged.connect(self._filter)
        self.table.itemDoubleClicked.connect(lambda _item: self._accept())
        cancel.clicked.connect(self.reject)
        add.clicked.connect(self._accept)
        self._filter()

    def _filter(self) -> None:
        query = self.search.text().strip().casefold()
        self.visible = [
            track
            for track in self.tracks
            if not query
            or query
            in f"{track.title} {track.artist} {track.album} {track.albumartist}".casefold()
        ]
        self._fill()
        self.count_label.setText(f"{len(self.visible)} PISTAS")

    def _fill(self) -> None:
        self.table.setUpdatesEnabled(False)
        self.table.clearContents()
        self.table.setRowCount(len(self.visible))
        for row, track in enumerate(self.visible):
            values = [
                track.title,
                track.display_artist,
                track.display_album,
                format_time(track.duration),
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                )
                if column == 3:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter
                    )
                if column == 0:
                    item.setToolTip(track.path)
                self.table.setItem(row, column, item)
        self.table.setUpdatesEnabled(True)

    def selected_tracks(self) -> list[Track]:
        rows = sorted(
            {
                index.row()
                for index in self.table.selectionModel().selectedRows()
            }
        )
        return [
            self.visible[row]
            for row in rows
            if 0 <= row < len(self.visible)
        ]

    def _accept(self) -> None:
        if not self.selected_tracks():
            self.error.setText("SELECCIONA AL MENOS UNA CANCIÓN")
            return
        self.accept()
