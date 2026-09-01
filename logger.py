import time
from pathlib import Path

LOG_FILE = Path(__file__).parent / "quase_nada_voz.log"


def log(msg):
    """Grava uma linha com timestamp no log e no stdout. Como o app roda
    sem console (atalho usa pythonw), esse arquivo e o unico jeito de
    diagnosticar o que aconteceu numa gravacao depois do fato."""
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            print(line, file=f)
    except OSError:
        pass
