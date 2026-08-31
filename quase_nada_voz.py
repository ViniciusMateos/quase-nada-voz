import os
import io
import wave
import time
import threading
import ctypes
from ctypes import wintypes
import winsound
import sounddevice as sd
import numpy as np
import requests
import win32clipboard
import win32api
import win32con
from dotenv import load_dotenv
from PIL import Image, ImageDraw
import pystray

import auth

load_dotenv()

OAI_DEVICE_ID = os.getenv("OAI_DEVICE_ID", "4735a0c5-377b-45d6-b480-85bdaf63d5d6")
HOTKEY_STR = os.getenv("HOTKEY", "F9").upper()

VK_MAPPING = {
    "F9": 0x78, "F10": 0x79, "F13": 0x7C, "CAPSLOCK": 0x14, "RCONTROL": 0xA3, "SCROLLLOCK": 0x91
}
VK_CODE = VK_MAPPING.get(HOTKEY_STR, 0x78)

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]

is_recording = False
toggle_mode = False
key_down_time = 0.0
audio_frames = []

TAP_THRESHOLD_S = 0.35

def _make_tray_image(color):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((6, 6, 58, 58), fill=color, outline=(255, 255, 255, 255), width=4)
    return img

ICON_IDLE = _make_tray_image((90, 90, 90, 255))
ICON_RECORDING = _make_tray_image((220, 40, 40, 255))

def _quit_app(icon, item):
    icon.stop()
    os._exit(0)

tray_icon = pystray.Icon(
    "quase_nada_voz",
    icon=ICON_IDLE,
    title=f"Quase Nada Voz - segure {HOTKEY_STR} para ditar",
    menu=pystray.Menu(pystray.MenuItem("Sair", _quit_app)),
)

def paste_text(text):
    if not text.strip(): return

    for vk in [win32con.VK_SHIFT, win32con.VK_CONTROL, win32con.VK_MENU, win32con.VK_LWIN, win32con.VK_RWIN]:
        if win32api.GetAsyncKeyState(vk) & 0x8000:
            win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)

    win32clipboard.OpenClipboard()
    try:
        old_clip = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
    except Exception:
        old_clip = ""
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()

    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    win32api.keybd_event(ord('V'), 0, 0, 0)
    win32api.keybd_event(ord('V'), 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)

    time.sleep(0.2)

    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(old_clip, win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()

def transcribe_and_paste(wav_bytes):
    url = "https://chatgpt.com/backend-api/transcribe"
    files = {
        "file": ("whisper.wav", wav_bytes, "audio/wav")
    }

    for attempt in range(2):
        try:
            token = auth.get_access_token(force_relogin=(attempt == 1))
            headers = {
                "authorization": f"Bearer {token}",
                "oai-device-id": OAI_DEVICE_ID,
                "oai-language": "pt-BR",
                "user-agent": auth.UA,
            }

            response = requests.post(url, headers=headers, files=files)
            if response.status_code == 401 and attempt == 0:
                print("Token expirado, renovando sessao...")
                continue
            response.raise_for_status()
            text = response.json().get("text", "")

            if text:
                winsound.Beep(1500, 150)
                paste_text(text)
            else:
                raise ValueError("Resposta vazia")
            return
        except Exception as e:
            if attempt == 1:
                print(f"Erro: {e}")
                winsound.Beep(500, 100)
                winsound.Beep(500, 100)

def process_audio():
    global audio_frames
    if not audio_frames: return
    audio_data = np.concatenate(audio_frames, axis=0)
    audio_frames = []

    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(audio_data.tobytes())

    wav_bytes = wav_io.getvalue()
    threading.Thread(target=transcribe_and_paste, args=(wav_bytes,), daemon=True).start()

def audio_callback(indata, frames, time_info, status):
    if is_recording:
        audio_frames.append(indata.copy())

stream = sd.InputStream(samplerate=16000, channels=1, dtype='int16', callback=audio_callback)
CMPFUNC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, wintypes.WPARAM, ctypes.POINTER(KBDLLHOOKSTRUCT))

def _start_recording():
    global is_recording, toggle_mode, key_down_time
    is_recording = True
    toggle_mode = False
    key_down_time = time.time()
    tray_icon.icon = ICON_RECORDING
    tray_icon.title = "Quase Nada Voz - gravando..."
    threading.Thread(target=lambda: winsound.Beep(800, 150), daemon=True).start()

def _stop_recording():
    global is_recording, toggle_mode
    is_recording = False
    toggle_mode = False
    tray_icon.icon = ICON_IDLE
    tray_icon.title = f"Quase Nada Voz - segure ou toque {HOTKEY_STR} para ditar"
    threading.Thread(target=process_audio, daemon=True).start()

def hook_proc(nCode, wParam, lParam):
    global toggle_mode
    if nCode >= 0:
        vk_code = lParam.contents.vkCode
        if vk_code == VK_CODE:
            if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                if not is_recording:
                    _start_recording()
                elif toggle_mode:
                    # segundo toque enquanto gravava travado -> para agora
                    _stop_recording()
                # senao: repeticao de tecla (segurando) enquanto ja grava -> ignora
            elif wParam in (WM_KEYUP, WM_SYSKEYUP):
                if is_recording and not toggle_mode:
                    if time.time() - key_down_time < TAP_THRESHOLD_S:
                        # toque rapido -> trava gravando ate o proximo toque
                        toggle_mode = True
                        tray_icon.title = "Quase Nada Voz - gravando (toque de novo pra parar)"
                    else:
                        # segurou e soltou -> para agora
                        _stop_recording()
            return 1
    return ctypes.windll.user32.CallNextHookEx(None, nCode, wParam, lParam)

def main():
    print(f"[Quase Nada Voz] Ativo. Pressione e segure {HOTKEY_STR} para ditar.")
    stream.start()

    threading.Thread(target=tray_icon.run, daemon=True).start()

    pointer = CMPFUNC(hook_proc)
    hook_id = ctypes.windll.user32.SetWindowsHookExW(WH_KEYBOARD_LL, pointer, None, 0)

    msg = wintypes.MSG()
    while ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
        ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
        ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))

    ctypes.windll.user32.UnhookWindowsHookEx(hook_id)
    stream.stop()

if __name__ == "__main__":
    main()
