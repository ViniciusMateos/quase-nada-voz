import ctypes
import sys
import threading
import winsound

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

import config
import paths
import sound
import theme
import transcriber
import updater
from hotkey import HotkeyListener, parse_hotkey, vk_to_name
from logger import log
from overlay import FloatingWidget
from recorder import Recorder
from settings_dialog import SettingsDialog

ICON_PATH = str(paths.ASSETS_DIR / "icon.ico")


def _beep(freq, dur):
    threading.Thread(target=lambda: winsound.Beep(freq, dur), daemon=True).start()


def _force_foreground(hwnd):
    # o Windows normalmente BLOQUEIA um processo em segundo plano de
    # roubar o foco pra uma janela nova (por isso o icone da bandeja
    # funciona -- ganha permissao especial -- mas clicar na bolha
    # flutuante nao). Anexar o input da nossa thread na thread da janela
    # atualmente em primeiro plano e o jeito documentado de contornar
    # isso, so pra essa troca.
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    fg_hwnd = user32.GetForegroundWindow()
    if fg_hwnd == hwnd:
        return
    fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
    cur_thread = kernel32.GetCurrentThreadId()
    user32.AttachThreadInput(fg_thread, cur_thread, True)
    try:
        user32.SetForegroundWindow(hwnd)
    finally:
        user32.AttachThreadInput(fg_thread, cur_thread, False)


class VoiceApp:
    def __init__(self):
        self.cfg = config.load_config()

        self.widget = FloatingWidget(
            initial_pos=self._saved_widget_pos(),
            on_position_changed=self._save_widget_pos,
            on_click=self._open_settings,
            on_context_menu=self._show_context_menu,
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

        self._update_check_thread = None
        self._update_download_thread = None
        if paths.FROZEN:
            # so faz sentido checar atualizacao rodando o .exe empacotado
            # (rodando do codigo-fonte nao ha nada pra "aplicar"); espera
            # um pouco pra nao competir com a inicializacao.
            QTimer.singleShot(4000, self._check_for_update)

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

    def _show_context_menu(self, global_pos):
        self.tray.contextMenu().popup(global_pos)

    def _open_settings(self):
        if self._settings_dialog is not None and self._settings_dialog.isVisible():
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            self._schedule_force_foreground(self._settings_dialog)
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
        self._schedule_force_foreground(dialog)

    def _schedule_force_foreground(self, dialog):
        # forcar o foreground direto apos o show() pode acontecer cedo
        # demais (a janela nativa ainda nao terminou de ser criada/
        # mapeada pelo SO, ainda mais com a animacao de geometria
        # rodando) -- um delay curto garante que ja existe de verdade.
        QTimer.singleShot(60, lambda: _force_foreground(int(dialog.winId())))

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

    def _check_for_update(self):
        self._update_check_thread = updater.UpdateCheckThread()
        self._update_check_thread.found.connect(self._on_update_found)
        self._update_check_thread.start()

    def _on_update_found(self, info):
        text = f"Nova versão {info['version']} disponível."
        notes = info["notes"].strip()
        if notes:
            text += f"\n\n{notes[:400]}"
        text += "\n\nAtualizar agora? O app fecha e reabre sozinho."
        reply = QMessageBox.question(
            None, "Quase Nada Voz - atualização", text, QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.tray.setToolTip("Quase Nada Voz - baixando atualização...")
        self._update_download_thread = updater.UpdateDownloadThread(info["download_url"])
        self._update_download_thread.done.connect(self._on_update_downloaded)
        self._update_download_thread.failed.connect(self._on_update_failed)
        self._update_download_thread.start()

    def _on_update_downloaded(self, new_exe_path):
        try:
            updater.apply_update_and_restart(new_exe_path)
        except Exception as e:
            QMessageBox.warning(None, "Quase Nada Voz", f"Falha ao aplicar atualização: {e}")
            return
        QApplication.quit()

    def _on_update_failed(self, message):
        self.tray.setToolTip(f"Quase Nada Voz - segure ou toque {vk_to_name(self.hotkey.vk_code)} para ditar")
        QMessageBox.warning(None, "Quase Nada Voz", f"Falha ao baixar atualização: {message}")

    def _quit(self):
        self.hotkey.uninstall()
        self.recorder.close_stream()
        QApplication.quit()


_SINGLE_INSTANCE_MUTEX_NAME = "QuaseNadaVoz_SingleInstance_Mutex"
_ERROR_ALREADY_EXISTS = 183


def _acquire_single_instance_lock():
    """Cria um mutex nomeado do Windows. Se ja existir (outra instancia
    rodando), retorna False -- o handle fica preso ao processo e some
    sozinho quando ele fechar (mesmo em crash), entao nao precisa
    liberar na mao."""
    ctypes.windll.kernel32.SetLastError(0)
    ctypes.windll.kernel32.CreateMutexW(None, False, _SINGLE_INSTANCE_MUTEX_NAME)
    return ctypes.windll.kernel32.GetLastError() != _ERROR_ALREADY_EXISTS


def main():
    if not _acquire_single_instance_lock():
        # ja tem uma instancia rodando -- nao abre outra (dois hooks de
        # teclado e duas gravacoes ao mesmo tempo dava m*).
        sys.exit(0)

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
