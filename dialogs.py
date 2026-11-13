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
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from library import Track, format_time
from i18n import tr

PICKER_HEADER_KEYS = ("col_title", "col_artist", "col_album", "col_duration")
PICKER_ALIGNMENTS = (
    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
)


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
        cancel = QPushButton(tr("cancel"))
        cancel.setObjectName("small")
        cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        accept = QPushButton(tr("save"))
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
            self.error.setText(tr("name_required"))
            return
        self.value = text
        self.accept()


class FolderDialog(QDialog):
    """Permite escribir, pegar o examinar la carpeta de la biblioteca."""

    def __init__(self, current: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.selected_path = ""
        self.setWindowTitle(tr("folder_dialog_title"))
        self.setModal(True)
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(10)

        title = QLabel(tr("library_path"))
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
        browse = QPushButton(tr("browse"))
        browse.setObjectName("small")
        browse.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        cancel = QPushButton(tr("cancel"))
        cancel.setObjectName("small")
        cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        accept = QPushButton(tr("load"))
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
            self, tr("folder_pick_title"), start
        )
        if folder:
            self.path_edit.setText(folder)
            self.error.setText("")

    def _accept(self) -> None:
        text = self.path_edit.text().strip()
        if not text:
            self.error.setText(tr("path_required"))
            return
        path = Path(text).expanduser()
        if not path.is_dir():
            self.error.setText(tr("folder_missing"))
            return
        self.selected_path = str(path)
        self.accept()


class BackgroundDialog(QDialog):
    """Elige fondo negro, color, portada actual o una imagen propia."""

    def __init__(
        self,
        mode: str,
        color: str,
        image_path: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.mode = mode
        self.color = color if QColor(color).isValid() else "#000000"
        self.image_path = image_path
        self.setWindowTitle(tr("background_title"))
        self.setModal(True)
        self.setMinimumWidth(540)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        heading = QLabel(tr("background_heading"))
        heading.setObjectName("section")
        layout.addWidget(heading)

        description = QLabel(tr("background_description"))
        description.setObjectName("muted")
        description.setWordWrap(True)
        layout.addWidget(description)

        options = QHBoxLayout()
        options.setSpacing(8)
        self.black_btn = QPushButton(tr("black"))
        self.color_btn = QPushButton(tr("color"))
        self.cover_btn = QPushButton(tr("cover"))
        self.image_btn = QPushButton(tr("image"))
        group = QButtonGroup(self)
        group.setExclusive(True)
        for button in (
            self.black_btn,
            self.color_btn,
            self.cover_btn,
            self.image_btn,
        ):
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
        pick = QPushButton(tr("pick_color"))
        pick.setObjectName("small")
        pick.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        color_row.addWidget(self.swatch)
        color_row.addWidget(self.hex_edit)
        color_row.addWidget(pick)
        color_row.addStretch(1)
        layout.addLayout(color_row)

        image_row = QHBoxLayout()
        image_row.setSpacing(8)
        self.image_label = QLabel(self._image_name())
        self.image_label.setObjectName("muted")
        self.image_label.setToolTip(self.image_path)
        self.image_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self.pick_image = QPushButton(tr("pick_image"))
        self.pick_image.setObjectName("small")
        self.pick_image.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        image_row.addWidget(self.image_label, 1)
        image_row.addWidget(self.pick_image)
        layout.addLayout(image_row)

        self.error = QLabel("")
        self.error.setObjectName("muted")
        layout.addWidget(self.error)

        row = QHBoxLayout()
        row.setSpacing(8)
        cancel = QPushButton(tr("cancel"))
        cancel.setObjectName("small")
        cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        apply_btn = QPushButton(tr("apply"))
        apply_btn.setObjectName("small")
        apply_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(apply_btn)
        layout.addLayout(row)

        self._select_mode(mode)
        self._update_swatch()
        self._sync_enabled()

        for button in (
            self.black_btn,
            self.color_btn,
            self.cover_btn,
            self.image_btn,
        ):
            button.toggled.connect(self._sync_enabled)
        pick.clicked.connect(self._pick)
        self.pick_image.clicked.connect(self._pick_image)
        self.hex_edit.textChanged.connect(self._hex_changed)
        cancel.clicked.connect(self.reject)
        apply_btn.clicked.connect(self._accept)

    def _select_mode(self, mode: str) -> None:
        self.black_btn.setChecked(mode == "black")
        self.color_btn.setChecked(mode == "color")
        self.cover_btn.setChecked(mode == "cover")
        self.image_btn.setChecked(mode == "image")

    def _current_mode(self) -> str:
        if self.color_btn.isChecked():
            return "color"
        if self.cover_btn.isChecked():
            return "cover"
        if self.image_btn.isChecked():
            return "image"
        return "black"

    def _image_name(self) -> str:
        if self.image_path:
            return Path(self.image_path).name
        return tr("no_image")

    def _sync_enabled(self) -> None:
        enabled = self.color_btn.isChecked()
        self.hex_edit.setEnabled(enabled)
        self.swatch.setEnabled(enabled)

    def _pick(self) -> None:
        chosen = QColorDialog.getColor(
            QColor(self.color), self, tr("color_dialog_title")
        )
        if chosen.isValid():
            self.color = chosen.name()
            self.color_btn.setChecked(True)
            self.hex_edit.setText(self.color)
            self._update_swatch()

    def _pick_image(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            tr("image_dialog_title"),
            str(Path.home()),
            f"{tr('images_filter')};;{tr('all_files_filter')}",
        )
        if not chosen:
            return
        self.image_path = chosen
        self.image_label.setText(self._image_name())
        self.image_label.setToolTip(chosen)
        self.image_btn.setChecked(True)
        self.error.setText("")

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
                self.error.setText(tr("invalid_color"))
                return
            self.color = chosen.name()
        elif mode == "image":
            path = Path(self.image_path).expanduser()
            if not path.is_file():
                self.error.setText(tr("invalid_image"))
                return
            self.image_path = str(path)
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
        self.setWindowTitle(tr("sleep_title"))
        self.setModal(True)
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        heading = QLabel(tr("sleep_heading"))
        heading.setObjectName("section")
        layout.addWidget(heading)

        description = QLabel(tr("sleep_description"))
        description.setObjectName("muted")
        description.setWordWrap(True)
        layout.addWidget(description)

        if remaining > 0:
            active = QLabel(
                tr("sleep_active_remaining", time=format_time(remaining))
            )
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
        minutes_label = QLabel(tr("minutes"))
        minutes_label.setObjectName("small")
        self.spin = QSpinBox()
        self.spin.setRange(1, 600)
        self.spin.setSuffix(tr("minutes_suffix"))
        initial = max(1, round(remaining / 60)) if remaining > 0 else 30
        self.spin.setValue(initial)
        minutes_row.addWidget(minutes_label)
        minutes_row.addWidget(self.spin)
        minutes_row.addStretch(1)
        layout.addLayout(minutes_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_label = QLabel(tr("when_finished"))
        action_label.setObjectName("small")
        self.action_combo = QComboBox()
        self.action_combo.addItem(tr("action_pause"), "pause")
        self.action_combo.addItem(tr("action_close"), "close")
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
            remove = QPushButton(tr("remove_timer"))
            remove.setObjectName("small")
            remove.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            remove.clicked.connect(self._remove)
            row.addWidget(remove)
        row.addStretch(1)
        cancel = QPushButton(tr("cancel"))
        cancel.setObjectName("small")
        cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        start = QPushButton(tr("start"))
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
        self.setWindowTitle(tr("add_songs_title"))
        self.setModal(True)
        self.setMinimumSize(820, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(10)

        heading = QLabel(
            tr("add_to_playlist_heading", name=playlist_name.upper())
        )
        heading.setObjectName("section")
        heading.setWordWrap(True)
        layout.addWidget(heading)

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("search_placeholder"))
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            [tr(key) for key in PICKER_HEADER_KEYS]
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
        for column, alignment in enumerate(PICKER_ALIGNMENTS):
            item = self.table.horizontalHeaderItem(column)
            if item is not None:
                item.setTextAlignment(alignment)
        self.table.setColumnWidth(1, 190)
        self.table.setColumnWidth(2, 190)
        self.table.setColumnWidth(3, 84)
        layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.count_label = QLabel("")
        self.count_label.setObjectName("small")
        self.error = QLabel("")
        self.error.setObjectName("muted")
        cancel = QPushButton(tr("cancel"))
        cancel.setObjectName("small")
        cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        add = QPushButton(tr("add_selection"))
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
        self.count_label.setText(tr("track_count", n=len(self.visible)))

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
                item.setTextAlignment(PICKER_ALIGNMENTS[column])
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
            self.error.setText(tr("select_at_least_one"))
            return
        self.accept()


class TrackInfoDialog(QDialog):
    """Muestra todos los datos disponibles de una pista."""

    def __init__(self, track: Track, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("track_info_title"))
        self.setModal(True)
        self.setMinimumWidth(540)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(10)

        heading = QLabel(track.title)
        heading.setObjectName("section")
        heading.setWordWrap(True)
        layout.addWidget(heading)

        subtitle = QLabel(track.display_artist)
        subtitle.setObjectName("artist")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        number = "—"
        if track.tracknumber and track.discnumber:
            number = tr(
                "info_track_disc",
                track=track.tracknumber,
                disc=track.discnumber,
            )
        elif track.tracknumber:
            number = tr("info_track", track=track.tracknumber)
        elif track.discnumber:
            number = tr("info_disc", disc=track.discnumber)

        rows = [
            ("info_album", track.display_album),
            ("info_album_artist", track.albumartist or "—"),
            ("info_year", track.year or "—"),
            ("info_genre", track.genre or "—"),
            ("info_number", number),
            ("info_duration", format_time(track.duration)),
            ("info_format", track.suffix.upper().lstrip(".") or "—"),
            ("info_quality", track.quality or "—"),
            ("info_cover", tr("yes") if track.has_cover else tr("no")),
            ("info_file", track.path),
        ]

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(7)
        self._info_rows: list[tuple[QLabel, QLabel]] = []
        for row, (key_name, value) in enumerate(rows):
            key = QLabel(tr(key_name))
            key.setObjectName("small")
            key.setAlignment(
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
            )
            text = QLabel(value)
            text.setWordWrap(True)
            text.setAlignment(
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
            )
            text.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            if key_name == "info_file":
                text.setObjectName("muted")
            grid.addWidget(key, row, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(text, row, 1, Qt.AlignmentFlag.AlignTop)
            self._info_rows.append((key, text))
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(len(rows), 1)
        layout.addLayout(grid)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton(tr("close"))
        close.setObjectName("small")
        close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        close.setDefault(True)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._align_info_rows()

    def _align_info_rows(self) -> None:
        """Alinea cada etiqueta con su valor por la línea base del texto.

        Las etiquetas usan una fuente distinta (y más pequeña) que los
        valores, así que se compensa la diferencia de ascenso con un margen
        superior para que ambas líneas base coincidan.
        """
        if not self._info_rows:
            return

        key_width = 0
        for key, value in self._info_rows:
            key.setContentsMargins(0, 0, 0, 0)
            value.setContentsMargins(0, 0, 0, 0)
            key.ensurePolished()
            value.ensurePolished()
            key_width = max(key_width, key.sizeHint().width())

        for key, value in self._info_rows:
            key.setFixedWidth(key_width)
            diff = value.fontMetrics().ascent() - key.fontMetrics().ascent()
            if diff > 0:
                key.setContentsMargins(0, diff, 0, 0)
            elif diff < 0:
                value.setContentsMargins(0, -diff, 0, 0)

        self.layout().activate()
