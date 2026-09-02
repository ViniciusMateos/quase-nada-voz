import ctypes
import threading
import time

import paths

_mci = ctypes.windll.winmm

SOUNDS_DIR = paths.ASSETS_DIR / "sounds"
START_STOP_RECORDING = str(SOUNDS_DIR / "start-stop-recording.mp3")
DONE_TRANSCRIBE = str(SOUNDS_DIR / "done-transcribe.mp3")


def _play(path):
    # MCI (winmm.dll) toca mp3 nativamente no Windows, sem precisar de
    # nenhuma biblioteca externa. Cada chamada usa um alias proprio pra
    # nao brigar com uma reproducao anterior que ainda esteja rodando.
    alias = f"qnv_{threading.get_ident()}_{time.monotonic_ns()}"
    try:
        _mci.mciSendStringW(f'open "{path}" type mpegvideo alias {alias}', None, 0, None)
        _mci.mciSendStringW(f'play {alias} wait', None, 0, None)
    except OSError:
        pass
    finally:
        _mci.mciSendStringW(f'close {alias}', None, 0, None)


def play(path):
    """Toca um mp3/wav em segundo plano (nao bloqueia quem chamou)."""
    threading.Thread(target=_play, args=(path,), daemon=True).start()
