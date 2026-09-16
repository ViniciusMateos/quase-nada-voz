"""Descobre se o foco atual e um lugar onde da pra colar texto.

Responde "yes", "no" ou "unknown" -- e so "no" faz o app deixar de colar.
Na duvida cola normal, como sempre foi: errar pro lado do "no" num campo
de texto de verdade quebraria o uso principal do app.
"""
import ctypes
import sys
import threading
from ctypes import wintypes

from logger import log

_RPC_E_CHANGED_MODE = -2147417850

YES, NO, UNKNOWN = "yes", "no", "unknown"

_user32 = ctypes.windll.user32

# area de trabalho e barra de tarefas: certeza de que nao tem onde colar
_NO_TEXT_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}
# terminais aceitam colar mas nao se expoem como campo de texto na UIA
_TERMINAL_CLASSES = {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "PseudoConsoleWindow"}

# cliente de acesso remoto: colar ali depende da sincronizacao de area de
# transferencia com a outra maquina, que nao da tempo -- o texto se perde
_REMOTE_VIEWER_PROCESSES = {
    "mstsc.exe", "msrdc.exe", "rdcman.exe", "rustdesk.exe", "anydesk.exe",
    "teamviewer.exe", "tvnviewer.exe", "vncviewer.exe", "parsecd.exe",
}

_UIA_EDIT = 50004
_UIA_DOCUMENT = 50030
# so tipos que com certeza nao sao lugar de digitar. Ficam de fora de
# proposito: Pane/Window/Custom/Group (apps Java como o PyCharm aparecem
# como um bloco so, sem expor os campos), DataItem/DataGrid/Table (celula
# do Excel aceita colar) -- esses caem em "unknown" e colam normal.
_UIA_NON_TEXT_TYPES = {
    50000,  # Button
    50002,  # CheckBox
    50005,  # Hyperlink
    50006,  # Image
    50007,  # ListItem (arquivo no Explorer)
    50008,  # List
    50009,  # Menu
    50010,  # MenuBar
    50011,  # MenuItem
    50012,  # ProgressBar
    50013,  # RadioButton
    50014,  # ScrollBar
    50015,  # Slider
    50018,  # Tab
    50019,  # TabItem
    50021,  # ToolBar
    50023,  # Tree
    50024,  # TreeItem
    50031,  # SplitButton
}
_PROP_HAS_KEYBOARD_FOCUS = 30008
_PROP_IS_TEXT_PATTERN_AVAILABLE = 30040

UIA_TIMEOUT_S = 1.5


class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND), ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


def _class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _process_name(hwnd):
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return buf.value.rsplit("\\", 1)[-1].lower()
    finally:
        kernel32.CloseHandle(handle)


def _has_caret(hwnd):
    info = _GUITHREADINFO(cbSize=ctypes.sizeof(_GUITHREADINFO))
    thread_id = _user32.GetWindowThreadProcessId(hwnd, None)
    if not _user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
        return False
    return bool(info.hwndCaret)


def _uia_verdict():
    if "comtypes" not in sys.modules:
        # o comtypes inicializa o COM na thread do primeiro import, e o
        # modo padrao dele (STA) conflita com o MTA recomendado pra UIA.
        # So e definido aqui, numa thread de fundo -- nunca no import do
        # app, pra nao interferir no COM da thread do Qt.
        sys.coinit_flags = 0  # COINIT_MULTITHREADED
    import comtypes
    import comtypes.client

    try:
        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        initialized = True
    except OSError as e:
        # thread ja inicializada em outro modo: segue nele mesmo
        if getattr(e, "winerror", None) != _RPC_E_CHANGED_MODE:
            raise
        initialized = False
    try:
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen.UIAutomationClient import CUIAutomation, IUIAutomation

        uia = comtypes.CoCreateInstance(
            CUIAutomation._reg_clsid_, interface=IUIAutomation,
            clsctx=comtypes.CLSCTX_INPROC_SERVER,
        )
        element = uia.GetFocusedElement()
        # Chrome/Electron (VS Code, WhatsApp, Discord...) so montam a arvore
        # de acessibilidade depois da primeira consulta -- ate la devolvem
        # um painel generico SEM foco de teclado. Isso nao prova nada.
        if not element.GetCurrentPropertyValue(_PROP_HAS_KEYBOARD_FOCUS):
            return UNKNOWN
        control_type = element.CurrentControlType
        if control_type in (_UIA_EDIT, _UIA_DOCUMENT):
            return YES
        if element.GetCurrentPropertyValue(_PROP_IS_TEXT_PATTERN_AVAILABLE):
            return YES
        # nao usar "tem valor editavel" como sinal de campo de texto: item
        # de arquivo no Explorer declara valor editavel (e o renomear)
        if control_type in _UIA_NON_TEXT_TYPES:
            return NO
        return UNKNOWN
    finally:
        if initialized:
            comtypes.CoUninitialize()


def _uia_verdict_with_timeout():
    # app travado do outro lado pode segurar a chamada da UIA -- nesse
    # caso desiste e trata como duvida (cola normal)
    result = [UNKNOWN]

    def run():
        try:
            result[0] = _uia_verdict()
        except Exception as e:
            log(f"Nao consegui checar o campo em foco: {e}")

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(UIA_TIMEOUT_S)
    return result[0] if not worker.is_alive() else UNKNOWN


def text_target():
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return NO
    cls = _class_name(hwnd)
    if cls in _NO_TEXT_CLASSES:
        return NO
    if _process_name(hwnd) in _REMOTE_VIEWER_PROCESSES:
        return NO
    if cls in _TERMINAL_CLASSES or _has_caret(hwnd):
        return YES
    return _uia_verdict_with_timeout()


def warm_up():
    """Consulta a UIA uma vez sem esperar resposta, pra acordar a
    arvore de acessibilidade do app em foco. Chamado quando a gravacao
    comeca: quando a transcricao termina (segundos depois), a checagem
    de verdade ja pega o elemento real em vez do painel generico."""
    threading.Thread(target=_uia_verdict_with_timeout, daemon=True).start()
