"""Visualizador de espectro retro para el reproductor FLAC.

Captura el audio del monitor del altavoz por defecto con ``parec`` y calcula
una FFT con numpy. Si falta alguna de las dos piezas, ``SPECTRUM_AVAILABLE``
queda en ``False`` y el reproductor sigue funcionando sin visualizador.
"""

from __future__ import annotations

import shutil
import subprocess
import threading

try:
    import numpy as np
except Exception:  # noqa: BLE001 - numpy es opcional
    np = None

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QWidget

RATE = 44100
CHANNELS = 2
FFT_SIZE = 2048
BAR_COUNT = 30
MIN_HZ = 40.0
MAX_HZ = 16000.0
SILENCE_DB = -58.0
FULL_DB = -8.0

SPECTRUM_AVAILABLE = np is not None and shutil.which("parec") is not None


def _monitor_source() -> str:
    """Nombre del monitor del altavoz por defecto."""
    try:
        result = subprocess.run(
            ["pactl", "get-default-sink"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        sink = result.stdout.strip()
        if sink:
            return f"{sink}.monitor"
    except (OSError, subprocess.SubprocessError):
        pass
    return "@DEFAULT_MONITOR@"


class AudioCapture(QObject):
    """Lee el audio del sistema en un hilo y emite los niveles de las barras."""

    levels = Signal(object)
    failed = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._process: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if not SPECTRUM_AVAILABLE:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="spectrum-capture", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        process = self._process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.5)
        self._thread = None
        self._process = None

    def _run(self) -> None:
        # Si parec termina (por ejemplo al cambiar de salida de audio) se
        # reintenta, salvo que se haya pedido parar.
        while not self._stop.is_set():
            try:
                process = subprocess.Popen(
                    [
                        "parec",
                        f"--device={_monitor_source()}",
                        "--format=s16le",
                        f"--rate={RATE}",
                        f"--channels={CHANNELS}",
                        "--latency-msec=30",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=0,
                )
            except OSError:
                self.failed.emit()
                return
            self._process = process
            try:
                self._pump(process)
            finally:
                if process.poll() is None:
                    try:
                        process.terminate()
                    except OSError:
                        pass
                if process.stdout is not None:
                    try:
                        process.stdout.close()
                    except OSError:
                        pass
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                self._process = None
            if self._stop.is_set():
                break
            self._stop.wait(2.0)

    def _pump(self, process: subprocess.Popen) -> None:
        window = np.hanning(FFT_SIZE).astype(np.float32)
        frequencies = np.fft.rfftfreq(FFT_SIZE, 1.0 / RATE)
        edges = np.geomspace(MIN_HZ, MAX_HZ, BAR_COUNT + 1)
        bands = [
            np.where((frequencies >= low) & (frequencies < high))[0]
            for low, high in zip(edges[:-1], edges[1:])
        ]
        reference = FFT_SIZE * 0.25
        frame_bytes = FFT_SIZE * CHANNELS * 2
        buffer = bytearray(frame_bytes)
        view = memoryview(buffer)

        while not self._stop.is_set():
            filled = 0
            while filled < frame_bytes and not self._stop.is_set():
                read = process.stdout.readinto(view[filled:])
                if not read:
                    return
                filled += read
            if filled < frame_bytes:
                return

            samples = np.frombuffer(buffer, dtype="<i2")
            samples = samples.reshape(-1, CHANNELS).mean(axis=1)
            samples = (samples / 32768.0) * window
            spectrum = np.abs(np.fft.rfft(samples))

            values: list[float] = []
            for indexes in bands:
                magnitude = (
                    float(spectrum[indexes].max())
                    if indexes.size
                    else 0.0
                )
                decibels = 20.0 * np.log10(
                    magnitude / reference + 1e-12
                )
                level = (decibels - SILENCE_DB) / (FULL_DB - SILENCE_DB)
                values.append(max(0.0, min(1.0, level)))
            self.levels.emit(values)


class SpectrumWidget(QWidget):
    """Barras segmentadas en blanco y negro sobre la portada."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self._capture = AudioCapture(self)
        self._capture.levels.connect(self._set_levels)
        self._target = [0.0] * BAR_COUNT
        self._levels = [0.0] * BAR_COUNT
        self._peaks = [0.0] * BAR_COUNT
        self._activity = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self.hide()

    @property
    def running(self) -> bool:
        return self._timer.isActive()

    def start(self) -> None:
        if not SPECTRUM_AVAILABLE:
            return
        self.show()
        self.raise_()
        self._capture.start()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._capture.stop()
        self._target = [0.0] * BAR_COUNT
        self._levels = [0.0] * BAR_COUNT
        self._peaks = [0.0] * BAR_COUNT
        self._activity = 0.0
        self.hide()

    def _set_levels(self, values: object) -> None:
        if not isinstance(values, list):
            return
        self._target = [
            float(value) for value in values[:BAR_COUNT]
        ] + [0.0] * max(0, BAR_COUNT - len(values))

    def _tick(self) -> None:
        was_active = self._activity > 0.0
        loudest = 0.0
        for index, target in enumerate(self._target):
            current = self._levels[index]
            # Ataque rápido y caída lenta, como un vúmetro de agujas.
            speed = 0.55 if target > current else 0.14
            current += (target - current) * speed
            if current < 0.001:
                current = 0.0
            self._levels[index] = current
            loudest = max(loudest, current)
            peak = self._peaks[index]
            if current >= peak:
                self._peaks[index] = current
            else:
                self._peaks[index] = max(0.0, peak - 0.018)

        goal = 1.0 if loudest > 0.02 else 0.0
        self._activity += (goal - self._activity) * 0.12
        if self._activity < 0.005:
            self._activity = 0.0
        if was_active or self._activity > 0.0:
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - API de Qt
        if self._activity <= 0.01:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        width = self.width()
        height = self.height()
        activity = self._activity

        # Velo degradado para que las barras se lean sobre cualquier portada.
        gradient = QLinearGradient(0, 0, 0, height)
        gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
        gradient.setColorAt(1.0, QColor(0, 0, 0, int(210 * activity)))
        painter.fillRect(self.rect(), gradient)

        margin_x = 12.0
        margin_top = 10.0
        margin_bottom = 10.0
        gap = 3.0
        bar_width = (
            width - margin_x * 2 - gap * (BAR_COUNT - 1)
        ) / BAR_COUNT
        area_height = height - margin_top - margin_bottom
        block = 3.0
        block_gap = 1.0
        blocks = max(1, int((area_height + block_gap) / (block + block_gap)))

        for index in range(BAR_COUNT):
            x = margin_x + index * (bar_width + gap)
            level = self._levels[index]
            lit = round(level * blocks)
            for step in range(blocks):
                y = height - margin_bottom - (step + 1) * block - step * block_gap
                if step < lit:
                    alpha = int(235 * activity)
                    color = QColor(255, 255, 255, alpha)
                else:
                    alpha = int(30 * activity)
                    color = QColor(255, 255, 255, alpha)
                painter.fillRect(
                    QRectF(x, y, bar_width, block), color
                )
            peak = self._peaks[index]
            if peak > 0.02:
                y = (
                    height
                    - margin_bottom
                    - peak * (area_height + block_gap)
                )
                painter.fillRect(
                    QRectF(x, max(margin_top, y), bar_width, 1.0),
                    QColor(255, 255, 255, int(245 * activity)),
                )
        painter.end()
