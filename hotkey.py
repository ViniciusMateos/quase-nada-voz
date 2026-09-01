import ctypes
import time
from ctypes import wintypes

VK_MAPPING = {
    "F9": 0x78, "F10": 0x79, "F13": 0x7C, "CAPSLOCK": 0x14, "RCONTROL": 0xA3, "SCROLLLOCK": 0x91,
}

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

TAP_THRESHOLD_S = 0.35

# teclas "estendidas" no layout padrao (setas, ctrl/alt direito, insert/delete,
# home/end/pgup/pgdn, num lock, scroll lock, divisao do teclado numerico) --
# precisam da flag estendida no lparam pra GetKeyNameTextW dar o nome certo.
_EXTENDED_VKS = {
    0xA3, 0xA5, 0x2D, 0x2E, 0x24, 0x23, 0x21, 0x22,
    0x25, 0x26, 0x27, 0x28, 0x90, 0x91, 0x6F,
}


def vk_to_name(vk_code):
    """Nome legivel de uma tecla a partir do codigo virtual do Windows."""
    scan_code = ctypes.windll.user32.MapVirtualKeyW(vk_code, 0)
    lparam = scan_code << 16
    if vk_code in _EXTENDED_VKS:
        lparam |= 1 << 24
    buf = ctypes.create_unicode_buffer(64)
    length = ctypes.windll.user32.GetKeyNameTextW(lparam, buf, 64)
    return buf.value if length else f"Tecla 0x{vk_code:02X}"


def parse_hotkey(raw):
    """Converte o valor salvo no config (codigo VK numerico, ou um nome
    antigo tipo 'F9') pro codigo VK inteiro. Cai pro F9 se vier vazio/invalido."""
    if raw is None:
        return VK_MAPPING["F9"]
    raw = str(raw).strip()
    if raw.isdigit():
        return int(raw)
    return VK_MAPPING.get(raw.upper(), VK_MAPPING["F9"])


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class HotkeyListener:
    """Hook de teclado global (baixo nivel) pra uma unica tecla, com dois
    modos de uso: segurar-e-soltar grava so enquanto pressionado; um
    toque rapido (< TAP_THRESHOLD_S) trava a gravacao ligada ate o
    proximo toque. Precisa rodar num loop de mensagens do Windows na
    mesma thread que instalou o hook (o event loop do Qt serve)."""

    def __init__(self, vk_code, on_start, on_stop):
        self.vk_code = vk_code
        self._on_start = on_start
        self._on_stop = on_stop

        self._recording = False
        self._toggle_mode = False
        self._key_down_time = 0.0

        self._pointer = ctypes.WINFUNCTYPE(
            ctypes.c_int, ctypes.c_int, wintypes.WPARAM, ctypes.POINTER(KBDLLHOOKSTRUCT)
        )(self._hook_proc)
        self._hook_id = None

    def install(self):
        self._hook_id = ctypes.windll.user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._pointer, None, 0
        )

    def uninstall(self):
        if self._hook_id:
            ctypes.windll.user32.UnhookWindowsHookEx(self._hook_id)
            self._hook_id = None

    def _start(self):
        self._recording = True
        self._toggle_mode = False
        self._key_down_time = time.time()
        self._on_start()

    def _stop(self):
        self._recording = False
        self._toggle_mode = False
        self._on_stop()

    def _hook_proc(self, nCode, wParam, lParam):
        if nCode >= 0 and lParam.contents.vkCode == self.vk_code:
            if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                if not self._recording:
                    self._start()
                elif self._toggle_mode:
                    self._stop()
                # senao: repeticao de tecla segurada, ja gravando -> ignora
            elif wParam in (WM_KEYUP, WM_SYSKEYUP):
                if self._recording and not self._toggle_mode:
                    if time.time() - self._key_down_time < TAP_THRESHOLD_S:
                        self._toggle_mode = True
                    else:
                        self._stop()
            return 1
        return ctypes.windll.user32.CallNextHookEx(None, nCode, wParam, lParam)
