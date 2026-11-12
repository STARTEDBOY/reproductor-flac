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
from library import (
    Track,
    format_time,
    get_cover_bytes,
    library_summary,
    scan_library,
)
from mpv_backend import MpvController
from theme import (
    DEFAULT_COVER_SIZE,
    PIXEL_EYE,
    PIXEL_EYE_OFF,
    PIXEL_MOON,
    PIXEL_REPEAT,
    PIXEL_REPEAT_ONE,
    PIXEL_SHUFFLE,
    PIXEL_SUN,
    PIXEL_SWAP,
    Backdrop,
    ClickSlider,
    app_icon,
    build_style,
    heart_icon,
    load_fonts,
    pixel_icon,
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
        self.current_cover: QPixmap | None = None
        self.track_by_path: dict[str, Track] = {}

        self.settings = QSettings("STARTED", "Reproductor FLAC")
        self.shuffle = bool(self.settings.value("shuffle", False, bool))
        self.repeat = str(self.settings.value("repeat", "off"))
        if self.repeat not in ("off", "all", "one"):
            self.repeat = "off"

        self.cover_size = DEFAULT_COVER_SIZE
        self.bg_mode = str(self.settings.value("background_mode", "black") or "black")
        if self.bg_mode not in ("black", "color", "cover"):
            self.bg_mode = "black"
        self.bg_color = str(
            self.settings.value("background_color", "#000000") or "#000000"
        )
        if not QColor(self.bg_color).isValid():
            self.bg_color = "#000000"

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

        self.setWindowTitle("Reproductor FLAC · STARTED")
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

    def _update_library_button(self) -> None:
        if self.library_hidden:
            self.hide_library_btn.setIcon(pixel_icon(PIXEL_EYE_OFF))
            self.hide_library_btn.setToolTip(
                "Mostrar la biblioteca (Ctrl+H)"
            )
        else:
            self.hide_library_btn.setIcon(pixel_icon(PIXEL_EYE))
            self.hide_library_btn.setToolTip(
                "Ocultar la biblioteca y dejar solo AHORA SUENA (Ctrl+H)"
            )

    def _toggle_library(self) -> None:
        self.library_hidden = not self.library_hidden
        self.library_panel.setVisible(not self.library_hidden)
        self._apply_panel_order()
        self._update_library_button()
        self.state_label.setText(
            "BIBLIOTECA OCULTA"
            if self.library_hidden
            else "BIBLIOTECA VISIBLE"
        )

    def _side_tooltip(self) -> str:
        target = "derecha" if self.player_on_left else "izquierda"
        return f"Mover el reproductor a la {target} (Ctrl+L)"

    def _toggle_panel_side(self) -> None:
        self.player_on_left = not self.player_on_left
        self._apply_panel_order()
        self.settings.setValue(
            "player_side", "left" if self.player_on_left else "right"
        )
        self.state_label.setText(
            "REPRODUCTOR A LA IZQUIERDA"
            if self.player_on_left
            else "REPRODUCTOR A LA DERECHA"
        )
        self.side_btn.setToolTip(self._side_tooltip())

    def _build_library_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("BIBLIOTECA")
        title.setObjectName("section")
        self.count_label = QLabel("0 PISTAS")
        self.count_label.setObjectName("small")
        self.count_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.side_btn = QPushButton()
        self.side_btn.setObjectName("icon")
        self.side_btn.setFixedSize(38, 30)
        self.side_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.side_btn.setIconSize(QSize(20, 20))
        self.side_btn.setIcon(pixel_icon(PIXEL_SWAP))
        self.side_btn.setToolTip(self._side_tooltip())
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.count_label)
        header.addSpacing(6)
        header.addWidget(self.side_btn)
        layout.addLayout(header)

        modes = QHBoxLayout()
        modes.setSpacing(6)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.library_mode_btn = QPushButton("BIBLIOTECA")
        self.favorites_mode_btn = QPushButton("FAVORITOS")
        self.playlists_mode_btn = QPushButton("LISTAS")
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
        self.new_playlist_btn = QPushButton("NUEVA")
        self.delete_playlist_btn = QPushButton("BORRAR")
        for button in (self.new_playlist_btn, self.delete_playlist_btn):
            button.setObjectName("small")
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        playlist_top.addWidget(self.playlist_combo, 1)
        playlist_top.addWidget(self.new_playlist_btn)
        playlist_top.addWidget(self.delete_playlist_btn)
        playlist_layout.addLayout(playlist_top)

        playlist_bottom = QHBoxLayout()
        playlist_bottom.setSpacing(6)
        self.add_songs_btn = QPushButton("AÑADIR…")
        self.remove_song_btn = QPushButton("QUITAR")
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
        self.search.setPlaceholderText("Buscar por título, artista o álbum…")
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
        self.table.setHorizontalHeaderLabels(
            ["FAV", "#", "TÍTULO", "ARTISTA", "ÁLBUM", "DUR."]
        )
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
        self.table.setColumnWidth(0, 42)
        self.table.setColumnWidth(1, 44)
        self.table.setColumnWidth(3, 150)
        self.table.setColumnWidth(4, 140)
        self.table.setColumnWidth(5, 60)
        layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.path_label = QLabel("Sin biblioteca")
        self.path_label.setObjectName("muted")
        self.path_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        footer.addWidget(self.path_label, 1)

        self.reload_btn = QPushButton("RECARGAR")
        self.reload_btn.setObjectName("small")
        self.reload_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.reload_btn.setToolTip("Volver a escanear la carpeta actual (F5)")
        self.folder_btn = QPushButton("CARPETA")
        self.folder_btn.setObjectName("small")
        self.folder_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.folder_btn.setToolTip(
            "Escribir, pegar o examinar otra carpeta (Ctrl+O)"
        )
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
        now = QLabel("AHORA SUENA")
        now.setObjectName("section")
        top.addWidget(now)
        top.addStretch(1)
        self.hide_library_btn = QPushButton()
        self.hide_library_btn.setObjectName("icon")
        self.hide_library_btn.setFixedSize(38, 30)
        self.hide_library_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide_library_btn.setIconSize(QSize(20, 20))
        self.hide_library_btn.setIcon(pixel_icon(PIXEL_EYE))
        self.hide_library_btn.setToolTip(
            "Ocultar la biblioteca y dejar solo AHORA SUENA (Ctrl+H)"
        )
        top.addWidget(self.hide_library_btn)
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

        self.title_label = QLabel("SIN REPRODUCCIÓN")
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
        self.progress.setToolTip("Clic o arrastra para moverte por la canción")
        layout.addWidget(self.progress)

        layout.addSpacing(8)

        controls = QHBoxLayout()
        controls.setSpacing(6)
        self.shuffle_btn = QPushButton()
        self.shuffle_btn.setObjectName("icon")
        self.shuffle_btn.setFixedSize(38, 38)
        self.shuffle_btn.setCheckable(True)
        self.shuffle_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.shuffle_btn.setIconSize(QSize(20, 20))
        self.shuffle_btn.setIcon(pixel_icon(PIXEL_SHUFFLE))
        self.shuffle_btn.setToolTip("Reproducción aleatoria (S)")
        self.prev_btn = QPushButton("<<")
        self.prev_btn.setObjectName("transport")
        self.prev_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.prev_btn.setToolTip("Anterior (P)")
        self.play_btn = QPushButton("PLAY")
        self.play_btn.setObjectName("play")
        self.play_btn.setMinimumSize(118, 44)
        self.play_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.play_btn.setToolTip("Reproducir / pausar (Espacio)")
        self.next_btn = QPushButton(">>")
        self.next_btn.setObjectName("transport")
        self.next_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.next_btn.setToolTip("Siguiente (N)")
        self.repeat_btn = QPushButton()
        self.repeat_btn.setObjectName("icon")
        self.repeat_btn.setFixedSize(38, 38)
        self.repeat_btn.setCheckable(True)
        self.repeat_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.repeat_btn.setIconSize(QSize(20, 20))
        self.repeat_btn.setIcon(pixel_icon(PIXEL_REPEAT))
        self.repeat_btn.setToolTip("Repetir: no / toda la lista / una pista (R)")
        controls.addWidget(self.shuffle_btn)
        controls.addWidget(self.prev_btn)
        controls.addWidget(self.play_btn, 1)
        controls.addWidget(self.next_btn)
        controls.addWidget(self.repeat_btn)
        layout.addLayout(controls)

        layout.addSpacing(6)

        volume_row = QHBoxLayout()
        volume_row.setSpacing(8)
        vol = QLabel("VOL")
        vol.setObjectName("small")
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
        volume_row.addWidget(vol)
        volume_row.addStretch(1)
        volume_row.addWidget(self.volume)
        volume_row.addWidget(self.volume_value)
        layout.addLayout(volume_row)

        tools = QHBoxLayout()
        tools.setSpacing(8)
        self.sleep_btn = QPushButton()
        self.sleep_btn.setObjectName("icon")
        self.sleep_btn.setFixedSize(38, 32)
        self.sleep_btn.setCheckable(True)
        self.sleep_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.sleep_btn.setIconSize(QSize(20, 20))
        self.sleep_btn.setIcon(pixel_icon(PIXEL_MOON))
        self.sleep_btn.setToolTip("Temporizador de apagado")
        self.background_btn = QPushButton()
        self.background_btn.setObjectName("icon")
        self.background_btn.setFixedSize(38, 32)
        self.background_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.background_btn.setIconSize(QSize(20, 20))
        self.background_btn.setIcon(pixel_icon(PIXEL_SUN))
        self.background_btn.setToolTip("Color o portada de fondo")
        self.sleep_label = QLabel("")
        self.sleep_label.setObjectName("small")
        self.sleep_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        tools.addWidget(self.sleep_btn)
        tools.addWidget(self.background_btn)
        tools.addStretch(1)
        tools.addWidget(self.sleep_label)
        layout.addLayout(tools)

        self.state_label = QLabel("INICIANDO…")
        self.state_label.setObjectName("state")
        layout.addWidget(self.state_label)

        self.cover_label.setPixmap(self._placeholder())
        return panel

    def _apply_style(self) -> None:
        self.setStyleSheet(build_style(self.bg_mode, self.bg_color))
        self.backdrop.set_background(self.bg_mode, self.bg_color)
        self.backdrop.set_cover(
            self.current_cover if self.bg_mode == "cover" else None
        )

    def _connect_signals(self) -> None:
        self.search.textChanged.connect(self._apply_filters)
        self.search.returnPressed.connect(self._search_enter)
        self.artist_combo.currentIndexChanged.connect(self._artist_changed)
        self.album_combo.currentIndexChanged.connect(self._apply_filters)
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
        self.state_label.setText("ELIGE UNA CARPETA")
        self.path_label.setText("Sin biblioteca")
        self.count_label.setText("0 PISTAS")

    def load_library(self, path: str, remember: bool = True) -> None:
        folder = Path(path)
        if not folder.is_dir():
            self.state_label.setText("CARPETA NO VÁLIDA")
            return
        if self.scan_thread is not None:
            self.pending_library = str(folder)
            self.state_label.setText("ESPERANDO ESCANEO…")
            return

        if remember:
            self.settings.setValue("library", str(folder))
        self.path_label.setText(str(folder))
        self.path_label.setToolTip(str(folder))
        self.state_label.setText("ESCANEANDO…")
        self.reload_btn.setEnabled(False)

        self.scan_thread = ScanWorker(str(folder))
        self.scan_thread.done.connect(self._library_loaded)
        self.scan_thread.fail.connect(self._scan_failed)
        self.scan_thread.finished.connect(self._scan_finished)
        self.scan_thread.start()

    def _library_loaded(self, tracks: list[Track], root: str) -> None:
        self.mpv.stop()
        self._reset_player()
        self.tracks = tracks
        self.track_by_path = {track.path: track for track in tracks}
        self.visible = tracks
        self._populate_filters()
        self._refresh_playlist_combo()
        self._apply_filters()
        self.path_label.setText(root)
        self.path_label.setToolTip(root)
        self.folder_btn.setEnabled(True)
        self.reload_btn.setEnabled(True)
        if tracks:
            self.state_label.setText("BIBLIOTECA LISTA")
            self.table.setFocus()
            QTimer.singleShot(250, self._restore_last_session)
        else:
            self.state_label.setText("SIN ARCHIVOS DE AUDIO")
        self.setWindowTitle(f"Reproductor FLAC · {Path(root).name or root}")

    def _scan_failed(self, message: str) -> None:
        self.state_label.setText("ERROR AL ESCANEAR")
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
        self.artist_combo.addItem("TODOS LOS ARTISTAS", "")
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
        self.album_combo.addItem("TODOS LOS ÁLBUMES", "")
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
            self.count_label.setText(f"{len(self.visible)} FAVORITOS")
        elif self.mode == "playlist":
            name = "SIN LISTA"
            if (
                self.current_playlist is not None
                and 0 <= self.current_playlist < len(self.playlists)
            ):
                name = self.playlists[self.current_playlist]["name"]
            self.count_label.setText(f"{len(self.visible)} PISTAS · {name.upper()}")
        elif len(self.visible) == len(self.tracks):
            self.count_label.setText(library_summary(self.tracks))
        else:
            self.count_label.setText(
                f"{len(self.visible)} / {len(self.tracks)} PISTAS"
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
                if column == 0:
                    item.setIcon(heart_icon(22, is_fav))
                    item.setToolTip("Marcar o quitar de favoritos")
                elif column in (1, 5):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter
                    )
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
        self._update_cover(track)

        self.progress.setEnabled(True)
        self.play_btn.setText("PAUSA" if autoplay else "PLAY")
        self.state_label.setText("CARGANDO…" if autoplay else "RETOMANDO…")
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
        self.play_btn.setText("PLAY")
        self.state_label.setText("FIN DE LA LISTA")

    def _on_position(self, position: float) -> None:
        self.position = position
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
        self.play_btn.setText("PLAY" if paused else "PAUSA")
        self.state_label.setText("EN PAUSA" if paused else "REPRODUCIENDO")

    def _on_loaded(self) -> None:
        if self.current is not None and not self.finished_queue:
            self.state_label.setText(
                "EN PAUSA" if self.mpv.paused else "REPRODUCIENDO"
            )

    def _on_ready(self) -> None:
        if not self.tracks:
            self.state_label.setText("MOTOR LISTO")

    def _on_failed(self, message: str) -> None:
        self.state_label.setText("ERROR DE AUDIO")
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
        rows = PIXEL_REPEAT_ONE if self.repeat == "one" else PIXEL_REPEAT
        self.repeat_btn.setIcon(pixel_icon(rows))
        names = {
            "off": "no",
            "all": "toda la lista",
            "one": "una pista",
        }
        self.repeat_btn.setToolTip(
            f"Repetir: {names[self.repeat]} (R)"
        )

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
            self.state_label.setText("NO SE PUDO GUARDAR LA LISTA")

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
            "Nueva lista",
            "NOMBRE DE LA LISTA",
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
            self.state_label.setText("ESA LISTA YA EXISTE")
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
            "BORRAR LISTA",
            f"¿Borrar la lista «{name}»?\n\nLas canciones no se borran del disco.",
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
            self.state_label.setText("LA BIBLIOTECA ESTÁ VACÍA")
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
            self.state_label.setText(f"{added} CANCIÓN(ES) AÑADIDA(S)")
        else:
            self.state_label.setText("YA ESTABAN EN LA LISTA")

    def _add_track_to_playlist(self, index: int, track: Track) -> None:
        if not (0 <= index < len(self.playlists)):
            return
        playlist = self.playlists[index]
        if track.path in playlist["paths"]:
            self.state_label.setText("YA ESTÁ EN LA LISTA")
            return
        playlist["paths"].append(track.path)
        self._save_playlists()
        self._refresh_playlist_combo()
        if self.mode == "playlist" and self.current_playlist == index:
            self._apply_filters()
        self.state_label.setText(f"AÑADIDA A «{playlist['name']}»")

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

        favorite_text = (
            "QUITAR DE FAVORITOS"
            if track.path in self.favorites
            else "AÑADIR A FAVORITOS"
        )
        favorite_action = menu.addAction(favorite_text)
        favorite_action.triggered.connect(
            lambda _checked=False: self._toggle_favorite(track)
        )

        add_menu = menu.addMenu("AÑADIR A LISTA")
        if self.playlists:
            for playlist_index, playlist in enumerate(self.playlists):
                action = add_menu.addAction(playlist["name"])
                action.triggered.connect(
                    lambda _checked=False, i=playlist_index, t=track: self._add_track_to_playlist(
                        i, t
                    )
                )
        else:
            empty = add_menu.addAction("SIN LISTAS")
            empty.setEnabled(False)
        add_menu.addSeparator()
        new_action = add_menu.addAction("NUEVA LISTA…")
        new_action.triggered.connect(
            lambda _checked=False: self._new_playlist(track)
        )

        if self.mode == "playlist" and self.current_playlist is not None:
            menu.addSeparator()
            remove_action = menu.addAction("QUITAR DE LA LISTA")
            remove_action.triggered.connect(
                lambda _checked=False: self._remove_from_playlist()
            )
            up_action = menu.addAction("MOVER ARRIBA")
            up_action.triggered.connect(
                lambda _checked=False: self._move_playlist_track(-1)
            )
            down_action = menu.addAction("MOVER ABAJO")
            down_action.triggered.connect(
                lambda _checked=False: self._move_playlist_track(1)
            )

        menu.addSeparator()
        info_action = menu.addAction("VER INFORMACIÓN")
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
            yes_button.setText("SÍ")
        if no_button is not None:
            no_button.setText("NO")
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
            "SIN PORTADA",
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
        self.title_label.setText("SIN REPRODUCCIÓN")
        self.title_label.setToolTip("")
        self.artist_label.setText("—")
        self.meta_label.setText("")
        self.cover_label.setPixmap(self._placeholder())
        if self.bg_mode == "cover":
            self.backdrop.set_cover(None)
        self.play_btn.setText("PLAY")
        self.state_label.setText("LISTO")

    # ------------------------------------------------------------------ fondo
    def _choose_background(self) -> None:
        dialog = BackgroundDialog(self.bg_mode, self.bg_color, self)
        dialog.setStyleSheet(self.styleSheet())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.bg_mode = dialog.mode
        self.bg_color = dialog.color
        self.settings.setValue("background_mode", self.bg_mode)
        self.settings.setValue("background_color", self.bg_color)
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
        self.state_label.setText("TEMPORIZADOR ACTIVO")

    def _update_sleep_label(self) -> None:
        if self.sleep_seconds_left > 0:
            self.sleep_label.setText(
                f"DORMIR {format_time(self.sleep_seconds_left)}"
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
            self.state_label.setText("CERRANDO…")
            self.close()
        else:
            self.mpv.pause()
            self.state_label.setText("TEMPORIZADOR: EN PAUSA")

    def _cancel_sleep_timer(self) -> None:
        was_active = self.sleep_seconds_left > 0
        self.sleep_timer.stop()
        self.sleep_seconds_left = 0
        self.sleep_label.setText("")
        self.sleep_btn.setChecked(False)
        if was_active:
            self.state_label.setText("TEMPORIZADOR CANCELADO")

    # ------------------------------------------------------------- sesión
    def _restore_last_session(self) -> None:
        if self._session_restored:
            return
        self._session_restored = True
        if not self.resume_path:
            return
        track = self.track_by_path.get(self.resume_path)
        if track is None:
            return
        position = max(0.0, self.resume_position)
        if track.duration > 0:
            position = min(position, max(0.0, track.duration - 0.25))
        self._play_track(
            track, start_position=position, autoplay=False
        )
        self.state_label.setText(
            f"RETOMANDO EN {format_time(position)}"
        )

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
