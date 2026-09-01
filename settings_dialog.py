from pathlib import Path

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

import auth
import config
from hotkey import parse_hotkey, vk_to_name
from recorder import list_input_devices


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

    def __init__(self, on_hotkey_changed=None, on_device_changed=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quase Nada Voz - Configurações")
        self.setMinimumWidth(380)
        self._on_hotkey_changed = on_hotkey_changed
        self._on_device_changed = on_device_changed
        self._login_thread = None

        self._values = config.load_config()

        self.email_edit = QLineEdit(self._values["OPENAI_EMAIL"])
        self.password_edit = QLineEdit(self._values["OPENAI_PASSWORD"])
        self.password_edit.setEchoMode(QLineEdit.Password)

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

        self.status_label = QLabel("")
        self.test_login_btn = QPushButton("Testar login agora")
        self.test_login_btn.clicked.connect(self._test_login)

        form = QFormLayout()
        form.addRow("Email do ChatGPT:", self.email_edit)
        form.addRow("Senha:", self.password_edit)
        form.addRow("Hotkey:", self.hotkey_button)
        form.addRow("Microfone:", self.device_combo)
        form.addRow(self.test_login_btn)
        form.addRow(self.status_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

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
