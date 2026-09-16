import ctypes

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from settings_dialog import AnimatedButton, _disable_dwm_transitions

NOTICE_WIDTH = 300
GAP_FROM_BUBBLE = 10
AUTO_HIDE_MS = 15000
FADE_MS = 150
PREVIEW_CHARS = 120

_HWND_TOPMOST = -1
_SWP_NOMOVE, _SWP_NOSIZE, _SWP_NOACTIVATE = 0x0002, 0x0001, 0x0010


class TranscriptNotice(QWidget):
    """Balaozinho preso do lado da bolinha flutuante, pra quando a
    transcricao terminou mas o texto nao foi colado (nao tinha campo de
    texto em foco). Nao rouba o foco da janela onde o usuario esta --
    da pra clicar nos botoes sem tirar o cursor de lugar nenhum."""

    def __init__(self, bubble, on_open_history):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedWidth(NOTICE_WIDTH)
        _disable_dwm_transitions(int(self.winId()))

        self._bubble = bubble
        self._on_open_history = on_open_history
        self._text = ""

        self._title = QLabel()
        self._title.setObjectName("noticeTitle")
        close_btn = QPushButton("✕")
        close_btn.setObjectName("noticeClose")
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.dismiss)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self._title, 1)
        header.addWidget(close_btn)

        self._preview = QLabel()
        self._preview.setObjectName("noticePreview")
        self._preview.setWordWrap(True)

        history_btn = AnimatedButton("Ver no histórico")
        history_btn.clicked.connect(self._open_history)
        self._copy_btn = AnimatedButton("Copiar", primary=True)
        self._copy_btn.clicked.connect(self._copy)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 4, 0, 0)
        buttons.addStretch()
        buttons.addWidget(history_btn)
        buttons.addWidget(self._copy_btn)

        panel = QWidget()
        panel.setObjectName("noticePanel")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(14, 10, 10, 12)
        panel_layout.setSpacing(6)
        panel_layout.addLayout(header)
        panel_layout.addWidget(self._preview)
        panel_layout.addLayout(buttons)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(panel)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.dismiss)

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.finished.connect(self._on_fade_finished)
        self._fading_out = False

        bubble.geometry_changed.connect(self._reposition)

    def show_text(self, text, title="Nenhum campo de texto em foco"):
        self._text = text
        self._title.setText(title)
        preview = " ".join(text.split())
        if len(preview) > PREVIEW_CHARS:
            preview = preview[:PREVIEW_CHARS].rstrip() + "…"
        self._preview.setText(preview)
        self._copy_btn.setText("Copiar")
        self._copy_btn.setEnabled(True)

        self.adjustSize()
        self._reposition(force=True)
        if not self.isVisible() or self._fading_out:
            self._fade_to(1.0, start=0.0)
        self.show()
        self._reassert_topmost()
        self._hide_timer.start(AUTO_HIDE_MS)

    def dismiss(self):
        if self.isVisible() and not self._fading_out:
            self._hide_timer.stop()
            self._fade_to(0.0)

    def _fade_to(self, target, start=None):
        self._fade.stop()
        self._fading_out = target == 0.0
        self._fade.setStartValue(self.windowOpacity() if start is None else start)
        self._fade.setEndValue(target)
        self._fade.start()

    def _on_fade_finished(self):
        if self._fading_out:
            self._fading_out = False
            self.hide()

    def _reposition(self, force=False):
        if not force and not self.isVisible():
            return
        bubble = self._bubble.content_geometry()
        screen = QGuiApplication.screenAt(bubble.center()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        size = self.sizeHint().expandedTo(self.size())

        # do lado esquerdo da bolinha (ela costuma ficar no canto
        # direito); se nao couber, vai pro direito
        x = bubble.left() - GAP_FROM_BUBBLE - size.width()
        if x < area.left():
            x = bubble.right() + GAP_FROM_BUBBLE
        y = bubble.center().y() - size.height() // 2
        x = max(area.left(), min(x, area.right() - size.width()))
        y = max(area.top(), min(y, area.bottom() - size.height()))
        self.move(QPoint(x, y))

    def _reassert_topmost(self):
        try:
            ctypes.windll.user32.SetWindowPos(
                int(self.winId()), _HWND_TOPMOST, 0, 0, 0, 0,
                _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE,
            )
        except OSError:
            pass

    def _copy(self):
        QGuiApplication.clipboard().setText(self._text)
        self._copy_btn.setText("Copiado!")
        self._hide_timer.start(900)

    def _open_history(self):
        self.dismiss()
        self._on_open_history()

    # passar o mouse por cima segura o balao aberto
    def enterEvent(self, event):
        self._hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.isVisible() and not self._fading_out:
            self._hide_timer.start(AUTO_HIDE_MS // 2)
        super().leaveEvent(event)
