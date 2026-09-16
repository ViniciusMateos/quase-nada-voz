import ctypes
import random
from pathlib import Path

from PySide6.QtCore import (
    QThread, Signal, Qt, QRect, QPointF, QTimer, QPropertyAnimation, QEasingCurve, Property,
)
from PySide6.QtGui import QPixmap, QColor, QIcon, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import auth
import autostart
import config
import history
import paths
import session as session_mod
import theme
import version
from hotkey import parse_hotkey, vk_to_name
from recorder import list_input_devices

ICON_PATH = paths.ICON_PATH
EYE_ICON = paths.ASSETS_DIR / "eye.png"
PASSWORD_ANIM_MS = 420
# esconder e mais rapido: e so a senha virando bolinha, nao tem o que ler
PASSWORD_HIDE_MS = 260
PASSWORD_TICK_MS = 28
PASSWORD_SCRAMBLE = "#@$%&*?!/\\=+<>abcdefghijkmnopqrstuvwxyz0123456789"
PASSWORD_BULLET = "\u25cf"


def _disable_dwm_transitions(hwnd):
    # com a janela na barra de tarefas, o Windows aplica a propria
    # animacao de abrir/fechar (o efeito que "puxa" da barra de
    # tarefas) por cima da nossa -- as duas competindo faz parecer
    # que "vem de baixo" e, pior, o primeiro clique so mostra o
    # botao na barra sem a janela aparecer de verdade. Isso desliga
    # a animacao nativa so pra essa janela, sobra so a nossa.
    try:
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 3, ctypes.byref(value), ctypes.sizeof(value))
    except OSError:
        pass


def _lerp_color(c1, c2, t):
    return QColor(
        round(c1.red() + (c2.red() - c1.red()) * t),
        round(c1.green() + (c2.green() - c1.green()) * t),
        round(c1.blue() + (c2.blue() - c1.blue()) * t),
    )


class AnimatedButton(QPushButton):
    """QPushButton com hover animado de verdade (o QSS do Qt nao suporta
    a propriedade transition, entao a troca de cor no :hover normalmente
    e instantanea -- aqui anima via QPropertyAnimation)."""

    def __init__(self, text="", parent=None, primary=False):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self._primary = primary
        if primary:
            self._bg = QColor(theme.TURQUOISE)
            self._bg_hover = QColor(theme.TURQUOISE_HOVER)
            self._border = QColor(theme.TURQUOISE)
            self._border_hover = QColor(theme.TURQUOISE_HOVER)
            self._text_color = QColor("#0a0a0a")
            self.setStyleSheet(f"font-weight: 600; color: {self._text_color.name()};")
        else:
            self._bg = QColor(theme.BG_INPUT)
            self._bg_hover = QColor("#303038")
            self._border = QColor(theme.BORDER)
            self._border_hover = QColor(theme.TURQUOISE)
            self._text_color = QColor(theme.TEXT)

        self._progress = 0.0
        self._anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._apply_style()

    def _get_progress(self):
        return self._progress

    def _set_progress(self, value):
        self._progress = value
        self._apply_style()

    hoverProgress = Property(float, _get_progress, _set_progress)

    def _apply_style(self):
        bg = _lerp_color(self._bg, self._bg_hover, self._progress)
        border = _lerp_color(self._border, self._border_hover, self._progress)
        base = (
            f"background-color: {bg.name()}; border: 1px solid {border.name()}; "
            f"border-radius: 10px; padding: 9px 18px; color: {self._text_color.name()};"
        )
        # pressionado precisa ser bem obvio (nao so um tom levemente
        # diferente) -- preenche solido de turquesa com texto escuro,
        # que contrasta forte com qualquer um dos dois estados de cima.
        if self._primary:
            pressed_bg = QColor(theme.TURQUOISE).darker(125)
        else:
            pressed_bg = QColor(theme.TURQUOISE)
        pressed = (
            f"background-color: {pressed_bg.name()}; border: 1px solid {pressed_bg.name()}; "
            f"border-radius: 10px; padding: 9px 18px; color: #0a0a0a; font-weight: 600;"
        )
        # a folha global tem regras QPushButton:hover/:pressed que, sem
        # isso, brigam com a cor animada (o hover fica "duro"/duplicado
        # em vez de seguir a transicao). Repetir explicito aqui garante
        # que essa instancia sempre usa a cor que a gente calculou.
        self.setStyleSheet(
            f"QPushButton {{ {base} }}"
            f"QPushButton:hover {{ {base} }}"
            f"QPushButton:pressed {{ {pressed} }}"
        )

    def _animate(self, target):
        self._anim.stop()
        self._anim.setStartValue(self._progress)
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, event):
        self._animate(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate(0.0)
        super().leaveEvent(event)


class AnimatedLineEdit(QLineEdit):
    """QLineEdit cuja borda anima suave pra turquesa ao ganhar foco (o
    QSS :focus do Qt troca a cor na hora, sem transicao nenhuma)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._border = QColor(theme.BORDER)
        self._border_hover = QColor("#48484f")
        self._border_focus = QColor(theme.TURQUOISE)
        self._progress = 0.0
        self._anim = QPropertyAnimation(self, b"borderProgress", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._apply_style()

    def _get_progress(self):
        return self._progress

    def _set_progress(self, value):
        self._progress = value
        self._apply_style()

    borderProgress = Property(float, _get_progress, _set_progress)

    def _apply_style(self):
        target = self._border_focus if self.hasFocus() else self._border_hover
        border = _lerp_color(self._border, target, self._progress)
        self.setStyleSheet(
            f"background-color: {theme.BG_INPUT}; border: 1px solid {border.name()}; "
            f"border-radius: 10px; padding: 9px 12px; color: {theme.TEXT}; "
            f"selection-background-color: {theme.TURQUOISE}; selection-color: #0a0a0a;"
        )

    def _animate(self, target):
        self._anim.stop()
        self._anim.setStartValue(self._progress)
        self._anim.setEndValue(target)
        self._anim.start()

    def focusInEvent(self, event):
        self._animate(1.0)
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self._animate(0.0)
        super().focusOutEvent(event)

    def enterEvent(self, event):
        if not self.hasFocus():
            self._animate(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.hasFocus():
            self._animate(0.0)
        super().leaveEvent(event)


class AnimatedComboBox(QComboBox):
    """QComboBox com a mesma ideia de borda animada (hover e foco/aberto)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._border = QColor(theme.BORDER)
        self._border_active = QColor(theme.TURQUOISE)
        self._progress = 0.0
        self._anim = QPropertyAnimation(self, b"borderProgress", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._apply_style()

    def _get_progress(self):
        return self._progress

    def _set_progress(self, value):
        self._progress = value
        self._apply_style()

    borderProgress = Property(float, _get_progress, _set_progress)

    def _apply_style(self):
        border = _lerp_color(self._border, self._border_active, self._progress)
        self.setStyleSheet(
            f"QComboBox {{ background-color: {theme.BG_INPUT}; border: 1px solid {border.name()}; "
            f"border-radius: 10px; padding: 9px 12px; color: {theme.TEXT}; }}"
            f"QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right; "
            f"width: 26px; border-left: 1px solid {border.name()}; }}"
            f"QComboBox::down-arrow {{ image: url(\"{theme.CHEVRON_DOWN}\"); width: 10px; height: 10px; margin-right: 8px; }}"
            f"QComboBox::down-arrow:on {{ image: url(\"{theme.CHEVRON_UP}\"); }}"
        )

    def _animate(self, target):
        self._anim.stop()
        self._anim.setStartValue(self._progress)
        self._anim.setEndValue(target)
        self._anim.start()

    def showPopup(self):
        self._animate(1.0)
        super().showPopup()

    def hidePopup(self):
        super().hidePopup()
        if not self.underMouse():
            self._animate(0.0)

    def enterEvent(self, event):
        self._animate(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.view().isVisible():
            self._animate(0.0)
        super().leaveEvent(event)


GUIDE_TEXT = (
    "Como funciona: o app loga sozinho no ChatGPT usando esse email/senha "
    "(abre o Chrome só na primeira vez, ou quando a sessão expira de vez). "
    "Depois disso, a sessão fica salva e o token é renovado sozinho, sem "
    "abrir navegador. Use \"Fazer login agora\" pra forçar uma renovação "
    "e confirmar que está tudo certo."
)


_VK_SHIFT, _VK_CONTROL, _VK_MENU = 0x10, 0x11, 0x12
_MAPVK_VSC_TO_VK_EX = 3


def _resolve_side_specific_vk(vk, scan_code):
    """Shift/Ctrl/Alt chegam no Qt como a tecla generica, mas o hook global
    ve o lado (esquerdo/direito). Sem converter, escolher Ctrl como atalho
    nunca disparava."""
    if vk not in (_VK_SHIFT, _VK_CONTROL, _VK_MENU) or not scan_code:
        return vk
    code = scan_code & 0xFF
    if scan_code & 0x100:  # tecla estendida (lado direito do Ctrl/Alt)
        code |= 0xE000
    resolved = ctypes.windll.user32.MapVirtualKeyW(code, _MAPVK_VSC_TO_VK_EX)
    return resolved or vk


class KeyCaptureButton(AnimatedButton):
    """Botao que captura QUALQUER tecla do teclado: clica, aperta a tecla
    desejada, pronto. Usa o codigo virtual nativo do Windows (o mesmo que
    o hook global usa), entao qualquer tecla que o Windows reconhece serve
    -- inclusive a que ja e o atalho atual (o painel pausa o atalho global
    enquanto escuta, via listening_changed)."""

    captured = Signal(int)
    listening_changed = Signal(bool)

    def __init__(self, vk_code, parent=None):
        super().__init__("", parent)
        self.vk_code = vk_code
        self._listening = False
        self.setFocusPolicy(Qt.StrongFocus)
        self._refresh_text()
        self.clicked.connect(self._start_listening)

    def _refresh_text(self):
        self.setText(vk_to_name(self.vk_code))

    def _start_listening(self):
        if self._listening:
            return
        self._listening = True
        self.listening_changed.emit(True)
        self.setText("Pressione uma tecla...")
        self.setFocus()
        self.grabKeyboard()

    def cancel_listening(self):
        self._stop_listening()

    def _stop_listening(self):
        if not self._listening:
            return
        self._listening = False
        self.releaseKeyboard()
        self._refresh_text()
        self.listening_changed.emit(False)

    def keyPressEvent(self, event):
        if not self._listening:
            super().keyPressEvent(event)
            return
        event.accept()
        if event.isAutoRepeat():
            return
        native_vk = _resolve_side_specific_vk(event.nativeVirtualKey(), event.nativeScanCode())
        if native_vk:
            self.vk_code = native_vk
            # captured ANTES de listening_changed(False): quem troca o
            # atalho precisa ja estar com a tecla nova quando decidir
            # quando reativar o atalho
            self.captured.emit(native_vk)
        self._stop_listening()

    def focusOutEvent(self, event):
        self._stop_listening()
        super().focusOutEvent(event)

    def hideEvent(self, event):
        self._stop_listening()
        super().hideEvent(event)


class _TitleBar(QWidget):
    """Barra de titulo customizada (logo + nome, arrastar a janela,
    botao de fechar), pra nao depender da moldura nativa do Windows."""

    def __init__(self, title, parent=None, on_help=None):
        super().__init__(parent)
        self.setObjectName("titleBar")
        self._drag_offset = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 10, 0)
        layout.setSpacing(8)

        # QPixmap(caminho).scaled(...) pega um frame arbitrario (as vezes
        # baixa resolucao) de dentro do .ico multi-tamanho e amplia --
        # sai borrado. QIcon.pixmap() escolhe o frame mais proximo do
        # tamanho pedido de verdade, entao sai nitido.
        icon_pixmap = QIcon(str(ICON_PATH)).pixmap(56, 56)
        icon_pixmap.setDevicePixelRatio(2.0)
        icon_label = QLabel()
        icon_label.setFixedSize(28, 28)
        icon_label.setPixmap(icon_pixmap)
        text_label = QLabel(title)
        text_label.setObjectName("titleLabel")
        close_btn = QPushButton("✕")
        close_btn.setObjectName("closeButton")
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(lambda: self.window().reject())

        layout.addWidget(icon_label)
        layout.addWidget(text_label)
        layout.addStretch()
        self.help_btn = None
        if on_help is not None:
            help_btn = QPushButton("?")
            self.help_btn = help_btn
            help_btn.setObjectName("helpButton")
            help_btn.setFixedSize(26, 26)
            help_btn.setCursor(Qt.PointingHandCursor)
            help_btn.setToolTip("Ver o passo a passo")
            help_btn.clicked.connect(on_help)
            layout.addWidget(help_btn)
        layout.addWidget(close_btn)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.window().pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_offset = None


class _HistoryItem(QWidget):
    """Uma transcricao do historico: clica em qualquer lugar pra expandir
    o texto completo, ou usa o botao de copiar direto (sem precisar
    expandir)."""

    PREVIEW_CHARS = 60

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.setObjectName("historyItem")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self._text = entry["text"]
        self._expanded = False

        preview = " ".join(self._text.split())
        if len(preview) > self.PREVIEW_CHARS:
            preview = preview[: self.PREVIEW_CHARS].rstrip() + "..."

        self._when_label = QLabel(entry.get("at", ""))
        self._when_label.setObjectName("historyWhen")
        self._preview_label = QLabel(preview)
        self._preview_label.setObjectName("historyPreview")

        self._copy_btn = QPushButton("Copiar")
        self._copy_btn.setObjectName("historyCopyButton")
        self._copy_btn.setCursor(Qt.PointingHandCursor)
        self._copy_btn.setFixedWidth(70)
        self._copy_btn.clicked.connect(self._copy)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        header.addWidget(self._when_label)
        header.addWidget(self._preview_label, 1)
        header.addWidget(self._copy_btn)

        self._full_label = QLabel(self._text)
        self._full_label.setObjectName("historyFull")
        self._full_label.setWordWrap(True)
        self._full_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._full_label.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addWidget(self._full_label)

    def _copy(self):
        QGuiApplication.clipboard().setText(self._text)
        self._copy_btn.setText("Copiado!")
        QTimer.singleShot(1200, lambda: self._copy_btn.setText("Copiar"))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle()
            event.accept()

    def _toggle(self):
        # expandir troca a previa de uma linha pelo texto completo -- a
        # area rolavel da aba absorve a altura extra, entao a janela nao
        # fica pulando de tamanho.
        self._expanded = not self._expanded
        self._full_label.setVisible(self._expanded)
        self._preview_label.setVisible(not self._expanded)


class _LoginTestThread(QThread):
    finished_ok = Signal()
    finished_error = Signal(str)

    def run(self):
        try:
            auth.get_access_token(force_relogin=True)
            self.finished_ok.emit()
        except Exception as e:
            self.finished_error.emit(str(e))


class UpdateDialog(QDialog):
    """Aviso de atualizacao disponivel, com a mesma cara do painel de
    configuracoes (em vez de um QMessageBox generico do sistema)."""

    update_clicked = Signal()

    def __init__(self, current_version, new_version, notes, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{paths.APP_NAME} - atualização")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        _disable_dwm_transitions(int(self.winId()))
        self.setFixedWidth(380)

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(160)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)

        subtitle = QLabel(f"Versão {new_version} disponível (você está na {current_version})")
        subtitle.setObjectName("updateSubtitle")
        subtitle.setWordWrap(True)

        notes_label = QLabel(notes.strip()[:500] or "Melhorias e correções.")
        notes_label.setObjectName("updateNotesLabel")
        notes_label.setWordWrap(True)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")

        self.later_btn = AnimatedButton("Agora não")
        self.later_btn.clicked.connect(self.reject)
        self.update_btn = AnimatedButton("Atualizar agora", primary=True)
        self.update_btn.clicked.connect(self._on_update_clicked)

        buttons_row = QHBoxLayout()
        buttons_row.addStretch()
        buttons_row.addWidget(self.later_btn)
        buttons_row.addWidget(self.update_btn)

        content = QVBoxLayout()
        content.setContentsMargins(20, 12, 20, 18)
        content.setSpacing(10)
        content.addWidget(subtitle)
        content.addWidget(notes_label)
        content.addWidget(self.status_label)
        content.addLayout(buttons_row)

        panel = QWidget()
        panel.setObjectName("panel")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(4)
        panel_layout.addWidget(_TitleBar("Nova versão disponível"))
        panel_layout.addLayout(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(panel)

    def showEvent(self, event):
        super().showEvent(event)
        self._fade_anim.stop()
        self._fade_anim.start()

    def _on_update_clicked(self):
        self.update_clicked.emit()

    def set_downloading(self):
        self.later_btn.setEnabled(False)
        self.update_btn.setEnabled(False)
        self.update_btn.setText("Baixando...")
        self.status_label.setText("Baixando atualização...")

    def set_progress(self, percent):
        self.update_btn.setText(f"Baixando {percent}%")
        self.status_label.setText(f"Baixando atualização... {percent}%")

    def set_restarting(self):
        self.update_btn.setText("Reiniciando...")
        self.status_label.setText("Pronto! O app vai fechar e abrir de novo em alguns segundos.")

    def set_error(self, message):
        self.later_btn.setEnabled(True)
        self.update_btn.setEnabled(True)
        self.update_btn.setText("Tentar de novo")
        self.status_label.setText(f"Falhou: {message}")


class SettingsDialog(QDialog):
    """Painel pra configurar credenciais, hotkey e microfone. Tudo salva e
    aplica NA HORA, sem botao de salvar: escolheu a tecla, trocou o
    microfone, marcou o checkbox -- ja vale. Email/senha salvam quando
    sai do campo (ou fecha o painel), pra nao gravar a cada letra."""

    def __init__(self, on_hotkey_changed=None, on_device_changed=None, on_hotkey_capture=None,
                 anchor_rect=None, session=None, parent=None):
        super().__init__(parent)
        self._anchor_rect = anchor_rect
        self._session = session
        self._geo_anim = None
        # windowTitle e windowIcon ficam so pro Windows (alt-tab, preview
        # ao passar o mouse na bandeja) -- a barra de titulo visivel e a
        # customizada (_TitleBar), sem moldura nativa.
        # Qt.Tool tira a janela da barra de tarefas -- o app so aparece
        # ali pela bandeja (system tray), nunca como um item separado na
        # taskbar (isso confundia: aparecia generico como "Python", com
        # jump list padrao do Windows sem nada a ver com o app).
        self.setWindowTitle(paths.APP_NAME)
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        _disable_dwm_transitions(int(self.winId()))
        self.setMinimumWidth(420)
        self._on_hotkey_changed = on_hotkey_changed
        self._on_device_changed = on_device_changed
        self._on_hotkey_capture = on_hotkey_capture
        self._login_thread = None

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(160)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)

        self._values = config.load_config()

        self.hotkey_button = KeyCaptureButton(parse_hotkey(self._values["HOTKEY"]))

        self.device_combo = AnimatedComboBox()
        self.device_combo.addItem("Microfone padrão do sistema", "")
        for name, _idx in list_input_devices():
            self.device_combo.addItem(name, name)
        saved_device = self._values["AUDIO_DEVICE"]
        if saved_device:
            found = self.device_combo.findData(saved_device)
            if found >= 0:
                self.device_combo.setCurrentIndex(found)

        self.autostart_check = QCheckBox("Iniciar com o Windows")
        self.autostart_check.setCursor(Qt.PointingHandCursor)
        self.autostart_check.setChecked(autostart.is_enabled())

        general_form = QFormLayout()
        general_form.setContentsMargins(4, 16, 4, 8)
        general_form.setSpacing(12)
        general_form.addRow("Hotkey:", self.hotkey_button)
        general_form.addRow("Microfone:", self.device_combo)
        general_form.addRow(self.autostart_check)
        general_tab = QWidget()
        general_tab.setLayout(general_form)

        self.email_edit = AnimatedLineEdit(self._values["OPENAI_EMAIL"])
        self.password_edit = AnimatedLineEdit(self._values["OPENAI_PASSWORD"])
        self.password_edit.setEchoMode(QLineEdit.Password)
        self._password_action = self.password_edit.addAction(
            self._eye_icon(0.0), QLineEdit.TrailingPosition)
        self._password_action.setToolTip("Mostrar senha")
        self._password_action.triggered.connect(self._toggle_password)
        self._password_revealed = False
        self._password_progress = 0.0
        self._password_target = 0.0
        self._password_real = self._values["OPENAI_PASSWORD"]
        self._password_timer = QTimer(self)
        self._password_timer.setInterval(PASSWORD_TICK_MS)
        self._password_timer.timeout.connect(self._tick_password)

        self.browser_combo = AnimatedComboBox()
        self.browser_combo.addItem("Automático (Chrome ou Edge)", "")
        self.browser_combo.addItem("Google Chrome", "chrome")
        self.browser_combo.addItem("Microsoft Edge", "msedge")
        saved_browser = self._values["BROWSER_CHANNEL"]
        found_browser = self.browser_combo.findData(saved_browser)
        if found_browser >= 0:
            self.browser_combo.setCurrentIndex(found_browser)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        self.test_login_btn = AnimatedButton("Fazer login agora")
        self.test_login_btn.clicked.connect(self._test_login)

        guide_label = QLabel(GUIDE_TEXT)
        guide_label.setObjectName("guideLabel")
        guide_label.setWordWrap(True)

        account_form = QFormLayout()
        account_form.setContentsMargins(4, 16, 4, 8)
        account_form.setSpacing(12)
        self._session_row = self._build_session_row()
        account_form.addRow("Sessão:", self._session_row)
        account_form.addRow("Email do ChatGPT:", self.email_edit)
        account_form.addRow("Senha:", self.password_edit)
        account_form.addRow("Navegador:", self.browser_combo)
        account_form.addRow(self.test_login_btn)
        account_form.addRow(self.status_label)
        account_tab = QWidget()
        account_layout = QVBoxLayout(account_tab)
        account_layout.setContentsMargins(0, 0, 0, 0)
        account_layout.addLayout(account_form)
        account_layout.addWidget(guide_label)

        tabs = QTabWidget()
        tabs.addTab(general_tab, "Configurações")
        tabs.addTab(account_tab, "Conta")
        self._history_tab = self._build_history_tab()
        tabs.addTab(self._history_tab, "Histórico")
        tabs.addTab(self._build_tutorial_tab(), "Tutorial")
        tabs.currentChanged.connect(self._animate_tab_change)
        self.tabs = tabs

        self._tour = None

        self._saved_label = QLabel(self.AUTOSAVE_HINT)
        self._saved_label.setObjectName("autosaveLabel")
        self._saved_timer = QTimer(self)
        self._saved_timer.setSingleShot(True)
        self._saved_timer.timeout.connect(self._reset_saved_label)

        version_label = QLabel(f"v{version.APP_VERSION}" + (" · dev" if paths.IS_DEV else ""))
        version_label.setObjectName("versionLabel")

        footer = QHBoxLayout()
        footer.setContentsMargins(4, 6, 4, 0)
        footer.addWidget(self._saved_label)
        footer.addStretch()
        footer.addWidget(version_label)

        content = QVBoxLayout()
        content.setContentsMargins(20, 0, 20, 14)
        content.addWidget(tabs)
        content.addLayout(footer)

        panel = QWidget()
        panel.setObjectName("panel")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        self._panel = panel
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(4)
        self._title_bar = _TitleBar(paths.APP_NAME, on_help=self.start_tour)
        panel_layout.addWidget(self._title_bar)
        panel_layout.addLayout(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(panel)

        # conectado so agora: preencher os valores iniciais acima nao pode
        # contar como "o usuario mudou"
        self.hotkey_button.captured.connect(self._on_hotkey_captured)
        self.hotkey_button.listening_changed.connect(self._on_hotkey_listening)
        self.device_combo.currentIndexChanged.connect(self._on_device_selected)
        self.autostart_check.toggled.connect(self._on_autostart_toggled)
        self.browser_combo.currentIndexChanged.connect(self._on_browser_selected)
        self.email_edit.editingFinished.connect(self._commit_credentials)
        self.password_edit.editingFinished.connect(self._commit_credentials)

    def _build_history_tab(self):
        """Ultimas transcricoes salvas. Serve principalmente pra quando a
        colagem automatica nao cai onde devia (acesso remoto, janela que
        perdeu o foco) -- o texto continua aqui pra copiar na mao."""
        self._history_entries = None

        inner = QWidget()
        self._history_layout = QVBoxLayout(inner)
        self._history_layout.setContentsMargins(0, 0, 0, 0)
        self._history_layout.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # teto de altura pra uma transcricao longa expandida rolar aqui
        # dentro em vez de esticar a janela inteira.
        scroll.setMaximumHeight(300)

        self._history_hint = QLabel("Clique numa transcrição pra ver o texto completo.")
        self._history_hint.setObjectName("historyHint")

        refresh_btn = QPushButton("Atualizar")
        self._history_refresh_btn = refresh_btn
        refresh_btn.setObjectName("historyRefreshButton")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setFocusPolicy(Qt.NoFocus)
        refresh_btn.setFixedWidth(80)
        refresh_btn.clicked.connect(self._refresh_history)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self._history_hint, 1)
        header.addWidget(refresh_btn, 0, Qt.AlignRight)

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 16, 4, 8)
        layout.setSpacing(8)
        layout.addLayout(header)
        layout.addWidget(scroll)

        self._refresh_history()

        # com o painel aberto, uma transcricao nova precisa aparecer
        # sozinha -- so redesenha quando o conteudo mudou de verdade,
        # senao um item que voce expandiu fecharia sozinho a cada tique.
        self._history_timer = QTimer(self)
        self._history_timer.timeout.connect(self._refresh_history)
        self._history_timer.start(1500)
        return tab

    def refresh_history(self):
        """Chamado pelo app assim que uma transcricao entra no historico
        -- aparece na hora, sem esperar o timer de seguranca."""
        self._refresh_history()

    _SESSION_DOT_COLORS = {
        session_mod.OK: "#22C55E",
        session_mod.EXPIRED: "#EF4444",
        session_mod.NO_CREDENTIALS: "#EF4444",
        session_mod.OFFLINE: "#F59E0B",
    }

    def _build_session_row(self):
        self._session_dot = QLabel("●")
        self._session_dot.setObjectName("sessionDot")
        self._session_text = QLabel()
        self._session_text.setObjectName("sessionText")
        self._session_text.setWordWrap(True)
        self._session_check_btn = QPushButton("Verificar agora")
        self._session_check_btn.setObjectName("historyRefreshButton")
        self._session_check_btn.setCursor(Qt.PointingHandCursor)
        # sem foco de teclado: desabilitar ele durante a checagem estava
        # empurrando o foco pro campo de email
        self._session_check_btn.setFocusPolicy(Qt.NoFocus)
        self._session_check_btn.clicked.connect(self._check_session)

        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._session_dot)
        layout.addWidget(self._session_text, 1)
        layout.addWidget(self._session_check_btn)

        if self._session is not None:
            self._session.status_changed.connect(self._show_session_status)
            self._session.check_started.connect(self._show_session_checking)
            if self._session.checking:
                self._show_session_checking()
            else:
                self._show_session_status(self._session.status)
        else:
            self._show_session_status(session_mod.UNKNOWN)
        return row

    def _show_session_checking(self):
        self._session_dot.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 14px;")
        self._session_text.setText("Verificando sessão...")
        self._session_check_btn.setEnabled(False)

    def _show_session_status(self, status):
        color = self._SESSION_DOT_COLORS.get(status, theme.TEXT_MUTED)
        self._session_dot.setStyleSheet(f"color: {color}; font-size: 14px;")
        text = session_mod.MESSAGES.get(status, status)
        if status == session_mod.EXPIRED:
            text += " — faça login"
        self._session_text.setText(text)
        self._session_check_btn.setEnabled(True)

    def _check_session(self):
        if self._session is not None:
            self._session.check()

    _TAB_INDEX = {"general": 0, "account": 1, "history": 2, "tutorial": 3}

    def show_tab(self, name):
        if name == "history":
            self._refresh_history()
        self.tabs.setCurrentIndex(self._TAB_INDEX[name])

    def show_account_tab(self):
        self.show_tab("account")

    def show_history_tab(self):
        self.show_tab("history")

    # --- passo a passo ---------------------------------------------------

    def tour_targets(self):
        return {
            "email": self.email_edit,
            "password": self.password_edit,
            "browser": self.browser_combo,
            "session": self._session_row,
            "login": self.test_login_btn,
            "hotkey": self.hotkey_button,
            "microphone": self.device_combo,
            "autostart": self.autostart_check,
            "history": self._history_focus_widgets(),
            "help": self._title_bar.help_btn,
        }

    def _history_focus_widgets(self):
        # a aba inteira e alta demais pra destacar (o cartao nao cabia):
        # so o botao Atualizar e o primeiro item (ou o aviso de vazio)
        widgets = [self._history_refresh_btn]
        for i in range(self._history_layout.count()):
            w = self._history_layout.itemAt(i).widget()
            if w is not None:
                widgets.append(w)
                break
        return widgets

    def start_tour(self):
        import tour
        if self._tour is not None:
            return
        self._tour = tour.TourOverlay(self._panel, self)
        self._tour.finished.connect(self._on_tour_finished)
        self._tour.start()

    def _on_tour_finished(self, completed):
        self._tour = None
        # concluido OU pulado: nao abre sozinho de novo (fica no botao ?)
        config.save_config({"TOUR_DONE": "1"})
        if completed:
            self.show_tab("general")

    def _build_tutorial_tab(self):
        import tour
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 6, 0)
        inner_layout.setSpacing(8)

        for number, step in enumerate(tour.STEPS, start=1):
            card = QWidget()
            card.setObjectName("tutorialItem")
            card.setAttribute(Qt.WA_StyledBackground, True)
            badge = QLabel(str(number))
            badge.setObjectName("tutorialBadge")
            badge.setAlignment(Qt.AlignCenter)
            badge.setFixedSize(24, 24)
            title = QLabel(step.title)
            title.setObjectName("tutorialTitle")
            text = QLabel(step.text)
            text.setObjectName("tutorialText")
            text.setWordWrap(True)
            texts = QVBoxLayout()
            texts.setSpacing(2)
            texts.addWidget(title)
            texts.addWidget(text)
            row = QHBoxLayout(card)
            row.setContentsMargins(10, 10, 10, 10)
            row.setSpacing(10)
            row.addWidget(badge, 0, Qt.AlignTop)
            row.addLayout(texts, 1)
            inner_layout.addWidget(card)
        inner_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMaximumHeight(300)

        start_btn = AnimatedButton("Ver passo a passo", primary=True)
        start_btn.clicked.connect(self.start_tour)
        header = QHBoxLayout()
        hint = QLabel("Como usar e configurar o app.")
        hint.setObjectName("historyHint")
        header.addWidget(hint, 1)
        header.addWidget(start_btn)

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 16, 4, 8)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(scroll)
        return tab

    def _refresh_history(self):
        entries = history.load()
        if entries == self._history_entries:
            return
        self._history_entries = entries

        while self._history_layout.count():
            item = self._history_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # setParent(None) tira da arvore na hora; so o
                # deleteLater() deixaria o widget velho pendurado ate o
                # event loop processar a destruicao.
                widget.setParent(None)
                widget.deleteLater()

        if entries:
            for entry in entries:
                self._history_layout.addWidget(_HistoryItem(entry))
        else:
            empty = QLabel(
                f"Nada transcrito ainda. As últimas {history.MAX_ITEMS} transcrições "
                "aparecem aqui pra você copiar caso a colagem automática não pegue."
            )
            empty.setObjectName("guideLabel")
            empty.setWordWrap(True)
            self._history_layout.addWidget(empty)
        self._history_layout.addStretch()
        self._history_hint.setVisible(bool(entries))

    def _animate_tab_change(self, index):
        widget = self.tabs.widget(index)
        if widget is None:
            return
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", widget)
        anim.setDuration(200)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start(QPropertyAnimation.DeleteWhenStopped)
        widget._tab_fade_anim_ref = anim

    def showEvent(self, event):
        super().showEvent(event)
        self._fade_anim.stop()
        self._fade_anim.start()

        # so anima "nascendo" da bolha uma vez -- em reaberturas
        # seguintes (raise_/activateWindow) o showEvent nao dispara de
        # novo, entao isso nao repete indevidamente.
        if self._anchor_rect is not None:
            final_geo = QRect(self.geometry())
            start_geo = QRect(0, 0, 44, 44)
            start_geo.moveCenter(self._anchor_rect.center())

            self._geo_anim = QPropertyAnimation(self, b"geometry", self)
            self._geo_anim.setDuration(240)
            self._geo_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._geo_anim.setStartValue(start_geo)
            self._geo_anim.setEndValue(final_geo)
            self._geo_anim.start()
            self._anchor_rect = None

    def _test_login(self):
        self._commit_credentials()
        self.test_login_btn.setEnabled(False)
        self.status_label.setText("Testando login (pode abrir o Chrome)...")
        self._login_thread = _LoginTestThread()
        self._login_thread.finished_ok.connect(self._on_login_ok)
        self._login_thread.finished_error.connect(self._on_login_error)
        self._login_thread.start()

    def _on_login_ok(self):
        self.test_login_btn.setEnabled(True)
        self.status_label.setText("Login OK, sessão renovada.")
        self._check_session()

    def _on_login_error(self, message):
        self.test_login_btn.setEnabled(True)
        self._check_session()
        self.status_label.setText("Falhou — veja login_debug.png se existir.")
        QMessageBox.warning(self, "Erro no login", message)

    # --- salvamento automatico ------------------------------------------

    AUTOSAVE_HINT = "As alterações são salvas automaticamente"

    def _flash_saved(self):
        self._saved_label.setText("✓ Salvo")
        self._set_saved_style(True)
        self._saved_timer.start(1600)

    def _reset_saved_label(self):
        self._saved_label.setText(self.AUTOSAVE_HINT)
        self._set_saved_style(False)

    def _set_saved_style(self, saved):
        self._saved_label.setProperty("saved", saved)
        self._saved_label.style().unpolish(self._saved_label)
        self._saved_label.style().polish(self._saved_label)

    def _on_hotkey_listening(self, listening):
        if self._on_hotkey_capture:
            self._on_hotkey_capture(listening)

    def _on_hotkey_captured(self, vk):
        if vk == parse_hotkey(self._values["HOTKEY"]):
            return  # escolheu a mesma tecla de novo
        config.save_config({"HOTKEY": str(vk)})
        self._values["HOTKEY"] = str(vk)
        if self._on_hotkey_changed:
            self._on_hotkey_changed(vk)
        self._flash_saved()

    def _on_device_selected(self, _index):
        device = self.device_combo.currentData()
        if device == self._values["AUDIO_DEVICE"]:
            return
        config.save_config({"AUDIO_DEVICE": device})
        self._values["AUDIO_DEVICE"] = device
        if self._on_device_changed:
            self._on_device_changed(device)
        self._flash_saved()

    def _on_autostart_toggled(self, checked):
        autostart.set_enabled(checked)
        self._flash_saved()

    def _on_browser_selected(self, _index):
        channel = self.browser_combo.currentData()
        if channel == self._values["BROWSER_CHANNEL"]:
            return
        config.save_config({"BROWSER_CHANNEL": channel})
        self._values["BROWSER_CHANNEL"] = channel
        self._flash_saved()

    # --- senha: revela/esconde com animacao ------------------------------

    def _eye_icon(self, fraction):
        """Olho com o risco crescendo junto com a animacao (em vez de
        trocar de imagem de um quadro pro outro)."""
        pixmap = QPixmap(str(EYE_ICON))
        if fraction > 0.01:
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            w = pixmap.width()
            x0, y0, x1, y1 = w * 0.17, w * 0.83, w * 0.83, w * 0.17
            ex = x0 + (x1 - x0) * fraction
            ey = y0 + (y1 - y0) * fraction
            for color, width in ((QColor(theme.BG_INPUT), w * 0.17), (QColor(theme.TEXT_MUTED), w * 0.09)):
                pen = QPen(color)
                pen.setWidthF(width)
                pen.setCapStyle(Qt.RoundCap)
                painter.setPen(pen)
                painter.drawLine(QPointF(x0, y0), QPointF(ex, ey))
            painter.end()
        return QIcon(pixmap)

    def _password_text(self):
        """Senha de verdade -- durante a animacao o campo mostra caracteres
        embaralhados/bolinhas, que nao podem ser salvos."""
        if self._password_timer.isActive():
            return self._password_real
        return self.password_edit.text()

    def _toggle_password(self):
        self._password_real = self._password_text()
        self._password_revealed = not self._password_revealed
        self._password_target = 1.0 if self._password_revealed else 0.0
        self._password_action.setToolTip("Esconder senha" if self._password_revealed else "Mostrar senha")
        if not self._password_real:
            self._finish_password()
            return
        # o campo nao pode ser editado enquanto mostra o embaralhado
        self.password_edit.setReadOnly(True)
        self.password_edit.setEchoMode(QLineEdit.Normal)
        # ja desenha o primeiro quadro: trocar o echoMode sem isso mostrava a
        # senha inteira por um instante antes do embaralhado comecar
        self._render_password_frame()
        self._password_timer.start()

    def _render_password_frame(self):
        real = self._password_real
        if self._password_revealed:
            # revelando: parte de tras ainda embaralhada, parte da frente ja
            # legivel -- da a sensacao de estar decifrando
            shown = round(len(real) * self._password_progress)
            rest = "".join(random.choice(PASSWORD_SCRAMBLE) for _ in range(len(real) - shown))
            self.password_edit.setText(real[:shown] + rest)
        else:
            # escondendo: as letras viram bolinha, da esquerda pra direita.
            # Embaralhar na volta ficava estranho (a senha virava lixo antes de
            # sumir), entao aqui e so a troca mesmo
            hidden = round(len(real) * (1.0 - self._password_progress))
            self.password_edit.setText(PASSWORD_BULLET * hidden + real[hidden:])
        self._password_action.setIcon(self._eye_icon(self._password_progress))

    def _tick_password(self):
        step = PASSWORD_TICK_MS / (PASSWORD_ANIM_MS if self._password_revealed else PASSWORD_HIDE_MS)
        if self._password_target > self._password_progress:
            self._password_progress = min(1.0, self._password_progress + step)
        else:
            self._password_progress = max(0.0, self._password_progress - step)

        self._render_password_frame()

        if self._password_progress in (0.0, 1.0):
            self._finish_password()

    def _finish_password(self):
        self._password_timer.stop()
        self._password_progress = 1.0 if self._password_revealed else 0.0
        self.password_edit.setReadOnly(False)
        self.password_edit.setEchoMode(QLineEdit.Normal if self._password_revealed else QLineEdit.Password)
        if self.password_edit.text() != self._password_real:
            self.password_edit.setText(self._password_real)
        self._password_action.setIcon(self._eye_icon(self._password_progress))

    def _commit_credentials(self):
        email = self.email_edit.text().strip()
        password = self._password_text()
        if email == self._values["OPENAI_EMAIL"] and password == self._values["OPENAI_PASSWORD"]:
            return
        if email != self._values["OPENAI_EMAIL"]:
            auth.remember_session_email(self._values["OPENAI_EMAIL"])
        config.save_config({"OPENAI_EMAIL": email, "OPENAI_PASSWORD": password})
        self._values["OPENAI_EMAIL"] = email
        self._values["OPENAI_PASSWORD"] = password
        self._flash_saved()
        self._check_session()

    def done(self, result):
        # fechou no meio da animacao da senha: volta o texto de verdade antes
        if self._password_timer.isActive():
            self._finish_password()
        # fechou com o cursor ainda no campo de email/senha: nao perde o
        # que foi digitado
        self._commit_credentials()
        super().done(result)

    def mousePressEvent(self, event):
        # clicou pra trocar a tecla e depois num espaco vazio do painel (que
        # nao tira o foco de ninguem): desiste da escolha, senao o atalho
        # global ficava pausado esperando uma tecla
        self.hotkey_button.cancel_listening()
        # clicar fora de um campo de texto tira o foco dele (e com isso
        # salva, ja que salvar acontece ao sair do campo)
        focused = QApplication.focusWidget()
        if isinstance(focused, QLineEdit):
            focused.clearFocus()
        super().mousePressEvent(event)
