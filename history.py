import json
import time

import paths

HISTORY_FILE = paths.DATA_DIR / "history.json"

# so as ultimas N ficam salvas -- a cada nova transcricao a mais antiga
# cai fora, entao o arquivo nunca cresce.
MAX_ITEMS = 5


def load():
    """Lista das ultimas transcricoes, da mais nova pra mais antiga.
    Nunca levanta excecao -- historico quebrado/ausente vira lista vazia
    (nao pode atrapalhar a transcricao em si)."""
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    items = []
    for entry in data[:MAX_ITEMS]:
        if isinstance(entry, dict) and entry.get("text"):
            items.append({"text": str(entry["text"]), "at": str(entry.get("at", ""))})
    return items


def add(text):
    text = (text or "").strip()
    if not text:
        return
    items = load()
    items.insert(0, {"text": text, "at": time.strftime("%d/%m %H:%M")})
    del items[MAX_ITEMS:]
    try:
        HISTORY_FILE.write_text(
            json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass
