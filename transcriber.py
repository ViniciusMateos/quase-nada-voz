import time

import requests
import win32api
import win32clipboard
import win32con

import auth
import history
from logger import log

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


def transcribe_and_paste(wav_bytes, oai_device_id):
    """Manda o audio pra API e cola o texto no cursor. Retorna:
    - "ok": transcreveu e colou
    - "silence": audio sem fala reconhecivel (mic mudo/baixo) -- nao e
      problema de sessao, entao nao forca relogin
    - "error": falha de rede/auth/parsing, ou falhou ao colar

    So reloga (abre o navegador) na 2a tentativa de 401/403 -- a 1a
    tenta renovar so pelo cookie salvo, sem navegador nenhum."""
    files = {"file": ("whisper.wav", wav_bytes, "audio/wav")}
    force_relogin = False

    for attempt in range(3):
        try:
            token = auth.get_access_token(force_relogin=force_relogin)
        except Exception as e:
            log(f"Falha ao obter token: {e}")
            return "error"

        headers = {
            "authorization": f"Bearer {token}",
            "oai-device-id": oai_device_id,
            "oai-language": "pt-BR",
            "user-agent": auth.UA,
        }

        try:
            response = requests.post(TRANSCRIBE_URL, headers=headers, files=files, timeout=60)
        except requests.RequestException as e:
            log(f"Falha de rede: {e}")
            return "error"

        if response.status_code in (401, 403):
            auth.invalidate_token_cache()
            force_relogin = attempt >= 1
            log(f"HTTP {response.status_code} - renovando sessao (relogin={force_relogin})")
            continue

        if response.status_code != 200:
            log(f"HTTP {response.status_code}: {response.text[:200]}")
            return "error"

        text = response.json().get("text", "").strip()
        if not text:
            log("Nada reconhecido no audio - nada colado")
            return "silence"

        log(f"Transcrito: {text[:80]}")
        # salva no historico ANTES de colar: se a colagem cair na janela
        # errada (acesso remoto, por exemplo) ou falhar, o texto ainda
        # da pra recuperar/copiar pelo painel.
        history.add(text)
        try:
            paste_text(text)
        except Exception as e:
            log(f"Texto transcrito mas falhou ao colar: {e}")
            return "error"
        return "ok"

    log("Nao consegui autenticar depois de 3 tentativas")
    return "error"
