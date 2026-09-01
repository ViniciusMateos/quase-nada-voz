import time

import requests
import win32api
import win32clipboard
import win32con

import auth

TRANSCRIBE_URL = "https://chatgpt.com/backend-api/transcribe"


def paste_text(text):
    if not text.strip():
        return

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


def transcribe(wav_bytes, oai_device_id):
    """Manda o audio pra API e retorna o texto transcrito. Levanta
    excecao se nao conseguir apos tentar renovar a sessao uma vez."""
    files = {"file": ("whisper.wav", wav_bytes, "audio/wav")}

    last_error = None
    for attempt in range(2):
        try:
            token = auth.get_access_token(force_relogin=(attempt == 1))
            headers = {
                "authorization": f"Bearer {token}",
                "oai-device-id": oai_device_id,
                "oai-language": "pt-BR",
                "user-agent": auth.UA,
            }
            response = requests.post(TRANSCRIBE_URL, headers=headers, files=files)
            if response.status_code == 401 and attempt == 0:
                continue
            response.raise_for_status()
            text = response.json().get("text", "")
            if not text:
                raise ValueError("Resposta vazia")
            return text
        except Exception as e:
            last_error = e
    raise last_error
