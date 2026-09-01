import ctypes
from pathlib import Path

from PySide6.QtCore import QThread, Signal, Qt, QRect, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QPixmap, QColor, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import auth
import config
import theme
from hotkey import parse_hotkey, vk_to_name
from recorder import list_input_devices

ICON_PATH = Path(__file__).parent / "assets" / "icon.ico"


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
        pressed_bg = self._border_hover.darker(115)
        base = (
            f"background-color: {bg.name()}; border: 1px solid {border.name()}; "
            f"border-radius: 10px; padding: 9px 18px; color: {self._text_color.name()};"
        )
        # a folha global tem regras QPushButton:hover/:pressed que, sem
        # isso, brigam com a cor animada (o hover fica "duro"/duplicado
        # em vez de seguir a transicao). Repetir explicito aqui garante
        # que essa instancia sempre usa a cor que a gente calculou.
        self.setStyleSheet(
            f"QPushButton {{ {base} }}"
            f"QPushButton:hover {{ {base} }}"
            f"QPushButton:pressed {{ background-color: {pressed_bg.name()}; border: 1px solid {border.name()}; "
            f"border-radius: 10px; padding: 9px 18px; color: {self._text_color.name()}; }}"
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

GUIDE_TEXT = (
    "Como funciona: o app loga sozinho no ChatGPT usando esse email/senha "
    "(abre o Chrome só na primeira vez, ou quando a sessão expira de vez). "
    "Depois disso, a sessão fica salva e o token é renovado sozinho, sem "
    "abrir navegador. Use \"Testar login agora\" pra forçar uma renovação "
    "e confirmar que está tudo certo."
)


class KeyCaptureButton(QPushButton):
    """Botao que captura QUALQUER tecla do teclado: clica, aperta a tecla
    desejada, pronto. Usa o codigo virtual nativo do Windows (o mesmo que
    o hook global usa), entao qualquer tecla que o Windows reconhece serve."""

    def __init__(self, vk_code, parent=None):
        super().__init__(parent)
        self.vk_code = vk_code
        self._listening = False
        self.setFocusPolicy(Qt.StrongFocus)
        self._refresh_text()
        self.clicked.connect(self._start_listening)

    def _refresh_text(self):
        self.setText(vk_to_name(self.vk_code))

    def _start_listening(self):
        self._listening = True
        self.setText("Pressione uma tecla...")
        self.setFocus()
        self.grabKeyboard()

    def keyPressEvent(self, event):
        if not self._listening:
            super().keyPressEvent(event)
            return
        native_vk = event.nativeVirtualKey()
        if native_vk:
            self.vk_code = native_vk
        self._listening = False
        self.releaseKeyboard()
        self._refresh_text()
        event.accept()

    def focusOutEvent(self, event):
        if self._listening:
            self._listening = False
            self.releaseKeyboard()
            self._refresh_text()
        super().focusOutEvent(event)


class _TitleBar(QWidget):
    """Barra de titulo customizada (logo + nome, arrastar a janela,
    botao de fechar), pra nao depender da moldura nativa do Windows."""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("titleBar")
        self._drag_offset = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 10, 0)
        layout.setSpacing(8)

        icon_label = QLabel()
        icon_label.setPixmap(QPixmap(str(ICON_PATH)).scaled(
            28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))
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


class _LoginTestThread(QThread):
    finished_ok = Signal()
    finished_error = Signal(str)

    def run(self):
        try:
            auth.get_access_token(force_relogin=True)
            self.finished_ok.emit()
        except Exception as e:
            self.finished_error.emit(str(e))


class SettingsDialog(QDialog):
    """Painel pra configurar credenciais, hotkey e microfone. Aplica na
    hora (sem precisar reiniciar o app) via os callbacks passados."""

    def __init__(self, on_hotkey_changed=None, on_device_changed=None, anchor_rect=None, parent=None):
        super().__init__(parent)
        self._anchor_rect = anchor_rect
        self._geo_anim = None
        # windowTitle e windowIcon ficam so pro Windows (barra de
        # tarefas, alt-tab, preview ao passar o mouse) -- a barra de
        # titulo visivel e a customizada (_TitleBar), sem moldura nativa.
        # Fica DE PROPOSITO na barra de tarefas (sem Qt.Tool) pra manter
        # a pre-visualizacao ao passar o mouse -- o icone errado era
        # porque o icone nao tinha sido setado direto NESSA janela
        # (so no app inteiro), o resto (Qt.Tool) nao era o problema.
        self.setWindowTitle("Quase Nada Voz")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._disable_dwm_transitions()
        self.setMinimumWidth(420)
        self._on_hotkey_changed = on_hotkey_changed
        self._on_device_changed = on_device_changed
        self._login_thread = None

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(160)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)

        self._values = config.load_config()

        self.hotkey_button = KeyCaptureButton(parse_hotkey(self._values["HOTKEY"]))

        self.device_combo = QComboBox()
        self.device_combo.addItem("Microfone padrão do sistema", "")
        for name, _idx in list_input_devices():
            self.device_combo.addItem(name, name)
        saved_device = self._values["AUDIO_DEVICE"]
        if saved_device:
            found = self.device_combo.findData(saved_device)
            if found >= 0:
                self.device_combo.setCurrentIndex(found)

        general_form = QFormLayout()
        general_form.setContentsMargins(4, 16, 4, 8)
        general_form.setSpacing(12)
        general_form.addRow("Hotkey:", self.hotkey_button)
        general_form.addRow("Microfone:", self.device_combo)
        general_tab = QWidget()
        general_tab.setLayout(general_form)

        self.email_edit = QLineEdit(self._values["OPENAI_EMAIL"])
        self.password_edit = QLineEdit(self._values["OPENAI_PASSWORD"])
        self.password_edit.setEchoMode(QLineEdit.Password)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        self.test_login_btn = AnimatedButton("Testar login agora")
        self.test_login_btn.clicked.connect(self._test_login)

        guide_label = QLabel(GUIDE_TEXT)
        guide_label.setObjectName("guideLabel")
        guide_label.setWordWrap(True)

        account_form = QFormLayout()
        account_form.setContentsMargins(4, 16, 4, 8)
        account_form.setSpacing(12)
        account_form.addRow("Email do ChatGPT:", self.email_edit)
        account_form.addRow("Senha:", self.password_edit)
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

        cancel_btn = AnimatedButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        save_btn = AnimatedButton("Salvar", primary=True)
        save_btn.clicked.connect(self._save)

        buttons_row = QHBoxLayout()
        buttons_row.addStretch()
        buttons_row.addWidget(cancel_btn)
        buttons_row.addWidget(save_btn)

        content = QVBoxLayout()
        content.setContentsMargins(20, 0, 20, 18)
        content.addWidget(tabs)
        content.addLayout(buttons_row)

        panel = QWidget()
        panel.setObjectName("panel")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(4)
        panel_layout.addWidget(_TitleBar("Quase Nada Voz"))
        panel_layout.addLayout(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(panel)

    def _disable_dwm_transitions(self):
        # com a janela na barra de tarefas, o Windows aplica a propria
        # animacao de abrir/fechar (o efeito que "puxa" da barra de
        # tarefas) por cima da nossa -- as duas competindo faz parecer
        # que "vem de baixo" e, pior, o primeiro clique so mostra o
        # botao na barra sem a janela aparecer de verdade. Isso desliga
        # a animacao nativa so pra essa janela, sobra so a nossa.
        try:
            hwnd = int(self.winId())
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 3, ctypes.byref(value), ctypes.sizeof(value)
            )
        except OSError:
            pass

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
        config.save_config({
            "OPENAI_EMAIL": self.email_edit.text().strip(),
            "OPENAI_PASSWORD": self.password_edit.text(),
        })
        self.test_login_btn.setEnabled(False)
        self.status_label.setText("Testando login (pode abrir o Chrome)...")
        self._login_thread = _LoginTestThread()
        self._login_thread.finished_ok.connect(self._on_login_ok)
        self._login_thread.finished_error.connect(self._on_login_error)
        self._login_thread.start()

    def _on_login_ok(self):
        self.test_login_btn.setEnabled(True)
        self.status_label.setText("Login OK, sessão renovada.")

    def _on_login_error(self, message):
        self.test_login_btn.setEnabled(True)
        self.status_label.setText("Falhou — veja login_debug.png se existir.")
        QMessageBox.warning(self, "Erro no login", message)

    def _save(self):
        old_email = self._values["OPENAI_EMAIL"]
        old_hotkey_vk = parse_hotkey(self._values["HOTKEY"])
        new_email = self.email_edit.text().strip()
        new_hotkey_vk = self.hotkey_button.vk_code
        new_device = self.device_combo.currentData()

        config.save_config({
            "OPENAI_EMAIL": new_email,
            "OPENAI_PASSWORD": self.password_edit.text(),
            "HOTKEY": str(new_hotkey_vk),
            "AUDIO_DEVICE": new_device,
        })

        if new_email != old_email:
            for f in (auth.COOKIE_FILE, auth.TOKEN_CACHE_FILE):
                Path(f).unlink(missing_ok=True)

        if new_hotkey_vk != old_hotkey_vk and self._on_hotkey_changed:
            self._on_hotkey_changed(new_hotkey_vk)
        if new_device != self._values["AUDIO_DEVICE"] and self._on_device_changed:
            self._on_device_changed(new_device)

        self.accept()
