from collections import deque

from PySide6.QtCore import Qt, QObject, Signal, QRectF
from PySide6.QtGui import QPainter, QColor, QPainterPath, QGuiApplication
from PySide6.QtWidgets import QWidget

BAR_COUNT = 28
WIDTH = 260
HEIGHT = 64
BOTTOM_MARGIN = 24


class LevelBridge(QObject):
    """Emitir aqui de qualquer thread (ex: callback de audio) e o Qt
    entrega a atualizacao com seguranca na thread da GUI."""
    level_changed = Signal(float)


class RecordingOverlay(QWidget):
    """Pilula flutuante sempre-por-cima que aparece durante a gravacao,
    mostrando um waveform em tempo real do nivel de audio."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.resize(WIDTH, HEIGHT)

        self._levels = deque([0.0] * BAR_COUNT, maxlen=BAR_COUNT)

        self.bridge = LevelBridge()
        self.bridge.level_changed.connect(self._on_level)

    def _reposition(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        x = screen.center().x() - self.width() // 2
        y = screen.bottom() - self.height() - BOTTOM_MARGIN
        self.move(x, y)

    def _on_level(self, level):
        self._levels.append(level)
        self.update()

    def show_recording(self):
        self._levels = deque([0.02] * BAR_COUNT, maxlen=BAR_COUNT)
        self._reposition()
        self.show()

    def hide_recording(self):
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self.width(), self.height()), 24, 24)
        painter.fillPath(path, QColor(24, 24, 28, 235))

        bar_area_w = self.width() - 32
        gap = 3
        bar_w = max(2.0, (bar_area_w - gap * (BAR_COUNT - 1)) / BAR_COUNT)
        max_bar_h = self.height() - 20
        mid_y = self.height() / 2

        for i, lvl in enumerate(self._levels):
            h = max(3.0, lvl * max_bar_h)
            x = 16 + i * (bar_w + gap)
            rect = QRectF(x, mid_y - h / 2, bar_w, h)
            color = QColor(90, 200, 130) if lvl > 0.04 else QColor(80, 80, 86)
            painter.fillRect(rect, color)
