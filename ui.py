"""Interfaz del reproductor FLAC con estética retro monocroma."""

from __future__ import annotations

import json
import os
import random
from pathlib import Path

from PySide6.QtCore import QEvent, QSettings, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeySequence,
    QPainter,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dialogs import (
    BackgroundDialog,
    FolderDialog,
    NameDialog,
    PlaylistPickerDialog,
    SleepDialog,
    TrackInfoDialog,
)
from i18n import DEFAULT_LANGUAGE, LANGUAGES, get_language, set_language, tr
from library import (
    Track,
    format_time,
    get_cover_bytes,
    get_lyrics,
    library_summary,
    load_cached_library,
    scan_library,
)
from mpv_backend import MpvController
from theme import (
    CONTROL_ICON_SIZE,
    DEFAULT_COVER_SIZE,
    PIXEL_SWAP,
    TIMER_ICON_SIZE,
    Backdrop,
    ClickSlider,
    app_icon,
    build_style,
    file_icon,
    heart_icon,
    library_icon,
    load_fonts,
    pixel_icon,
    repeat_icon,
)


MAIN_HEADER_KEYS = (
    "col_fav",
    "col_num",
    "col_title",
    "col_artist",
    "col_album",
    "col_duration",
)
MAIN_ALIGNMENTS = (
    Qt.AlignmentFlag.AlignCenter,
    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
)


class ScanWorker(QThread):
    done = Signal(object, str)
    fail = Signal(str)

    def __init__(self, root: str):
        super().__init__()
        self.root = root

    def run(self) -> None:
        try:
            self.done.emit(scan_library(self.root), self.root)
        except Exception as exc:  # noqa: BLE001 - se informa en la interfaz
            self.fail.emit(f"{type(exc).__name__}: {exc}")


class MainWindow(QMainWindow):
    def __init__(self, base_dir: Path, initial_library: str | None = None):
        super().__init__()
        self.base_dir = Path(base_dir)
        self.initial_library = initial_library

        self.tracks: list[Track] = []
        self.visible: list[Track] = []
        self.current: Track | None = None
        self.duration = 0.0
        self.position = 0.0
        self.seeking = False
        self.finished_queue = False
        self.last_volume = 70
        self.scan_thread: ScanWorker | None = None
        self.pending_library: str | None = None
        self._displayed_root = ""
        self.current_cover: QPixmap | None = None
        self.track_by_path: dict[str, Track] = {}
        self.lyrics: list[tuple[float, str]] = []
        self.lyric_index = -1

        self.settings = QSettings("STARTED", "Reproductor FLAC")
        self.language = str(
            self.settings.value("language", DEFAULT_LANGUAGE) or DEFAULT_LANGUAGE
        )
        if self.language not in {code for code, _name in LANGUAGES}:
            self.language = DEFAULT_LANGUAGE
        set_language(self.language)
        self.settings.setValue("language", self.language)
        self.shuffle = bool(self.settings.value("shuffle", False, bool))
        self.repeat = str(self.settings.value("repeat", "off"))
        if self.repeat not in ("off", "all", "one"):
            self.repeat = "off"

        self.cover_size = DEFAULT_COVER_SIZE
        self.bg_mode = str(self.settings.value("background_mode", "black") or "black")
        if self.bg_mode not in ("black", "color", "cover", "image"):
            self.bg_mode = "black"
        self.bg_color = str(
            self.settings.value("background_color", "#000000") or "#000000"
        )
        if not QColor(self.bg_color).isValid():
            self.bg_color = "#000000"
        self.bg_image_path = str(
            self.settings.value("background_image", "") or ""
        )
        self.bg_image: QPixmap | None = None
        if self.bg_image_path:
            path = Path(self.bg_image_path)
            if path.is_file():
                loaded = QPixmap(str(path))
                if not loaded.isNull():
                    self.bg_image = loaded
                else:
                    self.bg_image_path = ""
            else:
                self.bg_image_path = ""
        if self.bg_mode == "image" and self.bg_image is None:
            self.bg_mode = "black"

        self.player_on_left = str(
            self.settings.value("player_side", "right") or "right"
        ) == "left"
        self.library_hidden = False

        stored_favorites = self.settings.value("favorites", [])
        if isinstance(stored_favorites, str):
            stored_favorites = [stored_favorites]
        self.favorites: set[str] = {
            str(path) for path in (stored_favorites or [])
        }

        self.config_dir = (
            Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
            / "STARTED"
        )
        self.playlists_file = self.config_dir / "playlists.json"
        self.playlists: list[dict] = []
        self.current_playlist: int | None = None
        self.mode = "library"
        self._load_playlists()

        self._session_restored = False
        self.resume_path = str(self.settings.value("last_path", "") or "")
        try:
            self.resume_position = float(
                self.settings.value("last_position", 0) or 0
            )
        except (TypeError, ValueError):
            self.resume_position = 0.0

        self.sleep_seconds_left = 0
        self.sleep_action = "pause"
        self.sleep_timer = QTimer(self)
        self.sleep_timer.setInterval(1000)
        self.sleep_timer.timeout.connect(self._sleep_tick)

        volume = int(self.settings.value("volume", 70))
        self.mpv = MpvController(volume=volume, parent=self)

        self.setWindowTitle(f"{tr('app_name')} · STARTED")
        self.setWindowIcon(app_icon(self.base_dir))
        self.setMinimumSize(1080, 760)
        self.resize(1220, 820)
        self.setAcceptDrops(True)

        self._build_ui()
        self._apply_style()
        self._connect_signals()
        self._restore_state()

        self.mpv.start()
        QTimer.singleShot(300, self._open_initial_library)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self.backdrop = Backdrop()
        self.setCentralWidget(self.backdrop)
        self.outer = QHBoxLayout(self.backdrop)
        self.outer.setContentsMargins(14, 14, 14, 14)
        self.outer.setSpacing(14)

        self.library_panel = self._build_library_panel()
        self.player_panel = self._build_player_panel()
        self._apply_panel_order()

    def _apply_panel_order(self) -> None:
        """Coloca el reproductor a la izquierda, a la derecha o centrado."""
        while self.outer.count():
            self.outer.takeAt(0)
        if self.library_hidden:
            self.outer.addStretch(1)
            self.outer.addWidget(self.player_panel, 0)
            self.outer.addStretch(1)
            return
        if self.player_on_left:
            self.outer.addWidget(self.player_panel, 0)
            self.outer.addWidget(self.library_panel, 1)
        else:
            self.outer.addWidget(self.library_panel, 1)
            self.outer.addWidget(self.player_panel, 0)

    def _set_table_headers(self) -> None:
        """Traduce los encabezados y les da la misma alineación que las celdas."""
        self.table.setHorizontalHeaderLabels(
            [tr(key) for key in MAIN_HEADER_KEYS]
        )
        for column, alignment in enumerate(MAIN_ALIGNMENTS):
            item = self.table.horizontalHeaderItem(column)
            if item is not None:
                item.setTextAlignment(alignment)

    def _update_library_button(self) -> None:
        if self.library_hidden:
            self.hide_library_btn.setIcon(library_icon(True))
            self.hide_library_btn.setToolTip(tr("tooltip_show_library"))
        else:
            self.hide_library_btn.setIcon(library_icon(False))
            self.hide_library_btn.setToolTip(tr("tooltip_hide_library"))

    def _toggle_library(self) -> None:
        self.library_hidden = not self.library_hidden
        self.library_panel.setVisible(not self.library_hidden)
        self._apply_panel_order()
        self._update_library_button()
        self._set_state(
            "library_hidden" if self.library_hidden else "library_visible"
        )

    def _side_tooltip(self) -> str:
        key = "tooltip_move_right" if self.player_on_left else "tooltip_move_left"
        return tr(key)

    def _toggle_panel_side(self) -> None:
        self.player_on_left = not self.player_on_left
        self._apply_panel_order()
        self.settings.setValue(
            "player_side", "left" if self.player_on_left else "right"
        )
        self._set_state(
            "player_left" if self.player_on_left else "player_right"
        )
        self.side_btn.setToolTip(self._side_tooltip())

    def _build_library_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.library_title = QLabel(tr("library"))
        self.library_title.setObjectName("section")
        self.count_label = QLabel(tr("track_count", n=0))
        self.count_label.setObjectName("small")
        self.count_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.language_combo = QComboBox()
        self.language_combo.setObjectName("language")
        self.language_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.language_combo.setFixedWidth(112)
        self.language_combo.setToolTip(tr("tooltip_language"))
        for code, name in LANGUAGES:
            self.language_combo.addItem(name, code)
        self.language_combo.setCurrentIndex(
            max(0, [code for code, _name in LANGUAGES].index(self.language))
        )
        self.side_btn = QPushButton()
        self.side_btn.setObjectName("icon")
        self.side_btn.setFixedSize(38, 30)
        self.side_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.side_btn.setIconSize(QSize(20, 20))
        self.side_btn.setIcon(pixel_icon(PIXEL_SWAP))
        self.side_btn.setToolTip(self._side_tooltip())
        header.addWidget(self.library_title)
        header.addStretch(1)
        header.addWidget(self.language_combo)
        header.addSpacing(8)
        header.addWidget(self.count_label)
        header.addSpacing(6)
        header.addWidget(self.side_btn)
        layout.addLayout(header)

        modes = QHBoxLayout()
        modes.setSpacing(6)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.library_mode_btn = QPushButton(tr("library"))
        self.favorites_mode_btn = QPushButton(tr("favorites"))
        self.playlists_mode_btn = QPushButton(tr("playlists"))
        for button in (
            self.library_mode_btn,
            self.favorites_mode_btn,
            self.playlists_mode_btn,
        ):
            button.setObjectName("small")
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.mode_group.addButton(button)
            modes.addWidget(button)
        modes.addStretch(1)
        self.library_mode_btn.setChecked(True)
        layout.addLayout(modes)

        self.playlist_bar = QWidget()
        playlist_layout = QVBoxLayout(self.playlist_bar)
        playlist_layout.setContentsMargins(0, 0, 0, 0)
        playlist_layout.setSpacing(6)

        playlist_top = QHBoxLayout()
        playlist_top.setSpacing(6)
        self.playlist_combo = QComboBox()
        self.playlist_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.new_playlist_btn = QPushButton(tr("new"))
        self.delete_playlist_btn = QPushButton(tr("delete"))
        for button in (self.new_playlist_btn, self.delete_playlist_btn):
            button.setObjectName("small")
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        playlist_top.addWidget(self.playlist_combo, 1)
        playlist_top.addWidget(self.new_playlist_btn)
        playlist_top.addWidget(self.delete_playlist_btn)
        playlist_layout.addLayout(playlist_top)

        playlist_bottom = QHBoxLayout()
        playlist_bottom.setSpacing(6)
        self.add_songs_btn = QPushButton(tr("add_ellipsis"))
        self.remove_song_btn = QPushButton(tr("remove"))
        self.up_song_btn = QPushButton("↑")
        self.down_song_btn = QPushButton("↓")
        for button in (
            self.add_songs_btn,
            self.remove_song_btn,
            self.up_song_btn,
            self.down_song_btn,
        ):
            button.setObjectName("small")
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.up_song_btn.setFixedWidth(34)
        self.down_song_btn.setFixedWidth(34)
        playlist_bottom.addWidget(self.add_songs_btn)
        playlist_bottom.addWidget(self.remove_song_btn)
        playlist_bottom.addStretch(1)
        playlist_bottom.addWidget(self.up_song_btn)
        playlist_bottom.addWidget(self.down_song_btn)
        playlist_layout.addLayout(playlist_bottom)

        self.playlist_bar.setVisible(False)
        layout.addWidget(self.playlist_bar)

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("search_placeholder"))
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.artist_combo = QComboBox()
        self.artist_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.album_combo = QComboBox()
        self.album_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        filters.addWidget(self.artist_combo, 1)
        filters.addWidget(self.album_combo, 1)
        layout.addLayout(filters)

        self.table = QTableWidget(0, 6)
        self._set_table_headers()
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.table.verticalHeader().setDefaultSectionSize(31)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        header_view = self.table.horizontalHeader()
        header_view.setHighlightSections(False)
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header_view.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header_view.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setIconSize(QSize(22, 22))
        self.table.setColumnWidth(0, 46)
        self.table.setColumnWidth(1, 50)
        self.table.setColumnWidth(3, 160)
        self.table.setColumnWidth(4, 150)
        self.table.setColumnWidth(5, 84)
        layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.path_label = QLabel(tr("no_library"))
        self.path_label.setObjectName("muted")
        self.path_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        footer.addWidget(self.path_label, 1)

        self.reload_btn = QPushButton(tr("reload"))
        self.reload_btn.setObjectName("small")
        self.reload_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.reload_btn.setToolTip(tr("tooltip_reload"))
        self.folder_btn = QPushButton(tr("folder"))
        self.folder_btn.setObjectName("small")
        self.folder_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.folder_btn.setToolTip(tr("tooltip_folder"))
        footer.addWidget(self.reload_btn)
        footer.addWidget(self.folder_btn)
        layout.addLayout(footer)

        return panel

    def _build_player_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(440)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 14, 24, 12)
        layout.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(5)
        self.now_label = QLabel(tr("now_playing"))
        self.now_label.setObjectName("section")
        top.addWidget(self.now_label)
        top.addStretch(1)
        self.sleep_label = QLabel("")
        self.sleep_label.setObjectName("small")
        self.sleep_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.sleep_btn = QPushButton()
        self.sleep_btn.setObjectName("icon")
        self.sleep_btn.setFixedSize(38, 32)
        self.sleep_btn.setCheckable(True)
        self.sleep_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.sleep_btn.setIconSize(QSize(TIMER_ICON_SIZE, TIMER_ICON_SIZE))
        self.sleep_btn.setIcon(file_icon("timer.png"))
        self.sleep_btn.setToolTip(tr("tooltip_sleep"))
        self.background_btn = QPushButton()
        self.background_btn.setObjectName("icon")
        self.background_btn.setFixedSize(38, 32)
        self.background_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.background_btn.setIconSize(
            QSize(CONTROL_ICON_SIZE, CONTROL_ICON_SIZE)
        )
        self.background_btn.setIcon(file_icon("background.png"))
        self.background_btn.setToolTip(tr("tooltip_background"))
        self.hide_library_btn = QPushButton()
        self.hide_library_btn.setObjectName("icon")
        self.hide_library_btn.setFixedSize(38, 32)
        self.hide_library_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide_library_btn.setIconSize(
            QSize(CONTROL_ICON_SIZE, CONTROL_ICON_SIZE)
        )
        self.hide_library_btn.setIcon(library_icon(False))
        self.hide_library_btn.setToolTip(tr("tooltip_hide_library"))
        top.addWidget(self.sleep_label)
        top.addWidget(self.sleep_btn)
        top.addWidget(self.background_btn)
        top.addWidget(self.hide_library_btn)
        top.addSpacing(-10)
        layout.addLayout(top)

        self.cover_label = QLabel()
        self.cover_label.setObjectName("cover")
        self.cover_label.setFixedSize(self.cover_size, self.cover_size)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover_row = QHBoxLayout()
        cover_row.addStretch(1)
        cover_row.addWidget(self.cover_label)
        cover_row.addStretch(1)
        layout.addSpacing(6)
        layout.addLayout(cover_row)
        layout.addSpacing(8)

        self.title_label = QLabel(tr("nothing_playing"))
        self.title_label.setObjectName("title")
        self.title_label.setWordWrap(True)
        self.title_label.setFixedHeight(68)
        self.title_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        layout.addWidget(self.title_label)

        self.artist_label = QLabel("—")
        self.artist_label.setObjectName("artist")
        layout.addWidget(self.artist_label)

        self.meta_label = QLabel("")
        self.meta_label.setObjectName("meta")
        layout.addWidget(self.meta_label)

        self.lyrics_label = QLabel("")
        self.lyrics_label.setObjectName("lyrics")
        self.lyrics_label.setWordWrap(True)
        self.lyrics_label.setFixedHeight(86)
        self.lyrics_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self.lyrics_label.setVisible(False)
        layout.addWidget(self.lyrics_label)

        layout.addStretch(1)

        times = QHBoxLayout()
        self.time_current = QLabel("0:00")
        self.time_current.setObjectName("muted")
        self.time_total = QLabel("0:00")
        self.time_total.setObjectName("muted")
        self.time_total.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        times.addWidget(self.time_current)
        times.addStretch(1)
        times.addWidget(self.time_total)
        layout.addLayout(times)

        self.progress = ClickSlider(Qt.Orientation.Horizontal)
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setEnabled(False)
        self.progress.setToolTip(tr("tooltip_progress"))
        layout.addWidget(self.progress)

        layout.addSpacing(8)

        controls = QHBoxLayout()
        controls.setSpacing(6)
        self.shuffle_btn = QPushButton()
        self.shuffle_btn.setObjectName("icon")
        self.shuffle_btn.setFixedSize(38, 38)
        self.shuffle_btn.setCheckable(True)
        self.shuffle_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.shuffle_btn.setIconSize(
            QSize(CONTROL_ICON_SIZE, CONTROL_ICON_SIZE)
        )
        self.shuffle_btn.setIcon(file_icon("shuffle.png"))
        self.shuffle_btn.setToolTip(tr("tooltip_shuffle"))
        self.prev_btn = QPushButton("<<")
        self.prev_btn.setObjectName("transport")
        self.prev_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.prev_btn.setToolTip(tr("tooltip_prev"))
        self.play_btn = QPushButton(tr("play"))
        self.play_btn.setObjectName("play")
        self.play_btn.setMinimumSize(118, 44)
        self.play_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.play_btn.setToolTip(tr("tooltip_play"))
        self._play_key = "play"
        self.next_btn = QPushButton(">>")
        self.next_btn.setObjectName("transport")
        self.next_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.next_btn.setToolTip(tr("tooltip_next"))
        self.repeat_btn = QPushButton()
        self.repeat_btn.setObjectName("icon")
        self.repeat_btn.setFixedSize(38, 38)
        self.repeat_btn.setCheckable(True)
        self.repeat_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.repeat_btn.setIconSize(
            QSize(CONTROL_ICON_SIZE, CONTROL_ICON_SIZE)
        )
        self.repeat_btn.setIcon(repeat_icon(False))
        self.repeat_btn.setToolTip(tr("tooltip_repeat_off"))
        controls.addWidget(self.shuffle_btn)
        controls.addWidget(self.prev_btn)
        controls.addWidget(self.play_btn, 1)
        controls.addWidget(self.next_btn)
        controls.addWidget(self.repeat_btn)
        layout.addLayout(controls)

        layout.addSpacing(6)

        volume_row = QHBoxLayout()
        volume_row.setSpacing(8)
        self.volume_title = QLabel(tr("volume"))
        self.volume_title.setObjectName("small")
        self.volume = ClickSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(self.mpv.volume)
        self.volume.setFixedWidth(150)
        self.volume_value = QLabel(f"{self.volume.value()}")
        self.volume_value.setObjectName("muted")
        self.volume_value.setFixedWidth(34)
        self.volume_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        volume_row.addWidget(self.volume_title)
        volume_row.addStretch(1)
        volume_row.addWidget(self.volume)
        volume_row.addWidget(self.volume_value)
        layout.addLayout(volume_row)

        self.state_label = QLabel(tr("starting"))
        self.state_label.setObjectName("state")
        self._state_key = "starting"
        self._state_kwargs: dict[str, object] = {}
        layout.addWidget(self.state_label)

        self.cover_label.setPixmap(self._placeholder())
        return panel

    def _apply_style(self) -> None:
        self.setStyleSheet(build_style(self.bg_mode, self.bg_color))
        self.backdrop.set_background(self.bg_mode, self.bg_color)
        self.backdrop.set_cover(
            self.current_cover if self.bg_mode == "cover" else None
        )
        self.backdrop.set_image(
            self.bg_image if self.bg_mode == "image" else None
        )

    # -------------------------------------------------------------- idioma
    def _set_state(self, key: str, **kwargs: object) -> None:
        """Guarda el estado actual para poder retraducirlo al cambiar idioma."""
        self._state_key = key
        self._state_kwargs = kwargs
        self.state_label.setText(tr(key, **kwargs))

    def _refresh_state_text(self) -> None:
        self.state_label.setText(tr(self._state_key, **self._state_kwargs))

    def _set_play_text(self, key: str) -> None:
        self._play_key = key
        self.play_btn.setText(tr(key))

    def _refresh_play_text(self) -> None:
        self.play_btn.setText(tr(self._play_key))

    def _update_window_title(self) -> None:
        root = self.path_label.toolTip() if hasattr(self, "path_label") else ""
        if root:
            self.setWindowTitle(f"{tr('app_name')} · {Path(root).name or root}")
        else:
            self.setWindowTitle(f"{tr('app_name')} · STARTED")

    def _language_changed(self, index: int) -> None:
        code = self.language_combo.itemData(index)
        if not code or code == get_language():
            return
        self.language = str(code)
        set_language(self.language)
        self.settings.setValue("language", self.language)
        self._retranslate_ui()

    def _retranslate_ui(self) -> None:
        """Actualiza todos los textos visibles sin reconstruir la ventana."""
        self._update_window_title()

        self.library_title.setText(tr("library"))
        self.language_combo.setToolTip(tr("tooltip_language"))
        self.library_mode_btn.setText(tr("library"))
        self.favorites_mode_btn.setText(tr("favorites"))
        self.playlists_mode_btn.setText(tr("playlists"))
        self.new_playlist_btn.setText(tr("new"))
        self.delete_playlist_btn.setText(tr("delete"))
        self.add_songs_btn.setText(tr("add_ellipsis"))
        self.remove_song_btn.setText(tr("remove"))
        self.search.setPlaceholderText(tr("search_placeholder"))
        self._set_table_headers()
        if not self.path_label.toolTip():
            self.path_label.setText(tr("no_library"))
        self.reload_btn.setText(tr("reload"))
        self.reload_btn.setToolTip(tr("tooltip_reload"))
        self.folder_btn.setText(tr("folder"))
        self.folder_btn.setToolTip(tr("tooltip_folder"))
        self.side_btn.setToolTip(self._side_tooltip())
        self._update_library_button()

        self.now_label.setText(tr("now_playing"))
        self.sleep_btn.setToolTip(tr("tooltip_sleep"))
        self.background_btn.setToolTip(tr("tooltip_background"))
        self.progress.setToolTip(tr("tooltip_progress"))
        self.shuffle_btn.setToolTip(tr("tooltip_shuffle"))
        self.prev_btn.setToolTip(tr("tooltip_prev"))
        self.play_btn.setToolTip(tr("tooltip_play"))
        self.next_btn.setToolTip(tr("tooltip_next"))
        self._update_repeat_button()
        self.volume_title.setText(tr("volume"))
        if self.current is None:
            self.title_label.setText(tr("nothing_playing"))
        else:
            self.artist_label.setText(self.current.display_artist)
            album = self.current.display_album
            quality = self.current.quality
            self.meta_label.setText(
                f"{album} · {quality}" if quality else album
            )
        self._refresh_play_text()
        self._refresh_state_text()
        self._update_sleep_label()
        if self.current_cover is None:
            self._render_cover()

        artist = self.artist_combo.currentData() or ""
        album = self.album_combo.currentData() or ""
        self._populate_filters()
        self._restore_filters(artist, album)
        self._apply_filters()

    def _connect_signals(self) -> None:
        self.search.textChanged.connect(self._apply_filters)
        self.search.returnPressed.connect(self._search_enter)
        self.artist_combo.currentIndexChanged.connect(self._artist_changed)
        self.album_combo.currentIndexChanged.connect(self._apply_filters)
        self.language_combo.currentIndexChanged.connect(self._language_changed)
        self.table.itemActivated.connect(self._on_item_activated)
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.customContextMenuRequested.connect(self._table_menu)
        self.table.installEventFilter(self)

        self.folder_btn.clicked.connect(self._choose_folder)
        self.reload_btn.clicked.connect(self._reload_library)
        self.side_btn.clicked.connect(
            lambda _checked=False: self._toggle_panel_side()
        )

        self.play_btn.clicked.connect(self.play_pause)
        self.prev_btn.clicked.connect(self.prev_track)
        self.next_btn.clicked.connect(self.next_track)
        self.shuffle_btn.clicked.connect(self._toggle_shuffle)
        self.repeat_btn.clicked.connect(self._cycle_repeat)

        self.progress.scrubbed.connect(self._seek_scrub)
        self.progress.seekRequested.connect(self._seek_to)
        self.volume.valueChanged.connect(self._volume_slider)

        self.library_mode_btn.clicked.connect(
            lambda _checked=False: self._set_mode("library")
        )
        self.favorites_mode_btn.clicked.connect(
            lambda _checked=False: self._set_mode("favorites")
        )
        self.playlists_mode_btn.clicked.connect(
            lambda _checked=False: self._set_mode("playlist")
        )
        self.playlist_combo.currentIndexChanged.connect(
            self._playlist_changed
        )
        self.new_playlist_btn.clicked.connect(
            lambda _checked=False: self._new_playlist()
        )
        self.delete_playlist_btn.clicked.connect(self._delete_playlist)
        self.add_songs_btn.clicked.connect(self._add_songs_to_playlist)
        self.remove_song_btn.clicked.connect(self._remove_from_playlist)
        self.up_song_btn.clicked.connect(
            lambda _checked=False: self._move_playlist_track(-1)
        )
        self.down_song_btn.clicked.connect(
            lambda _checked=False: self._move_playlist_track(1)
        )

        self.hide_library_btn.clicked.connect(
            lambda _checked=False: self._toggle_library()
        )
        self.sleep_btn.clicked.connect(self._open_sleep_dialog)
        self.background_btn.clicked.connect(self._choose_background)

        self.mpv.positionChanged.connect(self._on_position)
        self.mpv.durationChanged.connect(self._on_duration)
        self.mpv.pausedChanged.connect(self._on_paused)
        self.mpv.volumeChanged.connect(self._on_mpv_volume)
        self.mpv.ended.connect(self._on_ended)
        self.mpv.loaded.connect(self._on_loaded)
        self.mpv.failed.connect(self._on_failed)
        self.mpv.ready.connect(self._on_ready)

        self.shortcuts = []
        for sequence, slot in (
            ("Ctrl+F", self._focus_search),
            ("Ctrl+O", self._choose_folder),
            ("F5", self._reload_library),
            ("Ctrl+L", self._toggle_panel_side),
            ("Ctrl+H", self._toggle_library),
            ("Ctrl+Up", self._volume_up),
            ("Ctrl+Down", self._volume_down),
            (QKeySequence(Qt.Key.Key_MediaPlay), self.play_pause),
            (QKeySequence(Qt.Key.Key_MediaNext), self.next_track),
            (QKeySequence(Qt.Key.Key_MediaPrevious), self.prev_track),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(slot)
            self.shortcuts.append(shortcut)

    def _restore_state(self) -> None:
        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self.shuffle_btn.setChecked(self.shuffle)
        self.repeat_btn.setChecked(self.repeat != "off")
        self._update_repeat_button()

        volume = int(self.settings.value("volume", 70))
        self.volume.blockSignals(True)
        self.volume.setValue(volume)
        self.volume.blockSignals(False)
        self.volume_value.setText(str(volume))

        self._refresh_playlist_combo()
        self._update_library_button()
        self._set_mode("library")

    # ------------------------------------------------------------- library
    def _open_initial_library(self) -> None:
        candidates = [
            self.initial_library,
            str(self.settings.value("library", "")),
            "/mnt/HDD/Musica",
            str(Path.home() / "Música"),
        ]
        for candidate in candidates:
            if candidate and Path(candidate).is_dir():
                self.load_library(candidate)
                return
        self._set_state("choose_folder")
        self.path_label.setText(tr("no_library"))
        self.count_label.setText(tr("track_count", n=0))

    def load_library(self, path: str, remember: bool = True) -> None:
        folder = Path(path)
        if not folder.is_dir():
            self._set_state("invalid_folder")
            return
        if self.scan_thread is not None:
            self.pending_library = str(folder)
            self._set_state("waiting_scan")
            return

        if remember:
            self.settings.setValue("library", str(folder))
        root = str(folder)
        self.path_label.setText(root)
        self.path_label.setToolTip(root)
        self.reload_btn.setEnabled(False)

        cached = load_cached_library(folder)
        if cached is not None:
            # Mostrar la lista guardada al instante; el escaneo solo comprueba
            # si hay archivos nuevos o modificados.
            self._show_library(cached, root, restore_session=True)
            self._set_state("updating_library")
        else:
            self._set_state("scanning")

        self.scan_thread = ScanWorker(root)
        self.scan_thread.done.connect(self._library_loaded)
        self.scan_thread.fail.connect(self._scan_failed)
        self.scan_thread.finished.connect(self._scan_finished)
        self.scan_thread.start()

    def _show_library(
        self, tracks: list[Track], root: str, restore_session: bool = False
    ) -> None:
        if self._displayed_root != root:
            self.mpv.stop()
            self._reset_player()
        self.tracks = tracks
        self.track_by_path = {track.path: track for track in tracks}
        self.visible = tracks
        self._populate_filters()
        self._refresh_playlist_combo()
        self._apply_filters()
        self._displayed_root = root
        self.path_label.setText(root)
        self.path_label.setToolTip(root)
        self.folder_btn.setEnabled(True)
        self.reload_btn.setEnabled(True)
        self._update_window_title()
        if restore_session and tracks:
            self.table.setFocus()
            QTimer.singleShot(0, self._restore_last_session)

    def _library_loaded(self, tracks: list[Track], root: str) -> None:
        if self._displayed_root == root:
            # Refresco en segundo plano: mantener la reproducción actual y los
            # filtros elegidos por el usuario.
            current_path = self.current.path if self.current is not None else ""
            artist = self.artist_combo.currentData() or ""
            album = self.album_combo.currentData() or ""
            self.tracks = tracks
            self.track_by_path = {track.path: track for track in tracks}
            self.visible = tracks
            self._populate_filters()
            self._restore_filters(artist, album)
            self._refresh_playlist_combo()
            self._apply_filters()
            if current_path:
                self.current = self.track_by_path.get(current_path, self.current)
            self.path_label.setText(root)
            self.path_label.setToolTip(root)
            self.folder_btn.setEnabled(True)
            self.reload_btn.setEnabled(True)
            if tracks:
                self._set_state("library_ready")
                if not self._session_restored:
                    QTimer.singleShot(0, self._restore_last_session)
            else:
                self._set_state("no_audio_files")
            self._update_window_title()
            return

        self._show_library(tracks, root, restore_session=True)
        if tracks:
            self._set_state("library_ready")
            self.table.setFocus()
        else:
            self._set_state("no_audio_files")

    def _scan_failed(self, message: str) -> None:
        self._set_state("scan_error")
        self.path_label.setToolTip(message)
        self.folder_btn.setEnabled(True)
        self.reload_btn.setEnabled(True)

    def _scan_finished(self) -> None:
        if self.scan_thread is not None:
            self.scan_thread.deleteLater()
            self.scan_thread = None
        if self.pending_library:
            path, self.pending_library = self.pending_library, None
            QTimer.singleShot(0, lambda: self.load_library(path))

    def _choose_folder(self) -> None:
        current = self.path_label.toolTip() or str(Path.home())
        dialog = FolderDialog(current, self)
        dialog.setStyleSheet(self.styleSheet())
        if (
            dialog.exec() == QDialog.DialogCode.Accepted
            and dialog.selected_path
        ):
            self.load_library(dialog.selected_path)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - API de Qt
        if any(Path(url.toLocalFile()).is_dir() for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802 - API de Qt
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_dir():
                self.load_library(str(path))
                event.acceptProposedAction()
                return
        event.ignore()

    def _reload_library(self) -> None:
        folder = self.path_label.toolTip()
        if folder and Path(folder).is_dir():
            self.load_library(folder)

    def _populate_filters(self) -> None:
        self.artist_combo.blockSignals(True)
        self.artist_combo.clear()
        self.artist_combo.addItem(tr("all_artists"), "")
        artists = sorted(
            {track.display_artist for track in self.tracks}, key=str.casefold
        )
        for artist in artists:
            self.artist_combo.addItem(artist, artist)
        self.artist_combo.setCurrentIndex(0)
        self.artist_combo.blockSignals(False)
        self._populate_albums()

    def _populate_albums(self) -> None:
        artist = self.artist_combo.currentData() or ""
        self.album_combo.blockSignals(True)
        self.album_combo.clear()
        self.album_combo.addItem(tr("all_albums"), "")
        albums = sorted(
            {
                track.display_album
                for track in self.tracks
                if not artist or track.display_artist == artist
            },
            key=str.casefold,
        )
        for album in albums:
            self.album_combo.addItem(album, album)
        self.album_combo.setCurrentIndex(0)
        self.album_combo.blockSignals(False)

    def _restore_filters(self, artist: str, album: str) -> None:
        if artist:
            index = self.artist_combo.findData(artist)
            if index > 0:
                self.artist_combo.blockSignals(True)
                self.artist_combo.setCurrentIndex(index)
                self.artist_combo.blockSignals(False)
                self._populate_albums()
        if album:
            index = self.album_combo.findData(album)
            if index > 0:
                self.album_combo.blockSignals(True)
                self.album_combo.setCurrentIndex(index)
                self.album_combo.blockSignals(False)

    def _artist_changed(self) -> None:
        self._populate_albums()
        self._apply_filters()

    def _apply_filters(self) -> None:
        if self.mode == "favorites":
            base = [
                track for track in self.tracks if track.path in self.favorites
            ]
        elif self.mode == "playlist":
            base = self._playlist_tracks()
        else:
            base = self.tracks

        artist = self.artist_combo.currentData() or ""
        album = self.album_combo.currentData() or ""
        query = self.search.text().strip().casefold()

        self.visible = [
            track
            for track in base
            if (not artist or track.display_artist == artist)
            and (not album or track.display_album == album)
            and (
                not query
                or query
                in f"{track.title} {track.artist} {track.album} {track.albumartist}".casefold()
            )
        ]
        self._fill_table()

        if self.mode == "favorites":
            self.count_label.setText(
                tr("favorites_count", n=len(self.visible))
            )
        elif self.mode == "playlist":
            name = tr("no_playlist")
            if (
                self.current_playlist is not None
                and 0 <= self.current_playlist < len(self.playlists)
            ):
                name = self.playlists[self.current_playlist]["name"]
            self.count_label.setText(
                tr("playlist_count", n=len(self.visible), name=name.upper())
            )
        elif len(self.visible) == len(self.tracks):
            self.count_label.setText(library_summary(self.tracks))
        else:
            self.count_label.setText(
                tr(
                    "filtered_count",
                    n=len(self.visible),
                    total=len(self.tracks),
                )
            )

    def _playlist_tracks(self) -> list[Track]:
        if (
            self.current_playlist is None
            or not (0 <= self.current_playlist < len(self.playlists))
        ):
            return []
        tracks: list[Track] = []
        for path in self.playlists[self.current_playlist]["paths"]:
            track = self.track_by_path.get(path)
            if track is not None:
                tracks.append(track)
        return tracks

    def _fill_table(self) -> None:
        self.table.setUpdatesEnabled(False)
        self.table.clearContents()
        self.table.setRowCount(len(self.visible))
        for row, track in enumerate(self.visible):
            number = f"{track.tracknumber:02d}" if track.tracknumber else "—"
            is_fav = track.path in self.favorites
            values = [
                "",
                number,
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
                item.setTextAlignment(MAIN_ALIGNMENTS[column])
                if column == 0:
                    item.setIcon(heart_icon(22, is_fav))
                    item.setToolTip(tr("tooltip_favorite"))
                if column == 2:
                    item.setToolTip(track.path)
                self.table.setItem(row, column, item)
        self.table.setUpdatesEnabled(True)
        self._mark_playing()

    def _mark_playing(self) -> None:
        for row in range(self.table.rowCount()):
            is_current = (
                self.current is not None
                and row < len(self.visible)
                and self.visible[row] == self.current
            )
            for column in range(self.table.columnCount()):
                item = self.table.item(row, column)
                if item is not None:
                    font = item.font()
                    font.setBold(is_current)
                    item.setFont(font)
        if self.current is not None and self.current in self.visible:
            self.table.selectRow(self.visible.index(self.current))

    def _focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def _search_enter(self) -> None:
        if self.visible:
            self._play_track(self.visible[0])
        self.table.setFocus()

    # ------------------------------------------------------------- playback
    def _on_item_activated(self, item: QTableWidgetItem) -> None:
        self._play_index(item.row())

    def _play_index(self, row: int) -> None:
        if 0 <= row < len(self.visible):
            self._play_track(self.visible[row])

    def _play_track(
        self,
        track: Track,
        start_position: float = 0.0,
        autoplay: bool = True,
    ) -> None:
        self.current = track
        self.finished_queue = False
        self.duration = track.duration
        if track.duration > 0:
            self.position = max(
                0.0, min(start_position, max(0.0, track.duration - 0.25))
            )
        else:
            self.position = max(0.0, start_position)
        self.seeking = False

        self.progress.blockSignals(True)
        if self.duration > 0:
            self.progress.setValue(
                int(self.position / self.duration * 1000)
            )
        else:
            self.progress.setValue(0)
        self.progress.blockSignals(False)
        self.time_current.setText(format_time(self.position))
        self.time_total.setText(format_time(track.duration))

        self.title_label.setText(track.title)
        self.title_label.setToolTip(track.title)
        self.artist_label.setText(track.display_artist)
        album = track.display_album
        quality = track.quality
        self.meta_label.setText(f"{album} · {quality}" if quality else album)
        self._load_lyrics(track)
        self._update_cover(track)

        self.progress.setEnabled(True)
        self._set_play_text("pause" if autoplay else "play")
        self._set_state("loading" if autoplay else "resuming")
        self._mark_playing()
        self.mpv.load(
            track.path,
            start=self.position,
            paused=not autoplay,
        )

    def play_pause(self) -> None:
        if self.finished_queue and self.current is not None:
            self._play_track(self.current)
            return
        if self.current is None:
            if self.visible:
                self._play_track(self.visible[0])
            return
        if not self.mpv.connected:
            self._play_track(
                self.current,
                start_position=self.position,
                autoplay=True,
            )
            return
        self.mpv.toggle_pause()

    def next_track(self, auto: bool = False) -> None:
        if not self.visible:
            return
        if self.shuffle and len(self.visible) > 1:
            choices = [
                track for track in self.visible if track != self.current
            ]
            self._play_track(random.choice(choices))
            return

        index = (
            self.visible.index(self.current)
            if self.current in self.visible
            else -1
        )
        if index + 1 < len(self.visible):
            self._play_track(self.visible[index + 1])
        elif self.repeat == "all":
            self._play_track(self.visible[0])
        elif auto:
            self._finish_queue()

    def prev_track(self) -> None:
        if self.current is not None and self.position > 3:
            self.mpv.seek(0)
            return
        if not self.visible:
            return
        index = (
            self.visible.index(self.current)
            if self.current in self.visible
            else -1
        )
        if index > 0:
            self._play_track(self.visible[index - 1])
        elif self.repeat == "all":
            self._play_track(self.visible[-1])
        else:
            self.mpv.seek(0)

    def _on_ended(self) -> None:
        if self.current is None:
            return
        if self.repeat == "one":
            self._play_track(self.current)
            return
        self.next_track(auto=True)

    def _finish_queue(self) -> None:
        self.finished_queue = True
        self.position = 0.0
        self.mpv.stop()
        self.progress.blockSignals(True)
        self.progress.setValue(0)
        self.progress.blockSignals(False)
        self.progress.setEnabled(False)
        self.time_current.setText("0:00")
        self._set_play_text("play")
        self._set_state("end_of_queue")
        self._clear_lyrics()

    def _load_lyrics(self, track: Track) -> None:
        """Carga la letra de la pista y muestra la línea de la posición."""
        try:
            self.lyrics = get_lyrics(track)
        except Exception:
            self.lyrics = []
        self.lyric_index = -1
        self.lyrics_label.setText("")
        self.lyrics_label.setVisible(bool(self.lyrics))
        self._update_lyrics(self.position)

    def _update_lyrics(self, position: float) -> None:
        """Muestra la línea actual y la siguiente según la reproducción."""
        if not self.lyrics:
            if self.lyrics_label.text():
                self.lyrics_label.setText("")
            self.lyrics_label.setVisible(False)
            return
        if self.lyrics_label.isHidden():
            self.lyrics_label.setVisible(True)

        index = -1
        for position_index, (stamp, _line) in enumerate(self.lyrics):
            if stamp <= position + 0.05:
                index = position_index
            else:
                break
        if index == self.lyric_index:
            return
        self.lyric_index = index

        if index < 0:
            self.lyrics_label.setText("")
            return

        text = self.lyrics[index][1]
        if index + 1 < len(self.lyrics):
            text = f"{text}\n{self.lyrics[index + 1][1]}"
        self.lyrics_label.setText(text)

    def _clear_lyrics(self) -> None:
        self.lyrics = []
        self.lyric_index = -1
        self.lyrics_label.setText("")
        self.lyrics_label.setVisible(False)

    def _on_position(self, position: float) -> None:
        self.position = position
        self._update_lyrics(position)
        if self.seeking or self.duration <= 0:
            return
        value = int(max(0.0, min(1.0, position / self.duration)) * 1000)
        self.progress.blockSignals(True)
        self.progress.setValue(value)
        self.progress.blockSignals(False)
        self.time_current.setText(format_time(position))

    def _on_duration(self, duration: float) -> None:
        self.duration = duration
        self.time_total.setText(format_time(duration))
        if not self.seeking and duration > 0:
            value = int(
                max(0.0, min(1.0, self.position / duration)) * 1000
            )
            self.progress.blockSignals(True)
            self.progress.setValue(value)
            self.progress.blockSignals(False)

    def _on_paused(self, paused: bool) -> None:
        if self.current is None or self.finished_queue:
            return
        self._set_play_text("play" if paused else "pause")
        self._set_state("paused" if paused else "playing")

    def _on_loaded(self) -> None:
        if self.current is not None and not self.finished_queue:
            self._set_state("paused" if self.mpv.paused else "playing")

    def _on_ready(self) -> None:
        if not self.tracks:
            self._set_state("engine_ready")

    def _on_failed(self, message: str) -> None:
        self._set_state("audio_error")
        self.state_label.setToolTip(message)

    def _seek_scrub(self, value: int) -> None:
        if self.duration <= 0:
            return
        self.seeking = True
        self.time_current.setText(format_time(value / 1000 * self.duration))

    def _seek_to(self, value: int) -> None:
        if self.duration <= 0:
            self.seeking = False
            return
        target = value / 1000 * self.duration
        self.mpv.seek(target)
        self.position = target
        self.time_current.setText(format_time(target))
        self.seeking = False

    def _volume_slider(self, value: int) -> None:
        self.volume_value.setText(str(value))
        self.mpv.set_volume(value)

    def _on_mpv_volume(self, value: int) -> None:
        self.volume.blockSignals(True)
        self.volume.setValue(value)
        self.volume.blockSignals(False)
        self.volume_value.setText(str(value))

    def _volume_up(self) -> None:
        self.volume.setValue(min(100, self.volume.value() + 5))

    def _volume_down(self) -> None:
        self.volume.setValue(max(0, self.volume.value() - 5))

    def _toggle_mute(self) -> None:
        if self.volume.value() > 0:
            self.last_volume = self.volume.value()
            self.volume.setValue(0)
        else:
            self.volume.setValue(self.last_volume or 70)

    def _toggle_shuffle(self) -> None:
        self.shuffle = not self.shuffle
        self.shuffle_btn.setChecked(self.shuffle)

    def _cycle_repeat(self) -> None:
        order = ["off", "all", "one"]
        self.repeat = order[(order.index(self.repeat) + 1) % len(order)]
        self.repeat_btn.setChecked(self.repeat != "off")
        self._update_repeat_button()

    def _update_repeat_button(self) -> None:
        self.repeat_btn.setIcon(repeat_icon(self.repeat == "one"))
        key = {
            "off": "tooltip_repeat_off",
            "all": "tooltip_repeat_all",
            "one": "tooltip_repeat_one",
        }[self.repeat]
        self.repeat_btn.setToolTip(tr(key))

    # ------------------------------------------------------------- favoritos
    def _on_cell_clicked(self, row: int, column: int) -> None:
        if column == 0 and 0 <= row < len(self.visible):
            self._toggle_favorite(self.visible[row])

    def _toggle_favorite(self, track: Track) -> None:
        if track.path in self.favorites:
            self.favorites.discard(track.path)
        else:
            self.favorites.add(track.path)
        self.settings.setValue("favorites", sorted(self.favorites))

        if self.mode == "favorites":
            self._apply_filters()
            return
        for row, visible_track in enumerate(self.visible):
            if visible_track.path == track.path:
                item = self.table.item(row, 0)
                if item is not None:
                    item.setIcon(
                        heart_icon(22, track.path in self.favorites)
                    )
                break

    def _selected_track(self) -> Track | None:
        row = self.table.currentRow()
        if 0 <= row < len(self.visible):
            return self.visible[row]
        return None

    def _toggle_favorite_current(self) -> None:
        track = self._selected_track() or self.current
        if track is not None:
            self._toggle_favorite(track)

    # --------------------------------------------------------------- listas
    def _load_playlists(self) -> None:
        try:
            data = json.loads(
                self.playlists_file.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            data = []
        self.playlists = []
        if not isinstance(data, list):
            return
        for item in data:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            paths = item.get("paths", [])
            if not name or not isinstance(paths, list):
                continue
            cleaned: list[str] = []
            for path in paths:
                text = str(path)
                if text and text not in cleaned:
                    cleaned.append(text)
            self.playlists.append({"name": name, "paths": cleaned})

    def _save_playlists(self) -> None:
        try:
            self.playlists_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.playlists_file.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(self.playlists, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(self.playlists_file)
        except OSError:
            self._set_state("playlists_save_error")

    def _set_mode(self, mode: str) -> None:
        if mode not in ("library", "favorites", "playlist"):
            return
        self.mode = mode
        self.library_mode_btn.setChecked(mode == "library")
        self.favorites_mode_btn.setChecked(mode == "favorites")
        self.playlists_mode_btn.setChecked(mode == "playlist")
        self.playlist_bar.setVisible(mode == "playlist")
        if mode == "playlist":
            if self.current_playlist is None and self.playlists:
                self.current_playlist = 0
            self._refresh_playlist_combo()
        self._apply_filters()

    def _refresh_playlist_combo(self) -> None:
        self.playlist_combo.blockSignals(True)
        self.playlist_combo.clear()
        for playlist in self.playlists:
            self.playlist_combo.addItem(playlist["name"])
        if (
            self.current_playlist is not None
            and 0 <= self.current_playlist < len(self.playlists)
        ):
            self.playlist_combo.setCurrentIndex(self.current_playlist)
        elif self.playlists:
            self.current_playlist = 0
            self.playlist_combo.setCurrentIndex(0)
        else:
            self.current_playlist = None
            self.playlist_combo.setCurrentIndex(-1)
        self.playlist_combo.blockSignals(False)

        has_playlist = bool(self.playlists)
        self.playlist_combo.setEnabled(has_playlist)
        self.add_songs_btn.setEnabled(has_playlist)
        self.remove_song_btn.setEnabled(has_playlist)
        self.up_song_btn.setEnabled(has_playlist)
        self.down_song_btn.setEnabled(has_playlist)
        self.delete_playlist_btn.setEnabled(has_playlist)

    def _playlist_changed(self, index: int) -> None:
        if 0 <= index < len(self.playlists):
            self.current_playlist = index
        else:
            self.current_playlist = None
        self._apply_filters()

    def _new_playlist(self, add_track: Track | None = None) -> bool:
        dialog = NameDialog(
            tr("new_playlist_title"),
            tr("playlist_name_label"),
            "",
            self,
        )
        dialog.setStyleSheet(self.styleSheet())
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.value:
            return False
        name = dialog.value
        if any(
            playlist["name"].casefold() == name.casefold()
            for playlist in self.playlists
        ):
            self._set_state("playlist_exists")
            return False
        paths = [add_track.path] if add_track is not None else []
        self.playlists.append({"name": name, "paths": paths})
        self.current_playlist = len(self.playlists) - 1
        self._save_playlists()
        self._set_mode("playlist")
        return True

    def _delete_playlist(self) -> None:
        if (
            self.current_playlist is None
            or not (0 <= self.current_playlist < len(self.playlists))
        ):
            return
        name = self.playlists[self.current_playlist]["name"]
        if not self._confirm(
            tr("delete_playlist_title"),
            tr("delete_playlist_message", name=name),
        ):
            return
        del self.playlists[self.current_playlist]
        if not self.playlists:
            self.current_playlist = None
        elif self.current_playlist >= len(self.playlists):
            self.current_playlist = len(self.playlists) - 1
        self._save_playlists()
        self._refresh_playlist_combo()
        self._apply_filters()

    def _add_songs_to_playlist(self) -> None:
        if (
            self.current_playlist is None
            or not (0 <= self.current_playlist < len(self.playlists))
        ):
            if not self._new_playlist():
                return
        if not self.tracks:
            self._set_state("library_empty")
            return
        playlist = self.playlists[self.current_playlist]
        dialog = PlaylistPickerDialog(self.tracks, playlist["name"], self)
        dialog.setStyleSheet(self.styleSheet())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        existing = set(playlist["paths"])
        added = 0
        for track in dialog.selected_tracks():
            if track.path not in existing:
                playlist["paths"].append(track.path)
                existing.add(track.path)
                added += 1
        if added:
            self._save_playlists()
            self._refresh_playlist_combo()
            self._apply_filters()
            self._set_state("songs_added", n=added)
        else:
            self._set_state("already_in_playlist")

    def _add_track_to_playlist(self, index: int, track: Track) -> None:
        if not (0 <= index < len(self.playlists)):
            return
        playlist = self.playlists[index]
        if track.path in playlist["paths"]:
            self._set_state("already_in_playlist_one")
            return
        playlist["paths"].append(track.path)
        self._save_playlists()
        self._refresh_playlist_combo()
        if self.mode == "playlist" and self.current_playlist == index:
            self._apply_filters()
        self._set_state("added_to_playlist", name=playlist["name"])

    def _remove_from_playlist(self) -> None:
        if (
            self.current_playlist is None
            or not (0 <= self.current_playlist < len(self.playlists))
        ):
            return
        row = self.table.currentRow()
        if not (0 <= row < len(self.visible)):
            return
        path = self.visible[row].path
        playlist = self.playlists[self.current_playlist]
        if path not in playlist["paths"]:
            return
        playlist["paths"].remove(path)
        self._save_playlists()
        self._apply_filters()
        if self.table.rowCount():
            self.table.selectRow(min(row, self.table.rowCount() - 1))

    def _move_playlist_track(self, delta: int) -> None:
        if (
            self.current_playlist is None
            or not (0 <= self.current_playlist < len(self.playlists))
        ):
            return
        row = self.table.currentRow()
        if not (0 <= row < len(self.visible)):
            return
        track = self.visible[row]
        paths = self.playlists[self.current_playlist]["paths"]
        try:
            index = paths.index(track.path)
        except ValueError:
            return
        target = index + delta
        if not (0 <= target < len(paths)):
            return
        paths[index], paths[target] = paths[target], paths[index]
        self._save_playlists()
        self._apply_filters()
        for visible_row, visible_track in enumerate(self.visible):
            if visible_track.path == track.path:
                self.table.selectRow(visible_row)
                break

    def _table_menu(self, position) -> None:  # noqa: ANN001 - API de Qt
        menu = self._build_table_menu(position)
        if menu is not None:
            menu.exec(self.table.viewport().mapToGlobal(position))

    def _build_table_menu(self, position) -> QMenu | None:
        index = self.table.indexAt(position)
        row = index.row()
        if not (0 <= row < len(self.visible)):
            return None
        track = self.visible[row]
        menu = QMenu(self)
        menu.setStyleSheet(self.styleSheet())

        favorite_text = tr(
            "remove_from_favorites"
            if track.path in self.favorites
            else "add_to_favorites"
        )
        favorite_action = menu.addAction(favorite_text)
        favorite_action.triggered.connect(
            lambda _checked=False: self._toggle_favorite(track)
        )

        add_menu = menu.addMenu(tr("add_to_playlist"))
        if self.playlists:
            for playlist_index, playlist in enumerate(self.playlists):
                action = add_menu.addAction(playlist["name"])
                action.triggered.connect(
                    lambda _checked=False, i=playlist_index, t=track: self._add_track_to_playlist(
                        i, t
                    )
                )
        else:
            empty = add_menu.addAction(tr("no_playlists"))
            empty.setEnabled(False)
        add_menu.addSeparator()
        new_action = add_menu.addAction(tr("new_playlist_menu"))
        new_action.triggered.connect(
            lambda _checked=False: self._new_playlist(track)
        )

        if self.mode == "playlist" and self.current_playlist is not None:
            menu.addSeparator()
            remove_action = menu.addAction(tr("remove_from_playlist"))
            remove_action.triggered.connect(
                lambda _checked=False: self._remove_from_playlist()
            )
            up_action = menu.addAction(tr("move_up"))
            up_action.triggered.connect(
                lambda _checked=False: self._move_playlist_track(-1)
            )
            down_action = menu.addAction(tr("move_down"))
            down_action.triggered.connect(
                lambda _checked=False: self._move_playlist_track(1)
            )

        menu.addSeparator()
        info_action = menu.addAction(tr("view_info"))
        info_action.triggered.connect(
            lambda _checked=False, t=track: self._show_track_info(t)
        )

        return menu

    def _show_track_info(self, track: Track) -> None:
        dialog = TrackInfoDialog(track, self)
        dialog.setStyleSheet(self.styleSheet())
        dialog.exec()

    def _confirm(self, title: str, message: str) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(message)
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.No)
        box.setStyleSheet(self.styleSheet())
        yes_button = box.button(QMessageBox.StandardButton.Yes)
        no_button = box.button(QMessageBox.StandardButton.No)
        if yes_button is not None:
            yes_button.setText(tr("yes"))
        if no_button is not None:
            no_button.setText(tr("no"))
        return box.exec() == QMessageBox.StandardButton.Yes

    # ---------------------------------------------------------------- portada
    def _update_cover(self, track: Track) -> None:
        data = get_cover_bytes(track)
        pixmap = QPixmap()
        if not data or not pixmap.loadFromData(data):
            original = None
        else:
            original = pixmap
        self.current_cover = original
        self._render_cover()
        if self.bg_mode == "cover":
            self.backdrop.set_cover(original)

    def _render_cover(self) -> None:
        if self.current_cover is not None:
            pixmap = self.current_cover.scaled(
                self.cover_size,
                self.cover_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            pixmap = self._placeholder()
        self.cover_label.setPixmap(pixmap)

    def _placeholder(self) -> QPixmap:
        size = self.cover_size
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.black)
        painter = QPainter(pixmap)
        painter.setPen(Qt.GlobalColor.darkGray)
        painter.drawRect(0, 0, size - 1, size - 1)
        font = QFont("Press Start 2P")
        font.setPixelSize(10)
        painter.setFont(font)
        painter.setPen(Qt.GlobalColor.gray)
        painter.drawText(
            pixmap.rect(),
            Qt.AlignmentFlag.AlignCenter,
            tr("no_cover"),
        )
        painter.end()
        return pixmap

    def _reset_player(self) -> None:
        self.current = None
        self.current_cover = None
        self.finished_queue = False
        self.duration = 0.0
        self.position = 0.0
        self.progress.blockSignals(True)
        self.progress.setValue(0)
        self.progress.blockSignals(False)
        self.progress.setEnabled(False)
        self.time_current.setText("0:00")
        self.time_total.setText("0:00")
        self.title_label.setText(tr("nothing_playing"))
        self.title_label.setToolTip("")
        self.artist_label.setText("—")
        self.meta_label.setText("")
        self._clear_lyrics()
        self.cover_label.setPixmap(self._placeholder())
        if self.bg_mode == "cover":
            self.backdrop.set_cover(None)
        self._set_play_text("play")
        self._set_state("ready")

    # ------------------------------------------------------------------ fondo
    def _choose_background(self) -> None:
        dialog = BackgroundDialog(
            self.bg_mode, self.bg_color, self.bg_image_path, self
        )
        dialog.setStyleSheet(self.styleSheet())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.bg_mode = dialog.mode
        self.bg_color = dialog.color
        if self.bg_mode == "image":
            if dialog.image_path != self.bg_image_path:
                loaded = QPixmap(dialog.image_path)
                if not loaded.isNull():
                    self.bg_image = loaded
                    self.bg_image_path = dialog.image_path
            if self.bg_image is None:
                self.bg_mode = "black"
        self.settings.setValue("background_mode", self.bg_mode)
        self.settings.setValue("background_color", self.bg_color)
        self.settings.setValue("background_image", self.bg_image_path)
        self._apply_style()

    # ---------------------------------------------------------- temporizador
    def _open_sleep_dialog(self) -> None:
        dialog = SleepDialog(
            self.sleep_seconds_left, self.sleep_action, self
        )
        dialog.setStyleSheet(self.styleSheet())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.sleep_btn.setChecked(self.sleep_seconds_left > 0)
            return
        if dialog.remove:
            self._cancel_sleep_timer()
        elif dialog.minutes:
            self._start_sleep_timer(dialog.minutes * 60, dialog.action)
        else:
            self.sleep_btn.setChecked(self.sleep_seconds_left > 0)

    def _start_sleep_timer(self, seconds: int, action: str) -> None:
        self.sleep_seconds_left = max(1, int(seconds))
        self.sleep_action = action
        self.sleep_timer.start()
        self.sleep_btn.setChecked(True)
        self._update_sleep_label()
        self._set_state("sleep_active")

    def _update_sleep_label(self) -> None:
        if self.sleep_seconds_left > 0:
            self.sleep_label.setText(
                tr(
                    "sleep_label",
                    time=format_time(self.sleep_seconds_left),
                )
            )
        else:
            self.sleep_label.setText("")

    def _sleep_tick(self) -> None:
        if self.sleep_seconds_left <= 0:
            self.sleep_timer.stop()
            return
        self.sleep_seconds_left -= 1
        if self.sleep_seconds_left > 0:
            self._update_sleep_label()
            return
        self.sleep_timer.stop()
        self.sleep_btn.setChecked(False)
        self.sleep_label.setText("")
        if self.sleep_action == "close":
            self._set_state("closing")
            self.close()
        else:
            self.mpv.pause()
            self._set_state("sleep_paused")

    def _cancel_sleep_timer(self) -> None:
        was_active = self.sleep_seconds_left > 0
        self.sleep_timer.stop()
        self.sleep_seconds_left = 0
        self.sleep_label.setText("")
        self.sleep_btn.setChecked(False)
        if was_active:
            self._set_state("sleep_cancelled")

    # ------------------------------------------------------------- sesión
    def _restore_last_session(self) -> None:
        if self._session_restored:
            return
        if not self.resume_path:
            self._session_restored = True
            return
        track = self.track_by_path.get(self.resume_path)
        if track is None:
            # La caché puede no tener la pista todavía: se reintenta cuando
            # termina el escaneo en segundo plano.
            return
        self._session_restored = True
        position = max(0.0, self.resume_position)
        if track.duration > 0:
            position = min(position, max(0.0, track.duration - 0.25))
        self._play_track(
            track, start_position=position, autoplay=False
        )
        self._set_state("resuming_at", time=format_time(position))

    # -------------------------------------------------------------- keyboard
    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - API de Qt
        if watched is self.table and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                return super().eventFilter(watched, event)
            if self._handle_shortcut_key(event):
                return True
        return super().eventFilter(watched, event)

    def _handle_shortcut_key(self, event) -> bool:
        modifiers = event.modifiers()
        if modifiers & (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
        ):
            return False
        key = event.key()
        if key == Qt.Key.Key_Space:
            self.play_pause()
        elif key == Qt.Key.Key_Right:
            self._seek_relative(5)
        elif key == Qt.Key.Key_Left:
            self._seek_relative(-5)
        elif key == Qt.Key.Key_Up:
            self.volume.setValue(min(100, self.volume.value() + 5))
        elif key == Qt.Key.Key_Down:
            self.volume.setValue(max(0, self.volume.value() - 5))
        elif key == Qt.Key.Key_N:
            self.next_track()
        elif key == Qt.Key.Key_P:
            self.prev_track()
        elif key == Qt.Key.Key_S:
            self._toggle_shuffle()
        elif key == Qt.Key.Key_R:
            self._cycle_repeat()
        elif key == Qt.Key.Key_M:
            self._toggle_mute()
        elif key == Qt.Key.Key_F:
            self._toggle_favorite_current()
        else:
            return False
        return True

    def keyPressEvent(self, event) -> None:  # noqa: N802 - API de Qt
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QComboBox, QSlider)):
            super().keyPressEvent(event)
            return
        if self._handle_shortcut_key(event):
            return
        if event.key() == Qt.Key.Key_Escape:
            self.table.setFocus()
            return
        super().keyPressEvent(event)

    def _seek_relative(self, seconds: float) -> None:
        if self.current is None or self.duration <= 0:
            return
        target = max(0.0, min(self.duration, self.position + seconds))
        self.mpv.seek(target)
        self.position = target
        self.time_current.setText(format_time(target))

    # ----------------------------------------------------------------- close
    def closeEvent(self, event) -> None:  # noqa: N802 - API de Qt
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("volume", self.volume.value())
        self.settings.setValue("shuffle", self.shuffle)
        self.settings.setValue("repeat", self.repeat)
        self.settings.setValue("background_mode", self.bg_mode)
        self.settings.setValue("background_color", self.bg_color)
        self.settings.setValue("background_image", self.bg_image_path)
        self.settings.setValue("favorites", sorted(self.favorites))
        if self.current is not None:
            self.settings.setValue("last_path", self.current.path)
            position = 0.0 if self.finished_queue else float(self.position)
            self.settings.setValue("last_position", position)
        self.settings.sync()
        self._save_playlists()
        if self.scan_thread is not None and self.scan_thread.isRunning():
            self.scan_thread.wait(3000)
        self.mpv.shutdown()
        super().closeEvent(event)
