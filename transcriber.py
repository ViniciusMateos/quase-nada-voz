import time

import requests
import win32api
import win32clipboard
import win32con

import auth
import focus
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


def transcribe_and_paste(wav_bytes, oai_device_id, on_saved=None):
    """Manda o audio pra API e cola o texto no cursor. Retorna uma tupla
    (status, texto), com status:
    - "ok": transcreveu e colou
    - "no_target": transcreveu, mas nao tinha campo de texto em foco --
      nao colou (o texto fica no historico e no retorno)
    - "silence": audio sem fala reconhecivel (mic mudo/baixo) -- nao e
      problema de sessao, entao nao forca relogin
    - "auth_error": nao conseguiu autenticar (sessao/login)
    - "error": falha de rede/parsing, ou falhou ao colar

    on_saved(texto) e chamado assim que a transcricao entra no historico,
    antes de colar -- pra quem mostra o historico atualizar na hora.

    So reloga (abre o navegador) na 2a tentativa de 401/403 -- a 1a
    tenta renovar so pelo cookie salvo, sem navegador nenhum."""
    files = {"file": ("whisper.wav", wav_bytes, "audio/wav")}
    force_relogin = False

    for attempt in range(3):
        try:
            token = auth.get_access_token(force_relogin=force_relogin)
        except Exception as e:
            log(f"Falha ao obter token: {e}")
            return "auth_error", None

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
            return "error", None

        if response.status_code in (401, 403):
            auth.invalidate_token_cache()
            force_relogin = attempt >= 1
            log(f"HTTP {response.status_code} - renovando sessao (relogin={force_relogin})")
            continue

        if response.status_code != 200:
            log(f"HTTP {response.status_code}: {response.text[:200]}")
            return "error", None

        text = response.json().get("text", "").strip()
        if not text:
            log("Nada reconhecido no audio - nada colado")
            return "silence", None

        log(f"Transcrito: {text[:80]}")
        # salva no historico ANTES de colar: se a colagem cair na janela
        # errada (acesso remoto, por exemplo) ou falhar, o texto ainda
        # da pra recuperar/copiar pelo painel.
        history.add(text)
        if on_saved:
            on_saved(text)

        # checado agora (nao quando comecou a gravar): o que importa e
        # onde o foco esta na hora de colar
        if focus.text_target() == focus.NO:
            log("Nenhum campo de texto em foco - nao colado (fica no historico)")
            return "no_target", text

        try:
            paste_text(text)
        except Exception as e:
            log(f"Texto transcrito mas falhou ao colar: {e}")
            return "error", text
        return "ok", text

    log("Nao consegui autenticar depois de 3 tentativas")
    return "auth_error", None
