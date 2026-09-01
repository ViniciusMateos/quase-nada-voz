import sys
import threading
import winsound
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

import config
import transcriber
from hotkey import HotkeyListener, parse_hotkey, vk_to_name
from logger import log
from overlay import RecordingOverlay
from recorder import Recorder
from settings_dialog import SettingsDialog


def _make_icon(color):
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(*color))
    painter.drawEllipse(6, 6, 52, 52)
    painter.end()
    return QIcon(pixmap)


ICON_IDLE = None
ICON_RECORDING = None


def _beep(freq, dur):
    threading.Thread(target=lambda: winsound.Beep(freq, dur), daemon=True).start()


class VoiceApp:
    def __init__(self):
        self.cfg = config.load_config()

        self.overlay = RecordingOverlay()
        self.recorder = Recorder(
            on_level=self._on_level, device_name=self.cfg["AUDIO_DEVICE"]
        )
        self.recorder.open_stream()

        self.hotkey = HotkeyListener(parse_hotkey(self.cfg["HOTKEY"]), self._start_recording, self._stop_recording)
        self.hotkey.install()

        self.tray = QSystemTrayIcon(ICON_IDLE)
        self.tray.setToolTip(f"Quase Nada Voz - segure ou toque {vk_to_name(self.hotkey.vk_code)} para ditar")
        menu = QMenu()
        settings_action = QAction("Configurações", menu)
        settings_action.triggered.connect(self._open_settings)
        quit_action = QAction("Sair", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(settings_action)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def _on_level(self, level):
        self.overlay.bridge.level_changed.emit(level)

    def _start_recording(self):
        log("gravando...")
        self.recorder.start()
        self.overlay.show_recording()
        self.tray.setIcon(ICON_RECORDING)
        self.tray.setToolTip("Quase Nada Voz - gravando...")
        _beep(800, 150)

    def _stop_recording(self):
        log("parou de gravar, transcrevendo...")
        wav_bytes = self.recorder.stop()
        self.overlay.hide_recording()
        self.tray.setIcon(ICON_IDLE)
        self.tray.setToolTip(f"Quase Nada Voz - segure ou toque {vk_to_name(self.hotkey.vk_code)} para ditar")
        if wav_bytes:
            threading.Thread(target=self._transcribe, args=(wav_bytes,), daemon=True).start()

    def _transcribe(self, wav_bytes):
        result = transcriber.transcribe_and_paste(wav_bytes, self.cfg["OAI_DEVICE_ID"])
        if result == "ok":
            _beep(1500, 150)
        elif result == "silence":
            _beep(400, 250)
        else:
            _beep(500, 100)
            _beep(500, 100)

    def _open_settings(self):
        dialog = SettingsDialog(
            on_hotkey_changed=self._apply_hotkey,
            on_device_changed=self._apply_device,
        )
        dialog.exec()
        self.cfg = config.load_config()

    def _apply_hotkey(self, new_vk_code):
        self.hotkey.uninstall()
        self.hotkey = HotkeyListener(new_vk_code, self._start_recording, self._stop_recording)
        self.hotkey.install()
        self.tray.setToolTip(f"Quase Nada Voz - segure ou toque {vk_to_name(new_vk_code)} para ditar")

    def _apply_device(self, new_device):
        self.recorder.close_stream()
        self.recorder = Recorder(on_level=self._on_level, device_name=new_device)
        self.recorder.open_stream()

    def _quit(self):
        self.hotkey.uninstall()
        self.recorder.close_stream()
        QApplication.quit()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "icon.ico")))

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "Quase Nada Voz", "Bandeja do sistema não disponível.")
        sys.exit(1)

    global ICON_IDLE, ICON_RECORDING
    ICON_IDLE = _make_icon((90, 90, 90))
    ICON_RECORDING = _make_icon((220, 40, 40))

    try:
        voice_app = VoiceApp()
    except Exception as e:
        QMessageBox.critical(None, "Quase Nada Voz - erro ao iniciar", str(e))
        sys.exit(1)

    log(f"Pronto. Segure ou toque {vk_to_name(voice_app.hotkey.vk_code)} para ditar.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
