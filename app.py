import ctypes
import sys
import threading
import winsound
from pathlib import Path

from PySide6.QtGui import QAction, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

import config
import sound
import theme
import transcriber
from hotkey import HotkeyListener, parse_hotkey, vk_to_name
from logger import log
from overlay import FloatingWidget
from recorder import Recorder
from settings_dialog import SettingsDialog

ICON_PATH = str(Path(__file__).parent / "assets" / "icon.ico")


def _beep(freq, dur):
    threading.Thread(target=lambda: winsound.Beep(freq, dur), daemon=True).start()


class VoiceApp:
    def __init__(self):
        self.cfg = config.load_config()

        self.widget = FloatingWidget(
            initial_pos=self._saved_widget_pos(),
            on_position_changed=self._save_widget_pos,
            on_click=self._open_settings,
        )
        self._settings_dialog = None
        self.recorder = Recorder(
            on_bands=self._on_bands, device_name=self.cfg["AUDIO_DEVICE"]
        )
        self.recorder.open_stream()

        self.hotkey = HotkeyListener(parse_hotkey(self.cfg["HOTKEY"]), self._start_recording, self._stop_recording)
        self.hotkey.install()

        self.tray = QSystemTrayIcon(QIcon(ICON_PATH))
        self.tray.setToolTip(f"Quase Nada Voz - segure ou toque {vk_to_name(self.hotkey.vk_code)} para ditar")
        menu = QMenu()
        settings_action = QAction("Configurações", menu)
        settings_action.triggered.connect(self._open_settings)
        quit_action = QAction("Sair", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(settings_action)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        # o menu de contexto do QSystemTrayIcon as vezes nao responde de
        # primeira no Windows (bug conhecido do Qt) -- clique simples
        # direto no icone tambem abre configuracoes, sem depender disso.
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _saved_widget_pos(self):
        x, y = self.cfg["WIDGET_X"], self.cfg["WIDGET_Y"]
        if x and y:
            try:
                return (int(x), int(y))
            except ValueError:
                return None
        return None

    def _save_widget_pos(self, x, y):
        config.save_config({"WIDGET_X": str(x), "WIDGET_Y": str(y)})

    def _on_bands(self, bands):
        self.widget.bridge.bands_changed.emit(bands)

    def _start_recording(self):
        log("gravando...")
        self.recorder.start()
        self.widget.start_recording()
        self.tray.setToolTip("Quase Nada Voz - gravando...")
        sound.play(sound.START_STOP_RECORDING)

    def _stop_recording(self):
        log("parou de gravar, transcrevendo...")
        wav_bytes = self.recorder.stop()
        self.widget.stop_recording(start_processing=bool(wav_bytes))
        self.tray.setToolTip(f"Quase Nada Voz - segure ou toque {vk_to_name(self.hotkey.vk_code)} para ditar")
        sound.play(sound.START_STOP_RECORDING)
        if wav_bytes:
            threading.Thread(target=self._transcribe, args=(wav_bytes,), daemon=True).start()

    def _transcribe(self, wav_bytes):
        try:
            result = transcriber.transcribe_and_paste(wav_bytes, self.cfg["OAI_DEVICE_ID"])
            if result == "ok":
                sound.play(sound.DONE_TRANSCRIBE)
            elif result == "silence":
                _beep(400, 250)
            else:
                _beep(500, 100)
                _beep(500, 100)
        finally:
            self.widget.bridge.processing_done.emit()

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._open_settings()

    def _open_settings(self):
        if self._settings_dialog is not None and self._settings_dialog.isVisible():
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return
        dialog = SettingsDialog(
            on_hotkey_changed=self._apply_hotkey,
            on_device_changed=self._apply_device,
            anchor_rect=self.widget.geometry(),
        )
        dialog.adjustSize()
        screen = QGuiApplication.screenAt(self.widget.geometry().center()) or QGuiApplication.primaryScreen()
        target = dialog.geometry()
        target.moveCenter(screen.availableGeometry().center())
        dialog.move(target.topLeft())
        dialog.finished.connect(self._on_settings_closed)
        self._settings_dialog = dialog
        dialog.show()

    def _on_settings_closed(self, _result):
        self.cfg = config.load_config()

    def _apply_hotkey(self, new_vk_code):
        self.hotkey.uninstall()
        self.hotkey = HotkeyListener(new_vk_code, self._start_recording, self._stop_recording)
        self.hotkey.install()
        self.tray.setToolTip(f"Quase Nada Voz - segure ou toque {vk_to_name(new_vk_code)} para ditar")

    def _apply_device(self, new_device):
        self.recorder.close_stream()
        self.recorder = Recorder(on_bands=self._on_bands, device_name=new_device)
        self.recorder.open_stream()

    def _quit(self):
        self.hotkey.uninstall()
        self.recorder.close_stream()
        QApplication.quit()


def main():
    # sem isso o Windows agrupa/identifica o processo como "Python"
    # generico (icone errado em notificacoes etc) em vez de usar a
    # marca do app.
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("QuaseNada.Voz")
    except (AttributeError, OSError):
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("Quase Nada Voz")
    app.setApplicationDisplayName("Quase Nada Voz")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(ICON_PATH))
    app.setStyleSheet(theme.STYLESHEET)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "Quase Nada Voz", "Bandeja do sistema não disponível.")
        sys.exit(1)

    try:
        voice_app = VoiceApp()
    except Exception as e:
        QMessageBox.critical(None, "Quase Nada Voz - erro ao iniciar", str(e))
        sys.exit(1)

    log(f"Pronto. Segure ou toque {vk_to_name(voice_app.hotkey.vk_code)} para ditar.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
