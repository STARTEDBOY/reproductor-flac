"""Controlador de mpv mediante su servidor IPC (JSON por socket Unix)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal
from PySide6.QtNetwork import QLocalSocket

from i18n import tr

OBSERVED = {
    "time-pos": 1,
    "duration": 2,
    "pause": 3,
    "volume": 4,
    "eof-reached": 5,
    "idle-active": 6,
}

# Arranca mpv desde un pequeño lanzador que le pone PR_SET_PDEATHSIG: si la
# aplicación muere de forma abrupta, mpv recibe SIGTERM y no queda huérfano.
_LAUNCHER = (
    "import ctypes, os, signal, sys\n"
    "try:\n"
    "    ctypes.CDLL('libc.so.6', use_errno=True).prctl(1, int(signal.SIGTERM), 0, 0, 0)\n"
    "except Exception:\n"
    "    pass\n"
    "os.execvp('mpv', ['mpv'] + sys.argv[1:])\n"
)


class MpvController(QObject):
    positionChanged = Signal(float)
    durationChanged = Signal(float)
    pausedChanged = Signal(bool)
    volumeChanged = Signal(int)
    ended = Signal()
    loaded = Signal()
    failed = Signal(str)
    ready = Signal()

    def __init__(self, volume: int = 70, parent: QObject | None = None):
        super().__init__(parent)
        self._volume = max(0, min(100, int(volume)))
        self._paused = False
        self._connected = False
        self._buffer = b""
        self._pending_load: str | None = None
        self._pending_seek: float | None = None
        self._pending_pause: bool | None = None
        self._next_request = 1
        self._requests: dict[int, list] = {}
        self._quitting = False

        self._proc = QProcess(self)
        self._proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._proc.errorOccurred.connect(self._on_process_error)
        self._proc.finished.connect(self._on_process_finished)

        self._socket = QLocalSocket(self)
        self._socket.readyRead.connect(self._on_read)
        self._socket.connected.connect(self._on_connected)
        self._socket.disconnected.connect(self._on_disconnected)

        uid = os.getuid() if hasattr(os, "getuid") else 0
        self._socket_path = str(
            Path(tempfile.gettempdir()) / f"reproductor-flac-{uid}-{os.getpid()}.sock"
        )

    # ------------------------------------------------------------------ start
    def start(self) -> None:
        if self._proc.state() != QProcess.ProcessState.NotRunning:
            return
        try:
            Path(self._socket_path).unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass

        args = [
            "--idle=yes",
            "--no-video",
            "--force-window=no",
            "--audio-display=no",
            "--no-terminal",
            "--really-quiet",
            "--no-config",
            "--gapless-audio=yes",
            "--keep-open=no",
            f"--volume={self._volume}",
            f"--input-ipc-server={self._socket_path}",
        ]
        audio_output = os.environ.get("REPRODUCTOR_AO")
        if audio_output:
            args.append(f"--ao={audio_output}")

        self._proc.start(sys.executable, ["-c", _LAUNCHER, *args])
        self._try_connect(0)

    def _try_connect(self, attempt: int) -> None:
        if self._connected or self._quitting:
            return
        if self._proc.state() == QProcess.ProcessState.NotRunning and attempt > 3:
            self.failed.emit(tr("mpv_start_failed"))
            return

        self._socket.abort()
        self._socket.connectToServer(self._socket_path)
        if self._socket.waitForConnected(120):
            return
        if attempt < 50:
            QTimer.singleShot(100, lambda: self._try_connect(attempt + 1))
        else:
            self.failed.emit(tr("mpv_connect_failed"))

    # ----------------------------------------------------------------- socket
    def _on_connected(self) -> None:
        if self._connected:
            return
        self._connected = True
        for name, request_id in OBSERVED.items():
            self._send(["observe_property", request_id, name])
        self.ready.emit()
        if self._pending_load:
            path, self._pending_load = self._pending_load, None
            start = self._pending_seek or 0.0
            paused = bool(self._pending_pause)
            self.load(path, start=start, paused=paused)

    def _on_disconnected(self) -> None:
        self._connected = False

    def _on_process_error(self, _error) -> None:
        if not self._quitting:
            self.failed.emit(tr("mpv_command_failed"))

    def _on_process_finished(self, *_args) -> None:
        self._connected = False
        if not self._quitting:
            self.failed.emit(tr("mpv_stopped"))

    def _send(self, command: list) -> bool:
        if not self._connected:
            return False
        payload = json.dumps({"command": command}) + "\n"
        self._socket.write(payload.encode("utf-8"))
        self._socket.flush()
        return True

    def _on_read(self) -> None:
        self._buffer += bytes(self._socket.readAll())
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            self._handle_message(message)

    def _handle_message(self, message: dict) -> None:
        event = message.get("event")
        if event == "property-change":
            name = message.get("name")
            data = message.get("data")
            if name == "time-pos" and data is not None:
                self.positionChanged.emit(float(data))
            elif name == "duration" and data is not None:
                self.durationChanged.emit(float(data))
            elif name == "pause" and data is not None:
                self._paused = bool(data)
                self.pausedChanged.emit(self._paused)
            elif name == "volume" and data is not None:
                self.volumeChanged.emit(int(round(float(data))))
        elif event == "file-loaded":
            if self._pending_seek is not None:
                self._send(["seek", self._pending_seek, "absolute"])
                self._pending_seek = None
            if self._pending_pause is not None:
                self._paused = self._pending_pause
                self._send(["set_property", "pause", self._pending_pause])
                self._pending_pause = None
            self.loaded.emit()
        elif event == "end-file":
            if message.get("reason") == "eof":
                self.ended.emit()

    # --------------------------------------------------------------- commands
    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def volume(self) -> int:
        return self._volume

    def ensure_running(self) -> None:
        if self._quitting:
            return
        if self._proc.state() == QProcess.ProcessState.NotRunning:
            self._connected = False
            self.start()

    def load(
        self,
        path: str,
        start: float = 0.0,
        paused: bool = False,
    ) -> None:
        if not self._connected:
            self._pending_load = path
            self._pending_seek = max(0.0, float(start))
            self._pending_pause = paused
            self.ensure_running()
            return
        self._pending_seek = max(0.0, float(start))
        self._pending_pause = paused
        self._paused = paused
        if paused:
            self._send(["set_property", "pause", True])
        self._send(["loadfile", path, "replace"])
        if not paused:
            self._send(["set_property", "pause", False])

    def play(self) -> None:
        self._send(["set_property", "pause", False])

    def pause(self) -> None:
        self._send(["set_property", "pause", True])

    def toggle_pause(self) -> None:
        self._send(["set_property", "pause", not self._paused])

    def seek(self, seconds: float) -> None:
        self._send(["seek", max(0.0, float(seconds)), "absolute"])

    def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(100, int(volume)))
        self._send(["set_property", "volume", self._volume])

    def stop(self) -> None:
        self._pending_load = None
        self._pending_seek = None
        self._pending_pause = None
        self._send(["stop"])

    def shutdown(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self._send(["quit"])
        if not self._proc.waitForFinished(800):
            self._proc.terminate()
            if not self._proc.waitForFinished(800):
                self._proc.kill()
        try:
            Path(self._socket_path).unlink()
        except OSError:
            pass
