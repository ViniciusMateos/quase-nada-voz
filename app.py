import ctypes
import sys
import threading
import time
import winsound

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QCheckBox, QMenu, QMessageBox, QSystemTrayIcon

import config
import focus
import installer
import paths
import session as session_mod
import sound
import theme
import transcriber
import updater
import version
from hotkey import HotkeyListener, parse_hotkey, vk_to_name
from logger import log
from notice import TranscriptNotice
from overlay import FloatingWidget
from recorder import Recorder
from session import SessionMonitor
from settings_dialog import SettingsDialog, UpdateDialog

ICON_PATH = str(paths.ICON_PATH)
# depois de atualizar: espera a bolinha aparecer/assentar antes do aviso
AFTER_UPDATE_NOTICE_DELAY_MS = 1800
AFTER_UPDATE_NOTICE_MS = 6000


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


class _AppBridge(QObject):
    """A transcricao roda em thread de fundo; emitir por aqui entrega o
    aviso com seguranca na thread do Qt."""
    history_saved = Signal()
    quit_requested = Signal()
    not_pasted = Signal(str, str)  # texto, titulo do aviso
    auth_failed = Signal()


class VoiceApp:
    def __init__(self):
        self.cfg = config.load_config()

        self.widget = FloatingWidget(
            initial_pos=self._saved_widget_pos(),
            on_position_changed=self._save_widget_pos,
            on_click=self._on_bubble_click,
            on_context_menu=self._show_context_menu,
        )
        self._settings_dialog = None

        self.session = SessionMonitor()
        self.session.status_changed.connect(self._on_session_status)
        QTimer.singleShot(1000, self.session.check)

        self._bridge = _AppBridge()
        self._notice = TranscriptNotice(self.widget, on_open_history=self._open_history)
        self._bridge.history_saved.connect(self._on_history_saved)
        self._bridge.not_pasted.connect(self._notice.show_text)
        self._bridge.auth_failed.connect(self._on_auth_failed)
        self._bridge.quit_requested.connect(self._quit)
        self._watch_quit_request()
        self.recorder = Recorder(
            on_bands=self._on_bands, device_name=self.cfg["AUDIO_DEVICE"]
        )
        self.recorder.open_stream()

        self.hotkey = HotkeyListener(parse_hotkey(self.cfg["HOTKEY"]), self._start_recording, self._stop_recording)
        self.hotkey.install()

        self.tray = QSystemTrayIcon(QIcon(ICON_PATH))
        self._refresh_tooltip()
        menu = QMenu()
        settings_action = QAction("Configurações", menu)
        settings_action.triggered.connect(self._open_settings)
        quit_action = QAction("Sair", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(settings_action)
        if paths.IS_DEV and paths.FROZEN:
            test_update_action = QAction("Testar atualização (dev)", menu)
            test_update_action.triggered.connect(self._simulate_update)
            menu.addAction(test_update_action)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        # o menu de contexto do QSystemTrayIcon as vezes nao responde de
        # primeira no Windows (bug conhecido do Qt) -- clique simples
        # direto no icone tambem abre configuracoes, sem depender disso.
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        self._update_check_thread = None
        self._update_download_thread = None
        self._update_dialog = None
        QTimer.singleShot(1500, self._maybe_start_onboarding)

        if updater.updates_enabled():
            # so no .exe empacotado; espera um pouco pra nao competir com a
            # inicializacao. O Dev so checa o feed local de teste.
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

    def _refresh_tooltip(self):
        if self.session.blocked:
            text = f"{paths.APP_NAME} - {session_mod.MESSAGES[self.session.status]}"
        else:
            text = f"{paths.APP_NAME} - segure ou toque {vk_to_name(self.hotkey.vk_code)} para ditar"
        self.tray.setToolTip(text)

    _ALERT_MESSAGES = {
        session_mod.NO_CREDENTIALS: "Sem login — clique para adicionar conta",
        session_mod.EXPIRED: "Sessão expirada — clique para entrar",
    }

    def _on_session_status(self, status):
        self.widget.set_alert(self.session.blocked, self._ALERT_MESSAGES.get(status))
        self._refresh_tooltip()

    def _start_recording(self):
        # sem conta funcionando nao adianta gravar: a transcricao ia falhar
        # (ou abrir navegador do nada). Avisa na propria bolinha e recusa
        # -- o False faz o hotkey nao entrar em modo "gravando".
        if self.session.blocked:
            self.widget.show_message(self._ALERT_MESSAGES.get(
                self.session.status, "Sem login — clique para adicionar conta"))
            _beep(500, 150)
            log(f"ditado bloqueado: sessao {self.session.status}")
            self.session.check()  # talvez ja tenha sido resolvido
            return False

        log("gravando...")
        self.recorder.start()
        # acorda a acessibilidade do app em foco (Chrome/Electron) agora,
        # pra checagem de "tem campo de texto?" no fim ja vir certa
        focus.warm_up()
        self._notice.dismiss()
        self.widget.start_recording()
        self.tray.setToolTip(f"{paths.APP_NAME} - gravando...")
        sound.play(sound.START_STOP_RECORDING)

    def _stop_recording(self):
        log("parou de gravar, transcrevendo...")
        wav_bytes = self.recorder.stop()
        self.widget.stop_recording(start_processing=bool(wav_bytes))
        self._refresh_tooltip()
        sound.play(sound.START_STOP_RECORDING)
        if wav_bytes:
            threading.Thread(target=self._transcribe, args=(wav_bytes,), daemon=True).start()

    def _transcribe(self, wav_bytes):
        try:
            status, text = transcriber.transcribe_and_paste(
                wav_bytes, self.cfg["OAI_DEVICE_ID"],
                on_saved=lambda _text: self._bridge.history_saved.emit(),
            )
            if status in ("ok", "no_target"):
                sound.play(sound.DONE_TRANSCRIBE)
            elif status == "silence":
                _beep(400, 250)
            else:
                _beep(500, 100)
                _beep(500, 100)

            if status == "auth_error":
                self._bridge.auth_failed.emit()
            elif status == "no_target":
                self._bridge.not_pasted.emit(text, "Nenhum campo de texto em foco")
            elif status == "error" and text:
                # transcreveu mas a colagem falhou: o texto nao pode se perder
                self._bridge.not_pasted.emit(text, "Não consegui colar")
        finally:
            self.widget.bridge.processing_done.emit()

    def _on_auth_failed(self):
        self.widget.show_message("Não consegui entrar na conta")
        self.session.check()

    def _on_bubble_click(self):
        if self.session.blocked:
            self._open_account()
        else:
            self._open_settings()

    def _on_history_saved(self):
        if self._settings_dialog is not None and self._settings_dialog.isVisible():
            self._settings_dialog.refresh_history()

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
            on_hotkey_capture=self._on_hotkey_capture,
            on_uninstall=self._uninstall_from_app,
            on_install=self._install_from_app,
            anchor_rect=self.widget.geometry(),
            session=self.session,
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

    def _maybe_start_onboarding(self):
        # so pra quem acabou de instalar: nunca viu o tutorial e ainda nao
        # tem conta. Quem ja usa nao e interrompido (tem o botao ? no painel)
        if self.cfg.get("TOUR_DONE") or self.cfg.get("OPENAI_EMAIL"):
            return
        self._open_settings()
        if self._settings_dialog is not None:
            # espera a animacao de abrir o painel terminar
            QTimer.singleShot(450, self._settings_dialog.start_tour)

    def _open_account(self):
        self._open_settings()
        if self._settings_dialog is not None:
            self._settings_dialog.show_account_tab()

    def _open_history(self):
        self._open_settings()
        if self._settings_dialog is not None:
            self._settings_dialog.show_history_tab()

    def _schedule_force_foreground(self, dialog):
        # forcar o foreground direto apos o show() pode acontecer cedo
        # demais (a janela nativa ainda nao terminou de ser criada/
        # mapeada pelo SO, ainda mais com a animacao de geometria
        # rodando) -- um delay curto garante que ja existe de verdade.
        QTimer.singleShot(60, lambda: _force_foreground(int(dialog.winId())))

    def _on_settings_closed(self, _result):
        self.cfg = config.load_config()
        # rede de seguranca: painel fechou no meio de uma escolha de tecla
        self._on_hotkey_capture(False)

    def _on_hotkey_capture(self, listening):
        """O painel esta esperando o usuario apertar a tecla nova: o atalho
        global deixa TODA tecla passar ate la (senao apertar a tecla atual
        comecava a gravar em vez de ser escolhida)."""
        self._capturing_hotkey = listening
        if listening:
            self.hotkey.stop_if_recording()
            self.hotkey.paused = True
        else:
            QTimer.singleShot(0, self._resume_hotkey_when_released)

    def _resume_hotkey_when_released(self):
        # a tecla recem-escolhida ainda pode estar pressionada: se o atalho
        # voltasse na hora, a repeticao automatica dela ja comecava a gravar
        if getattr(self, "_capturing_hotkey", False):
            return
        if ctypes.windll.user32.GetAsyncKeyState(self.hotkey.vk_code) & 0x8000:
            QTimer.singleShot(50, self._resume_hotkey_when_released)
            return
        self.hotkey.paused = False

    def _apply_hotkey(self, new_vk_code):
        paused = self.hotkey.paused
        self.hotkey.uninstall()
        self.hotkey = HotkeyListener(new_vk_code, self._start_recording, self._stop_recording)
        self.hotkey.paused = paused
        self.hotkey.install()
        self._refresh_tooltip()
        log(f"Atalho trocado para {vk_to_name(new_vk_code)}")

    def _apply_device(self, new_device):
        self.recorder.close_stream()
        self.recorder = Recorder(on_bands=self._on_bands, device_name=new_device)
        self.recorder.open_stream()

    def _simulate_update(self):
        # so no Dev: finge que saiu uma versao nova (copia do proprio .exe)
        # pra dar pra testar o fluxo inteiro de atualizacao sem publicar nada
        import json
        import shutil
        source = paths.DATA_DIR / "update" / "teste_atualizacao.exe"
        source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(sys.executable, source)
        updater.DEV_FEED_FILE.write_text(json.dumps({
            "version": "99.0.0",
            "notes": "Atualização de teste do Dev: o app vai baixar, fechar e abrir de novo sozinho.",
            "file": str(source),
        }), encoding="utf-8")
        self._check_for_update()

    def _check_for_update(self):
        self._update_check_thread = updater.UpdateCheckThread()
        self._update_check_thread.found.connect(self._on_update_found)
        self._update_check_thread.start()

    def _on_update_found(self, info):
        dialog = UpdateDialog(version.APP_VERSION, info["version"], info["notes"])
        dialog.adjustSize()
        screen = QGuiApplication.primaryScreen()
        target = dialog.geometry()
        target.moveCenter(screen.availableGeometry().center())
        dialog.move(target.topLeft())
        dialog.update_clicked.connect(lambda: self._start_update_download(dialog, info))
        self._update_dialog = dialog
        dialog.show()

    def _start_update_download(self, dialog, info):
        dialog.set_downloading()
        self.tray.setToolTip(f"{paths.APP_NAME} - baixando atualização...")
        self._update_download_thread = updater.UpdateDownloadThread(info["download_url"])
        self._update_download_thread.progress.connect(dialog.set_progress)
        self._update_download_thread.done.connect(lambda path: self._on_update_downloaded(dialog, path))
        self._update_download_thread.failed.connect(lambda msg: self._on_update_failed(dialog, msg))
        self._update_download_thread.start()

    def _on_update_downloaded(self, dialog, new_exe_path):
        # avisa antes de sumir: sem isso parecia que o app so tinha fechado
        dialog.set_restarting()
        QTimer.singleShot(1800, lambda: self._apply_update(dialog, new_exe_path))

    def _apply_update(self, dialog, new_exe_path):
        try:
            updater.apply_update_and_restart(new_exe_path)
        except Exception as e:
            log(f"Falha ao aplicar atualizacao: {e}")
            self._refresh_tooltip()
            dialog.set_error(f"não consegui instalar ({e})")
            return
        self._quit()

    def _on_update_failed(self, dialog, message):
        self._refresh_tooltip()
        dialog.set_error(message)

    def _watch_quit_request(self):
        """O desinstalador (que roda como outro processo) sinaliza um
        evento do Windows em vez de matar o app: assim o Qt fecha
        direito e o PyInstaller limpa a pasta temporaria dele."""
        kernel32 = ctypes.windll.kernel32
        evento = kernel32.CreateEventW(None, True, False, installer.QUIT_EVENT_NAME)
        if not evento:
            return

        def esperar():
            kernel32.WaitForSingleObject(evento, 0xFFFFFFFF)
            # volta pra thread do Qt antes de mexer em qualquer janela
            self._bridge.quit_requested.emit()

        threading.Thread(target=esperar, daemon=True).start()

    def _install_from_app(self):
        """Instalar pelo painel -- caminho de quem recusou a oferta da
        primeira vez. Depois de copiar, quem assume e o .exe instalado:
        este fecha pra nao ficar com dois rodando."""
        try:
            exe = installer.install()
            updater.launch(exe)
        except Exception as e:
            QMessageBox.critical(self._settings_dialog, paths.APP_NAME,
                                 "Nao deu pra instalar: {}".format(e))
            return
        config.save_config({"INSTALL_DECLINED": ""})
        if self._settings_dialog is not None:
            self._settings_dialog.close()
        self._quit()

    def _uninstall_from_app(self):
        """Desinstalar sem precisar ir na lista de programas do Windows.
        Aqui o app ja esta rodando, entao nao precisa fechar instancia
        nenhuma: limpa tudo e fecha a si mesmo no fim."""
        remove_data = QCheckBox("Apagar tambem meu login, historico e configuracoes")
        box = QMessageBox(self._settings_dialog)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(paths.APP_NAME)
        box.setText("Desinstalar o {} deste computador?".format(paths.APP_NAME))
        box.setInformativeText(
            "O app sai da lista de programas, para de abrir com o Windows e fecha agora."
        )
        box.setCheckBox(remove_data)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        try:
            installer.uninstall(remove_data=remove_data.isChecked())
        except OSError as e:
            QMessageBox.critical(self._settings_dialog, paths.APP_NAME,
                                 "Nao deu pra desinstalar: {}".format(e))
            return
        if self._settings_dialog is not None:
            self._settings_dialog.close()
        self._quit()

    def _quit(self):
        self.hotkey.uninstall()
        self.recorder.close_stream()
        QApplication.quit()


_SINGLE_INSTANCE_MUTEX_NAME = f"{paths.APP_ID}_SingleInstance_Mutex"
_ERROR_ALREADY_EXISTS = 183


def _acquire_single_instance_lock(wait_s=0.0):
    """Cria um mutex nomeado do Windows. Se ja existir (outra instancia
    rodando), retorna False -- o handle fica preso ao processo e some
    sozinho quando ele fechar (mesmo em crash), entao nao precisa
    liberar na mao.

    wait_s > 0: fica tentando por esse tempo antes de desistir. Usado
    logo depois de uma atualizacao, quando a versao antiga ainda esta
    terminando de fechar."""
    kernel32 = ctypes.windll.kernel32
    deadline = time.time() + wait_s
    while True:
        kernel32.SetLastError(0)
        handle = kernel32.CreateMutexW(None, False, _SINGLE_INSTANCE_MUTEX_NAME)
        if kernel32.GetLastError() != _ERROR_ALREADY_EXISTS:
            return True
        # soltar o nosso handle, senao o mutex nunca deixa de existir
        if handle:
            kernel32.CloseHandle(handle)
        if time.time() >= deadline:
            return False
        time.sleep(0.25)


def _run_install(argv):
    """Instalar pela linha de comando (--install, com --quiet opcional).
    Mesmo caminho da oferta da primeira vez, sem depender de clique --
    serve pra script e pra testar o ciclo inteiro."""
    quiet = installer.QUIET_FLAG in argv
    app = QApplication(argv)
    app.setStyleSheet(theme.STYLESHEET)
    app.setWindowIcon(QIcon(ICON_PATH))
    try:
        exe = installer.install()
    except Exception as e:
        log("Instalacao falhou: {}".format(e))
        if not quiet:
            QMessageBox.critical(None, paths.APP_NAME, "Nao deu pra instalar: {}".format(e))
        sys.exit(1)
    config.save_config({"INSTALL_DECLINED": ""})
    if not quiet:
        QMessageBox.information(None, paths.APP_NAME,
                                "{} instalado. Ele ja aparece na lista de programas "
                                "do Windows.".format(paths.APP_NAME))
    updater.launch(exe)


def _run_uninstall(argv):
    """Caminho que a lista de programas do Windows chama
    (UninstallString). Roda como processo separado, provavelmente com o
    app aberto -- por isso fecha a instancia que estiver rodando antes
    de limpar."""
    quiet = installer.QUIET_FLAG in argv
    app = QApplication(argv)
    app.setStyleSheet(theme.STYLESHEET)
    app.setWindowIcon(QIcon(ICON_PATH))

    remove_data = False
    if not quiet:
        check = QCheckBox("Apagar tambem meu login, historico e configuracoes")
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(paths.APP_NAME)
        box.setText("Desinstalar o {} deste computador?".format(paths.APP_NAME))
        box.setInformativeText("O app sai da lista de programas e para de abrir com o Windows.")
        box.setCheckBox(check)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        remove_data = check.isChecked()

    installer.kill_other_instances()
    installer.uninstall(remove_data=remove_data)
    if not quiet:
        QMessageBox.information(None, paths.APP_NAME,
                                "{} desinstalado.".format(paths.APP_NAME))


def _offer_install():
    """Primeira vez que o .exe roda solto (baixado da Release, por
    exemplo): oferece virar programa instalado. Se aceitar, reabre ja da
    pasta de instalacao e este processo sai. Se recusar, nao pergunta de
    novo -- continua funcionando solto, como antes."""
    if config.load_config().get("INSTALL_DECLINED"):
        return
    box = QMessageBox()
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(paths.APP_NAME)
    box.setText("Instalar o {} neste computador?".format(paths.APP_NAME))
    box.setInformativeText(
        "Ele passa a aparecer na lista de programas do Windows (da pra desinstalar por la "
        "ou pelas Configuracoes do proprio app) e ganha atalho no Menu Iniciar.\n\n"
        "Seu login, historico e configuracoes continuam os mesmos."
    )
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.Yes)
    if box.exec() != QMessageBox.StandardButton.Yes:
        config.save_config({"INSTALL_DECLINED": "1"})
        return
    try:
        exe = installer.install()
        updater.launch(exe)
    except Exception as e:
        log("Instalacao falhou: {}".format(e))
        QMessageBox.critical(None, paths.APP_NAME, "Nao deu pra instalar: {}".format(e))
        return
    sys.exit(0)


def main():
    if installer.UNINSTALL_FLAG in sys.argv:
        _run_uninstall(sys.argv)
        return

    if installer.INSTALL_FLAG in sys.argv:
        _run_install(sys.argv)
        return

    previous_version = updater.previous_version_from_args(sys.argv)
    after_update = previous_version is not None
    if not _acquire_single_instance_lock(wait_s=30 if after_update else 0):
        # ja tem uma instancia rodando -- nao abre outra (dois hooks de
        # teclado e duas gravacoes ao mesmo tempo dava m*).
        sys.exit(0)

    # sem isso o Windows agrupa/identifica o processo como "Python"
    # generico (icone errado em notificacoes etc) em vez de usar a
    # marca do app.
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"QuaseNada.{paths.APP_ID}")
    except (AttributeError, OSError):
        pass

    app = QApplication(sys.argv)
    app.setApplicationName(paths.APP_NAME)
    app.setApplicationDisplayName(paths.APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(ICON_PATH))
    app.setStyleSheet(theme.STYLESHEET)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, paths.APP_NAME, "Bandeja do sistema não disponível.")
        sys.exit(1)

    if installer.can_install():
        _offer_install()
    installer.refresh_registry()

    try:
        voice_app = VoiceApp()
    except Exception as e:
        QMessageBox.critical(None, f"{paths.APP_NAME} - erro ao iniciar", str(e))
        sys.exit(1)

    updater.cleanup_old_executables()
    if after_update:
        log(f"Atualizado de v{previous_version or '?'} para v{version.APP_VERSION}")
        # no teste de atualizacao do Dev o .exe novo e o mesmo: nao faz
        # sentido dizer "da 1.1.1 para a 1.1.1"
        if previous_version and previous_version != version.APP_VERSION:
            aviso = f"Atualizado da versão {previous_version} para a {version.APP_VERSION}"
        else:
            aviso = f"Atualizado para a versão {version.APP_VERSION}"
        voice_app.tray.showMessage(paths.APP_NAME, aviso + ".", QIcon(ICON_PATH), 5000)
        # o app some da tela enquanto troca de .exe: quando a bolinha volta,
        # ela mesma conta que deu certo (a bandeja passa batido)
        QTimer.singleShot(
            AFTER_UPDATE_NOTICE_DELAY_MS,
            lambda: voice_app.widget.show_message(aviso, AFTER_UPDATE_NOTICE_MS, tone="info"),
        )

    log(f"Pronto. Segure ou toque {vk_to_name(voice_app.hotkey.vk_code)} para ditar.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
